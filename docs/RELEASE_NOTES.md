# Release notes

## v0.2.0 — rename to `healthkit_export` (2026-09-12)

**Breaking rename** of the extension id and SQL table functions (no aliases).

| Before (≤24h community preview) | After |
|--|--|
| `INSTALL apple_health FROM community` | `INSTALL healthkit_export FROM community` |
| `read_apple_health` | `read_healthkit_export` |
| `apple_health_workouts` | `healthkit_workouts` |
| `apple_health_activity_summaries` | `healthkit_activity_summaries` |
| `apple_health_workout_routes` | `healthkit_workout_routes` |
| `apple_health_workout_route_points` | `healthkit_workout_route_points` |

Scanner behaviour and column schemas are unchanged. Local optional DB path remains `output/apple_health.duckdb`.

Trademark: not affiliated with Apple Inc.

---

## v0.1.1 — community extension (2026-09-10)

**Community publish.** `healthkit_export` is installable from DuckDB community on **macOS**.

### Install

```sql
INSTALL healthkit_export FROM community;
LOAD healthkit_export;
```

- DuckDB **1.5.5+**, platforms **`osx_arm64`** / **`osx_amd64`**
- Merged listing: [duckdb/community-extensions#2653](https://github.com/duckdb/community-extensions/pull/2653)
- Source pin: tag **v0.1.1** (`TARGET_DUCKDB_VERSION=v1.2.0` stable C extension ABI)

### Fix vs v0.1.0 packaging attempt

v0.1.0 mistakenly stamped extension metadata as C API **v1.5.6** (DuckDB release conflated with C ABI). Hosts only load C-API extensions built for **≤ v1.2.0**. v0.1.1 corrects the stamp so community CI and `LOAD` succeed.

### Still local-only

Linux/Windows/Wasm community binaries, streaming execute, named scan filters — see [ROADMAP.md](ROADMAP.md).

---

## v0.1.0 — core extension (2026-09-06)

**Layer A freeze.** First numbered core release of the DuckDB Apple Health **scanner** (C, stable C API).

### Table functions

| Function | Role |
|----------|------|
| `read_healthkit_export(path)` | Top-level Health records |
| `healthkit_workouts(path)` | Workouts |
| `healthkit_activity_summaries(path)` | Daily activity rings |
| `healthkit_workout_routes(path)` | WorkoutRoute + FileReference (`gpx_path`) |
| `healthkit_workout_route_points(path)` | GPX track points |

`path` may be `export.zip`, a directory containing `export.xml`, or `export.xml`.

### Install / load

```bash
just bootstrap   # or: just configure && just debug && just fixture
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/healthkit_export/healthkit_export.duckdb_extension';
FROM read_healthkit_export('test/data/export.zip');
```

Community install landed in **v0.1.1** — see above and [CREATE_COMM_EXT.md](CREATE_COMM_EXT.md).

### Correctness (freeze)

- SQLLogic: `test/sql/apple_health.test`, `workouts.test`, `activity_summaries.test` — **PASS**
- pytest: `tests/test_extension_smoke.py`, `tests/test_compare_healthkit_to_sqlite.py` — **17 passed, 1 skipped** (real-export optional)
- Semantics: top-level `<Record>` only; nested Correlation children skipped

### Limits (intentional for v0.1.0)

- Parse largely in **bind**; RAM can track export size on full loads
- Prefer materialise: `COPY … TO parquet` or optional `just build-db` (Python add-on)
- No named `types` / `start` / `end` parameters yet
- Platforms proven: macOS Apple Silicon; multi-arch CI artifacts optional
- DuckDB **1.5.x** unsigned C-API load; **2.0** remains strategic

### Not this release (add-ons)

Optional same-repo Python package **`health-data-store`**, maps, Photos, journeys, marimo walk-stories — **not** part of the extension binary. See [PYTHON_PACKAGE.md](PYTHON_PACKAGE.md), [PERSONA.md](PERSONA.md).

### Upgrade from v0.1.0-beta

Same SQL surface plus routes/route_points already on main before tag. Tag **v0.1.0** pins extension metadata via git tag ([VERSIONING.md](VERSIONING.md)).

---

## v0.1.0-beta (2026-08-29)

Developer preview: records, workouts, activity summaries; fixture golden; unsigned load. Superseded by **v0.1.0**.
