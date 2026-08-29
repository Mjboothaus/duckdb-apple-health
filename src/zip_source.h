#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#include "parse_health.h"

/* Open Apple Health path as a stream of export.xml bytes.
 * path may be:
 *   - .zip containing a member ending in export.xml (e.g. apple_health_export/export.xml)
 *   - directory containing export.xml
 *   - export.xml (or any .xml file)
 *
 * No DuckDB headers. Uses zlib for DEFLATE members only.
 */

typedef struct ah_xml_source ah_xml_source;

/* Open source. On success returns non-NULL; caller must ah_xml_source_close. */
ah_xml_source *ah_xml_source_open(const char *path, char *err, size_t err_len);

/* FILE* positioned at start of export.xml content (may be a temp file). */
FILE *ah_xml_source_file(ah_xml_source *src);

/* Path used for the logical filename column (zip member or file path). */
const char *ah_xml_source_filename(const ah_xml_source *src);

void ah_xml_source_close(ah_xml_source *src);

/* Convenience: open path, parse with callbacks, close. */
int ah_parse_health_path(const char *path, const ah_parse_callbacks *cb, ah_parse_stats *stats_out, char *err,
                         size_t err_len);
