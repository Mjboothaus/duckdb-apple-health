#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

/* Streaming Apple Health export.xml parser. No DuckDB headers. */

#define AH_ATTR_MAX 512
#define AH_TYPE_MAX 128

typedef struct {
	char type[AH_TYPE_MAX];
	char type_short[AH_TYPE_MAX];
	char unit[64];
	bool has_value;
	double value;
	char value_text[AH_ATTR_MAX];
	char start_date[64];
	char end_date[64];
	char creation_date[64];
	char source_name[AH_ATTR_MAX];
	char source_version[64];
	char device[AH_ATTR_MAX];
} ah_record;

typedef struct {
	char activity_type[AH_TYPE_MAX];
	char activity_type_short[AH_TYPE_MAX];
	bool has_duration;
	double duration;
	char duration_unit[32];
	bool has_total_distance;
	double total_distance;
	char total_distance_unit[32];
	bool has_total_energy;
	double total_energy;
	char total_energy_unit[32];
	char start_date[64];
	char end_date[64];
	char creation_date[64];
	char source_name[AH_ATTR_MAX];
	char source_version[64];
	char device[AH_ATTR_MAX];
} ah_workout;

typedef struct {
	char date_components[32];
	bool has_active_energy;
	double active_energy_burned;
	bool has_active_energy_goal;
	double active_energy_burned_goal;
	char active_energy_unit[32];
	/* Older exports */
	bool has_move_minutes;
	double apple_move_minutes;
	bool has_move_minutes_goal;
	double apple_move_minutes_goal;
	/* iOS 14+ */
	bool has_move_time;
	double apple_move_time;
	bool has_move_time_goal;
	double apple_move_time_goal;
	bool has_exercise_time;
	double apple_exercise_time;
	bool has_exercise_time_goal;
	double apple_exercise_time_goal;
	bool has_stand_hours;
	double apple_stand_hours;
	bool has_stand_hours_goal;
	double apple_stand_hours_goal;
} ah_activity_summary;

typedef struct {
	/* Parent workout (when route is nested under <Workout>) */
	char workout_activity_type[AH_TYPE_MAX];
	char workout_activity_type_short[AH_TYPE_MAX];
	char workout_start_date[64];
	char workout_end_date[64];
	/* Route element attrs */
	char start_date[64];
	char end_date[64];
	char creation_date[64];
	char source_name[AH_ATTR_MAX];
	char source_version[64];
	char device[AH_ATTR_MAX];
	/* FileReference path, e.g. /workout-routes/route_….gpx */
	char gpx_path[AH_ATTR_MAX];
} ah_workout_route;

typedef struct {
	void (*on_record)(const ah_record *row, void *userdata);
	void (*on_workout)(const ah_workout *row, void *userdata);
	void (*on_activity_summary)(const ah_activity_summary *row, void *userdata);
	void (*on_workout_route)(const ah_workout_route *row, void *userdata);
	void *userdata;
} ah_parse_callbacks;

typedef struct {
	size_t records;
	size_t workouts;
	size_t activity_summaries;
	size_t workout_routes;
	size_t skipped_nested_records;
} ah_parse_stats;

/* Stream path as UTF-8 XML. Returns 0 on success, non-zero on I/O or parse error. */
int ah_parse_xml_file(const char *path, const ah_parse_callbacks *cb, ah_parse_stats *stats_out);

/* Stream an already-open FILE*. */
int ah_parse_xml_filep(FILE *fp, const ah_parse_callbacks *cb, ah_parse_stats *stats_out);

/* Helpers also used by tests / later DuckDB glue. */
void ah_type_short(const char *type_id, char *out, size_t out_len);
bool ah_parse_double(const char *text, double *out);
/* Apple Health date: "yyyy-MM-dd HH:mm:ss Z" with Z like +1100 / -0800 / +0530.
   On success writes normalised copy to out (may equal input shape) and optional
   UTC epoch microseconds. Returns false on hard failure. */
bool ah_parse_apple_date(const char *text, char *out, size_t out_len, int64_t *utc_micros_out);
