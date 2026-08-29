# `duckdb-apple-health`

AppleHealth extension for DuckDB

A DuckDB extension that turns an Apple Health export (`export.zip` or `export.xml`) into SQL tables.

**Status:** early development. Targets the **DuckDB 2.0 stable C API** (preview / fall 2026). Not in the community repository yet. Load unsigned.

Data never leaves the process. This repository contains **no real Health exports**.

```sql
-- after a local unsigned load
FROM read_apple_health('~/Downloads/export.zip');

FROM read_apple_health(
  'export.zip',
  types := ['HeartRate', 'HKQuantityTypeIdentifierStepCount'],
  start := TIMESTAMPTZ '2026-01-01 00:00:00+10',
  "end" := TIMESTAMPTZ '2026-02-01 00:00:00+10'
);

FROM apple_health_workouts('export.zip');
FROM apple_health_activity_summaries('export.xml');
```

Then materialise once:

```sql
COPY (
  FROM read_apple_health('export.zip', types := ['HeartRate'])
) TO 'hr.parquet' (FORMAT parquet);
```

Raw XML is a scan. Parquet is the fast path. That is intentional.

## Why an extension

`webbed` already reads generic XML. `healthkit-to-sqlite` already converts an export to SQLite. This project exists for the missing piece: **HealthKit-aware, streaming, in-process SQL** with no Python ETL step.

- Accepts the zip the Health app actually produces
- Streams `export.xml` (multi-GB is normal)
- Types dates (`yyyy-MM-dd HH:mm:ss Z`) as `TIMESTAMPTZ`
- Splits numeric `value` from category `value_text` (sleep stages etc.)
- Stays on the stable C ABI so the binary is not rebuilt for every DuckDB patch

## Language

**C.** Parser and zip code have no DuckDB headers. Only the table-function file talks to the C API.

Thin C++ (the 2.0 `duckdb_cpp` wrapper only) is a fallback if the stable C table-function surface is incomplete in preview. It is not the default.

Python is used for fixtures and golden-table tests, not inside the extension. Rust and Mojo are out of scope.

## Requirements (Mac)

- Xcode CLT (`clang`, `make`, `cmake`)
- Python 3.12+ (template `make configure` + fixture scripts)
- DuckDB **2.0-dev / preview** CLI for load tests
- Optional: Ninja + ccache

```bash
xcode-select --install
brew install cmake python ninja ccache
```

## Build (local, unsigned)

The live tree will be initialised from [`duckdb/extension-template-c`](https://github.com/duckdb/extension-template-c). Until that is merged in, this repo is docs + fixtures only.

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
make configure
GEN=ninja make debug

# 2.0-dev CLI; allow unsigned community-style binaries
duckdb -unsigned
```

```sql
LOAD 'build/debug/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
```

Exact output paths follow the C-API template once it is vendored. See [DEV_PLAN.md](DEV_PLAN.md).

## v0.1 SQL API (frozen intent)

### `read_apple_health(path [, types, start, end, ignore_errors])`

| Column | Type | Notes |
|---|---|---|
| `type` | `VARCHAR` | Full HealthKit id |
| `type_short` | `VARCHAR` | Id with `HKQuantityTypeIdentifier` / `HKCategoryTypeIdentifier` / `HKDataType` prefix stripped when present |
| `unit` | `VARCHAR` | |
| `value` | `DOUBLE` | Null if `value` is not numeric |
| `value_text` | `VARCHAR` | Raw attribute when non-numeric (or always the raw string — see DEV_PLAN) |
| `start_date` | `TIMESTAMPTZ` | |
| `end_date` | `TIMESTAMPTZ` | |
| `creation_date` | `TIMESTAMPTZ` | |
| `source_name` | `VARCHAR` | |
| `source_version` | `VARCHAR` | |
| `device` | `VARCHAR` | Raw device string |
| `filename` | `VARCHAR` | Zip member or file path |

`path` may be a zip, a directory containing `export.xml`, or `export.xml` itself.

### `apple_health_workouts(path)`

Workout attributes: activity type, duration + unit, distance + unit, energy + unit, dates, source/device.

### `apple_health_activity_summaries(path)`

Daily rings. Tolerates both `appleMoveMinutes` (older exports) and `appleMoveTime` (iOS 14+).

### Not in v0.1

Workout routes / GPX, ECG files, `ClinicalRecord`, `Correlation` as a first-class table, Wasm, metadata exploded into columns.

## Privacy

- No telemetry
- No network I/O in the extension
- CI fixtures are hand-written XML with fictional values
- Do not commit a real `export.zip`

## Licence

Apache-2.0. Maintained by [DataBooth](https://www.databooth.com.au).

## Related

- Plan and blockers: [DEV_PLAN.md](DEV_PLAN.md)
- Personal stub (do not use): [`Mjboothaus/duckdb-ext-apple-health`](https://github.com/Mjboothaus/duckdb-ext-apple-health)
- C-API template: [`duckdb/extension-template-c`](https://github.com/duckdb/extension-template-c)
- Domain cousins: community `fit`, `webbed`; Dogsheep `healthkit-to-sqlite`

