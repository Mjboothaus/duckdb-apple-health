# From Health export to SQL: building a DuckDB scanner in C

*DataBooth · August 2026 · Australian English*

Apple’s Health app will cheerfully hand you a multi‑gigabyte `export.zip`. Getting that into a place where you can ask ordinary SQL questions — without a Python ETL job, without shipping PHI to a warehouse, and without rebuilding an extension for every DuckDB patch — is still awkward.

This post is the build diary for [`DataBooth/duckdb-apple-health`](https://github.com/DataBooth/duckdb-apple-health): a **DuckDB scanner** that turns `export.zip` / `export.xml` into typed tables, written in **C** against the **stable C API**.

> Raw XML is a scan. Parquet is the fast path. That is intentional.

## The gap

- **`webbed`** reads generic XML.
- **`healthkit-to-sqlite`** batch‑converts an export to SQLite.
- What we wanted: **HealthKit‑aware, streaming, in‑process SQL**.

No MCP server. No dashboard. No dbt package. A scanner.

## Bets we locked early

| Bet | Choice |
|---|---|
| Language | **C** — parser and zip code never `#include` DuckDB headers |
| ABI | DuckDB **stable C API** only (`USE_UNSTABLE_C_API=0`) |
| Load path | **Unsigned** until 2.0 GA + community C‑API CI |
| Out of v0.1 | Wasm, routes/GPX, ECG, clinical records, community `INSTALL` |

Privacy was a design constraint from day one: synthetic fixtures only in git, no network I/O in the extension, no real exports in CI.

## Docs and fixtures before extension C

The first useful commit was not C. It was product docs, an implementation brief with **hard gates**, a cross‑platform `justfile`, and `scripts/make_fixture.py`: heart rate, steps, sleep categories, Sydney/`-0800` offsets, a non‑ASCII source name (`Café Run Club`), blood pressure both top‑level and nested under `Correlation`, one running workout, and activity summaries covering both legacy `appleMoveMinutes*` and iOS 14+ `appleMoveTime*`.

Golden table: **7** top‑level records. Nested correlation children must not double‑count.

## Gate diary (one day on a Mac)

### Gate 0 — machine

Toolchain was fine (clang, cmake, ninja, ccache, Python). Two mundane failures:

1. `just 1.49` rejected `if path_exists(x) { … }` — `path_exists` returns the **strings** `"true"`/`"false"`, so you need `== "true"`.
2. DuckDB on PATH was **1.5.2**, not 2.0‑dev.

We fixed the justfile, forced LF golden CSVs, and deferred 2.0‑dev until load tests mattered.

### Gate 1–2 — vendor template, unsigned load

Vendored [`duckdb/extension-template-c`](https://github.com/duckdb/extension-template-c) as extension id `apple_health` without destroying product docs. `just configure` + `just debug` produced:

`build/debug/extension/apple_health/apple_health.duckdb_extension`

Surprise relative to the brief: **DuckDB 1.5.2 loaded the unsigned C‑API binary** and ran the sample scalar. `-unsigned` was required (signature missing otherwise). Template metadata still pins `TARGET_DUCKDB_VERSION=v1.2.0` / `C_STRUCT` ABI.

### Gate 3 — table function spike

The stable C API **does** expose `duckdb_create_table_function` / bind / init / emit. A hardcoded `read_apple_health(path)` emitting three rows proved registration without enabling unstable APIs. Gate 3a (bail to parser‑only) was avoided.

### Gate 4 — streaming parser, no DuckDB

`src/parse_health.c` is a zero‑dependency streaming tag scanner (no libxml2 DOM, no expat/yxml vendor). Attribute‑centric Health XML is a good fit: find `<…>`, parse attributes, track `Correlation` depth so nested `<Record>`s are skipped.

CLI: `make parse_health_cli` → `build/debug/parse_health`. Matched golden CSV exactly: 7 records, sleep `value_text`, Café intact, `skipped_nested_records=2`.

### Gate 5 — zip / directory / file

`src/zip_source.c` opens:

- `.zip` → member ending in `export.xml` (fixture: `apple_health_export/export.xml`) via a minimal central‑directory reader + zlib raw DEFLATE
- directory → `export.xml` inside
- bare `.xml` → file

Same 7 golden rows from all three path shapes.

### Gate 6 — wire the scanner

Replaced the hardcoded spike. Bind opens the path, streams records, emits v0.1 columns including **`TIMESTAMP WITH TIME ZONE`** (Apple offsets honoured), numeric/`value_text` split, and zip member `filename`.

```text
just demo  → 7 rows from test/data/export.zip
typeof(start_date) = TIMESTAMP WITH TIME ZONE
```

### Gate 7 — workouts and rings

- `apple_health_workouts(path)` — activity, duration, distance, energy, dates, source/device
- `apple_health_activity_summaries(path)` — nullable columns for **both** move‑minutes and move‑time eras

Fixture: one Running workout; two summary days (2020 legacy attrs + 2026 iOS 14+ attrs).

## Reality check: a real Health zip

Against a personal export kept **outside** the repo (~269 MiB zip, ~1.97 GiB `export.xml` uncompressed):

| Metric | Value |
|---|---:|
| `read_apple_health` rows | **4,305,469** |
| workouts | **1,681** |
| activity summary days | **2,713** |

Top types were the usual suspects (ActiveEnergyBurned, BasalEnergyBurned, DistanceWalkingRunning, HeartRate, StepCount, …). No row‑level PHI left the machine; we only kept aggregates.

**Honest performance note:** v0.1 parses in **bind** and buffers rows. Memory scales with export size; re‑querying re‑scans the zip. The intended workflow is still: filter once, **`COPY` to Parquet**, then iterate. Streaming chunk emit and named `types`/`start`/`end` parameters are the obvious next cuts.

## Explore it

```bash
just debug
uv sync
uv run marimo edit notebooks/explore_export.py   # metrics
just build-db export_zip=/path/to/export.zip
just map-walks                                 # walks/hikes map from local DB
```

`explore_export` loads the unsigned extension, times inventory / type histogram / workouts / rings, materialises selected `type_short` values to gitignored `output/*.parquet`, and plots daily averages from Parquet (the fast path).

## What v0.1 is — and is not

**Is:** local unsigned `LOAD`, zip/xml/dir paths, records + workouts + activity summaries, TIMESTAMPTZ dates, synthetic fixtures, Apache‑2.0.

**Is not:** community `INSTALL`, Wasm, ECG, clinical records, Watch/iPhone dedupe, or a promise that 1.5.x remains the forever target.



## After v0.1: workouts, GPS, and a local database

The scanner grew a **workouts + GPS** stack:

- `apple_health_workouts` — summaries  
- `apple_health_workout_routes` — `gpx_path` index  
- `apple_health_workout_route_points` — track points from companion GPX members  

Re-scanning a multi‑GB zip on every map click is the wrong loop. The practical architecture is:

```text
export.zip  →  just build-db  →  output/apple_health.duckdb  →  just map-walks
```

The DuckDB file holds clear tables (`workouts`, `routes`, `route_points`, `route_points_map`) rather than a confusing set of similarly named Parquet files. Parquet remains an **optional export**, not the default store.

Two notebooks stay separate on purpose:

| Notebook | Job |
|---|---|
| `explore_export.py` | Records, rings, type charts, metric Parquet |
| `map_walks.py` | Select walks/hikes and draw GPS from the **local DB** |

Data model diagrams: [`docs/ERD.md`](../docs/ERD.md). Progressive multi-export options (full rebuild vs append-by-`gpx_path`): [`docs/ROADMAP.md`](../docs/ROADMAP.md).

On one personal export, walks/hikes alone were on the order of **~1.3k workouts**, **~1.3k routes**, and **~6M** raw track points — hence a downsampled `route_points_map` layer for plotting.

## Credits and links

- Repo: [DataBooth/duckdb-apple-health](https://github.com/DataBooth/duckdb-apple-health)
- C‑API template: [duckdb/extension-template-c](https://github.com/duckdb/extension-template-c)
- Implementation gates: `docs/DESIGN.md`
- Data model: `docs/ERD.md`
- Roadmap (incl. multi-export DB options): `docs/ROADMAP.md`

Built gate‑by‑gate on a MacBook (Apple Silicon) in one focused day — mostly because the brief refused to let us skip evidence.
