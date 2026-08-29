# Design & development guide

Single source of truth for **what** `duckdb-apple-health` is, **how** it is built, and **what must not change** without an explicit decision.

- Product overview & install: [README.md](README.md), [QUICKSTART.md](QUICKSTART.md)
- Forward plan (v0.2+, DuckDB 2.0 packaging): [ROADMAP.md](ROADMAP.md)
- Shipped versions: [RELEASE_NOTES.md](RELEASE_NOTES.md)

Decisions in this file override older chat notes. Last updated: 2026-08-29.

---

## Project in one paragraph

DuckDB **scanner** extension: stream Apple Health `export.zip` / `export.xml` into SQL tables.
Language: **C**. ABI: DuckDB **stable C API** only (no `duckdb.hpp`, no unstable C++ extension template).
Load **unsigned** until 2.0 GA + community C-API CI exist.
Python is for fixtures and tests only. Rust/Mojo out of scope.

```text
export.zip | export.xml | export-dir
        → stream parse
        → typed DataChunks
        → SQL / COPY Parquet
```

Not a warehouse, MCP server, dashboard, or dbt package.

---

## Locked decisions

| Topic | Decision |
|---|---|
| GitHub | Public `DataBooth/duckdb-apple-health` (not the old personal C++ stub) |
| Licence | Apache-2.0 |
| Language | **C.** Thin C++ only if the stable table-function C API is unusable |
| ABI | Stable C API. No `#include <duckdb.hpp>`, no unstable extension internals |
| DuckDB target | 2.0 path strategically; v0.1 verified load on 1.5.x unsigned C-API binaries |
| Community `INSTALL` | After 2.0 GA + community C-API CI. Until then: unsigned `LOAD` |
| Dev machine first | macOS Apple Silicon (`osx_arm64`) |
| Wasm | Out of v0.1 |
| Parser | Streaming tag scan (no libxml2 DOM). Zip via minimal reader + zlib |
| Python | Fixtures, golden tables, pytest, optional marimo — not inside the extension |
| Privacy | No telemetry, no network I/O, no real Health exports in git/CI |

### Why C (default)

- Output is flat rows, not object graphs
- SAX-style callbacks are C-shaped
- ABI bet: talk to DuckDB only through `duckdb_extension.h`
- If bind/init/emit in C becomes unmaintainable, switch **only** `apple_health_tf.c` to a stable C++ wrapper; leave `parse_health.c` / `zip_source.c` as C

### Hard rules (do not break casually)

1. Parser and zip code must not `#include` DuckDB headers. Only table-function / entrypoint files may.
2. Do not set `USE_UNSTABLE_C_API=1` without an explicit decision.
3. Do not switch to `duckdb/extension-template` (unstable C++ internals) as the default.
4. Do not add Wasm, GPX routes, ECG, clinical records, MCP, dbt, or telemetry in-tree without scope change.
5. Do not commit a real Health export.
6. Prefer the smallest diff that advances the current goal.

Personal stub `Mjboothaus/duckdb-ext-apple-health` is a C++ hello-world — **do not copy it.**

---

## Architecture

```text
path
  ├─ zip  → member **/export.xml   (zip_source.c + zlib)
  ├─ dir  → export.xml
  └─ xml  → file
        │
        ▼
 parse_health.c     stream tags, dates, type_short, value vs value_text
        │
        ▼
 apple_health_tf.c  DuckDB C API table functions only
```

### Semantic rules

1. **v0.1 memory:** implementation currently buffers in bind (known limit). **Design intent:** peak memory ≈ one XML element + one output chunk (~2–8k rows) once streaming execute lands ([ROADMAP.md](ROADMAP.md)).
2. Unknown attributes/tags are ignored (export DTD drifts by iOS version).
3. **`Correlation` child `Record`s:** emit **top-level** `Record` only. Nested copies are skipped (same samples usually also appear top-level). Differs from `healthkit-to-sqlite`, which counts every `</Record>` end event — see tests.
4. `ClinicalRecord`, routes, ECG: ignore in v0.1.

### v0.1 SQL surface

1. `read_apple_health(path)` — full v0.1 record columns; named `types` / `start` / `end` / `ignore_errors` still **planned**
2. `apple_health_workouts(path)`
3. `apple_health_activity_summaries(path)` — nullable columns for both `appleMoveMinutes*` and `appleMoveTime*`

**Date parse:** `yyyy-MM-dd HH:mm:ss Z` (`+1100`, `-0800`, `+0530`) → `TIMESTAMPTZ`.

**Value split:** if attribute parses as double → `value` set, `value_text` empty; else `value` null, `value_text` = raw.

### Layout (current)

```text
README.md  QUICKSTART.md  DESIGN.md  ROADMAP.md  RELEASE_NOTES.md
LICENSE  justfile  Makefile  CMakeLists.txt
src/
  parse_health.{c,h}  zip_source.{c,h}  apple_health_tf.c
  parse_health_main.c   # CLI
  capi_quack.c          # entrypoint (template name)
  add_numbers.c         # template sample scalar
scripts/make_fixture.py
test/data/  test/sql/
tests/                  # pytest vs golden + healthkit-to-sqlite
notebooks/explore_export.py
duckdb_capi/  extension-ci-tools/
```

---

## Current state (v0.1 developer preview)

| Area | Status |
|---|---|
| C-API template vendored as `apple_health` | Done |
| Unsigned load (1.5.x / C_STRUCT metadata) | Done |
| Streaming XML parser + CLI | Done |
| Zip / dir / xml paths | Done |
| `read_apple_health` + workouts + activity summaries | Done |
| Fixture golden + pytest vs `healthkit-to-sqlite` | Done |
| Real-export smoke (multi-million rows) | Done (manual); formal HK full-import optional |
| Docs pass / community INSTALL | Docs beta done; community INSTALL not yet |
| Streaming execute + filter pushdown | Not yet — [ROADMAP.md](ROADMAP.md) |

### Gate history (v0.1 build)

Original implementer gates (from the former implementation brief). All completed for preview:

| Gate | Outcome |
|---|---|
| 0 Machine / tools | Pass (justfile `path_exists == "true"`; DuckDB 1.5.x on PATH) |
| 1 Vendor `extension-template-c` | Pass |
| 2 Unsigned load | Pass on 1.5.2 |
| 3 Hardcoded TF spike | Pass (stable C API has table functions) |
| 4 Parser CLI vs golden | Pass (7 records; Correlation nested skipped) |
| 5 Zip/dir source | Pass |
| 6 Wire TF to zip | Pass (`TIMESTAMPTZ`) |
| 7 Workouts + summaries | Pass |
| 8 Docs polish | Pass (v0.1.0-beta docs pack) |

### Mac workflow

```bash
just check-tools
just configure
just debug
just fixture
just demo
just pytest-ext
```

```sql
-- duckdb -unsigned
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
```

---

## Correctness notes

- **Golden fixture:** 7 top-level records; sleep uses `value_text`; non-ASCII `Café Run Club`; BP also nested under Correlation (must not double-count).
- **vs healthkit-to-sqlite:** compare top-level multisets; expect HK total records = ours + nested Correlation children when those exist.
- **Real exports:** keep outside git; optional `APPLE_HEALTH_EXPORT_ZIP` for slow pytest.

---

## Blockers & mitigations

| Blocker | Mitigation |
|---|---|
| 2.0 headers / community CI churn | Isolate DuckDB glue in TF file; pin `duckdb_capi`; unsigned until CI supports C-API |
| Multi-GB scan feels slow | Streaming execute + `types`/`start`/`end`; document COPY→Parquet |
| Apple date / schema drift | Tests; ignore unknown attrs |
| Tempted to DOM-parse XML | No — streaming only |
| Tempted to copy personal C++ stub | No |

---

## Out of scope (do not start without a decision)

- Per-type physical tables inside the extension
- Silent Watch + iPhone dedupe
- Live HealthKit sync
- MCP / Streamlit / dbt as core deliverables
- Depending on `webbed`
- Shipping a real export in CI
- Unstable C API / C++ template as default

---

## For implementers (LLM or human)

1. Read this file + [ROADMAP.md](ROADMAP.md) before coding.
2. Prefer smallest diff; do not expand scope.
3. Run `just pytest-ext` after behavioural changes.
4. Do not batch large unrelated refactors without evidence.
5. After each substantial change: commands run, key output, files touched.
