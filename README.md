# duckdb-apple-health

**v0.2.0** — Health app / HealthKit `export.zip` → DuckDB SQL, in-process.

DuckDB **scanner** extension **`healthkit_export`**: reads exports produced by the Apple Health app (HealthKit `export.zip` / `export.xml`) as typed tables. Written in **C** on the **stable C API**. Community publish on **macOS** (DuckDB **1.5.5+**) is being updated to this name — see [CREATE_COMM_EXT.md](docs/CREATE_COMM_EXT.md).

> **Not affiliated with, endorsed by, or sponsored by Apple Inc.** Apple, Apple Health, and HealthKit are trademarks of Apple Inc.

Data never leaves the process. This repository contains **no real Health exports**.

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;

FROM read_healthkit_export('~/Downloads/export.zip');
FROM healthkit_workouts('export.zip');
FROM healthkit_activity_summaries('export.xml');
```

Materialise once, then query Parquet (the fast path):

```sql
COPY (
  SELECT *
  FROM read_healthkit_export('export.zip')
  WHERE type_short = 'HeartRate'
) TO 'hr.parquet' (FORMAT parquet);
```

> **Raw XML is a scan. Parquet (or the local DuckDB file) is the fast path. That is intentional.**

### What that means

Health app exports are large attribute-centric XML (often multi‑GB once unzipped). Reading them with a table function is a **full scan**: CPU and memory scale with how much of the export you touch, and **re-running the same `SELECT` re-scans** unless you materialise.

The design is therefore two-stage:

1. **Scan once** (extension) — filter in SQL if you can, accept that the first pass is the expensive one.
2. **Materialise** — `COPY … TO '….parquet'` and/or `just build-db` → `output/apple_health.duckdb`, then iterate in milliseconds on columnar storage.

v0.1 still parses largely in **bind** and can buffer rows (RAM roughly tracks export size for a full load). That is a known limit, not the end state — see [Performance](#performance-real-exports) and [ROADMAP.md](docs/ROADMAP.md).

## Why an extension (and how we relate to cousins)

Two excellent projects already sit near this problem — they are **not** wrong; they solve different jobs:

| Project | What it does well | How we differ |
|---------|-------------------|---------------|
| **[webbed](https://github.com/teaguesterling/duckdb_webbed)** ([community docs](https://duckdb.org/community_extensions/extensions/webbed.html)) | General **XML/HTML** in DuckDB: XPath, schema inference, SAX streaming for large markup | We are **HealthKit-shaped**: typed Health records/workouts/routes/GPX, Apple date offsets, zip layout the Health app emits — not a general XML toolkit |
| **[healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite)** (Dogsheep / Datasette) | **Batch convert** an export zip → SQLite file you explore offline (progress bar, great personal-analytics story) | We stay **in-process in DuckDB**: `LOAD` + SQL table functions, optional Parquet/`build-db`, no separate Python ETL step required for the scan itself |

This project fills the gap between those: **HealthKit-aware, in-process SQL** aimed at technical Apple users who already live in DuckDB (see [PERSONA.md](docs/PERSONA.md)).

- Accepts the zip the Health app produces
- Parses `export.xml` (multi-GB is normal) via a C scanner on the **stable C API**
- Types dates (`yyyy-MM-dd HH:mm:ss Z`) as `TIMESTAMPTZ`
- Splits numeric `value` from category `value_text` (sleep stages, etc.)
- Stable C ABI so the binary is not rebuilt for every DuckDB patch
- Optional **Python add-ons** (local DB, maps, Photos, journeys) — not required to unlock data in SQL

## Status (v0.2.0)

| | |
|---|---|
| Extension name | **`healthkit_export`** (renamed from short-lived `apple_health` community id) |
| Version | **v0.2.0** |
| Install | **`INSTALL healthkit_export FROM community`** on **macOS** once the rename listing lands; until then use a local unsigned build |
| First community listing | [PR #2653](https://github.com/duckdb/community-extensions/pull/2653) published **`apple_health`** briefly — **use `healthkit_export` going forward** |
| Platforms | Community target: **macOS only** for now |
| DuckDB | Host **1.5.5+**; local unsigned builds for development |
| Correctness | SQLLogic + fixture golden + pytest vs `healthkit-to-sqlite` (top-level records) |
| Limits | Parse buffers in bind (RAM ∝ export size); named `types`/`start`/`end` filters not shipped yet |

See [RELEASE_NOTES.md](docs/RELEASE_NOTES.md) and [ROADMAP.md](docs/ROADMAP.md).

## Language and packaging

**C (core).** Parser and zip code have no DuckDB headers. Only the table-function / entrypoint files talk to the C API. Versioning: root [`VERSION`](VERSION) + git tags → extension metadata ([VERSIONING.md](docs/VERSIONING.md)).

**Python (supplementary package, optional).** Installable as **`health-data-store`** (`import health_data_store`) under `python/health_data_store/`. Base: local DuckDB store, journeys, places, Photos via `ATTACH`. Extras: `maps`, `notebooks`, `dev`, `all` — see [PYTHON_PACKAGE.md](docs/PYTHON_PACKAGE.md). Not required to `LOAD` the extension. Not mixed into the C binary. v0.1 does not require PyPI publish.

## Requirements (Mac)

**To use the community extension only:** DuckDB CLI **1.5.5+** (or matching Python `duckdb` wheel) on macOS — no local C build required.

**To build from source / run tests:**

- Xcode CLT (`clang`, `make`, `cmake`)
- Python 3.12+ (`uv` recommended for tests/notebook)
- DuckDB CLI on `PATH` (1.5.5+ preferred; unsigned load for local binaries)
- Optional: Ninja, ccache, [just](https://github.com/casey/just)

```bash
xcode-select --install
brew install cmake python ninja ccache just
```

## Install (community — preferred)

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;
FROM read_healthkit_export('test/data/export.zip');  -- or your export.zip
```

Requires DuckDB **1.5.5+** on **macOS**. Older CLI builds (e.g. 1.5.2) will 404 on the community CDN until you upgrade.

## Build (local, unsigned — developers)

```bash
git clone --recurse-submodules git@github.com:mjboothaus/duckdb-apple-health.git
cd duckdb-apple-health
just bootstrap   # or: just configure && just debug
```

```bash
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/healthkit_export/healthkit_export.duckdb_extension';
FROM read_healthkit_export('test/data/export.zip');
```

Full walkthrough: [QUICKSTART.md](docs/QUICKSTART.md).

## SQL API

### `read_healthkit_export(path)` — **implemented**

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

### `healthkit_workouts(path)` — **implemented**

Activity type, duration, distance, energy, dates, source/device.

### `healthkit_workout_routes(path)` — **implemented**

Route metadata + `gpx_path` (`FileReference`) with parent workout type/dates for joins.

### `healthkit_workout_route_points(path)` — **implemented**

GPX `trkpt` rows: lat/lon/ele/time, optional speed/course/h_acc/v_acc, joined to parent workout via route metadata.

### `healthkit_activity_summaries(path)` — **implemented**

Daily rings. Both `appleMoveMinutes*` (older) and `appleMoveTime*` (iOS 14+) as nullable columns.

### Not in v0.1.x core

ECG as a first-class table, Correlation as a table, Wasm, non-macOS community binaries, Watch/iPhone dedupe, named `types`/`start`/`end` pushdown, streaming execute.

**Semantics:** top-level `<Record>` only — nested Correlation children are skipped (see [DESIGN.md](docs/DESIGN.md) and tests).

**Optional add-ons** (same repo, not required to use the extension): local DuckDB via `just build-db`, maps/photos/journeys — see [PYTHON_PACKAGE.md](docs/PYTHON_PACKAGE.md).

## Tests

```bash
just debug          # extension binary
just pytest-ext     # fixture golden + healthkit-to-sqlite compare
```

Optional real export (path stays outside the repo):

```bash
just pytest-ext-real export_zip=/path/to/export.zip
```

## Optional add-ons (not the extension)

**You do not need this section to use the C extension.** Community `INSTALL` / `LOAD` is enough for SQL.

Same repo, separate tooling: Python helpers that build a **local DuckDB file** from your export, then optional maps, multi-day journeys, and Photos matching. Package: **`health-data-store`** ([PYTHON_PACKAGE.md](docs/PYTHON_PACKAGE.md)). Suggested path for going further: [PERSONA.md](docs/PERSONA.md).

| Step | Command | What it does |
|------|---------|----------------|
| Dev env | `just uv-sync` | Install Python extras (`maps`, `notebooks`, …) |
| Local DB | `just build-db export_zip=/path/to/export.zip` | Scan once → `output/apple_health.duckdb` (gitignored) |
| List walks | `just list-walks 20` | SQL over the local DB (no marimo) |
| Metrics notebook | `just explore` | marimo over fixture or a path you set |
| Map walks | `just map-walks` | Folium map of walks/hikes (experimental UI) |
| Journey stories | `just walk-stories` | Multi-day journeys + map app view (experimental) |

```bash
just uv-sync
just build-db export_zip=/path/to/export.zip   # keep the zip outside the repo
just list-walks 20
just walk-stories    # app view; edit mode: just walk-stories-edit
```

Privacy: real exports, Photos library access, and `output/` stay local — never commit them.


## Performance (real exports)

**Expectation for v0.1:** the **first full scan** of a real export is the slow, memory-heavy step. After you materialise (Parquet and/or `just build-db`), day-to-day queries should be fast.

Illustrative offline smoke on one personal export kept **outside** git (~270 MiB zip, ~2 GiB uncompressed `export.xml`):

| Metric | Order of magnitude |
|--------|--------------------|
| `read_healthkit_export` rows | ~**4.3 million** top-level records |
| Workouts | ~**1.7k** |
| Activity summary days | ~**2.7k** |
| Walking/Hiking GPS (when built into local DB) | ~**1.3k** routes, millions of track points |

Wall-clock and peak RAM depend on machine, disk, and whether you pull **all** records vs filtered `COPY`, and whether you also ingest **all** GPX points. Full GPS `build-db` is typically **minutes**, not seconds, on a large multi-year export.

**Optimisation opportunities (not all shipped):** streaming execute (emit chunks without buffering the whole bind), streaming zip inflate, named `types`/`start`/`end` pushdown, string interning, incremental DB append by `gpx_path`. Tracked in [ROADMAP.md](docs/ROADMAP.md).

**Recommended workflow:** scan → filter → Parquet and/or local DuckDB → analytics/maps. Do not loop `FROM read_healthkit_export(huge.zip)` in a notebook cell.

## Privacy

- No telemetry and no network I/O in the extension
- CI/fixtures use synthetic XML only
- Do not commit a real `export.zip`

## Licence

Apache-2.0. Maintained by [mjboothaus](https://github.com/mjboothaus).

## Related

- Docs index: [docs/README.md](docs/README.md)
- Quick start: [QUICKSTART.md](docs/QUICKSTART.md)
- Design & rules: [DESIGN.md](docs/DESIGN.md)
- Data model (ERD / local DB): [docs/ERD.md](docs/ERD.md)
- Roadmap (v0.2 + DuckDB 2.0): [ROADMAP.md](docs/ROADMAP.md)
- Release notes / changelog: [RELEASE_NOTES.md](docs/RELEASE_NOTES.md), [CHANGELOG.md](CHANGELOG.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)
- C-API template: [`duckdb/extension-template-c`](https://github.com/duckdb/extension-template-c)
- Cousins (different jobs, complementary): [webbed](https://github.com/teaguesterling/duckdb_webbed) (XML/HTML in DuckDB), [healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite) (export → SQLite); community `fit` for FIT files
