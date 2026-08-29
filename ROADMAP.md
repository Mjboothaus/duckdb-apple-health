# Roadmap

Working plan for `DataBooth/duckdb-apple-health` after **v0.1**.
Decisions here should stay aligned with `DESIGN.md`.

Last updated: 2026-08-29.

## North star

A **fast, local, privacy-preserving DuckDB scanner** for Apple Health exports:

```text
export.zip | export.xml | export-dir
        → stream parse (bounded memory)
        → typed DataChunks
        → SQL / COPY Parquet
```

Unsigned load today. **DuckDB 2.0** stable C API + community packaging when the platform is ready.

## Shipped (v0.1)

- C extension on the stable C API (`USE_UNSTABLE_C_API=0`)
- `read_apple_health(path)` — records with TIMESTAMPTZ, value / value_text split
- `apple_health_workouts(path)` / `apple_health_activity_summaries(path)`
- Path shapes: `.zip` (member `**/export.xml`), directory, bare XML
- Synthetic fixtures + golden CSV; pytest vs golden and `healthkit-to-sqlite`
- Marimo explore notebook (timing + Parquet materialise)
- Real-export smoke: multi-million-row zip loads and agrees with pull-parser **top-level** record semantics

Known v0.1 limits (honest):

- Parse runs in **bind** and buffers rows (RAM ∝ export size; re-query re-scans)
- Zip member fully inflated to a temp file before parse
- No named `types` / `start` / `end` filters yet (filter in SQL or `COPY`)
- No first-class progress bar during bind
- Nested `Correlation` / `Record` children intentionally skipped (same samples usually appear top-level)

## Near term — v0.1.x (correctness & ergonomics)

1. **Zip inflate completeness** — **done** (this cycle): require `Z_STREAM_END` + central-directory sizes for data-descriptor members; real `export.zip` matches bare `export.xml` (HRV −2 gap closed).  
2. **justfile uplift** — **done**: `just bootstrap`; `ensure-ext` so demos/`pytest-ext` build debug when missing; `demo-real export_zip=…`; refreshed header comments. Makefile remains source of truth for CMake/metadata.  
3. **Streaming execute** — open/parse in the table-function body, emit ~vector-size chunks; stop buffering the full export in bind  
4. **Streaming zip inflate** — feed zlib directly into the XML scanner (no full temp `export.xml` when avoidable); only after completeness tests are solid  
5. **Named parameters** — `types`, `start`, `end`, `ignore_errors` on `read_apple_health`  
6. **CLI / notebook progress** — bytes read + row counters (client-side); interrupt-friendly once parse is in execute  
7. **Projection pushdown** — skip unused columns when the SELECT list is narrow  
8. **Broader correctness** — optional real-export pytest (`APPLE_HEALTH_EXPORT_ZIP`); document Correlation vs `healthkit-to-sqlite` clearly in README  

## Product focus — workouts & GPS (priority track)

Personal / product priority after zip correctness. Real exports already carry routes as companion GPX, not inline coordinates in `export.xml`.

**Observed shape (typical full export):**

- `apple_health_workouts` today: summary attributes only (type, duration, distance, energy, dates, source/device) — **no GPS**
- Nested under `<Workout>`: `WorkoutEvent`, `WorkoutStatistics`, `MetadataEntry`
- `WorkoutRoute` + `FileReference path="/workout-routes/route_….gpx"` (often ~1 route per outdoor workout)
- Zip members: `apple_health_export/workout-routes/*.gpx` with `<trkpt lat lon>`, `ele`, `time`, extensions (`speed`, `course`, `hAcc`, `vAcc`)

**Suggested PR sequence (GPS track):**

1. **Route index** — **done**: `apple_health_workout_routes(path)`: route metadata + `gpx_path` / zip member; stable join key to parent workout (start/end/source or synthetic id). Fixture with one tiny GPX.  
2. **Track points** — `apple_health_workout_route_points(path)` (or named param on routes): stream GPX `trkpt` → `lat`, `lon`, `ele`, `time` TIMESTAMPTZ, optional speed/course/accuracy; zip multi-member open.  
3. **Workout enrichments** — optional `apple_health_workout_events` / statistics tables; keep opt-in so summary scan stays cheap.  
4. **Ergonomics** — join examples in QUICKSTART; `COPY` routes/points to Parquet; document privacy (precise location).

**Non-goals for early GPS PRs:** map UI, live HealthKit, silent Watch/iPhone dedupe, loading every GPX when the user only asked for workout summaries.

## Medium term — v0.2 (performance product)

1. String interning for repeated `type` / `source_name` / `unit`  
2. Store Apple dates as micros once at parse time (no string re-parse at emit)  
3. Single-scan session option (records + workouts + summaries without triple inflate)  
4. Release binaries for `osx_arm64` (and later `osx_amd64` / `linux_amd64`) with clear unsigned install docs  
5. SQLLogic coverage expanded beyond template + smoke  

Target user story:

```sql
COPY (
  FROM read_apple_health('export.zip', types := ['HeartRate', 'StepCount'])
) TO 'activity.parquet' (FORMAT parquet);
-- subsequent analytics hit Parquet in milliseconds
```

```sql
-- GPS track (planned): summaries ⋈ route points
SELECT w.activity_type_short, p.time, p.lat, p.lon
FROM apple_health_workouts('export.zip') w
JOIN apple_health_workout_route_points('export.zip') p USING (/* join key TBD */);
```

## DuckDB 2.0 extension framework

v0.1 already **bets on** the stable C API path that 2.0 is standardising (`extension-template-c`, `duckdb_extension.h`, unsigned community-style load).

When **DuckDB 2.0 GA** (and community C-API CI) lands, we intend to:

| Work item | Intent |
|---|---|
| Pin / refresh `duckdb_capi` headers | Track 2.0 stable ABI, not nightlies ad hoc |
| Community extension descriptor | `description.yml` / `INSTALL apple_health FROM community` when CI supports C-API extensions |
| Drop “preview only” messaging | QUICKSTART assumes 2.0 CLI; keep unsigned fallback documented until signing is automatic |
| Optional thin C++ | Only if 2.0 stable table-function C surface regresses; parser/zip stay C |
| CI matrix | `osx_arm64`, `linux_amd64` (Wasm still out unless requested) |

**Non-goals still:** unstable C++ `duckdb.hpp` template as the default; requiring a full DuckDB rebuild to develop the scanner.

Until 2.0 community install works, distribution remains:

```bash
just debug
duckdb -unsigned -c "LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension'; …"
```

## Later / v0.3+ (opt-in)

- ECG / clinical records (explicit opt-in; privacy review)
- Deduping Watch vs iPhone double counts (analytics policy, not silent)
- Wasm / `excluded_platforms` only if there is demand
- Python wheel wrapping the extension (fixtures stay Python; runtime stays C)

Workout routes / GPX moved up to **Product focus — workouts & GPS** (no longer “someday only”).

## Explicitly out of scope

- Telemetry or network I/O inside the extension  
- Shipping real Health exports in git or CI  
- MCP / Streamlit / dbt packages as core deliverables  
- Live HealthKit / Health Auto Export sync  

## Success metrics

| Signal | v0.1 | v0.2 aim |
|---|---|---|
| Fixture golden + HK compare | pass | pass |
| Real export top-level counts vs pull-parser | agree | agree |
| Peak RAM on ~2 GB `export.xml` | full buffer | O(chunk) |
| HeartRate slice → Parquet | works | filters in scanner; much less CPU |
| Install | unsigned local | community `INSTALL` on 2.0 when available |

## Feedback

Issues and PRs: [DataBooth/duckdb-apple-health](https://github.com/DataBooth/duckdb-apple-health).
