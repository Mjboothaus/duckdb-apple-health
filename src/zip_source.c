#include "zip_source.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include <zlib.h>

/* Minimal ZIP reader for DEFLATE/STORE local files. Enough for Health export.zip. */

#pragma pack(push, 1)
typedef struct {
	uint32_t signature; /* 0x04034b50 */
	uint16_t version_needed;
	uint16_t flags;
	uint16_t method;
	uint16_t mod_time;
	uint16_t mod_date;
	uint32_t crc32;
	uint32_t comp_size;
	uint32_t uncomp_size;
	uint16_t name_len;
	uint16_t extra_len;
} zip_local_header;

typedef struct {
	uint32_t signature; /* 0x02014b50 */
	uint16_t version_made;
	uint16_t version_needed;
	uint16_t flags;
	uint16_t method;
	uint16_t mod_time;
	uint16_t mod_date;
	uint32_t crc32;
	uint32_t comp_size;
	uint32_t uncomp_size;
	uint16_t name_len;
	uint16_t extra_len;
	uint16_t comment_len;
	uint16_t disk_start;
	uint16_t int_attr;
	uint32_t ext_attr;
	uint32_t local_header_offset;
} zip_central_header;

typedef struct {
	uint32_t signature; /* 0x06054b50 */
	uint16_t disk_no;
	uint16_t cd_disk;
	uint16_t cd_entries_disk;
	uint16_t cd_entries_total;
	uint32_t cd_size;
	uint32_t cd_offset;
	uint16_t comment_len;
} zip_end_record;
#pragma pack(pop)

struct ah_xml_source {
	FILE *fp;
	char *filename; /* heap */
	char *temp_path; /* if inflated to temp */
	int owns_fp;
};

static void set_err(char *err, size_t err_len, const char *msg) {
	if (err && err_len) {
		snprintf(err, err_len, "%s", msg ? msg : "error");
	}
}

static int path_is_dir(const char *path) {
	struct stat st;
	if (stat(path, &st) != 0) {
		return 0;
	}
	return S_ISDIR(st.st_mode);
}

static int ends_with_ci(const char *s, const char *suffix) {
	size_t n = strlen(s);
	size_t m = strlen(suffix);
	if (n < m) {
		return 0;
	}
	const char *a = s + (n - m);
	for (size_t i = 0; i < m; i++) {
		char c1 = a[i];
		char c2 = suffix[i];
		if (c1 >= 'A' && c1 <= 'Z') {
			c1 = (char)(c1 - 'A' + 'a');
		}
		if (c2 >= 'A' && c2 <= 'Z') {
			c2 = (char)(c2 - 'A' + 'a');
		}
		if (c1 != c2) {
			return 0;
		}
	}
	return 1;
}

static int name_is_export_xml(const char *name, size_t len) {
	/* Match bare export.xml or any path ending in /export.xml. */
	const char *needle = "export.xml";
	size_t nlen = strlen(needle);
	if (len < nlen) {
		return 0;
	}
	if (len == nlen && strncmp(name, needle, nlen) == 0) {
		return 1;
	}
	if (len > nlen && name[len - nlen - 1] == '/' && strncmp(name + len - nlen, needle, nlen) == 0) {
		return 1;
	}
	return 0;
}

static int read_fully(FILE *fp, void *buf, size_t n) {
	return fread(buf, 1, n, fp) == n;
}

static int find_end_of_central_dir(FILE *fp, zip_end_record *out) {
	if (fseek(fp, 0, SEEK_END) != 0) {
		return -1;
	}
	long fsize = ftell(fp);
	if (fsize < (long)sizeof(zip_end_record)) {
		return -1;
	}
	/* Search last 64k + end record for EOCD signature */
	long max_back = 65557;
	if (max_back > fsize) {
		max_back = fsize;
	}
	long start = fsize - max_back;
	if (fseek(fp, start, SEEK_SET) != 0) {
		return -1;
	}
	size_t blen = (size_t)(fsize - start);
	unsigned char *buf = (unsigned char *)malloc(blen);
	if (!buf) {
		return -1;
	}
	if (!read_fully(fp, buf, blen)) {
		free(buf);
		return -1;
	}
	int found = -1;
	for (long i = (long)blen - 4; i >= 0; i--) {
		if (buf[i] == 0x50 && buf[i + 1] == 0x4b && buf[i + 2] == 0x05 && buf[i + 3] == 0x06) {
			if ((size_t)i + sizeof(zip_end_record) <= blen) {
				memcpy(out, buf + i, sizeof(*out));
				found = 0;
				break;
			}
		}
	}
	free(buf);
	return found;
}

static FILE *inflate_member_to_temp(FILE *zip_fp, uint32_t comp_size, uint32_t uncomp_size, uint16_t method,
                                    char **temp_path_out, char *err, size_t err_len) {
	char tmpl[] = "/tmp/ah_export_XXXXXX";
	int fd = mkstemp(tmpl);
	if (fd < 0) {
		set_err(err, err_len, "mkstemp failed");
		return NULL;
	}
	FILE *out = fdopen(fd, "w+b");
	if (!out) {
		close(fd);
		unlink(tmpl);
		set_err(err, err_len, "fdopen failed");
		return NULL;
	}

	if (method == 0) {
		/* stored */
		char buf[8192];
		uint32_t left = comp_size;
		while (left > 0) {
			size_t n = left > sizeof(buf) ? sizeof(buf) : left;
			if (!read_fully(zip_fp, buf, n)) {
				fclose(out);
				unlink(tmpl);
				set_err(err, err_len, "zip read failed (stored)");
				return NULL;
			}
			if (fwrite(buf, 1, n, out) != n) {
				fclose(out);
				unlink(tmpl);
				set_err(err, err_len, "temp write failed");
				return NULL;
			}
			left -= (uint32_t)n;
		}
	} else if (method == 8) {
		z_stream strm;
		memset(&strm, 0, sizeof(strm));
		/* raw deflate (no zlib wrapper) — ZIP uses -MAX_WBITS */
		if (inflateInit2(&strm, -MAX_WBITS) != Z_OK) {
			fclose(out);
			unlink(tmpl);
			set_err(err, err_len, "inflateInit2 failed");
			return NULL;
		}
		unsigned char in[8192];
		unsigned char outbuf[16384];
		uint32_t left = comp_size;
		uLong total_out = 0;
		int reached_end = 0;
		/* Must reach Z_STREAM_END. Do not stop on Z_BUF_ERROR when the output
		 * buffer fills — that truncated real Apple Health zips (~12 KiB short).
		 * Data-descriptor members still supply sizes via the central directory. */
		for (;;) {
			if (strm.avail_in == 0 && left > 0) {
				size_t n = left > sizeof(in) ? sizeof(in) : left;
				if (!read_fully(zip_fp, in, n)) {
					inflateEnd(&strm);
					fclose(out);
					unlink(tmpl);
					set_err(err, err_len, "zip read failed (deflate)");
					return NULL;
				}
				strm.next_in = in;
				strm.avail_in = (uInt)n;
				left -= (uint32_t)n;
			}
			strm.next_out = outbuf;
			strm.avail_out = sizeof(outbuf);
			int flush = (left == 0) ? Z_FINISH : Z_NO_FLUSH;
			int zrc = inflate(&strm, flush);
			size_t have = sizeof(outbuf) - strm.avail_out;
			if (have && fwrite(outbuf, 1, have, out) != have) {
				inflateEnd(&strm);
				fclose(out);
				unlink(tmpl);
				set_err(err, err_len, "temp write failed");
				return NULL;
			}
			if (zrc == Z_STREAM_END) {
				reached_end = 1;
				break;
			}
			if (zrc == Z_OK) {
				continue;
			}
			if (zrc == Z_BUF_ERROR) {
				/* No progress only if nothing written and no input left to feed. */
				if (have == 0 && left == 0 && strm.avail_in == 0) {
					inflateEnd(&strm);
					fclose(out);
					unlink(tmpl);
					set_err(err, err_len, "inflate incomplete (buf error)");
					return NULL;
				}
				continue;
			}
			inflateEnd(&strm);
			fclose(out);
			unlink(tmpl);
			set_err(err, err_len, "inflate failed");
			return NULL;
		}
		total_out = strm.total_out;
		inflateEnd(&strm);
		if (!reached_end) {
			fclose(out);
			unlink(tmpl);
			set_err(err, err_len, "inflate missing stream end");
			return NULL;
		}
		if (uncomp_size != 0 && total_out != (uLong)uncomp_size) {
			fclose(out);
			unlink(tmpl);
			set_err(err, err_len, "inflate size mismatch vs zip directory");
			return NULL;
		}
	} else {
		fclose(out);
		unlink(tmpl);
		set_err(err, err_len, "unsupported zip compression method");
		return NULL;
	}

	if (fflush(out) != 0 || fseek(out, 0, SEEK_SET) != 0) {
		fclose(out);
		unlink(tmpl);
		set_err(err, err_len, "temp rewind failed");
		return NULL;
	}
	*temp_path_out = strdup(tmpl);
	return out;
}


static int member_matches_logical(const char *name, size_t name_len, const char *logical) {
	/* logical like "/workout-routes/foo.gpx" or "workout-routes/foo.gpx" */
	const char *log = logical;
	if (log[0] == '/') {
		log++;
	}
	size_t llen = strlen(log);
	if (llen == 0 || name_len < llen) {
		return 0;
	}
	if (name_len == llen && strncmp(name, log, llen) == 0) {
		return 1;
	}
	/* suffix match: .../workout-routes/foo.gpx */
	if (name_len > llen && name[name_len - llen - 1] == '/' && strncmp(name + name_len - llen, log, llen) == 0) {
		return 1;
	}
	return 0;
}

static ah_xml_source *open_zip_matching(const char *path, int (*match)(const char *, size_t, const char *),
                                        const char *match_arg, char *err, size_t err_len) {
	FILE *fp = fopen(path, "rb");
	if (!fp) {
		set_err(err, err_len, "cannot open zip");
		return NULL;
	}
	zip_end_record eocd;
	if (find_end_of_central_dir(fp, &eocd) != 0) {
		fclose(fp);
		set_err(err, err_len, "not a zip or missing EOCD");
		return NULL;
	}
	if (fseek(fp, (long)eocd.cd_offset, SEEK_SET) != 0) {
		fclose(fp);
		set_err(err, err_len, "seek central directory failed");
		return NULL;
	}

	char *member_name = NULL;
	uint32_t local_off = 0;
	uint16_t method = 0;
	uint32_t comp_size = 0, uncomp_size = 0;
	int found = 0;

	for (uint16_t i = 0; i < eocd.cd_entries_total; i++) {
		zip_central_header ch;
		if (!read_fully(fp, &ch, sizeof(ch))) {
			fclose(fp);
			set_err(err, err_len, "read central header failed");
			return NULL;
		}
		if (ch.signature != 0x02014b50u) {
			fclose(fp);
			set_err(err, err_len, "bad central header signature");
			return NULL;
		}
		char *name = (char *)malloc((size_t)ch.name_len + 1);
		if (!name || !read_fully(fp, name, ch.name_len)) {
			free(name);
			fclose(fp);
			set_err(err, err_len, "read name failed");
			return NULL;
		}
		name[ch.name_len] = '\0';
		if (fseek(fp, ch.extra_len + ch.comment_len, SEEK_CUR) != 0) {
			free(name);
			fclose(fp);
			set_err(err, err_len, "skip extra failed");
			return NULL;
		}
		if (!found && match(name, ch.name_len, match_arg)) {
			found = 1;
			member_name = name;
			local_off = ch.local_header_offset;
			method = ch.method;
			comp_size = ch.comp_size;
			uncomp_size = ch.uncomp_size;
		} else {
			free(name);
		}
	}

	if (!found) {
		fclose(fp);
		set_err(err, err_len, "zip member not found");
		return NULL;
	}

	if (fseek(fp, (long)local_off, SEEK_SET) != 0) {
		free(member_name);
		fclose(fp);
		set_err(err, err_len, "seek local header failed");
		return NULL;
	}
	zip_local_header lh;
	if (!read_fully(fp, &lh, sizeof(lh)) || lh.signature != 0x04034b50u) {
		free(member_name);
		fclose(fp);
		set_err(err, err_len, "bad local header");
		return NULL;
	}
	if (fseek(fp, lh.name_len + lh.extra_len, SEEK_CUR) != 0) {
		free(member_name);
		fclose(fp);
		set_err(err, err_len, "skip local name/extra failed");
		return NULL;
	}
	if (lh.comp_size) {
		comp_size = lh.comp_size;
	}
	if (lh.uncomp_size) {
		uncomp_size = lh.uncomp_size;
	}
	if (lh.method) {
		method = lh.method;
	}
	if (comp_size == 0 && uncomp_size == 0) {
		free(member_name);
		fclose(fp);
		set_err(err, err_len, "zip member has zero sizes (missing central directory sizes)");
		return NULL;
	}

	char *temp_path = NULL;
	FILE *xml_fp = inflate_member_to_temp(fp, comp_size, uncomp_size, method, &temp_path, err, err_len);
	fclose(fp);
	if (!xml_fp) {
		free(member_name);
		return NULL;
	}

	ah_xml_source *src = (ah_xml_source *)calloc(1, sizeof(*src));
	if (!src) {
		fclose(xml_fp);
		if (temp_path) {
			unlink(temp_path);
			free(temp_path);
		}
		free(member_name);
		set_err(err, err_len, "oom");
		return NULL;
	}
	src->fp = xml_fp;
	src->owns_fp = 1;
	src->filename = member_name;
	src->temp_path = temp_path;
	return src;
}

static int match_export_xml(const char *name, size_t len, const char *arg) {
	(void)arg;
	return name_is_export_xml(name, len);
}

static int match_logical_path(const char *name, size_t len, const char *arg) {
	return member_matches_logical(name, len, arg);
}

static ah_xml_source *open_zip(const char *path, char *err, size_t err_len) {
	return open_zip_matching(path, match_export_xml, NULL, err, err_len);
}

static ah_xml_source *open_file(const char *path, char *err, size_t err_len) {
	FILE *fp = fopen(path, "rb");
	if (!fp) {
		set_err(err, err_len, "cannot open file");
		return NULL;
	}
	ah_xml_source *src = (ah_xml_source *)calloc(1, sizeof(*src));
	if (!src) {
		fclose(fp);
		set_err(err, err_len, "oom");
		return NULL;
	}
	src->fp = fp;
	src->owns_fp = 1;
	src->filename = strdup(path);
	return src;
}

ah_xml_source *ah_xml_source_open(const char *path, char *err, size_t err_len) {
	if (!path || !*path) {
		set_err(err, err_len, "empty path");
		return NULL;
	}
	if (path_is_dir(path)) {
		char buf[4096];
		snprintf(buf, sizeof(buf), "%s/export.xml", path);
		/* also try trailing slash already handled by snprintf */
		return open_file(buf, err, err_len);
	}
	if (ends_with_ci(path, ".zip")) {
		return open_zip(path, err, err_len);
	}
	return open_file(path, err, err_len);
}

FILE *ah_xml_source_file(ah_xml_source *src) {
	return src ? src->fp : NULL;
}

const char *ah_xml_source_filename(const ah_xml_source *src) {
	return src && src->filename ? src->filename : "";
}

void ah_xml_source_close(ah_xml_source *src) {
	if (!src) {
		return;
	}
	if (src->owns_fp && src->fp) {
		fclose(src->fp);
	}
	if (src->temp_path) {
		unlink(src->temp_path);
		free(src->temp_path);
	}
	free(src->filename);
	free(src);
}


ah_xml_source *ah_xml_source_open_member(const char *export_path, const char *logical_path, char *err,
                                         size_t err_len) {
	if (!export_path || !*export_path || !logical_path || !*logical_path) {
		set_err(err, err_len, "empty path");
		return NULL;
	}
	if (ends_with_ci(export_path, ".zip")) {
		return open_zip_matching(export_path, match_logical_path, logical_path, err, err_len);
	}

	/* Directory or export.xml: try several filesystem layouts. */
	char candidates[4][4096];
	int nc = 0;
	const char *log = logical_path[0] == '/' ? logical_path + 1 : logical_path;

	if (path_is_dir(export_path)) {
		snprintf(candidates[nc++], 4096, "%s/%s", export_path, log);
		snprintf(candidates[nc++], 4096, "%s/apple_health_export/%s", export_path, log);
		snprintf(candidates[nc++], 4096, "%s/workout-routes/%s", export_path,
		         (strrchr(log, '/') ? strrchr(log, '/') + 1 : log));
	} else {
		/* parent directory of file */
		char parent[4096];
		snprintf(parent, sizeof(parent), "%s", export_path);
		char *slash = strrchr(parent, '/');
		if (slash) {
			*slash = '\0';
		} else {
			snprintf(parent, sizeof(parent), ".");
		}
		snprintf(candidates[nc++], 4096, "%s/%s", parent, log);
		snprintf(candidates[nc++], 4096, "%s/apple_health_export/%s", parent, log);
		snprintf(candidates[nc++], 4096, "%s/workout-routes/%s", parent,
		         (strrchr(log, '/') ? strrchr(log, '/') + 1 : log));
		/* if export is .../apple_health_export/export.xml, parent already that folder */
		snprintf(candidates[nc++], 4096, "%s/%s", parent, (strrchr(log, '/') ? strrchr(log, '/') + 1 : log));
	}

	for (int i = 0; i < nc; i++) {
		FILE *fp = fopen(candidates[i], "rb");
		if (!fp) {
			continue;
		}
		fclose(fp);
		return open_file(candidates[i], err, err_len);
	}
	set_err(err, err_len, "gpx member/file not found");
	return NULL;
}

int ah_parse_health_path(const char *path, const ah_parse_callbacks *cb, ah_parse_stats *stats_out, char *err,
                         size_t err_len) {
	ah_xml_source *src = ah_xml_source_open(path, err, err_len);
	if (!src) {
		return 1;
	}
	int rc = ah_parse_xml_filep(ah_xml_source_file(src), cb, stats_out);
	ah_xml_source_close(src);
	if (rc != 0) {
		set_err(err, err_len, "xml parse failed");
	}
	return rc;
}
