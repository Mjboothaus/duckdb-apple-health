#include "parse_health.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ---------------------------------------------------------------------------
 * Helpers
 * -------------------------------------------------------------------------*/

void ah_type_short(const char *type_id, char *out, size_t out_len) {
	static const char *prefixes[] = {
	    "HKQuantityTypeIdentifier",
	    "HKCategoryTypeIdentifier",
	    "HKCorrelationTypeIdentifier",
	    "HKWorkoutActivityType",
	    "HKDataType",
	    NULL,
	};
	if (!out || out_len == 0) {
		return;
	}
	out[0] = '\0';
	if (!type_id) {
		return;
	}
	for (const char **p = prefixes; *p; p++) {
		size_t n = strlen(*p);
		if (strncmp(type_id, *p, n) == 0) {
			snprintf(out, out_len, "%s", type_id + n);
			return;
		}
	}
	snprintf(out, out_len, "%s", type_id);
}

bool ah_parse_double(const char *text, double *out) {
	if (!text || !*text || !out) {
		return false;
	}
	char *end = NULL;
	errno = 0;
	double v = strtod(text, &end);
	if (errno != 0 || end == text || (end && *end != '\0')) {
		return false;
	}
	*out = v;
	return true;
}

static int days_from_civil(int y, unsigned m, unsigned d) {
	/* Howard Hinnant civil_from_days inverse */
	y -= m <= 2;
	const int era = (y >= 0 ? y : y - 399) / 400;
	const unsigned yoe = (unsigned)(y - era * 400);
	const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
	const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
	return (int)(era * 146097 + (int)doe - 719468);
}

bool ah_parse_apple_date(const char *text, char *out, size_t out_len, int64_t *utc_micros_out) {
	if (!text) {
		return false;
	}
	if (out && out_len) {
		snprintf(out, out_len, "%s", text);
	}
	/* yyyy-MM-dd HH:mm:ss Z  with Z = +HHMM or -HHMM */
	int y = 0, mo = 0, d = 0, h = 0, mi = 0, s = 0, off_h = 0, off_m = 0;
	char sign = '+';
	int n = sscanf(text, "%d-%d-%d %d:%d:%d %c%d", &y, &mo, &d, &h, &mi, &s, &sign, &off_h);
	if (n < 8) {
		return false;
	}
	/* off_h may be 1100 style */
	if (off_h >= 100 || off_h <= -100) {
		off_m = abs(off_h) % 100;
		off_h = off_h / 100;
	}
	if (sign == '-') {
		off_h = -off_h;
		off_m = -off_m;
	} else if (sign != '+') {
		return false;
	}
	if (utc_micros_out) {
		int64_t days = days_from_civil(y, (unsigned)mo, (unsigned)d);
		int64_t secs = days * 86400LL + h * 3600LL + mi * 60LL + s;
		/* convert local to UTC: subtract offset */
		int offset_secs = off_h * 3600 + off_m * 60;
		secs -= offset_secs;
		*utc_micros_out = secs * 1000000LL;
	}
	return true;
}

static void copy_attr(char *dst, size_t dst_len, const char *src) {
	if (!dst || dst_len == 0) {
		return;
	}
	if (!src) {
		dst[0] = '\0';
		return;
	}
	snprintf(dst, dst_len, "%s", src);
}

static void xml_unescape_inplace(char *s) {
	if (!s) {
		return;
	}
	char *r = s;
	char *w = s;
	while (*r) {
		if (*r == '&') {
			if (strncmp(r, "&amp;", 5) == 0) {
				*w++ = '&';
				r += 5;
			} else if (strncmp(r, "&lt;", 4) == 0) {
				*w++ = '<';
				r += 4;
			} else if (strncmp(r, "&gt;", 4) == 0) {
				*w++ = '>';
				r += 4;
			} else if (strncmp(r, "&quot;", 6) == 0) {
				*w++ = '"';
				r += 6;
			} else if (strncmp(r, "&apos;", 6) == 0) {
				*w++ = '\'';
				r += 6;
			} else {
				*w++ = *r++;
			}
		} else {
			*w++ = *r++;
		}
	}
	*w = '\0';
}

/* ---------------------------------------------------------------------------
 * Attribute map (small fixed set)
 * -------------------------------------------------------------------------*/

typedef struct {
	char name[64];
	char value[AH_ATTR_MAX];
} ah_attr;

#define AH_MAX_ATTRS 32

typedef struct {
	ah_attr items[AH_MAX_ATTRS];
	int count;
} ah_attr_map;

static const char *attr_get(const ah_attr_map *m, const char *name) {
	for (int i = 0; i < m->count; i++) {
		if (strcmp(m->items[i].name, name) == 0) {
			return m->items[i].value;
		}
	}
	return NULL;
}

static void attr_put(ah_attr_map *m, const char *name, const char *value) {
	if (m->count >= AH_MAX_ATTRS || !name || !value) {
		return;
	}
	snprintf(m->items[m->count].name, sizeof(m->items[m->count].name), "%s", name);
	snprintf(m->items[m->count].value, sizeof(m->items[m->count].value), "%s", value);
	xml_unescape_inplace(m->items[m->count].value);
	m->count++;
}

static void fill_record_from_attrs(ah_record *row, const ah_attr_map *m) {
	memset(row, 0, sizeof(*row));
	const char *type = attr_get(m, "type");
	const char *unit = attr_get(m, "unit");
	const char *value = attr_get(m, "value");
	const char *start = attr_get(m, "startDate");
	const char *end = attr_get(m, "endDate");
	const char *creation = attr_get(m, "creationDate");
	const char *source = attr_get(m, "sourceName");
	const char *sver = attr_get(m, "sourceVersion");
	const char *device = attr_get(m, "device");

	copy_attr(row->type, sizeof(row->type), type ? type : "");
	ah_type_short(row->type, row->type_short, sizeof(row->type_short));
	copy_attr(row->unit, sizeof(row->unit), unit ? unit : "");
	copy_attr(row->start_date, sizeof(row->start_date), start ? start : "");
	copy_attr(row->end_date, sizeof(row->end_date), end ? end : "");
	copy_attr(row->creation_date, sizeof(row->creation_date), creation ? creation : "");
	copy_attr(row->source_name, sizeof(row->source_name), source ? source : "");
	copy_attr(row->source_version, sizeof(row->source_version), sver ? sver : "");
	copy_attr(row->device, sizeof(row->device), device ? device : "");

	if (value && ah_parse_double(value, &row->value)) {
		row->has_value = true;
		row->value_text[0] = '\0';
	} else {
		row->has_value = false;
		copy_attr(row->value_text, sizeof(row->value_text), value ? value : "");
	}
}

static void fill_workout_from_attrs(ah_workout *row, const ah_attr_map *m) {
	memset(row, 0, sizeof(*row));
	const char *atype = attr_get(m, "workoutActivityType");
	copy_attr(row->activity_type, sizeof(row->activity_type), atype ? atype : "");
	ah_type_short(row->activity_type, row->activity_type_short, sizeof(row->activity_type_short));

	const char *v;
	if ((v = attr_get(m, "duration")) && ah_parse_double(v, &row->duration)) {
		row->has_duration = true;
	}
	copy_attr(row->duration_unit, sizeof(row->duration_unit), attr_get(m, "durationUnit") ? attr_get(m, "durationUnit") : "");

	if ((v = attr_get(m, "totalDistance")) && ah_parse_double(v, &row->total_distance)) {
		row->has_total_distance = true;
	}
	copy_attr(row->total_distance_unit, sizeof(row->total_distance_unit),
	          attr_get(m, "totalDistanceUnit") ? attr_get(m, "totalDistanceUnit") : "");

	if ((v = attr_get(m, "totalEnergyBurned")) && ah_parse_double(v, &row->total_energy)) {
		row->has_total_energy = true;
	}
	copy_attr(row->total_energy_unit, sizeof(row->total_energy_unit),
	          attr_get(m, "totalEnergyBurnedUnit") ? attr_get(m, "totalEnergyBurnedUnit") : "");

	copy_attr(row->start_date, sizeof(row->start_date), attr_get(m, "startDate") ? attr_get(m, "startDate") : "");
	copy_attr(row->end_date, sizeof(row->end_date), attr_get(m, "endDate") ? attr_get(m, "endDate") : "");
	copy_attr(row->creation_date, sizeof(row->creation_date),
	          attr_get(m, "creationDate") ? attr_get(m, "creationDate") : "");
	copy_attr(row->source_name, sizeof(row->source_name), attr_get(m, "sourceName") ? attr_get(m, "sourceName") : "");
	copy_attr(row->source_version, sizeof(row->source_version),
	          attr_get(m, "sourceVersion") ? attr_get(m, "sourceVersion") : "");
	copy_attr(row->device, sizeof(row->device), attr_get(m, "device") ? attr_get(m, "device") : "");
}

static void fill_summary_from_attrs(ah_activity_summary *row, const ah_attr_map *m) {
	memset(row, 0, sizeof(*row));
	copy_attr(row->date_components, sizeof(row->date_components),
	          attr_get(m, "dateComponents") ? attr_get(m, "dateComponents") : "");
	const char *v;
	if ((v = attr_get(m, "activeEnergyBurned")) && ah_parse_double(v, &row->active_energy_burned)) {
		row->has_active_energy = true;
	}
	if ((v = attr_get(m, "activeEnergyBurnedGoal")) && ah_parse_double(v, &row->active_energy_burned_goal)) {
		row->has_active_energy_goal = true;
	}
	copy_attr(row->active_energy_unit, sizeof(row->active_energy_unit),
	          attr_get(m, "activeEnergyBurnedUnit") ? attr_get(m, "activeEnergyBurnedUnit") : "");

	if ((v = attr_get(m, "appleMoveMinutes")) && ah_parse_double(v, &row->apple_move_minutes)) {
		row->has_move_minutes = true;
	}
	if ((v = attr_get(m, "appleMoveMinutesGoal")) && ah_parse_double(v, &row->apple_move_minutes_goal)) {
		row->has_move_minutes_goal = true;
	}
	if ((v = attr_get(m, "appleMoveTime")) && ah_parse_double(v, &row->apple_move_time)) {
		row->has_move_time = true;
	}
	if ((v = attr_get(m, "appleMoveTimeGoal")) && ah_parse_double(v, &row->apple_move_time_goal)) {
		row->has_move_time_goal = true;
	}
	if ((v = attr_get(m, "appleExerciseTime")) && ah_parse_double(v, &row->apple_exercise_time)) {
		row->has_exercise_time = true;
	}
	if ((v = attr_get(m, "appleExerciseTimeGoal")) && ah_parse_double(v, &row->apple_exercise_time_goal)) {
		row->has_exercise_time_goal = true;
	}
	if ((v = attr_get(m, "appleStandHours")) && ah_parse_double(v, &row->apple_stand_hours)) {
		row->has_stand_hours = true;
	}
	if ((v = attr_get(m, "appleStandHoursGoal")) && ah_parse_double(v, &row->apple_stand_hours_goal)) {
		row->has_stand_hours_goal = true;
	}
}


static void fill_route_from_attrs(ah_workout_route *row, const ah_attr_map *m, const ah_workout *parent, int has_parent) {
	memset(row, 0, sizeof(*row));
	if (has_parent && parent) {
		copy_attr(row->workout_activity_type, sizeof(row->workout_activity_type), parent->activity_type);
		copy_attr(row->workout_activity_type_short, sizeof(row->workout_activity_type_short), parent->activity_type_short);
		copy_attr(row->workout_start_date, sizeof(row->workout_start_date), parent->start_date);
		copy_attr(row->workout_end_date, sizeof(row->workout_end_date), parent->end_date);
	}
	copy_attr(row->start_date, sizeof(row->start_date), attr_get(m, "startDate") ? attr_get(m, "startDate") : "");
	copy_attr(row->end_date, sizeof(row->end_date), attr_get(m, "endDate") ? attr_get(m, "endDate") : "");
	copy_attr(row->creation_date, sizeof(row->creation_date),
	          attr_get(m, "creationDate") ? attr_get(m, "creationDate") : "");
	copy_attr(row->source_name, sizeof(row->source_name), attr_get(m, "sourceName") ? attr_get(m, "sourceName") : "");
	copy_attr(row->source_version, sizeof(row->source_version),
	          attr_get(m, "sourceVersion") ? attr_get(m, "sourceVersion") : "");
	copy_attr(row->device, sizeof(row->device), attr_get(m, "device") ? attr_get(m, "device") : "");
	row->gpx_path[0] = '\0';
}

/* ---------------------------------------------------------------------------
 * Streaming tag scanner (no DOM, no external XML lib)
 *
 * Health export is attribute-centric. We stream bytes, extract complete tags
 * starting at '<' through matching '>', parse name + attributes, and track
 * Correlation nesting so nested <Record>s are skipped.
 * -------------------------------------------------------------------------*/

typedef struct {
	const ah_parse_callbacks *cb;
	ah_parse_stats stats;
	int correlation_depth;
	int workout_depth;
	/* Snapshot of current open Workout attrs for nested WorkoutRoute. */
	ah_workout current_workout;
	int has_current_workout;
	/* Pending WorkoutRoute attrs until FileReference or end. */
	ah_workout_route pending_route;
	int has_pending_route;
} ah_parser;

static void emit_pending_route(ah_parser *P) {
	if (!P->has_pending_route) {
		return;
	}
	if (P->cb && P->cb->on_workout_route) {
		P->cb->on_workout_route(&P->pending_route, P->cb->userdata);
	}
	P->stats.workout_routes++;
	P->has_pending_route = 0;
	memset(&P->pending_route, 0, sizeof(P->pending_route));
}

static int is_name_start(unsigned char c) {
	return isalpha(c) || c == '_' || c == ':';
}

static int is_name_char(unsigned char c) {
	return isalnum(c) || c == '_' || c == ':' || c == '-' || c == '.';
}

/* Parse attributes from a pointer just after the element name. */
static void parse_attributes(const char *p, const char *end, ah_attr_map *map) {
	map->count = 0;
	while (p < end) {
		while (p < end && isspace((unsigned char)*p)) {
			p++;
		}
		if (p >= end || *p == '/' || *p == '>') {
			break;
		}
		const char *name_start = p;
		if (!is_name_start((unsigned char)*p)) {
			p++;
			continue;
		}
		p++;
		while (p < end && is_name_char((unsigned char)*p)) {
			p++;
		}
		size_t name_len = (size_t)(p - name_start);
		while (p < end && isspace((unsigned char)*p)) {
			p++;
		}
		if (p >= end || *p != '=') {
			continue;
		}
		p++;
		while (p < end && isspace((unsigned char)*p)) {
			p++;
		}
		if (p >= end) {
			break;
		}
		char quote = *p;
		if (quote != '"' && quote != '\'') {
			continue;
		}
		p++;
		const char *val_start = p;
		while (p < end && *p != quote) {
			p++;
		}
		size_t val_len = (size_t)(p - val_start);
		if (p < end && *p == quote) {
			p++;
		}
		char name[64];
		char value[AH_ATTR_MAX];
		if (name_len >= sizeof(name)) {
			name_len = sizeof(name) - 1;
		}
		if (val_len >= sizeof(value)) {
			val_len = sizeof(value) - 1;
		}
		memcpy(name, name_start, name_len);
		name[name_len] = '\0';
		memcpy(value, val_start, val_len);
		value[val_len] = '\0';
		attr_put(map, name, value);
	}
}

static void handle_start_tag(ah_parser *P, const char *name, const ah_attr_map *attrs, int self_closing) {
	if (strcmp(name, "Correlation") == 0) {
		P->correlation_depth++;
		return;
	}
	if (strcmp(name, "Workout") == 0) {
		P->workout_depth++;
		ah_workout row;
		fill_workout_from_attrs(&row, attrs);
		P->current_workout = row;
		P->has_current_workout = 1;
		if (P->cb && P->cb->on_workout) {
			P->cb->on_workout(&row, P->cb->userdata);
		}
		P->stats.workouts++;
		if (self_closing) {
			P->workout_depth--;
			P->has_current_workout = 0;
			memset(&P->current_workout, 0, sizeof(P->current_workout));
		}
		return;
	}
	if (strcmp(name, "WorkoutRoute") == 0) {
		/* Finish any previous route without FileReference. */
		emit_pending_route(P);
		fill_route_from_attrs(&P->pending_route, attrs, &P->current_workout, P->has_current_workout);
		P->has_pending_route = 1;
		if (self_closing) {
			emit_pending_route(P);
		}
		return;
	}
	if (strcmp(name, "FileReference") == 0) {
		const char *path = attr_get(attrs, "path");
		if (P->has_pending_route && path) {
			copy_attr(P->pending_route.gpx_path, sizeof(P->pending_route.gpx_path), path);
		}
		/* Emit on FileReference when nested under a pending route (common shape). */
		if (P->has_pending_route) {
			emit_pending_route(P);
		}
		return;
	}
	if (strcmp(name, "ActivitySummary") == 0) {
		if (P->cb && P->cb->on_activity_summary) {
			ah_activity_summary row;
			fill_summary_from_attrs(&row, attrs);
			P->cb->on_activity_summary(&row, P->cb->userdata);
		}
		P->stats.activity_summaries++;
		return;
	}
	if (strcmp(name, "Record") == 0) {
		if (P->correlation_depth > 0) {
			P->stats.skipped_nested_records++;
			return;
		}
		if (P->cb && P->cb->on_record) {
			ah_record row;
			fill_record_from_attrs(&row, attrs);
			P->cb->on_record(&row, P->cb->userdata);
		}
		P->stats.records++;
		return;
	}
	/* ClinicalRecord, WorkoutEvent, Me, ExportDate, HealthData, etc. ignored */
}

static void handle_end_tag(ah_parser *P, const char *name) {
	if (strcmp(name, "Correlation") == 0 && P->correlation_depth > 0) {
		P->correlation_depth--;
	} else if (strcmp(name, "WorkoutRoute") == 0) {
		/* Route without FileReference still emits (empty gpx_path). */
		emit_pending_route(P);
	} else if (strcmp(name, "Workout") == 0 && P->workout_depth > 0) {
		P->workout_depth--;
		if (P->workout_depth == 0) {
			P->has_current_workout = 0;
			memset(&P->current_workout, 0, sizeof(P->current_workout));
		}
	}
}

static void process_tag(ah_parser *P, const char *tag, size_t len) {
	/* tag points at '<', length includes '<' and '>' */
	if (len < 3) {
		return;
	}
	const char *p = tag + 1;
	const char *end = tag + len - 1; /* points at '>' */
	if (*p == '?' || *p == '!') {
		/* XML decl / comment / doctype */
		return;
	}
	int closing = 0;
	if (*p == '/') {
		closing = 1;
		p++;
	}
	while (p < end && isspace((unsigned char)*p)) {
		p++;
	}
	const char *name_start = p;
	if (p >= end || !is_name_start((unsigned char)*p)) {
		return;
	}
	p++;
	while (p < end && is_name_char((unsigned char)*p)) {
		p++;
	}
	char name[64];
	size_t name_len = (size_t)(p - name_start);
	if (name_len >= sizeof(name)) {
		name_len = sizeof(name) - 1;
	}
	memcpy(name, name_start, name_len);
	name[name_len] = '\0';

	if (closing) {
		handle_end_tag(P, name);
		return;
	}

	/* self-closing if ends with / before > */
	int self_closing = 0;
	const char *scan = end - 1;
	while (scan > p && isspace((unsigned char)*scan)) {
		scan--;
	}
	if (scan >= p && *scan == '/') {
		self_closing = 1;
		end = scan; /* attributes end before '/' */
	}

	ah_attr_map attrs;
	parse_attributes(p, end, &attrs);
	handle_start_tag(P, name, &attrs, self_closing);
}

int ah_parse_xml_filep(FILE *fp, const ah_parse_callbacks *cb, ah_parse_stats *stats_out) {
	ah_parser P;
	memset(&P, 0, sizeof(P));
	P.cb = cb;

	/* Carry buffer for tags that span fread chunks. */
	size_t cap = 1 << 16;
	char *buf = (char *)malloc(cap);
	if (!buf) {
		return 1;
	}
	size_t len = 0;

	char chunk[8192];
	size_t nread;
	while ((nread = fread(chunk, 1, sizeof(chunk), fp)) > 0) {
		if (len + nread + 1 > cap) {
			size_t ncap = cap * 2;
			while (len + nread + 1 > ncap) {
				ncap *= 2;
			}
			char *nb = (char *)realloc(buf, ncap);
			if (!nb) {
				free(buf);
				return 1;
			}
			buf = nb;
			cap = ncap;
		}
		memcpy(buf + len, chunk, nread);
		len += nread;
		buf[len] = '\0';

		size_t i = 0;
		while (i < len) {
			char *lt = memchr(buf + i, '<', len - i);
			if (!lt) {
				/* discard non-tag prefix */
				len = 0;
				break;
			}
			size_t start = (size_t)(lt - buf);
			char *gt = memchr(buf + start, '>', len - start);
			if (!gt) {
				/* incomplete tag — keep from '<' onward */
				if (start > 0) {
					memmove(buf, buf + start, len - start);
					len -= start;
				}
				break;
			}
			size_t tag_len = (size_t)(gt - (buf + start) + 1);
			process_tag(&P, buf + start, tag_len);
			i = start + tag_len;
			if (i >= len) {
				len = 0;
				break;
			}
			/* continue scanning after this tag; compact occasionally */
			if (i > (1 << 14)) {
				memmove(buf, buf + i, len - i);
				len -= i;
				i = 0;
			}
		}
	}

	int err = ferror(fp) ? 2 : 0;
	free(buf);
	if (stats_out) {
		*stats_out = P.stats;
	}
	return err;
}

int ah_parse_xml_file(const char *path, const ah_parse_callbacks *cb, ah_parse_stats *stats_out) {
	FILE *fp = fopen(path, "rb");
	if (!fp) {
		return 1;
	}
	int rc = ah_parse_xml_filep(fp, cb, stats_out);
	fclose(fp);
	return rc;
}
