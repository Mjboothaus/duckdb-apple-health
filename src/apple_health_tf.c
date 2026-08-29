#include "duckdb_extension.h"

#include "apple_health_tf.h"

#include <stdbool.h>
#include <string.h>

DUCKDB_EXTENSION_EXTERN

/* Week-1 spike: ignore path, emit 3 hardcoded rows. */

typedef struct {
	bool done;
} read_apple_health_init_data;

static void DestroyInitData(void *ptr) {
	duckdb_free(ptr);
}

static void ReadAppleHealthBind(duckdb_bind_info info) {
	/* path is required for the signature; spike intentionally ignores it */
	(void)info;

	duckdb_logical_type varchar_type = duckdb_create_logical_type(DUCKDB_TYPE_VARCHAR);
	duckdb_logical_type double_type = duckdb_create_logical_type(DUCKDB_TYPE_DOUBLE);
	duckdb_logical_type ts_type = duckdb_create_logical_type(DUCKDB_TYPE_TIMESTAMP);

	duckdb_bind_add_result_column(info, "type", varchar_type);
	duckdb_bind_add_result_column(info, "value", double_type);
	duckdb_bind_add_result_column(info, "start_date", ts_type);

	duckdb_destroy_logical_type(&varchar_type);
	duckdb_destroy_logical_type(&double_type);
	duckdb_destroy_logical_type(&ts_type);

	duckdb_bind_set_cardinality(info, 3, true);
}

static void ReadAppleHealthInit(duckdb_init_info info) {
	read_apple_health_init_data *init =
	    (read_apple_health_init_data *)duckdb_malloc(sizeof(read_apple_health_init_data));
	if (!init) {
		duckdb_init_set_error(info, "out of memory");
		return;
	}
	init->done = false;
	duckdb_init_set_init_data(info, init, DestroyInitData);
}

/* 2026-01-15 06:30:00+11 → UTC 2026-01-14 19:30:00 = epoch micros */
static int64_t SpikeTimestampMicros(void) {
	/* 2026-01-14 19:30:00 UTC */
	return 1768419000000000LL;
}

static void ReadAppleHealthFunction(duckdb_function_info info, duckdb_data_chunk output) {
	read_apple_health_init_data *init =
	    (read_apple_health_init_data *)duckdb_function_get_init_data(info);
	if (!init || init->done) {
		duckdb_data_chunk_set_size(output, 0);
		return;
	}

	duckdb_vector type_vec = duckdb_data_chunk_get_vector(output, 0);
	duckdb_vector value_vec = duckdb_data_chunk_get_vector(output, 1);
	duckdb_vector start_vec = duckdb_data_chunk_get_vector(output, 2);

	double *value_data = (double *)duckdb_vector_get_data(value_vec);
	duckdb_timestamp *start_data = (duckdb_timestamp *)duckdb_vector_get_data(start_vec);

	duckdb_vector_ensure_validity_writable(value_vec);
	uint64_t *value_validity = duckdb_vector_get_validity(value_vec);

	const int64_t ts = SpikeTimestampMicros();

	/* Row 0: HeartRate 72 */
	duckdb_vector_assign_string_element(type_vec, 0, "HKQuantityTypeIdentifierHeartRate");
	value_data[0] = 72.0;
	start_data[0].micros = ts;

	/* Row 1: StepCount 1234 */
	duckdb_vector_assign_string_element(type_vec, 1, "HKQuantityTypeIdentifierStepCount");
	value_data[1] = 1234.0;
	start_data[1].micros = ts;

	/* Row 2: SleepAnalysis — numeric value NULL */
	duckdb_vector_assign_string_element(type_vec, 2, "HKCategoryTypeIdentifierSleepAnalysis");
	duckdb_validity_set_row_invalid(value_validity, 2);
	start_data[2].micros = ts;

	duckdb_data_chunk_set_size(output, 3);
	init->done = true;
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
