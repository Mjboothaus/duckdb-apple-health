# Quick start

End-user path once a local unsigned build exists.  
**Today (2026-08-29):** the repo has docs, fixtures, and a `justfile`. There is not yet a loadable `.duckdb_extension`. Come back to this file after `just debug` works.

## 1. Export from the Health app

On iPhone:

1. Health → profile picture → **Export All Health Data**
2. AirDrop or copy the zip to the Mac
3. Optional: unzip. Either the zip or `export.xml` is fine

The zip is often several GB. That is normal.

Do not commit a real export to git.

## 2. Build the extension (developer preview)

Needs DuckDB **2.0-dev / preview**, Xcode CLT, CMake, Python 3.

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
brew install cmake ninja ccache just
just check-tools
just configure
just debug
```

Load **unsigned**. Community install is not available yet.

```bash
duckdb -unsigned
```

```sql
LOAD 'build/debug/apple_health.duckdb_extension';
-- if LOAD cannot find that path, search:
--   find build -name '*.duckdb_extension'
```

Update the path if the C-API template writes a different location. `justfile` variables `ext_debug` / `ext_release` should match reality.

## 3. Query

```sql
-- zip from the Health app, or unzipped xml, or a directory containing export.xml
FROM read_apple_health('~/Downloads/export.zip');

FROM read_apple_health(
  'export.zip',
  types := ['HeartRate', 'StepCount'],
  start := TIMESTAMPTZ '2026-01-01 00:00:00+11',
  "end" := TIMESTAMPTZ '2026-02-01 00:00:00+11'
);

FROM apple_health_workouts('export.zip');
FROM apple_health_activity_summaries('export.zip');
```

Synthetic data for smoke tests (no PHI):

```bash
just fixture
```

```sql
FROM read_apple_health('test/data/export.zip');
```

## 4. Materialise once

Raw XML is a single-thread scan. After the first filter, write Parquet:

```sql
COPY (
  FROM read_apple_health('export.zip', types := ['HeartRate'])
) TO 'hr.parquet' (FORMAT parquet);

SELECT date_trunc('day', start_date) AS day, avg(value)
FROM 'hr.parquet'
GROUP BY 1
ORDER BY 1;
```

## 5. What you will see

| Column | Meaning |
|---|---|
| `type` | Full HealthKit id (`HKQuantityTypeIdentifierHeartRate`) |
| `type_short` | `HeartRate` |
| `unit` | e.g. `count/min` |
| `value` | Number, or null for categories |
| `value_text` | Category string when `value` is null (sleep stages, etc.) |
| `start_date` / `end_date` | `TIMESTAMPTZ` from `yyyy-MM-dd HH:mm:ss Z` |
| `source_name` / `device` | App or Watch string |

Sleep and other categories live in `value_text`, not `value`. `avg(value)` on a mixed scan will ignore those rows.

## Privacy

The extension only reads a path you pass in. No network, no telemetry. Keep real exports off GitHub and out of CI logs.

## Not in v0.1

Workout GPS routes, ECG files, clinical records, `INSTALL apple_health FROM community`, Wasm.

## If something fails

| Symptom | Check |
|---|---|
| `LOAD` refuses the file | Use `duckdb -unsigned` and a 2.0-dev CLI, not 1.5.x |
| File not found | `find build -name '*.duckdb_extension'` |
| Query hangs on a 5 GB zip | Add `types` and/or `start`/`end`, then `COPY` to Parquet |
| Dates look shifted | Offsets in the export are like `+1100`; parser must honour them |
| `just configure` missing Makefile | C-API template is not vendored yet — see `IMPLEMENTATION_BRIEF.md` |
