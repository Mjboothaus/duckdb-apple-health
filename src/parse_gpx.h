#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "parse_health.h"

/* Streaming Apple Health workout-route GPX parser. No DuckDB headers. */

typedef struct {
	char gpx_path[AH_ATTR_MAX];
	char gpx_member[AH_ATTR_MAX]; /* zip member or filesystem path */
	/* Parent workout (copied from ah_workout_route when available) */
	char workout_activity_type[AH_TYPE_MAX];
	char workout_activity_type_short[AH_TYPE_MAX];
	char workout_start_date[64];
	char workout_end_date[64];
	int64_t point_index;
	double lat;
	double lon;
	bool has_ele;
	double ele;
	/* ISO-8601 UTC time from GPX, e.g. 2026-01-14T20:00:00Z */
	char time_iso[64];
	bool has_speed;
	double speed;
	bool has_course;
	double course;
	bool has_h_acc;
	double h_acc;
	bool has_v_acc;
	double v_acc;
} ah_gpx_point;

typedef struct {
	void (*on_point)(const ah_gpx_point *row, void *userdata);
	void *userdata;
} ah_gpx_callbacks;

typedef struct {
	size_t points;
} ah_gpx_stats;

/* Parse GPX from an open FILE*. route_meta may be NULL (empty parent fields). */
int ah_parse_gpx_filep(FILE *fp, const ah_workout_route *route_meta, const char *gpx_member,
                       const ah_gpx_callbacks *cb, ah_gpx_stats *stats_out);

/* Parse GPX ISO-8601 time (…Z or with offset) to UTC micros. */
bool ah_parse_gpx_time(const char *text, int64_t *utc_micros_out);
