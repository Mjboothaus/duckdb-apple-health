# Blog progress — duckdb-apple-health

Working notes toward a final `BLOG_POST.md`. Not polished copy yet.
Updated as gates land. Australian English for narrative; code/identifiers stay as-is.

---

## Angle (draft)

Building a DuckDB **scanner** for Apple Health exports in **C**, on the **2.0 stable C API**, so multi-GB `export.zip` files become SQL without a Python ETL step — and without locking the extension to unstable C++ internals.

Why this exists: `webbed` is generic XML; `healthkit-to-sqlite` is a batch convert. The gap is HealthKit-aware, streaming, in-process SQL.

---

## Snapshot — 2026-08-29 (repo intake)

### What the tree actually is

- Public early-stage repo: docs, `justfile`, fixture generator, synthetic Health XML/CSV.
- **No** C sources, **no** `Makefile` from `extension-template-c`, **no** `.duckdb_extension` yet.
- Intent is frozen in `docs/DESIGN.md` (gated steps 0–8) and `docs/DESIGN.md`.

### Locked product bets (from docs)

| Bet | Choice |
|---|---|
| Language | C (parser/zip free of DuckDB headers) |
| ABI | DuckDB 2.0 stable C API only |
| Load path | Unsigned until 2.0 GA + community C-API CI |
| Out of v0.1.0 core | Wasm, ECG table, community INSTALL (doc path ready) |

### Fixture design (already good story material)

`scripts/make_fixture.py` writes fictional data only:

- HR + steps (numeric), sleep category (non-numeric `value_text`)
- `+1100` (Sydney) and `-0800` date offsets
- Non-ASCII source name (`Café Run Club`)
- Blood pressure both as top-level `Record`s **and** inside a `Correlation` (parser must not double-count)
- One running workout; two activity summaries (old `appleMoveMinutes*` vs new `appleMoveTime*`)
- Zip layout: `apple_health_export/export.xml` (matches real Health app layout)
- Golden: **7** top-level records in `test/data/golden/records.csv`

### Machine check (pre–Gate 0 formal run)

| Tool | Result |
|---|---|
| Host | macOS, Apple Silicon expected |
| `duckdb` on PATH | **v1.5.2** (`/opt/homebrew/bin/duckdb`) — **not** 2.0-dev |
| Fixture files | `export.xml` + golden CSV present; **`export.zip` missing** until `just fixture` runs |
| `just` recipes | **Broken today**: `justfile` line 23 uses brace `if` syntax the installed `just` rejects |
| Template | Not vendored (`Makefile` absent; `.gitignore` even ignores root `Makefile`) |

### Narrative hooks so far

1. **Docs-first bootstrap** — product, plan, quickstart, and gated implementation brief before a single line of extension C.
2. **Privacy as a design constraint** — synthetic fixtures, no real exports in git, no network/telemetry in the extension.
3. **ABI patience** — bet on 2.0 stable C API; accept unsigned load and a possible “parser CLI first” fallback if table functions are not ready.
4. **Immediate friction is mundane** — wrong DuckDB major on PATH, `just` dialect mismatch, zip not generated until the recipe works. Good reminder that “early stage” means glue as much as architecture.

### Decisions (author, 2026-08-29)

| Topic | Choice |
|---|---|
| DuckDB 2.0 | Compile against template on 1.5 first; install 2.0-dev before Gate 2 load |
| justfile | Fix now for portable Mac/Windows/Linux |
| Pace | Gate-by-gate from Step 0 leftovers into Step 1 |
| Git | Feature branch + PR per brief commit guidance |
| Blog | `BLOG_PROGRESS.md` only until the end; then `BLOG_POST.md` |

---

## Gate log

| Gate | Status | Evidence / notes |
|---|---|---|
| 0 Confirm machine | **Pass (with known gap)** | Tools OK; `just check-tools` + `just fixture` work after justfile fix; DuckDB still **1.5.2** (2.0-dev deferred to Gate 2) |
| 1 Vendor template | **Pass** | PR #2; Makefile, duckdb_capi/, src sample, extension-ci-tools @ ef15a2a; EXT_NAME=apple_health |
| 2 Unsigned load | **Pass on 1.5.2** | Built + loaded unsigned; path matches justfile; 2.0-dev still planned for later ABI work |
| 3 TF spike | **Pass (3b)** | Stable C API table functions work; 3 hardcoded rows via `read_apple_health` |
| 4 Parser CLI | **Pass** | 7 top-level records; sleep value_text; Café; nested Correlation skipped (2) |
| 5 Zip source | **Pass** | zip/dir/xml all yield 7 golden records via CLI |
| 6 Wire TF | **Pass** | just demo → 7 rows from zip; TIMESTAMPTZ; value_text; filename member |
| 7 Workouts / summaries | **Pass** | 1 Running workout; 2 activity summaries (old minutes + new move time) |
| 8 Docs pass | Not started | |

### Gate 0 evidence

```text
== tools ==
Python 3.14.4
cmake version 4.3.1
Apple clang version 17.0.0
just 1.49.0
v1.5.2 (Variegata)   # DuckDB — not yet 2.0-dev
ninja: 1.13.2
ccache: 4.13.3
template Makefile: NOT YET

just fixture → 7 records, 1 workout, 2 activity summaries
+ test/data/export.zip
```

justfile bug: `if path_exists(x)` is invalid; must be `if path_exists(x) == "true"` (path_exists returns strings).

---

## Chronology (append-only)

### 2026-08-29 — Intake

- Cloned / pulled `mjboothaus/duckdb-apple-health` on `main` (`f31dcad`).
- Read `docs/DESIGN.md`, `README.md`, `docs/DESIGN.md`, `QUICKSTART.md`, `justfile`, `scripts/make_fixture.py`.
- Confirmed fixture semantics vs golden CSV (7 records).
- Started this progressive record for a later `BLOG_POST.md`.

### 2026-08-29 — Gate 0 + author decisions

- Fixed justfile `path_exists` comparison; fixture CSV forced to LF.
- Committed synthetic `export.zip`.
- Branch workflow: feature branch + PR.
- Next: vendor `extension-template-c` as `apple_health` (Step 1).

---

## Draft outline for final post

1. The gap: Health export → SQL without leaving the process  
2. Why a scanner, not a warehouse  
3. Betting on DuckDB 2.0 stable C API (and what we refused to do)  
4. Fixtures before code (and why PHI never enters the repo)  
5. Gate-by-gate build diary (unsigned load → hardcoded TF → SAX parser → zip → real scan)  
6. What broke on day one (toolchain, justfile, 1.5 vs 2.0)  
7. What v0.1 does and deliberately does not  
8. Next: community install when the platform catches up  

---

## Snippets / quotes to reuse

- From README: “Raw XML is a scan. Parquet is the fast path. That is intentional.”
- From brief: “Parser and zip code must not `#include` DuckDB headers.”
- From docs/DESIGN.md: peak memory = one XML element + one output chunk.

### 2026-08-29 — Step 1 vendor extension-template-c

- Cloned `duckdb/extension-template-c` with submodules.
- Copied Makefile, CMakeLists, duckdb_capi, sample src, test/sql, CI workflow.
- Added `extension-ci-tools` submodule @ ef15a2a (v1.5 line).
- Renamed extension id `capi_quack` → `apple_health` (kept `src/capi_quack.c` filename for now).
- Stopped ignoring root `Makefile` in `.gitignore`.
- `USE_UNSTABLE_C_API` remains 0.
- Template pins `TARGET_DUCKDB_VERSION=v1.2.0`; CI workflow references DuckDB v1.5.4 / variegata tools — note for Gate 2 / 2.0-dev story.

### 2026-08-29 — Gate 2 unsigned load

- `just configure` OK (venv + duckdb 1.5.5 wheel + sqllogictest).
- `just debug` OK → `build/debug/extension/apple_health/apple_health.duckdb_extension` (also `build/debug/apple_health.duckdb_extension`).
- Metadata: `C_STRUCT` ABI, duckdb_version **v1.2.0** (template TARGET), platform **osx_arm64**, extension_version git short hash.
- Load:

```text
duckdb --version
v1.5.2 (Variegata)

duckdb -unsigned -c "LOAD '.../apple_health.duckdb_extension'; SELECT multiply_numbers_together(1, 2);"
→ 2

without -unsigned → IO Error: signature missing/invalid, unsigned disabled
```

- justfile `ext_debug` path already correct — no path fix commit needed.
- Surprise relative to brief: **1.5.2 CLI loads this C-API extension**. 2.0-dev still wanted for the stable-TF / long-term ABI story, but Gate 2 is green on the machine today.

### 2026-08-29 — Gate 3 hardcoded table function

- Stable C API **does** expose `duckdb_create_table_function` / bind / init / emit (Gate 3a avoided).
- Added `src/apple_health_tf.c` + header; wired from entrypoint; CMake sources updated.
- Spike ignores `path`, emits 3 rows: HeartRate 72, StepCount 1234, SleepAnalysis value NULL.
- `start_date` is `TIMESTAMP` (UTC micros for 2026-01-15 06:30+11).

```text
duckdb -unsigned -c "LOAD '...'; FROM read_apple_health('ignored');"
→ 3 rows, exit 0
count(*) = 3, count(value) = 2
```

- No `USE_UNSTABLE_C_API`. Next: Step 4 streaming parser (no DuckDB headers).

### 2026-08-29 — Gate 4 streaming parser

- Zero-dep streaming tag scanner in `src/parse_health.c` (no DuckDB, no libxml2 DOM, no expat/yxml).
- CLI `build/debug/parse_health` via `make parse_health_cli` / `just parse-cli`.
- Top-level `<Record>` only; Correlation children skipped (`skipped_nested_records=2`).
- Workouts + activity summaries parsed into structs (callbacks ready for Gate 7).
- Golden CSV match (7 rows); sleep non-numeric → empty value + value_text; `Café Run Club` intact.
- `parse_health.c` also linked into the extension library for later TF wiring (still unused by TF).

```text
records=7 workouts=1 activity_summaries=2 skipped_nested_records=2
diff golden == empty
```

### 2026-08-29 — Gate 5 zip source

- `src/zip_source.c` / `.h`: path may be `.zip`, directory, or xml file.
- Minimal ZIP reader (central directory + local header) + zlib raw DEFLATE.
- Fixture member `apple_health_export/export.xml` found via `**/export.xml` match.
- Inflates to a temp file, then reuses `ah_parse_xml_filep`.
- CLI now calls `ah_parse_health_path` for all path kinds.

```text
parse_health test/data/export.xml  → 7 records (golden)
parse_health test/data/export.zip  → 7 records (golden)
parse_health test/data             → 7 records (golden)
```

### 2026-08-29 — Gate 6 wire TF

- Replaced hardcoded spike with real scan: bind opens path via `zip_source`, streams `parse_health`, buffers records, emits v0.1 columns.
- `start_date` / `end_date` / `creation_date` as `TIMESTAMP WITH TIME ZONE` (Apple offsets honoured).
- `just demo` against `test/data/export.zip` → 7 rows; sleep has NULL value + value_text; Café source; filename `apple_health_export/export.xml`.

```text
count(*) = 7, count(value) = 6
typeof(start_date) = TIMESTAMP WITH TIME ZONE
```

### 2026-08-29 — Gate 7 workouts and activity summaries

- `apple_health_workouts(path)` and `apple_health_activity_summaries(path)`.
- SQLLogic stubs under `test/sql/workouts.test` and `activity_summaries.test`.
- Fixture: one Running workout (25 min, 4.2 km, 280 kcal).
- Summaries: 2020-06-01 has `apple_move_minutes=32` (move_time NULL); 2026-01-15 has `apple_move_time=41` (move_minutes NULL).

```text
just demo-workouts  → Running | 25 | 4.2 | 280
just demo-summaries → two rows with old/new move attrs
```

---

## Chronology (continued)

### 2026-08-30 — GPS product + local DB

- Workout routes + route points table functions; real-export smoke on multi‑million points.
- `just build-db` → `output/apple_health.duckdb` (workouts / routes / route_points / route_points_map).
- Marimo `map_walks` (DB-only); docs under `docs/` (ERD, ROADMAP progressive-export options).
- Naming: prefer “local database” over “lake”.

### 2026-08-31 — Helper extraction + places

- PR **#18**: `python/apple_health_data/` (`HealthDataStore`, Folium maps, free tiles); thin UI notebook; `build_health_db` CLI wrapper.
- Taller map (default ~820px); start/end place reverse-geocode (Nominatim + cache).
- PR **#19**: materialise `route_places` in DuckDB; `just geocode-places`; `list-walks` joins places.

### 2026-09-05 — Photos.sqlite preprocess + walk stories direction

- DuckDB **`ATTACH` Photos.sqlite** (read-only) works; ~200k `ZASSET` rows; join to `routes` on time window is fast vs full osxphotos library open.
- Cocoa date offset (`+ 978307200`) required for correct `taken_at`.
- Derivatives JPEGs under `resources/derivatives/` are good map thumbs (originals often HEIC / iCloud-off-machine).
- In progress on `feat/walk-stories-photos`: `photos.py`, `just photos-for-walks`, `walk_photos` table, Folium photo layer — toward an elegant marimo walk-stories app (map + filmstrip).
- Parallel: DuckDB 2.0-alpha build notes (parseable metadata version; absolute LOAD paths); keep stable default pin for day-to-day.

### Blog angle update

Still a **scanner** story — but the sequel is **local product loop**: export → DB → places → photos → map, all offline, helpers testable without marimo.

## v0.1.0 core freeze (2026-09-06)

- SQLLogic 3/3 PASS; pytest-ext 17 passed / 1 skipped
- TF surface includes routes + route_points
- Docs: RELEASE_NOTES v0.1.0, CREATE_COMM_EXT, README status bump
- Tag `v0.1.0` pending push after this release PR lands on main
