# Release notes

## v0.1.0-beta — 2026-08-29

First public **developer beta** (`v0.1.0-beta`) of `duckdb-apple-health`: a DuckDB **scanner** for Apple Health exports, written in **C** on the **stable C API**.

### Highlights

- **`read_apple_health(path)`** — stream HealthKit `Record` rows into SQL  
  - Columns: `type`, `type_short`, `unit`, `value`, `value_text`, `start_date`, `end_date`, `creation_date`, `source_name`, `source_version`, `device`, `filename`  
  - Dates as **`TIMESTAMPTZ`** (Apple `yyyy-MM-dd HH:mm:ss Z` offsets honoured)  
  - Numeric vs category split (`value` / `value_text`)
- **`apple_health_workouts(path)`** — activity type, duration, distance, energy, dates, source/device  
- **`apple_health_activity_summaries(path)`** — daily rings; both legacy `appleMoveMinutes*` and iOS 14+ `appleMoveTime*`  
- **Paths:** `.zip` (member ending in `export.xml`), directory containing `export.xml`, or bare XML  
- **Local only:** no network I/O, no telemetry; synthetic fixtures in-repo (no real exports in git)  
- **Load:** unsigned `.duckdb_extension` (not on community `INSTALL` yet)

### Build & try

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
just configure && just debug
just demo
just demo-workouts
just demo-summaries
```

```sql
-- duckdb -unsigned
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
```

Explore interactively (optional):

```bash
uv sync
uv run marimo edit notebooks/explore_export.py
```

### Correctness

- Fixture **golden CSV** (7 top-level records) matched by CLI and extension  
- **pytest** suite: smoke/golden + comparison to [`healthkit-to-sqlite`](https://github.com/dogsheep/healthkit-to-sqlite)  
- **Semantic note:** we emit **top-level** `<Record>` only; `healthkit-to-sqlite` also counts `Record` children of `<Correlation>`. Tests document the +2 nested BP rows on the fixture.  
- Manual real-export smoke (offline): multi-million-row zip, workouts and activity summaries load; keep personal zips outside the repo  
- **Post-beta zip fix (unreleased):** complete DEFLATE inflate for data-descriptor zips so `.zip` and bare `export.xml` agree on record counts (see [CHANGELOG.md](../CHANGELOG.md) / [ROADMAP.md](ROADMAP.md)).  

```bash
just pytest-ext
# optional:
# just pytest-ext-real export_zip=/path/to/export.zip
```

### Performance (preview honesty)

v0.1 parses in **bind** and buffers rows; zip members are inflated to a temp file first. Fine for fixtures and one-shot `COPY` to Parquet; heavy for repeated full scans of multi-GB exports. **Parquet after first filter is the intended fast path.** Streaming execute + filter pushdown are on the [roadmap](ROADMAP.md).

### Not in v0.1

- `INSTALL apple_health FROM community`  
- Named `types` / `start` / `end` parameters  
- Workout GPS routes, ECG, clinical records  
- Wasm  
- Progress bar inside DuckDB bind  
- Watch vs iPhone dedupe  

### Compatibility

- Developed/tested on **macOS Apple Silicon** (`osx_arm64`)  
- DuckDB **1.5.x** CLI loaded the unsigned C-API binary in testing; **2.0** remains the strategic target (see [ROADMAP.md](ROADMAP.md))  
- Template metadata still pins extension API **v1.2.0** / `C_STRUCT` via `extension-template-c`  

### Licence

Apache-2.0 — [DataBooth](https://www.databooth.com.au)

### Links

- Repository: https://github.com/DataBooth/duckdb-apple-health  
- Build diary: [archive/BLOG_POST.md](../archive/BLOG_POST.md)  
- Roadmap (incl. DuckDB 2.0 community install): [ROADMAP.md](ROADMAP.md)
- Changelog: [CHANGELOG.md](../CHANGELOG.md)  
