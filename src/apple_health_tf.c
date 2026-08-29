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

static void OnWorkoutRouteIgnore(const ah_workout_route *row, void *userdata) {
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
	    .on_workout_route = OnWorkoutRouteIgnore,
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


/* -------------------------------------------------------------------------- */
/* apple_health_workouts                                                      */
/* -------------------------------------------------------------------------- */

typedef struct {
	ah_workout *rows;
	size_t count;
	size_t capacity;
	char *filename;
	char *path;
} workouts_bind_data;

typedef struct {
	size_t offset;
} scan_init_data;

static void DestroyWorkoutsBind(void *ptr) {
	workouts_bind_data *b = (workouts_bind_data *)ptr;
	if (!b) {
		return;
	}
	free(b->rows);
	free(b->filename);
	free(b->path);
	duckdb_free(b);
}

static void DestroyScanInit(void *ptr) {
	duckdb_free(ptr);
}

static void OnWorkoutCollect(const ah_workout *row, void *userdata) {
	workouts_bind_data *b = (workouts_bind_data *)userdata;
	if (b->count >= b->capacity) {
		size_t ncap = b->capacity ? b->capacity * 2 : 16;
		ah_workout *nr = (ah_workout *)realloc(b->rows, ncap * sizeof(ah_workout));
		if (!nr) {
			return;
		}
		b->rows = nr;
		b->capacity = ncap;
	}
	b->rows[b->count++] = *row;
}

static void OnRecordIgnore(const ah_record *row, void *userdata) {
	(void)row;
	(void)userdata;
}

static void AssignOptionalDouble(duckdb_vector vec, uint64_t *validity, idx_t row, bool has, double value) {
	double *data = (double *)duckdb_vector_get_data(vec);
	if (has) {
		data[row] = value;
	} else {
		duckdb_validity_set_row_invalid(validity, row);
	}
}

static char *BindPathOrError(duckdb_bind_info info, const char *fname) {
	if (duckdb_bind_get_parameter_count(info) < 1) {
		char msg[128];
		snprintf(msg, sizeof(msg), "%s requires a path argument", fname);
		duckdb_bind_set_error(info, msg);
		return NULL;
	}
	duckdb_value path_val = duckdb_bind_get_parameter(info, 0);
	if (!path_val) {
		duckdb_bind_set_error(info, "missing path");
		return NULL;
	}
	char *path_cstr = duckdb_get_varchar(path_val);
	duckdb_destroy_value(&path_val);
	if (!path_cstr || !path_cstr[0]) {
		if (path_cstr) {
			duckdb_free(path_cstr);
		}
		duckdb_bind_set_error(info, "empty path");
		return NULL;
	}
	char *out = strdup(path_cstr);
	duckdb_free(path_cstr);
	if (!out) {
		duckdb_bind_set_error(info, "out of memory");
		return NULL;
	}
	return out;
}

static void WorkoutsBind(duckdb_bind_info info) {
	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_logical_type double_type = duckdb_create_logical_type(DUCKDB_TYPE_DOUBLE);
	duckdb_logical_type ts_type = duckdb_create_logical_type(DUCKDB_TYPE_TIMESTAMP_TZ);

	duckdb_bind_add_result_column(info, "activity_type", varchar_type);
	duckdb_bind_add_result_column(info, "activity_type_short", varchar_type);
	duckdb_bind_add_result_column(info, "duration", double_type);
	duckdb_bind_add_result_column(info, "duration_unit", varchar_type);
	duckdb_bind_add_result_column(info, "total_distance", double_type);
	duckdb_bind_add_result_column(info, "total_distance_unit", varchar_type);
	duckdb_bind_add_result_column(info, "total_energy", double_type);
	duckdb_bind_add_result_column(info, "total_energy_unit", varchar_type);
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

	char *path = BindPathOrError(info, "apple_health_workouts");
	if (!path) {
		return;
	}

	workouts_bind_data *bind = (workouts_bind_data *)duckdb_malloc(sizeof(workouts_bind_data));
	if (!bind) {
		free(path);
		duckdb_bind_set_error(info, "out of memory");
		return;
	}
	memset(bind, 0, sizeof(*bind));
	bind->path = path;

	char err[256];
	err[0] = '\0';
	ah_xml_source *src = ah_xml_source_open(bind->path, err, sizeof(err));
	if (!src) {
		char msg[320];
		snprintf(msg, sizeof(msg), "apple_health_workouts: cannot open '%s': %s", bind->path, err[0] ? err : "error");
		DestroyWorkoutsBind(bind);
		duckdb_bind_set_error(info, msg);
		return;
	}
	bind->filename = strdup(ah_xml_source_filename(src));

	ah_parse_callbacks cb = {
	    .on_record = OnRecordIgnore,
	    .on_workout = OnWorkoutCollect,
	    .on_activity_summary = OnSummaryIgnore,
	    .on_workout_route = OnWorkoutRouteIgnore,
	    .userdata = bind,
	};
	ah_parse_stats stats;
	memset(&stats, 0, sizeof(stats));
	int rc = ah_parse_xml_filep(ah_xml_source_file(src), &cb, &stats);
	ah_xml_source_close(src);
	if (rc != 0) {
		DestroyWorkoutsBind(bind);
		duckdb_bind_set_error(info, "apple_health_workouts: parse failed");
		return;
	}

	duckdb_bind_set_bind_data(info, bind, DestroyWorkoutsBind);
	duckdb_bind_set_cardinality(info, (idx_t)bind->count, true);
}

static void ScanInit(duckdb_init_info info) {
	scan_init_data *init = (scan_init_data *)duckdb_malloc(sizeof(scan_init_data));
	if (!init) {
		duckdb_init_set_error(info, "out of memory");
		return;
	}
	init->offset = 0;
	duckdb_init_set_init_data(info, init, DestroyScanInit);
}

static void WorkoutsFunction(duckdb_function_info info, duckdb_data_chunk output) {
	workouts_bind_data *bind = (workouts_bind_data *)duckdb_function_get_bind_data(info);
	scan_init_data *init = (scan_init_data *)duckdb_function_get_init_data(info);
	if (!bind || !init || init->offset >= bind->count) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}

	const idx_t vector_size = duckdb_vector_size();
	size_t remaining = bind->count - init->offset;
	idx_t n = remaining > (size_t)vector_size ? vector_size : (idx_t)remaining;

	duckdb_vector v_atype = duckdb_data_chunk_get_vector(output, 0);
	duckdb_vector v_ashort = duckdb_data_chunk_get_vector(output, 1);
	duckdb_vector v_dur = duckdb_data_chunk_get_vector(output, 2);
	duckdb_vector v_dur_u = duckdb_data_chunk_get_vector(output, 3);
	duckdb_vector v_dist = duckdb_data_chunk_get_vector(output, 4);
	duckdb_vector v_dist_u = duckdb_data_chunk_get_vector(output, 5);
	duckdb_vector v_energy = duckdb_data_chunk_get_vector(output, 6);
	duckdb_vector v_energy_u = duckdb_data_chunk_get_vector(output, 7);
	duckdb_vector v_start = duckdb_data_chunk_get_vector(output, 8);
	duckdb_vector v_end = duckdb_data_chunk_get_vector(output, 9);
	duckdb_vector v_creation = duckdb_data_chunk_get_vector(output, 10);
	duckdb_vector v_source = duckdb_data_chunk_get_vector(output, 11);
	duckdb_vector v_sver = duckdb_data_chunk_get_vector(output, 12);
	duckdb_vector v_device = duckdb_data_chunk_get_vector(output, 13);
	duckdb_vector v_filename = duckdb_data_chunk_get_vector(output, 14);

	duckdb_vector_ensure_validity_writable(v_dur);
	duckdb_vector_ensure_validity_writable(v_dist);
	duckdb_vector_ensure_validity_writable(v_energy);
	duckdb_vector_ensure_validity_writable(v_start);
	duckdb_vector_ensure_validity_writable(v_end);
	duckdb_vector_ensure_validity_writable(v_creation);
	uint64_t *dur_v = duckdb_vector_get_validity(v_dur);
	uint64_t *dist_v = duckdb_vector_get_validity(v_dist);
	uint64_t *energy_v = duckdb_vector_get_validity(v_energy);
	uint64_t *start_v = duckdb_vector_get_validity(v_start);
	uint64_t *end_v = duckdb_vector_get_validity(v_end);
	uint64_t *creation_v = duckdb_vector_get_validity(v_creation);

	const char *filename = bind->filename ? bind->filename : "";

	for (idx_t i = 0; i < n; i++) {
		const ah_workout *row = &bind->rows[init->offset + i];
		AssignVarchar(v_atype, i, row->activity_type);
		AssignVarchar(v_ashort, i, row->activity_type_short);
		AssignOptionalDouble(v_dur, dur_v, i, row->has_duration, row->duration);
		AssignVarchar(v_dur_u, i, row->duration_unit);
		AssignOptionalDouble(v_dist, dist_v, i, row->has_total_distance, row->total_distance);
		AssignVarchar(v_dist_u, i, row->total_distance_unit);
		AssignOptionalDouble(v_energy, energy_v, i, row->has_total_energy, row->total_energy);
		AssignVarchar(v_energy_u, i, row->total_energy_unit);
		AssignTimestamp(v_start, start_v, i, row->start_date);
		AssignTimestamp(v_end, end_v, i, row->end_date);
		AssignTimestamp(v_creation, creation_v, i, row->creation_date);
		AssignVarchar(v_source, i, row->source_name);
		AssignVarchar(v_sver, i, row->source_version);
		AssignVarchar(v_device, i, row->device);
		AssignVarchar(v_filename, i, filename);
	}

	init->offset += n;
	duckdb_data_chunk_set_size(output, n);
}

void RegisterAppleHealthWorkoutsFunction(duckdb_connection connection) {
	duckdb_table_function function = duckdb_create_table_function();
	duckdb_table_function_set_name(function, "apple_health_workouts");

	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_table_function_add_parameter(function, varchar_type);
	duckdb_destroy_logical_type(&varchar_type);

	duckdb_table_function_set_bind(function, WorkoutsBind);
	duckdb_table_function_set_init(function, ScanInit);
	duckdb_table_function_set_function(function, WorkoutsFunction);

	duckdb_register_table_function(connection, function);
	duckdb_destroy_table_function(&function);
}

/* -------------------------------------------------------------------------- */
/* apple_health_activity_summaries                                            */
/* -------------------------------------------------------------------------- */

typedef struct {
	ah_activity_summary *rows;
	size_t count;
	size_t capacity;
	char *filename;
	char *path;
} summaries_bind_data;

static void DestroySummariesBind(void *ptr) {
	summaries_bind_data *b = (summaries_bind_data *)ptr;
	if (!b) {
		return;
	}
	free(b->rows);
	free(b->filename);
	free(b->path);
	duckdb_free(b);
}

static void OnSummaryCollect(const ah_activity_summary *row, void *userdata) {
	summaries_bind_data *b = (summaries_bind_data *)userdata;
	if (b->count >= b->capacity) {
		size_t ncap = b->capacity ? b->capacity * 2 : 16;
		ah_activity_summary *nr = (ah_activity_summary *)realloc(b->rows, ncap * sizeof(ah_activity_summary));
		if (!nr) {
			return;
		}
		b->rows = nr;
		b->capacity = ncap;
	}
	b->rows[b->count++] = *row;
}

static void SummariesBind(duckdb_bind_info info) {
	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_logical_type double_type = duckdb_create_logical_type(DUCKDB_TYPE_DOUBLE);

	duckdb_bind_add_result_column(info, "date_components", varchar_type);
	duckdb_bind_add_result_column(info, "active_energy_burned", double_type);
	duckdb_bind_add_result_column(info, "active_energy_burned_goal", double_type);
	duckdb_bind_add_result_column(info, "active_energy_unit", varchar_type);
	duckdb_bind_add_result_column(info, "apple_move_minutes", double_type);
	duckdb_bind_add_result_column(info, "apple_move_minutes_goal", double_type);
	duckdb_bind_add_result_column(info, "apple_move_time", double_type);
	duckdb_bind_add_result_column(info, "apple_move_time_goal", double_type);
	duckdb_bind_add_result_column(info, "apple_exercise_time", double_type);
	duckdb_bind_add_result_column(info, "apple_exercise_time_goal", double_type);
	duckdb_bind_add_result_column(info, "apple_stand_hours", double_type);
	duckdb_bind_add_result_column(info, "apple_stand_hours_goal", double_type);
	duckdb_bind_add_result_column(info, "filename", varchar_type);

	duckdb_destroy_logical_type(&varchar_type);
	duckdb_destroy_logical_type(&double_type);

	char *path = BindPathOrError(info, "apple_health_activity_summaries");
	if (!path) {
		return;
	}

	summaries_bind_data *bind = (summaries_bind_data *)duckdb_malloc(sizeof(summaries_bind_data));
	if (!bind) {
		free(path);
		duckdb_bind_set_error(info, "out of memory");
		return;
	}
	memset(bind, 0, sizeof(*bind));
	bind->path = path;

	char err[256];
	err[0] = '\0';
	ah_xml_source *src = ah_xml_source_open(bind->path, err, sizeof(err));
	if (!src) {
		char msg[320];
		snprintf(msg, sizeof(msg), "apple_health_activity_summaries: cannot open '%s': %s", bind->path,
		         err[0] ? err : "error");
		DestroySummariesBind(bind);
		duckdb_bind_set_error(info, msg);
		return;
	}
	bind->filename = strdup(ah_xml_source_filename(src));

	ah_parse_callbacks cb = {
	    .on_record = OnRecordIgnore,
	    .on_workout = OnWorkoutIgnore,
	    .on_activity_summary = OnSummaryCollect,
	    .on_workout_route = OnWorkoutRouteIgnore,
	    .userdata = bind,
	};
	ah_parse_stats stats;
	memset(&stats, 0, sizeof(stats));
	int rc = ah_parse_xml_filep(ah_xml_source_file(src), &cb, &stats);
	ah_xml_source_close(src);
	if (rc != 0) {
		DestroySummariesBind(bind);
		duckdb_bind_set_error(info, "apple_health_activity_summaries: parse failed");
		return;
	}

	duckdb_bind_set_bind_data(info, bind, DestroySummariesBind);
	duckdb_bind_set_cardinality(info, (idx_t)bind->count, true);
}

static void SummariesFunction(duckdb_function_info info, duckdb_data_chunk output) {
	summaries_bind_data *bind = (summaries_bind_data *)duckdb_function_get_bind_data(info);
	scan_init_data *init = (scan_init_data *)duckdb_function_get_init_data(info);
	if (!bind || !init || init->offset >= bind->count) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}

	const idx_t vector_size = duckdb_vector_size();
	size_t remaining = bind->count - init->offset;
	idx_t n = remaining > (size_t)vector_size ? vector_size : (idx_t)remaining;

	duckdb_vector cols[13];
	for (int c = 0; c < 13; c++) {
		cols[c] = duckdb_data_chunk_get_vector(output, (idx_t)c);
	}
	/* double columns: 1,2,4,5,6,7,8,9,10,11 */
	int dbl_cols[] = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11};
	uint64_t *vals[13] = {0};
	for (size_t k = 0; k < sizeof(dbl_cols) / sizeof(dbl_cols[0]); k++) {
		int c = dbl_cols[k];
		duckdb_vector_ensure_validity_writable(cols[c]);
		vals[c] = duckdb_vector_get_validity(cols[c]);
	}

	const char *filename = bind->filename ? bind->filename : "";

	for (idx_t i = 0; i < n; i++) {
		const ah_activity_summary *row = &bind->rows[init->offset + i];
		AssignVarchar(cols[0], i, row->date_components);
		AssignOptionalDouble(cols[1], vals[1], i, row->has_active_energy, row->active_energy_burned);
		AssignOptionalDouble(cols[2], vals[2], i, row->has_active_energy_goal, row->active_energy_burned_goal);
		AssignVarchar(cols[3], i, row->active_energy_unit);
		AssignOptionalDouble(cols[4], vals[4], i, row->has_move_minutes, row->apple_move_minutes);
		AssignOptionalDouble(cols[5], vals[5], i, row->has_move_minutes_goal, row->apple_move_minutes_goal);
		AssignOptionalDouble(cols[6], vals[6], i, row->has_move_time, row->apple_move_time);
		AssignOptionalDouble(cols[7], vals[7], i, row->has_move_time_goal, row->apple_move_time_goal);
		AssignOptionalDouble(cols[8], vals[8], i, row->has_exercise_time, row->apple_exercise_time);
		AssignOptionalDouble(cols[9], vals[9], i, row->has_exercise_time_goal, row->apple_exercise_time_goal);
		AssignOptionalDouble(cols[10], vals[10], i, row->has_stand_hours, row->apple_stand_hours);
		AssignOptionalDouble(cols[11], vals[11], i, row->has_stand_hours_goal, row->apple_stand_hours_goal);
		AssignVarchar(cols[12], i, filename);
	}

	init->offset += n;
	duckdb_data_chunk_set_size(output, n);
}

void RegisterAppleHealthActivitySummariesFunction(duckdb_connection connection) {
	duckdb_table_function function = duckdb_create_table_function();
	duckdb_table_function_set_name(function, "apple_health_activity_summaries");

	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_table_function_add_parameter(function, varchar_type);
	duckdb_destroy_logical_type(&varchar_type);

	duckdb_table_function_set_bind(function, SummariesBind);
	duckdb_table_function_set_init(function, ScanInit);
	duckdb_table_function_set_function(function, SummariesFunction);

	duckdb_register_table_function(connection, function);
	duckdb_destroy_table_function(&function);
}

/* -------------------------------------------------------------------------- */
/* apple_health_workout_routes                                                */
/* -------------------------------------------------------------------------- */

typedef struct {
	ah_workout_route *rows;
	size_t count;
	size_t capacity;
	char *filename;
	char *path;
} routes_bind_data;

static void DestroyRoutesBind(void *ptr) {
	routes_bind_data *b = (routes_bind_data *)ptr;
	if (!b) {
		return;
	}
	free(b->rows);
	free(b->filename);
	free(b->path);
	duckdb_free(b);
}

static void OnRouteCollect(const ah_workout_route *row, void *userdata) {
	routes_bind_data *b = (routes_bind_data *)userdata;
	if (b->count >= b->capacity) {
		size_t ncap = b->capacity ? b->capacity * 2 : 16;
		ah_workout_route *nr = (ah_workout_route *)realloc(b->rows, ncap * sizeof(ah_workout_route));
		if (!nr) {
			return;
		}
		b->rows = nr;
		b->capacity = ncap;
	}
	b->rows[b->count++] = *row;
}

static void RoutesBind(duckdb_bind_info info) {
	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_logical_type ts_type = duckdb_create_logical_type(DUCKDB_TYPE_TIMESTAMP_TZ);

	duckdb_bind_add_result_column(info, "workout_activity_type", varchar_type);
	duckdb_bind_add_result_column(info, "workout_activity_type_short", varchar_type);
	duckdb_bind_add_result_column(info, "workout_start_date", ts_type);
	duckdb_bind_add_result_column(info, "workout_end_date", ts_type);
	duckdb_bind_add_result_column(info, "start_date", ts_type);
	duckdb_bind_add_result_column(info, "end_date", ts_type);
	duckdb_bind_add_result_column(info, "creation_date", ts_type);
	duckdb_bind_add_result_column(info, "source_name", varchar_type);
	duckdb_bind_add_result_column(info, "source_version", varchar_type);
	duckdb_bind_add_result_column(info, "device", varchar_type);
	duckdb_bind_add_result_column(info, "gpx_path", varchar_type);
	duckdb_bind_add_result_column(info, "filename", varchar_type);

	duckdb_destroy_logical_type(&varchar_type);
	duckdb_destroy_logical_type(&ts_type);

	char *path = BindPathOrError(info, "apple_health_workout_routes");
	if (!path) {
		return;
	}

	routes_bind_data *bind = (routes_bind_data *)duckdb_malloc(sizeof(routes_bind_data));
	if (!bind) {
		free(path);
		duckdb_bind_set_error(info, "out of memory");
		return;
	}
	memset(bind, 0, sizeof(*bind));
	bind->path = path;

	char err[256];
	err[0] = '\0';
	ah_xml_source *src = ah_xml_source_open(bind->path, err, sizeof(err));
	if (!src) {
		char msg[320];
		snprintf(msg, sizeof(msg), "apple_health_workout_routes: cannot open '%s': %s", bind->path,
		         err[0] ? err : "error");
		DestroyRoutesBind(bind);
		duckdb_bind_set_error(info, msg);
		return;
	}
	bind->filename = strdup(ah_xml_source_filename(src));

	ah_parse_callbacks cb = {
	    .on_record = OnRecordIgnore,
	    .on_workout = OnWorkoutIgnore,
	    .on_activity_summary = OnSummaryIgnore,
	    .on_workout_route = OnRouteCollect,
	    .userdata = bind,
	};
	ah_parse_stats stats;
	memset(&stats, 0, sizeof(stats));
	int rc = ah_parse_xml_filep(ah_xml_source_file(src), &cb, &stats);
	ah_xml_source_close(src);
	if (rc != 0) {
		DestroyRoutesBind(bind);
		duckdb_bind_set_error(info, "apple_health_workout_routes: parse failed");
		return;
	}

	duckdb_bind_set_bind_data(info, bind, DestroyRoutesBind);
	duckdb_bind_set_cardinality(info, (idx_t)bind->count, true);
}

static void RoutesFunction(duckdb_function_info info, duckdb_data_chunk output) {
	routes_bind_data *bind = (routes_bind_data *)duckdb_function_get_bind_data(info);
	scan_init_data *init = (scan_init_data *)duckdb_function_get_init_data(info);
	if (!bind || !init || init->offset >= bind->count) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}

	const idx_t vector_size = duckdb_vector_size();
	size_t remaining = bind->count - init->offset;
	idx_t n = remaining > (size_t)vector_size ? vector_size : (idx_t)remaining;

	duckdb_vector v_wtype = duckdb_data_chunk_get_vector(output, 0);
	duckdb_vector v_wshort = duckdb_data_chunk_get_vector(output, 1);
	duckdb_vector v_wstart = duckdb_data_chunk_get_vector(output, 2);
	duckdb_vector v_wend = duckdb_data_chunk_get_vector(output, 3);
	duckdb_vector v_start = duckdb_data_chunk_get_vector(output, 4);
	duckdb_vector v_end = duckdb_data_chunk_get_vector(output, 5);
	duckdb_vector v_creation = duckdb_data_chunk_get_vector(output, 6);
	duckdb_vector v_source = duckdb_data_chunk_get_vector(output, 7);
	duckdb_vector v_sver = duckdb_data_chunk_get_vector(output, 8);
	duckdb_vector v_device = duckdb_data_chunk_get_vector(output, 9);
	duckdb_vector v_gpx = duckdb_data_chunk_get_vector(output, 10);
	duckdb_vector v_filename = duckdb_data_chunk_get_vector(output, 11);

	duckdb_vector_ensure_validity_writable(v_wstart);
	duckdb_vector_ensure_validity_writable(v_wend);
	duckdb_vector_ensure_validity_writable(v_start);
	duckdb_vector_ensure_validity_writable(v_end);
	duckdb_vector_ensure_validity_writable(v_creation);
	uint64_t *wstart_v = duckdb_vector_get_validity(v_wstart);
	uint64_t *wend_v = duckdb_vector_get_validity(v_wend);
	uint64_t *start_v = duckdb_vector_get_validity(v_start);
	uint64_t *end_v = duckdb_vector_get_validity(v_end);
	uint64_t *creation_v = duckdb_vector_get_validity(v_creation);

	const char *filename = bind->filename ? bind->filename : "";

	for (idx_t i = 0; i < n; i++) {
		const ah_workout_route *row = &bind->rows[init->offset + i];
		AssignVarchar(v_wtype, i, row->workout_activity_type);
		AssignVarchar(v_wshort, i, row->workout_activity_type_short);
		AssignTimestamp(v_wstart, wstart_v, i, row->workout_start_date);
		AssignTimestamp(v_wend, wend_v, i, row->workout_end_date);
		AssignTimestamp(v_start, start_v, i, row->start_date);
		AssignTimestamp(v_end, end_v, i, row->end_date);
		AssignTimestamp(v_creation, creation_v, i, row->creation_date);
		AssignVarchar(v_source, i, row->source_name);
		AssignVarchar(v_sver, i, row->source_version);
		AssignVarchar(v_device, i, row->device);
		AssignVarchar(v_gpx, i, row->gpx_path);
		AssignVarchar(v_filename, i, filename);
	}

	init->offset += n;
	duckdb_data_chunk_set_size(output, n);
}

void RegisterAppleHealthWorkoutRoutesFunction(duckdb_connection connection) {
	duckdb_table_function function = duckdb_create_table_function();
	duckdb_table_function_set_name(function, "apple_health_workout_routes");

	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_table_function_add_parameter(function, varchar_type);
	duckdb_destroy_logical_type(&varchar_type);

	duckdb_table_function_set_bind(function, RoutesBind);
	duckdb_table_function_set_init(function, ScanInit);
	duckdb_table_function_set_function(function, RoutesFunction);

	duckdb_register_table_function(connection, function);
	duckdb_destroy_table_function(&function);
}

