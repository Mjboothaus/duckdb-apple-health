# Quick start

**v0.1.0-beta** — local unsigned build of the Apple Health scanner.

## 1. Export from the Health app

On iPhone:

1. Health → profile → **Export All Health Data**
2. Copy the zip to the Mac (AirDrop, Files, etc.)
3. Optional: unzip — zip, directory, or `export.xml` all work

Multi-GB zips are normal. **Do not commit a real export to git.**

## 2. Build the extension

Needs Xcode CLT, CMake, Python 3, and a DuckDB CLI that can load unsigned extensions (1.5+ works in testing; 2.0 is the target).

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
brew install cmake ninja ccache just
just check-tools
just bootstrap   # configure (if needed) + debug + fixture
# or: just configure && just debug
```

## 3. Load unsigned

```bash
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
-- alternate path after debug:
-- LOAD 'build/debug/apple_health.duckdb_extension';
```

If `LOAD` cannot find the file:

```bash
find build -name '*.duckdb_extension'
```

`justfile` variables `ext_debug` / `ext_release` should match these paths.

## 4. Query

```sql
FROM read_apple_health('~/Downloads/export.zip');

FROM apple_health_workouts('export.zip');
FROM apple_health_workout_routes('export.zip');
FROM apple_health_activity_summaries('export.zip');
```

Synthetic fixture (no PHI):

```bash
just fixture
just demo
just demo-workouts
just demo-routes
just demo-summaries
```

```sql
FROM read_apple_health('test/data/export.zip');
```

Named `types` / `start` / `end` filters are not in v0.1 yet — filter in SQL:

```sql
SELECT * FROM read_apple_health('export.zip')
WHERE type_short = 'HeartRate';
```

## 5. Materialise once (recommended for large exports)

```sql
COPY (
  SELECT *
  FROM read_apple_health('export.zip')
  WHERE type_short = 'HeartRate'
) TO 'hr.parquet' (FORMAT parquet);

SELECT date_trunc('day', start_date) AS day, avg(value)
FROM 'hr.parquet'
GROUP BY 1
ORDER BY 1;
```

v0.1 parses in bind and can use a lot of RAM on multi-GB XML. Parquet is the fast path for repeat analytics.

## 6. Tests

```bash
just pytest-ext
```

## 7. Optional notebook

```bash
uv sync
uv run marimo edit notebooks/explore_export.py
```

## What you will see

| Column | Meaning |
|---|---|
| `type` | Full HealthKit id |
| `type_short` | e.g. `HeartRate` |
| `unit` | e.g. `count/min` |
| `value` | Number, or null for categories |
| `value_text` | Category string when `value` is null |
| `start_date` / `end_date` | `TIMESTAMPTZ` |
| `source_name` / `device` | App or Watch string |

## Privacy

The extension only reads a path you pass in. No network, no telemetry. Keep real exports off GitHub and out of CI logs.

## Not in this beta

Community `INSTALL`, Wasm, GPX track points, ECG, clinical records, bind-time progress bar, named scan filters.

## If something fails

| Symptom | Check |
|---|---|
| `LOAD` refuses the file | `duckdb -unsigned`; find the `.duckdb_extension` under `build/` |
| File not found | `find build -name '*.duckdb_extension'` |
| Slow / large RAM on big zip | Filter in SQL and `COPY` to Parquet; see [ROADMAP.md](ROADMAP.md) |
| Dates look shifted | Offsets like `+1100` must be honoured (they are in v0.1) |
| Tests fail | `just debug` then `just pytest-ext` |

More detail: [DESIGN.md](DESIGN.md), [RELEASE_NOTES.md](RELEASE_NOTES.md).
