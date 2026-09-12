#include "duckdb_extension.h"

#include "healthkit_export_tf.h"

DUCKDB_EXTENSION_ENTRYPOINT(duckdb_connection connection, duckdb_extension_info info,
                            struct duckdb_extension_access *access) {
	(void)info;
	(void)access;
	RegisterReadHealthkitExportFunction(connection);
	RegisterHealthkitWorkoutsFunction(connection);
	RegisterHealthkitActivitySummariesFunction(connection);
	RegisterHealthkitWorkoutRoutesFunction(connection);
	RegisterHealthkitWorkoutRoutePointsFunction(connection);
	return true;
}
