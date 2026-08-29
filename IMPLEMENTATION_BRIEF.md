# Implementation brief (for an LLM or human implementer)

Self-contained instructions to build `DataBooth/duckdb-apple-health`.
Do one step at a time. Stop at each **Gate** and report evidence before continuing.
Do not skip gates. Do not expand scope.

## Project in one paragraph

DuckDB **scanner** extension: stream Apple Health `export.zip` / `export.xml` into SQL tables.
Language: **C**. ABI: DuckDB **2.0 stable C API** only (no `duckdb.hpp`, no unstable C++ extension template).
Dev machine: MacBook Apple Silicon. Load unsigned until 2.0 GA + community C-API CI exist.
Python is for fixtures only. Rust/Mojo out of scope.

Canonical docs already in the repo:

- `README.md` — product
- `DEV_PLAN.md` — decisions and blockers
- `QUICKSTART.md` — end user
- `justfile` — Mac recipes
- `scripts/make_fixture.py` — synthetic XML/zip/golden CSV
- `test/data/` — generated fixtures (no PHI)

Personal stub `Mjboothaus/duckdb-ext-apple-health` is a C++ hello-world. **Do not copy it.**

## Hard rules

1. Parser and zip code must not `#include` DuckDB headers. Only the table-function / entrypoint file may.
2. Do not set `USE_UNSTABLE_C_API=1` unless a gate explicitly fails and the user agrees.
3. Do not switch to `github.com/duckdb/extension-template` (unstable C++ internals).
4. Do not add Wasm, GPX routes, ECG, clinical records, MCP, dbt, or telemetry.
5. Do not commit a real Health export.
6. Keep existing README, DEV_PLAN, QUICKSTART, justfile, scripts, test/data when vendoring the template.
7. Prefer smallest diff that passes the current gate.

## Current state (as of 2026-08-29)

Present: docs, justfile, fixture generator, synthetic `export.xml` / zip / `golden/records.csv`.
Absent: `Makefile` from the C-API template, `duckdb_capi/`, C sources, a `.duckdb_extension` binary.

`just configure` / `just debug` / `just demo` are expected to fail until Step 1 lands.

---

## Step 0 — Confirm the machine

Work in the existing git clone of `DataBooth/duckdb-apple-health` on the Mac.

```bash
just check-tools
just fixture
```

Need: `clang`, `cmake`, `python3`, `just`. Want: `ninja`, `ccache`, DuckDB **2.0-dev or preview** CLI on `PATH` as `duckdb`.

**Gate 0.** Paste `just check-tools` output and `duckdb --version`.
If DuckDB is 1.5.x, install 2.0-dev before Step 2 load tests. You may still vendor the template on 1.5 for compile-only.

---

## Step 1 — Vendor `extension-template-c` without destroying project files

Template: https://github.com/duckdb/extension-template-c  
Clone with submodules. Copy **into** this repo. Do not replace product docs.

```bash
git clone --recurse-submodules https://github.com/duckdb/extension-template-c.git /tmp/ext-c
```

Copy across (merge `.gitignore`; do not overwrite README / DEV_PLAN / QUICKSTART / justfile / scripts / test/data):

```text
Makefile
CMakeLists.txt
.gitmodules
.github/workflows/
duckdb_capi/
extension-ci-tools/    # git submodule — init properly
src/capi_quack.c
src/add_numbers.c
src/include/
test/sql/              # template sample test; keep beside our test/data
```

Rename extension id from `capi_quack` → `apple_health`:

- `Makefile` `EXT_NAME` / equivalent
- `CMakeLists.txt` source list can stay `add_numbers.c` + `capi_quack.c` for the first load
- `test/sql/*.test` filenames if the runner expects the extension name
- Any `LOAD capi_quack` in tests → `LOAD apple_health` / path load

`CMakeLists.txt` (template) uses:

```cmake
project(${EXTENSION_NAME} LANGUAGES C)
set(EXTENSION_SOURCES
        src/add_numbers.c
        src/capi_quack.c
)
```

`EXTENSION_NAME` is injected by the Makefile. After rename it should be `apple_health`.

Init submodule:

```bash
git submodule update --init --recursive
```

**Gate 1.** `test -f Makefile && test -d duckdb_capi && test -f src/capi_quack.c`.
`rg capi_quack Makefile CMakeLists.txt test` should only remain as **source filenames** if you kept them, not as the installed extension name.
Commit: `chore: vendor extension-template-c as apple_health`.

---

## Step 2 — Prove unsigned load on the Mac

```bash
just configure     # or make configure
just debug         # GEN=ninja make debug
find build -name '*.duckdb_extension'
```

Fix `ext_debug` / `ext_release` in `justfile` to the real path. Template README mentions `build/debug/` after a footer is appended to the dylib.

Load with **2.0-dev** CLI:

```bash
duckdb -unsigned -c "LOAD 'THE_REAL_PATH'; SELECT add_numbers(1, 2);"
```

(Use the actual sample function name from `src/add_numbers.c` if it differs.)

**Gate 2.** Command prints a number and exits 0.
Record:

- DuckDB version
- Full path of the `.duckdb_extension`
- Whether `-unsigned` was required (it should be)

If `make configure` or `make debug` fails, fix the template/Mac issue. Do not start a parser.
If load fails with ABI / version mismatch, you are on the wrong DuckDB CLI — install 2.0-dev.

Commit justfile path fix if needed: `chore: point justfile at built extension`.

---

## Step 3 — Week-1 table-function spike (hardcoded rows)

Add `src/apple_health_tf.c` (DuckDB C API includes allowed **only here** and in the existing entrypoint).

Register table function `read_apple_health(path VARCHAR)` that **ignores** `path` and emits 3 hardcoded rows:

| type | value | start_date |
|---|---|---|
| `HKQuantityTypeIdentifierHeartRate` | 72 | a TIMESTAMP you choose |
| `HKQuantityTypeIdentifierStepCount` | 1234 | |
| `HKCategoryTypeIdentifierSleepAnalysis` | NULL | |

Schema for the spike can be 3 columns only.

Wire it from `capi_quack.c` (or rename entrypoint file to `apple_health.c` if cleaner). Add `src/apple_health_tf.c` to `EXTENSION_SOURCES`.

SQLLogic or manual:

```sql
LOAD '...apple_health.duckdb_extension';
FROM read_apple_health('ignored');
```

**Gate 3a.** If the **stable** C API cannot register a table function, **stop**. Do not enable unstable API. Report the missing symbols. Go to Step 4 (parser CLI) instead.

**Gate 3b.** If it works: 3 rows, unsigned load. Commit: `feat: hardcoded read_apple_health table function`.

---

## Step 4 — Parser as C, no DuckDB

New files only:

```text
src/parse_health.h
src/parse_health.c
```

Optional tiny CLI `src/parse_health_main.c` linked as `build/debug/parse_health` so you can run without DuckDB.

Behaviour:

- Stream XML (expat or yxml). Do not DOM the file.
- Emit one output row per top-level `<Record>`.
- Do **not** also emit `<Record>` children of `<Correlation>` (fixture duplicates BP both ways; golden CSV has 7 records).
- Ignore `<ClinicalRecord>`, GPX, ECG.
- Parse dates `yyyy-MM-dd HH:mm:ss Z` (`+1100`, `-0800`, `+0530`).
- `type_short`: strip `HKQuantityTypeIdentifier` / `HKCategoryTypeIdentifier` / `HKDataType` prefixes.
- If `value` parses as double → `value` set, `value_text` empty; else `value` null, `value_text` = raw.
- Unknown attributes: ignore.

Match `test/data/golden/records.csv` (compare types/values; dates in golden are still Apple strings until you decide to emit ISO in the CLI).

Also parse `<Workout>` and `<ActivitySummary>` into separate row structs (can be later functions; structs now are fine).

Activity summaries: nullable columns for both `appleMoveMinutes*` and `appleMoveTime*`.

**Gate 4.**

```bash
just fixture
./build/debug/parse_health test/data/export.xml
```

Row count for records == 7. Sleep row has empty numeric value and `value_text` set. Café source name survives. Commit: `feat: streaming Health XML parser`.

---

## Step 5 — Zip source

`src/zip_source.c` / `.h`:

- If path is `.zip`, find member matching `**/export.xml` (fixture uses `apple_health_export/export.xml`).
- If path is a directory, open `export.xml` inside it.
- If path is a file, treat as xml.

vcpkg/`minizip-ng` only if the template already has vcpkg. Otherwise a small minizip or libcompression approach on Mac is acceptable. Keep it out of the TF file.

**Gate 5.** CLI accepts `test/data/export.zip` and yields the same 7 records. Commit: `feat: read export.xml from zip or directory`.

---

## Step 6 — Connect parser to the table function

`read_apple_health` uses parse_health + zip_source. Emit the v0.1 columns:

`type, type_short, unit, value, value_text, start_date, end_date, creation_date, source_name, source_version, device, filename`

`start_date` / `end_date` / `creation_date` as `TIMESTAMPTZ`.

Named parameters when the C API allows them; otherwise skip filters until a follow-up:

- `types` (list of full ids or short names)
- `start`, `end` on `start_date`
- `ignore_errors`

Update `just demo` so it runs against `test/data/export.zip`.

**Gate 6.**

```bash
just debug
just demo
```

7 record rows from the zip. Dates are timestamptz, not varchar. Commit: `feat: read_apple_health scans fixture zip`.

---

## Step 7 — Workouts and activity summaries

Table functions:

- `apple_health_workouts(path)`
- `apple_health_activity_summaries(path)`

SQLLogic tests under `test/sql/` using `test/data/export.xml`.

**Gate 7.** One running workout, two activity-summary rows (2020-06-01 old attrs + 2026-01-15 new attrs). Commit: `feat: workouts and activity summaries`.

---

## Step 8 — Docs pass

- Put the real `.duckdb_extension` path in `QUICKSTART.md` and `justfile`.
- Mark v0.1 functions as implemented vs planned in README.
- Do not claim `INSTALL FROM community`.

**Gate 8.** `just check-tools`, `just fixture`, `just debug`, `just demo` all documented and working on the author’s Mac.

---

## Explicit non-goals until the user says so

- Community `description.yml` / `INSTALL apple_health FROM community`
- Wasm / `excluded_platforms`
- Routes, ECG, ClinicalRecord
- Unstable C API
- C++ `duckdb.hpp` template
- Deduping Watch vs iPhone
- Python wheel wrapping the extension

## If you get stuck

| Failure | Action |
|---|---|
| Template build breaks on Mac | Stay on template sample `add_numbers`; fix configure/debug only |
| Stable API has no table functions | Gate 3a → Step 4 CLI; report symbols; wait |
| 2.0 headers churn | Pin a nightly hash in DEV_PLAN; keep DuckDB glue in one file |
| Tempted to use libxml2 DOM | No. Streaming only |
| Tempted to copy Mjboothaus stub | No |

## How to report back

After each gate: commands run, last 30 lines of output, files changed, whether to proceed.
Do not batch Steps 1–6 in one commit storm without gates.
