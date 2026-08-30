#include "parse_gpx.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void copy_str(char *dst, size_t dst_len, const char *src) {
	if (!dst || dst_len == 0) {
		return;
	}
	if (!src) {
		dst[0] = '\0';
		return;
	}
	snprintf(dst, dst_len, "%s", src);
}

static int days_from_civil(int y, unsigned m, unsigned d) {
	y -= m <= 2;
	const int era = (y >= 0 ? y : y - 399) / 400;
	const unsigned yoe = (unsigned)(y - era * 400);
	const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
	const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
	return (int)(era * 146097 + (int)doe - 719468);
}

bool ah_parse_gpx_time(const char *text, int64_t *utc_micros_out) {
	if (!text || !utc_micros_out) {
		return false;
	}
	int y = 0, mo = 0, d = 0, h = 0, mi = 0, s = 0;
	/* 2021-12-21T05:20:35Z  or with fractional seconds */
	char tz = 'Z';
	int off_h = 0, off_m = 0;
	int n = sscanf(text, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &s);
	if (n < 6) {
		return false;
	}
	const char *p = strchr(text, 'T');
	if (!p) {
		return false;
	}
	/* skip to after seconds */
	p = strchr(p, ':');
	if (!p) {
		return false;
	}
	p = strchr(p + 1, ':');
	if (!p) {
		return false;
	}
	p += 1;
	while (*p && (isdigit((unsigned char)*p) || *p == '.')) {
		p++;
	}
	if (*p == 'Z' || *p == 'z') {
		tz = 'Z';
	} else if (*p == '+' || *p == '-') {
		tz = *p;
		if (sscanf(p + 1, "%d:%d", &off_h, &off_m) < 1) {
			if (sscanf(p + 1, "%2d%2d", &off_h, &off_m) < 1) {
				return false;
			}
		}
		if (tz == '-') {
			off_h = -off_h;
			off_m = -off_m;
		}
	} else if (*p != '\0') {
		return false;
	}
	int64_t days = days_from_civil(y, (unsigned)mo, (unsigned)d);
	int64_t secs = days * 86400LL + h * 3600LL + mi * 60LL + s;
	if (tz != 'Z') {
		secs -= (int64_t)off_h * 3600LL + (int64_t)off_m * 60LL;
	}
	*utc_micros_out = secs * 1000000LL;
	return true;
}

static double attr_double(const char *tag, size_t len, const char *key, int *ok) {
	*ok = 0;
	char pat[64];
	snprintf(pat, sizeof(pat), "%s=\"", key);
	size_t plen = strlen(pat);
	for (size_t i = 0; i + plen < len; i++) {
		if (memcmp(tag + i, pat, plen) == 0) {
			const char *v = tag + i + plen;
			char *end = NULL;
			double d = strtod(v, &end);
			if (end != v) {
				*ok = 1;
				return d;
			}
			return 0.0;
		}
	}
	return 0.0;
}

/* Extract text content of first child element named elname inside span [start,end). */
static int child_text(const char *buf, size_t start, size_t end, const char *elname, char *out, size_t out_len) {
	if (!out || out_len == 0) {
		return 0;
	}
	out[0] = '\0';
	char open[64];
	snprintf(open, sizeof(open), "<%s>", elname);
	char open2[64];
	snprintf(open2, sizeof(open2), "<%s ", elname);
	char close[64];
	snprintf(close, sizeof(close), "</%s>", elname);
	size_t open_len = strlen(open);
	size_t close_len = strlen(close);
	for (size_t i = start; i + open_len < end; i++) {
		int hit = 0;
		size_t ol = 0;
		if (i + open_len <= end && memcmp(buf + i, open, open_len) == 0) {
			hit = 1;
			ol = open_len;
		} else if (i + strlen(open2) <= end && memcmp(buf + i, open2, strlen(open2)) == 0) {
			/* skip to > */
			const char *gt = memchr(buf + i, '>', end - i);
			if (!gt) {
				return 0;
			}
			hit = 1;
			ol = (size_t)(gt - (buf + i) + 1);
		}
		if (!hit) {
			continue;
		}
		size_t content = i + ol;
		const char *cpos = NULL;
		for (size_t j = content; j + close_len <= end; j++) {
			if (memcmp(buf + j, close, close_len) == 0) {
				cpos = buf + j;
				break;
			}
		}
		if (!cpos) {
			return 0;
		}
		size_t n = (size_t)(cpos - (buf + content));
		if (n >= out_len) {
			n = out_len - 1;
		}
		memcpy(out, buf + content, n);
		out[n] = '\0';
		/* trim */
		char *a = out;
		while (*a && isspace((unsigned char)*a)) {
			a++;
		}
		if (a != out) {
			memmove(out, a, strlen(a) + 1);
		}
		size_t L = strlen(out);
		while (L > 0 && isspace((unsigned char)out[L - 1])) {
			out[--L] = '\0';
		}
		return 1;
	}
	return 0;
}

static int child_double(const char *buf, size_t start, size_t end, const char *elname, double *out) {
	char tmp[64];
	if (!child_text(buf, start, end, elname, tmp, sizeof(tmp))) {
		return 0;
	}
	char *e = NULL;
	double d = strtod(tmp, &e);
	if (e == tmp) {
		return 0;
	}
	*out = d;
	return 1;
}

typedef struct {
	const ah_gpx_callbacks *cb;
	ah_gpx_stats stats;
	ah_gpx_point base; /* path + parent workout */
	int64_t index;
} gpx_parser;

static void emit_trkpt(gpx_parser *P, const char *open_tag, size_t open_len, const char *inner, size_t inner_len) {
	int ok_lat = 0, ok_lon = 0;
	double lat = attr_double(open_tag, open_len, "lat", &ok_lat);
	double lon = attr_double(open_tag, open_len, "lon", &ok_lon);
	if (!ok_lat || !ok_lon) {
		return;
	}
	ah_gpx_point row = P->base;
	row.point_index = P->index++;
	row.lat = lat;
	row.lon = lon;
	double v;
	if (child_double(inner, 0, inner_len, "ele", &v)) {
		row.has_ele = true;
		row.ele = v;
	}
	char tbuf[64];
	if (child_text(inner, 0, inner_len, "time", tbuf, sizeof(tbuf))) {
		copy_str(row.time_iso, sizeof(row.time_iso), tbuf);
	}
	/* extensions may nest speed/course/hAcc/vAcc */
	if (child_double(inner, 0, inner_len, "speed", &v)) {
		row.has_speed = true;
		row.speed = v;
	}
	if (child_double(inner, 0, inner_len, "course", &v)) {
		row.has_course = true;
		row.course = v;
	}
	if (child_double(inner, 0, inner_len, "hAcc", &v)) {
		row.has_h_acc = true;
		row.h_acc = v;
	}
	if (child_double(inner, 0, inner_len, "vAcc", &v)) {
		row.has_v_acc = true;
		row.v_acc = v;
	}
	if (P->cb && P->cb->on_point) {
		P->cb->on_point(&row, P->cb->userdata);
	}
	P->stats.points++;
}

int ah_parse_gpx_filep(FILE *fp, const ah_workout_route *route_meta, const char *gpx_member,
                       const ah_gpx_callbacks *cb, ah_gpx_stats *stats_out) {
	gpx_parser P;
	memset(&P, 0, sizeof(P));
	P.cb = cb;
	if (route_meta) {
		copy_str(P.base.gpx_path, sizeof(P.base.gpx_path), route_meta->gpx_path);
		copy_str(P.base.workout_activity_type, sizeof(P.base.workout_activity_type), route_meta->workout_activity_type);
		copy_str(P.base.workout_activity_type_short, sizeof(P.base.workout_activity_type_short),
		         route_meta->workout_activity_type_short);
		copy_str(P.base.workout_start_date, sizeof(P.base.workout_start_date), route_meta->workout_start_date);
		copy_str(P.base.workout_end_date, sizeof(P.base.workout_end_date), route_meta->workout_end_date);
	}
	copy_str(P.base.gpx_member, sizeof(P.base.gpx_member), gpx_member ? gpx_member : "");

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
			/* find <trkpt */
			char *lt = NULL;
			for (size_t j = i; j + 6 < len; j++) {
				if (buf[j] == '<' && (j + 6 <= len) &&
				    (memcmp(buf + j + 1, "trkpt", 5) == 0 ||
				     (j + 9 <= len && memcmp(buf + j + 1, "gpx:trkpt", 9) == 0))) {
					lt = buf + j;
					break;
				}
			}
			if (!lt) {
				/* keep tail for incomplete tag */
				if (len - i > 64) {
					memmove(buf, buf + len - 64, 64);
					len = 64;
				} else if (i > 0) {
					memmove(buf, buf + i, len - i);
					len -= i;
				}
				break;
			}
			size_t start = (size_t)(lt - buf);
			/* find end of open tag > */
			char *gt = memchr(buf + start, '>', len - start);
			if (!gt) {
				if (start > 0) {
					memmove(buf, buf + start, len - start);
					len -= start;
				}
				break;
			}
			size_t open_end = (size_t)(gt - buf);
			int self_closing = 0;
			if (open_end > start && buf[open_end - 1] == '/') {
				self_closing = 1;
			}
			if (self_closing) {
				emit_trkpt(&P, buf + start, open_end - start + 1, "", 0);
				i = open_end + 1;
				continue;
			}
			/* find </trkpt> */
			const char *close1 = "</trkpt>";
			const char *close2 = "</gpx:trkpt>";
			char *cl = NULL;
			for (size_t j = open_end + 1; j + 8 <= len; j++) {
				if (memcmp(buf + j, close1, 8) == 0) {
					cl = buf + j;
					break;
				}
				if (j + 12 <= len && memcmp(buf + j, close2, 12) == 0) {
					cl = buf + j;
					break;
				}
			}
			if (!cl) {
				if (start > 0) {
					memmove(buf, buf + start, len - start);
					len -= start;
				}
				break;
			}
			size_t close_at = (size_t)(cl - buf);
			size_t close_len = (cl[2] == 'g') ? 12 : 8;
			emit_trkpt(&P, buf + start, open_end - start + 1, buf + open_end + 1, close_at - (open_end + 1));
			i = close_at + close_len;
			if (i > (1 << 14) && i < len) {
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
