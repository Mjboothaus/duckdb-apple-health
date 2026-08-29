#include "parse_health.h"
#include "zip_source.h"

#include <stdio.h>
#include <string.h>

/* CSV escape: wrap in quotes if needed; double internal quotes. */
static void csv_field(FILE *out, const char *s) {
	if (!s) {
		s = "";
	}
	int need_quote = 0;
	for (const char *p = s; *p; p++) {
		if (*p == ',' || *p == '"' || *p == '\n' || *p == '\r') {
			need_quote = 1;
			break;
		}
	}
	if (!need_quote) {
		fputs(s, out);
		return;
	}
	fputc('"', out);
	for (const char *p = s; *p; p++) {
		if (*p == '"') {
			fputc('"', out);
			fputc('"', out);
		} else {
			fputc(*p, out);
		}
	}
	fputc('"', out);
}

static void on_record(const ah_record *row, void *userdata) {
	FILE *out = (FILE *)userdata;
	csv_field(out, row->type);
	fputc(',', out);
	csv_field(out, row->type_short);
	fputc(',', out);
	csv_field(out, row->unit);
	fputc(',', out);
	if (row->has_value) {
		fprintf(out, "%.15g", row->value);
	}
	fputc(',', out);
	csv_field(out, row->value_text);
	fputc(',', out);
	csv_field(out, row->start_date);
	fputc(',', out);
	csv_field(out, row->end_date);
	fputc(',', out);
	csv_field(out, row->creation_date);
	fputc(',', out);
	csv_field(out, row->source_name);
	fputc(',', out);
	csv_field(out, row->source_version);
	fputc('\n', out);
}

static void on_workout(const ah_workout *row, void *userdata) {
	(void)row;
	(void)userdata;
}

static void on_summary(const ah_activity_summary *row, void *userdata) {
	(void)row;
	(void)userdata;
}

static void usage(const char *argv0) {
	fprintf(stderr, "Usage: %s <export.xml|export.zip|export-dir>\n", argv0);
	fprintf(stderr,
	        "Streams Apple Health export; prints top-level Record rows as CSV.\n"
	        "Path may be export.xml, a zip containing **/export.xml, or a directory with export.xml.\n");
}

int main(int argc, char **argv) {
	if (argc != 2) {
		usage(argv[0]);
		return 2;
	}
	const char *path = argv[1];
	if (strcmp(path, "-h") == 0 || strcmp(path, "--help") == 0) {
		usage(argv[0]);
		return 0;
	}

	ah_parse_callbacks cb = {
	    .on_record = on_record,
	    .on_workout = on_workout,
	    .on_activity_summary = on_summary,
	    .on_workout_route = NULL,
	    .userdata = stdout,
	};
	ah_parse_stats stats;
	memset(&stats, 0, sizeof(stats));

	/* header matches golden/records.csv */
	fputs("type,type_short,unit,value,value_text,start_date,end_date,creation_date,source_name,source_version\n",
	      stdout);

	char err[256];
	err[0] = '\0';
	int rc = ah_parse_health_path(path, &cb, &stats, err, sizeof(err));
	if (rc != 0) {
		fprintf(stderr, "parse failed (%d) for %s: %s\n", rc, path, err[0] ? err : "(unknown)");
		return 1;
	}
	fprintf(stderr, "records=%zu workouts=%zu activity_summaries=%zu workout_routes=%zu skipped_nested_records=%zu\n", stats.records,
	        stats.workouts, stats.activity_summaries, stats.workout_routes, stats.skipped_nested_records);
	return 0;
}
