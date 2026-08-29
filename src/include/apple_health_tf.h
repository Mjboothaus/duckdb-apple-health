#pragma once

#include "duckdb_extension.h"

void RegisterReadAppleHealthFunction(duckdb_connection connection);
void RegisterAppleHealthWorkoutsFunction(duckdb_connection connection);
void RegisterAppleHealthActivitySummariesFunction(duckdb_connection connection);
void RegisterAppleHealthWorkoutRoutesFunction(duckdb_connection connection);
