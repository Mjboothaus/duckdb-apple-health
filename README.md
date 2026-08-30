# duckdb-apple-health

**v0.1.0-beta** (developer preview) — Apple Health exports → DuckDB SQL, in-process.

A DuckDB **scanner** extension that turns an Apple Health `export.zip` / `export.xml` into typed tables. Written in **C** on the **stable C API**. Load **unsigned** (not in the community repository yet).

Data never leaves the process. This repository contains **no real Health exports**.

```sql
-- duckdb -unsigned
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';

FROM read_apple_health('~/Downloads/export.zip');
FROM apple_health_workouts('export.zip');
FROM apple_health_activity_summaries('export.xml');
```

Materialise once, then query Parquet (the fast path):

```sql
COPY (
  SELECT *
  FROM read_apple_health('export.zip')
  WHERE type_short = 'HeartRate'
) TO 'hr.parquet' (FORMAT parquet);
```

> Raw XML is a scan. Parquet is the fast path. That is intentional.

## Why an extension

`webbed` reads generic XML. `healthkit-to-sqlite` batch-converts to SQLite. This project fills the gap: **HealthKit-aware, streaming, in-process SQL** with no Python ETL step.

- Accepts the zip the Health app produces
- Streams `export.xml` (multi-GB is normal)
- Types dates (`yyyy-MM-dd HH:mm:ss Z`) as `TIMESTAMPTZ`
- Splits numeric `value` from category `value_text` (sleep stages, etc.)
- Stable C ABI so the binary is not rebuilt for every DuckDB patch

## Status (beta)

| | |
|---|---|
| Version | **v0.1.0-beta** |
| Install | Local unsigned `LOAD` only |
| Platforms proven | macOS Apple Silicon (`osx_arm64`) |
| DuckDB | Tested with **1.5.x** unsigned C-API load; **2.0** is the strategic target ([ROADMAP.md](ROADMAP.md)) |
| Correctness | Fixture golden + pytest vs `healthkit-to-sqlite` (top-level record semantics) |
| Limits | Parse currently buffers in bind (RAM ∝ export size); named `types`/`start`/`end` filters not shipped yet |

See [RELEASE_NOTES.md](RELEASE_NOTES.md) and [ROADMAP.md](ROADMAP.md).

## Language

**C.** Parser and zip code have no DuckDB headers. Only the table-function / entrypoint files talk to the C API.

Python is for fixtures, pytest, and an optional marimo notebook — not inside the extension.

## Requirements (Mac)

- Xcode CLT (`clang`, `make`, `cmake`)
- Python 3.12+ (`uv` recommended for tests/notebook)
- DuckDB CLI on `PATH` (1.5+ with unsigned extensions; 2.0 when available)
- Optional: Ninja, ccache, [just](https://github.com/casey/just)

```bash
xcode-select --install
brew install cmake python ninja ccache just
```

## Build (local, unsigned)

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
just bootstrap   # or: just configure && just debug
```

Extension binary (either path works after debug):

```text
build/debug/extension/apple_health/apple_health.duckdb_extension
build/debug/apple_health.duckdb_extension
```

```bash
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
```

Full walkthrough: [QUICKSTART.md](QUICKSTART.md).

## v0.1 SQL API

### `read_apple_health(path)` — **implemented**

| Column | Type | Notes |
|---|---|---|
| `type` | `VARCHAR` | Full HealthKit id |
| `type_short` | `VARCHAR` | Prefix stripped when present |
| `unit` | `VARCHAR` | |
| `value` | `DOUBLE` | Null if not numeric |
| `value_text` | `VARCHAR` | Category string when `value` is null |
| `start_date` / `end_date` / `creation_date` | `TIMESTAMPTZ` | |
| `source_name` / `source_version` / `device` | `VARCHAR` | |
| `filename` | `VARCHAR` | Zip member or file path |

`path` may be a zip, a directory containing `export.xml`, or `export.xml` itself.

Named parameters `types` / `start` / `end` / `ignore_errors` are **planned** (filter in SQL for now).

### `apple_health_workouts(path)` — **implemented**

Activity type, duration, distance, energy, dates, source/device.

### `apple_health_workout_routes(path)` — **implemented**

Route metadata + `gpx_path` (`FileReference`) with parent workout type/dates for joins. ### `apple_health_workout_route_points(path)` — **implemented**

GPX `trkpt` rows: lat/lon/ele/time, optional speed/course/h_acc/v_acc, joined to parent workout via route metadata.

### `apple_health_activity_summaries(path)` — **implemented**

Daily rings. Both `appleMoveMinutes*` (older) and `appleMoveTime*` (iOS 14+) as nullable columns.

### Not in v0.1

ECG, `ClinicalRecord`, Correlation as a table, Wasm, community `INSTALL`, Watch/iPhone dedupe.

**Semantics:** top-level `<Record>` only — nested Correlation children are skipped (see [DESIGN.md](DESIGN.md) and tests).

## Tests

```bash
just debug          # extension binary
just pytest-ext     # fixture golden + healthkit-to-sqlite compare
```

Optional real export (path stays outside the repo):

```bash
just pytest-ext-real export_zip=/path/to/export.zip
```

## Explore (optional)

```bash
uv sync
uv run marimo edit notebooks/explore_export.py
# walks / hikes map (GPS):
uv run marimo edit notebooks/map_walks.py
# or: just map-walks
```

## Privacy

- No telemetry and no network I/O in the extension
- CI/fixtures use synthetic XML only
- Do not commit a real `export.zip`

## Licence

Apache-2.0. Maintained by [DataBooth](https://www.databooth.com.au).

## Related

- Quick start: [QUICKSTART.md](QUICKSTART.md)
- Design & rules: [DESIGN.md](DESIGN.md)
- Roadmap (v0.2 + DuckDB 2.0): [ROADMAP.md](ROADMAP.md)
- Release notes / changelog: [RELEASE_NOTES.md](RELEASE_NOTES.md), [CHANGELOG.md](CHANGELOG.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)
- C-API template: [`duckdb/extension-template-c`](https://github.com/duckdb/extension-template-c)
- Cousins: community `fit`, `webbed`; Dogsheep `healthkit-to-sqlite`
