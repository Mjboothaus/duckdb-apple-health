# Development plan

Working document for `DataBooth/duckdb-apple-health`.
Decisions in this file override older notes in chat.

Last updated: 2026-08-29.

## Goal

A DuckDB **scanner** for Apple Health exports:

```text
export.zip | export.xml | export-dir
        → stream parse
        → typed DataChunks
        → SQL
```

Not a warehouse, MCP server, dashboard, or dbt package.

## Locked decisions

| Topic | Decision |
|---|---|
| GitHub | New public repo `DataBooth/duckdb-apple-health` (option 2). Do not continue `Mjboothaus/duckdb-ext-apple-health` |
| Licence | Apache-2.0 |
| Language | **C.** Thin C++ only if the 2.0 stable table-function C API is unusable |
| ABI | Stable C API. No `#include <duckdb.hpp>`, no unstable extension internals |
| DuckDB target | 2.0-dev / preview now; 2.0 GA in **fall 2026** (October is a planning assumption, not a calendar commitment) |
| Community `INSTALL FROM community` | After 2.0 GA + community C-API CI. Until then: unsigned `LOAD` |
| Interim publish | 2.0 custom signed repo if community CI still requires the old C++ template |
| Dev machine | MacBook (Apple Silicon). Native `osx_arm64` first |
| Wasm | Out of v0.1 (`excluded_platforms` later if needed) |
| Parser deps | Streaming XML (`expat` or `yxml`) + zip (`minizip-ng` via vcpkg if the template uses it). No libxml2 |
| Python | Fixtures + golden tables only (`scripts/`) |

## Why C, not thin C++ (default)

For this scanner the C++ wrapper does not buy much:

- Output is flat rows, not object graphs
- SAX callbacks are C-shaped already
- The ABI bet is “talk to DuckDB only through `duckdb_extension.h` / v2 C API”
- C++ advantage appears only if registering table functions in C is painfully verbose

Revisit after the week-1 spike (below). If bind/init/chunk-emit in C is a wall of macros, switch **only** the `*_tf.c` file to the stable C++ wrapper. Leave `parse_health.c` as C.

## Architecture

```text
path
  ├─ zip  → member export.xml
  ├─ dir  → export.xml
  └─ xml  → file
        │
        ▼
 parse_health.c     SAX, dates, type_short, value vs value_text
        │
        ▼
 apple_health_tf.c  DuckDB C API table functions only
```

Rules:

1. Peak memory = one XML element + one output chunk (~2–8k rows).
2. Unknown attributes are ignored (export DTD drifts by iOS version).
3. `Correlation` child `Record`s also appear top-level — emit records only, do not double-count by also walking correlations.
4. `ClinicalRecord`, routes, ECG: ignore in v0.1.

## v0.1 functions

1. `read_apple_health(path, types?, start?, end?, ignore_errors?)`
2. `apple_health_workouts(path)`
3. `apple_health_activity_summaries(path)`

Filter `types` accepts full HealthKit ids **or** short names (`HeartRate`).
Date filters apply to `start_date`.

### Date parse

Input: `2024-02-06 07:00:00 -0800` and `2026-01-15 06:30:00 +1100` (and `+0530`).
Output: `TIMESTAMPTZ`. Wrong TZ silently ruins daily aggregates — this parser needs tests before the XML loop is “done”.

### Value split

- If `value` parses as `double` → `value` set, `value_text` null (or raw; pick one in the fixture script and stick to it).
- Else → `value` null, `value_text` = raw (`HKCategoryValueSleepAnalysisAsleepCore`).

Preferred v0.1: `value` numeric-or-null, `value_text` only when non-numeric. Smaller strings.

### Activity summary drift

Read whichever of these attributes exist:

- `appleMoveMinutes` / `appleMoveMinutesGoal`
- `appleMoveTime` / `appleMoveTimeGoal`

Expose both pairs as nullable columns rather than pretending they are the same.

## Week-1 spike (gate)

On DuckDB **2.0-dev**, Mac, unsigned load:

1. Register a table function with a `VARCHAR` path argument.
2. Emit a 3-column chunk (`type VARCHAR`, `value DOUBLE`, `start_date TIMESTAMP`) from hardcoded rows (no XML).
3. `LOAD` the `.duckdb_extension` in the 2.0-dev CLI.

**Pass:** start `parse_health.c`.
**Fail (API missing / unstable):** finish `parse_health` as a CLI (`parse_health export.xml > records.csv`) and wait for the TF surface. Do **not** switch to `extension-template` (unstable C++).

## File layout (target)

```text
README.md
DEV_PLAN.md
LICENSE
CMakeLists.txt          # from template, renamed apple_health
Makefile
src/
  parse_health.h
  parse_health.c
  zip_source.h
  zip_source.c
  apple_health_tf.c     # only DuckDB includes
scripts/
  make_fixture.py       # writes test/data/export.xml + golden csv
test/
  data/export.xml
  data/export.zip
  sql/read_apple_health.test
  sql/workouts.test
  sql/activity_summaries.test
  sql/dates.test
docs/
  API.md                # split out of README when the TF exists
```

This checkout currently holds README + DEV_PLAN only. Next drop: fixture XML + `make_fixture.py`.

## Mac workflow

```bash
# one-time
xcode-select --install
brew install cmake ninja ccache python

# per session
make configure
GEN=ninja make debug
make test_debug          # SQLLogic once tests exist

# manual
duckdb -unsigned -c "LOAD 'build/debug/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.xml');"
```

Pin a **working 2.0-dev CLI version** in this file when we find one. Nightlies move; do not float `main` daily after the spike works.

Template note: `extension-template-c` is still marked experimental and “community coming soon”. That is accepted. We are betting on 2.0, not on 1.5 community CI.

## Implementation order

1. Repo bootstrap from `extension-template-c` (rename extension id → `apple_health`).
2. Week-1 TF spike (hardcoded rows).
3. `scripts/make_fixture.py` + synthetic `export.xml` / zip (no PHI).
4. Date parser + unit tests (CLI or tiny C test).
5. SAX `Record` → stdout CSV, match golden file.
6. Zip open (`export.xml` member).
7. Wire `read_apple_health`.
8. Workouts + activity summaries.
9. `types` / `start` / `end` filters.
10. README load instructions with real build paths.
11. Stop. Routes/ECG are v0.2.

## Synthetic fixture requirements

Hand-written, ~40–60 elements, covering:

- Quantity record (HR, steps) with numeric `value` + unit
- Category record (sleep stage) with non-numeric `value`
- Workout with duration/distance/energy
- `ActivitySummary` with **old** move-minutes attrs
- `ActivitySummary` with **new** move-time attrs
- Dates with `+1100` (Sydney) and `-0800`
- Non-ASCII `sourceName` (e.g. café / Watch name)
- A `Correlation` wrapping records that also appear top-level (parser must not duplicate if we only emit top-level Records — document the choice)
- Locale on `<HealthData>`

No real DOB, no real device UDI, no real GPS.

## Blockers to watch

| Blocker | Mitigation |
|---|---|
| Stable C API has no table-function registration yet | Parser-as-CLI; wrap later |
| v2 entrypoint / headers churn before RC | Isolate DuckDB glue in one file; pin a nightly |
| Community CI still C++-template-only after 2.0 | Custom repo / unsigned; descriptor later |
| Zip library + vcpkg on osx_arm64 | Bare `export.xml` works first; zip second |
| 5 GB single-thread scan feels “slow” | Document COPY-to-Parquet; `types`/`start`/`end` required for UX |
| Apple date format | Dedicated tests before claiming done |
| Schema drift (new record types yearly) | Ignore unknown tags/attrs |

## Out of scope (do not start)

- Per-type SQL tables inside the extension
- Deduping iPhone + Watch double counts
- Live HealthKit / Health Auto Export sync
- MCP, Streamlit, dbt models
- Depending on `webbed`
- Shipping a real export in CI

## Personal stub

`Mjboothaus/duckdb-ext-apple-health` is a C++ template hello-world. Archive it and point the README at this repo. Do not transfer history.

## Next concrete drop

1. Create `DataBooth/duckdb-apple-health` on GitHub (empty or this tree).
2. Add `scripts/make_fixture.py` + `test/data/export.xml`.
3. Vendor `extension-template-c` and run the week-1 spike on the Mac.
