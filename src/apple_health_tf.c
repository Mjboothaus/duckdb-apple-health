#include "duckdb_extension.h"

#include "apple_health_tf.h"
#include "parse_health.h"
#include "zip_source.h"

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

DUCKDB_EXTENSION_EXTERN

/* v0.1 columns:
 * type, type_short, unit, value, value_text,
 * start_date, end_date, creation_date,
 * source_name, source_version, device, filename
 */

typedef struct {
	ah_record *rows;
	size_t count;
	size_t capacity;
	char *filename;
	char *path;
} read_ah_bind_data;

typedef struct {
	size_t offset;
} read_ah_init_data;

static void DestroyBindData(void *ptr) {
	read_ah_bind_data *b = (read_ah_bind_data *)ptr;
	if (!b) {
		return;
	}
	free(b->rows);
	free(b->filename);
	free(b->path);
	duckdb_free(b);
}

static void DestroyInitData(void *ptr) {
	duckdb_free(ptr);
}

static void OnRecordCollect(const ah_record *row, void *userdata) {
	read_ah_bind_data *b = (read_ah_bind_data *)userdata;
	if (b->count >= b->capacity) {
		size_t ncap = b->capacity ? b->capacity * 2 : 64;
		ah_record *nr = (ah_record *)realloc(b->rows, ncap * sizeof(ah_record));
		if (!nr) {
			return;
		}
		b->rows = nr;
		b->capacity = ncap;
	}
	b->rows[b->count++] = *row;
}

static void OnWorkoutIgnore(const ah_workout *row, void *userdata) {
	(void)row;
	(void)userdata;
}

static void OnSummaryIgnore(const ah_activity_summary *row, void *userdata) {
	(void)row;
	(void)userdata;
}

static void AssignVarchar(duckdb_vector vec, idx_t row, const char *s) {
	if (!s) {
		s = "";
	}
	duckdb_vector_assign_string_element(vec, row, s);
}

static void AssignTimestamp(duckdb_vector vec, uint64_t *validity, idx_t row, const char *apple_date) {
	duckdb_timestamp *data = (duckdb_timestamp *)duckdb_vector_get_data(vec);
	int64_t micros = 0;
	if (apple_date && apple_date[0] && ah_parse_apple_date(apple_date, NULL, 0, &micros)) {
		data[row].micros = micros;
	} else {
		duckdb_validity_set_row_invalid(validity, row);
	}
}

static void ReadAppleHealthBind(duckdb_bind_info info) {
	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_logical_type double_type = duckdb_create_logical_type(DUCKDB_TYPE_DOUBLE);
	duckdb_logical_type ts_type = duckdb_create_logical_type(DUCKDB_TYPE_TIMESTAMP_TZ);

	duckdb_bind_add_result_column(info, "type", varchar_type);
	duckdb_bind_add_result_column(info, "type_short", varchar_type);
	duckdb_bind_add_result_column(info, "unit", varchar_type);
	duckdb_bind_add_result_column(info, "value", double_type);
	duckdb_bind_add_result_column(info, "value_text", varchar_type);
	duckdb_bind_add_result_column(info, "start_date", ts_type);
	duckdb_bind_add_result_column(info, "end_date", ts_type);
	duckdb_bind_add_result_column(info, "creation_date", ts_type);
	duckdb_bind_add_result_column(info, "source_name", varchar_type);
	duckdb_bind_add_result_column(info, "source_version", varchar_type);
	duckdb_bind_add_result_column(info, "device", varchar_type);
	duckdb_bind_add_result_column(info, "filename", varchar_type);

	duckdb_destroy_logical_type(&varchar_type);
	duckdb_destroy_logical_type(&double_type);
	duckdb_destroy_logical_type(&ts_type);

	if (duckdb_bind_get_parameter_count(info) < 1) {
		duckdb_bind_set_error(info, "read_apple_health requires a path argument");
		return;
	}

	duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
	if (!path_val) {
		duckdb_bind_set_error(info, "read_apple_health: missing path");
		return;
	}
	char *path_cstr = duckdb_get_varchar(path_val);
	if (!path_cstr || !path_cstr[0]) {
		if (path_cstr) {
			duckdb_free(path_cstr);
		}
		duckdb_destroy_value(&path_val);
		duckdb_bind_set_error(info, "read_apple_health: empty path");
		return;
	}

	read_ah_bind_data *bind = (read_ah_bind_data *)duckdb_malloc(sizeof(read_ah_bind_data));
	if (!bind) {
		duckdb_free(path_cstr);
		duckdb_destroy_value(&path_val);
		duckdb_bind_set_error(info, "out of memory");
		return;
	}
	memset(bind, 0, sizeof(*bind));
	bind->path = strdup(path_cstr);
	duckdb_free(path_cstr);
	duckdb_destroy_value(&path_val);

	char err[256];
	err[0] = '\0';
	ah_xml_source *src = ah_xml_source_open(bind->path, err, sizeof(err));
	if (!src) {
		char msg[320];
		snprintf(msg, sizeof(msg), "read_apple_health: cannot open '%s': %s", bind->path, err[0] ? err : "error");
		DestroyBindData(bind);
		duckdb_bind_set_error(info, msg);
		return;
	}
	bind->filename = strdup(ah_xml_source_filename(src));

	ah_parse_callbacks cb = {
	    .on_record = OnRecordCollect,
	    .on_workout = OnWorkoutIgnore,
	    .on_activity_summary = OnSummaryIgnore,
	    .userdata = bind,
	};
	ah_parse_stats stats;
	memset(&stats, 0, sizeof(stats));
	int rc = ah_parse_xml_filep(ah_xml_source_file(src), &cb, &stats);
	ah_xml_source_close(src);
	if (rc != 0) {
		char msg[320];
		snprintf(msg, sizeof(msg), "read_apple_health: parse failed for '%s'", bind->path);
		DestroyBindData(bind);
		duckdb_bind_set_error(info, msg);
		return;
	}

	duckdb_bind_set_bind_data(info, bind, DestroyBindData);
	duckdb_bind_set_cardinality(info, (idx_t)bind->count, true);
}

static void ReadAppleHealthInit(duckdb_init_info info) {
	read_ah_init_data *init = (read_ah_init_data *)duckdb_malloc(sizeof(read_ah_init_data));
	if (!init) {
		duckdb_init_set_error(info, "out of memory");
		return;
	}
	init->offset = 0;
	duckdb_init_set_init_data(info, init, DestroyInitData);
}

static void ReadAppleHealthFunction(duckdb_function_info info, duckdb_data_chunk output) {
	read_ah_bind_data *bind = (read_ah_bind_data *)duckdb_function_get_bind_data(info);
	read_ah_init_data *init = (read_ah_init_data *)duckdb_function_get_init_data(info);
	if (!bind || !init) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}
	if (init->offset >= bind->count) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}

	const idx_t vector_size = duckdb_vector_size();
	size_t remaining = bind->count - init->offset;
	idx_t n = remaining > (size_t)vector_size ? vector_size : (idx_t)remaining;

	duckdb_vector v_type = duckdb_data_chunk_get_vector(output, 0);
	duckdb_vector v_type_short = duckdb_data_chunk_get_vector(output, 1);
	duckdb_vector v_unit = duckdb_data_chunk_get_vector(output, 2);
	duckdb_vector v_value = duckdb_data_chunk_get_vector(output, 3);
	duckdb_vector v_value_text = duckdb_data_chunk_get_vector(output, 4);
	duckdb_vector v_start = duckdb_data_chunk_get_vector(output, 5);
	duckdb_vector v_end = duckdb_data_chunk_get_vector(output, 6);
	duckdb_vector v_creation = duckdb_data_chunk_get_vector(output, 7);
	duckdb_vector v_source = duckdb_data_chunk_get_vector(output, 8);
	duckdb_vector v_sver = duckdb_data_chunk_get_vector(output, 9);
	duckdb_vector v_device = duckdb_data_chunk_get_vector(output, 10);
	duckdb_vector v_filename = duckdb_data_chunk_get_vector(output, 11);

	double *value_data = (double *)duckdb_vector_get_data(v_value);
	duckdb_vector_ensure_validity_writable(v_value);
	duckdb_vector_ensure_validity_writable(v_start);
	duckdb_vector_ensure_validity_writable(v_end);
	duckdb_vector_ensure_validity_writable(v_creation);
	uint64_t *value_validity = duckdb_vector_get_validity(v_value);
	uint64_t *start_validity = duckdb_vector_get_validity(v_start);
	uint64_t *end_validity = duckdb_vector_get_validity(v_end);
	uint64_t *creation_validity = duckdb_vector_get_validity(v_creation);

	const char *filename = bind->filename ? bind->filename : "";

	for (idx_t i = 0; i < n; i++) {
		const ah_record *row = &bind->rows[init->offset + i];
		AssignVarchar(v_type, i, row->type);
		AssignVarchar(v_type_short, i, row->type_short);
		AssignVarchar(v_unit, i, row->unit);
		if (row->has_value) {
			value_data[i] = row->value;
		} else {
			duckdb_validity_set_row_invalid(value_validity, i);
		}
		AssignVarchar(v_value_text, i, row->value_text);
		AssignTimestamp(v_start, start_validity, i, row->start_date);
		AssignTimestamp(v_end, end_validity, i, row->end_date);
		AssignTimestamp(v_creation, creation_validity, i, row->creation_date);
		AssignVarchar(v_source, i, row->source_name);
		AssignVarchar(v_sver, i, row->source_version);
		AssignVarchar(v_device, i, row->device);
		AssignVarchar(v_filename, i, filename);
	}

	init->offset += n;
	duckdb_data_chunk_set_size(output, n);
}

void RegisterReadAppleHealthFunction(duckdb_connection connection) {
	duckdb_table_function function = duckdb_create_table_function();
	duckdb_table_function_set_name(function, "read_apple_health");

	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_table_function_add_parameter(function, varchar_type);
	duckdb_destroy_logical_type(&varchar_type);

	duckdb_table_function_set_bind(function, ReadAppleHealthBind);
	duckdb_table_function_set_init(function, ReadAppleHealthInit);
	duckdb_table_function_set_function(function, ReadAppleHealthFunction);

	duckdb_state rc = duckdb_register_table_function(connection, function);
	duckdb_destroy_table_function(&function);
	(void)rc;
}
