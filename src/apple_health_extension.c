#include "duckdb_extension.h"

#include "apple_health_tf.h"

DUCKDB_EXTENSION_ENTRYPOINT(duckdb_connection connection, duckdb_extension_info info,
                            struct duckdb_extension_access *access) {
	(void)info;
	(void)access;
	RegisterReadAppleHealthFunction(connection);
	RegisterAppleHealthWorkoutsFunction(connection);
	RegisterAppleHealthActivitySummariesFunction(connection);
	return true;
}
