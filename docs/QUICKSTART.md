# Quick start

**v0.1.1** — community install on macOS, or local unsigned build for developers.

## 1. Export from the Health app

On iPhone:

1. Health → profile → **Export All Health Data**
2. Copy the zip to the Mac (AirDrop, Files, etc.)
3. Optional: unzip — zip, directory, or `export.xml` all work

Multi-GB zips are normal. **Do not commit a real export to git.**

## 2. Install (community — preferred)

Needs DuckDB CLI **1.5.5+** on **macOS** (`osx_arm64` or `osx_amd64`).

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;
```

If install 404s, your DuckDB build is older than the published community artifacts — upgrade the CLI (Homebrew/`duckdb` releases) or use the local build path below.

## 3. Build locally (optional / developers)

Needs Xcode CLT, CMake, Python 3, and a DuckDB CLI that can load unsigned extensions.

```bash
git clone --recurse-submodules git@github.com:mjboothaus/duckdb-apple-health.git
cd duckdb-apple-health
brew install cmake ninja ccache just
just check-tools
just bootstrap   # configure (if needed) + debug + fixture
# or: just configure && just debug
```

```bash
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/healthkit_export/healthkit_export.duckdb_extension';
-- alternate path after debug:
-- LOAD 'build/debug/healthkit_export.duckdb_extension';
```

If `LOAD` cannot find the file:

```bash
find build -name '*.duckdb_extension'
```

## 4. Query

```sql
FROM read_healthkit_export('~/Downloads/export.zip');

FROM healthkit_workouts('export.zip');
FROM healthkit_workout_routes('export.zip');
FROM healthkit_workout_route_points('export.zip');
FROM healthkit_activity_summaries('export.zip');
```

Synthetic fixture (no PHI):

```bash
just fixture
just demo
just demo-workouts
just demo-routes
just demo-route-points
just demo-summaries
```

```sql
FROM read_healthkit_export('test/data/export.zip');
```

Named `types` / `start` / `end` filters are not in v0.1 yet — filter in SQL:

```sql
SELECT * FROM read_healthkit_export('export.zip')
WHERE type_short = 'HeartRate';
```

## 5. Materialise once (recommended for large exports)

```sql
COPY (
  SELECT *
  FROM read_healthkit_export('export.zip')
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
uv run marimo edit notebooks/map_walks.py   # walks / hikes GPS map
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

## Not in this release

Non-macOS community binaries, Wasm, ECG, clinical records, bind-time progress bar, named scan filters.

## If something fails

| Symptom | Check |
|---|---|
| Community `INSTALL` HTTP 404 | Upgrade to DuckDB **1.5.5+**; binaries are macOS-only today |
| `LOAD` refuses a local file | `duckdb -unsigned`; find the `.duckdb_extension` under `build/` |
| File not found (local build) | `find build -name '*.duckdb_extension'` |
| Slow / large RAM on big zip | Filter in SQL and `COPY` to Parquet; see [ROADMAP.md](ROADMAP.md) |
| Dates look shifted | Offsets like `+1100` must be honoured (they are in v0.1) |
| Tests fail | `just debug` then `just pytest-ext` |

More detail: [DESIGN.md](DESIGN.md), [RELEASE_NOTES.md](RELEASE_NOTES.md).
