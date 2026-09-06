# Release notes

## v0.1.0 — core extension (2026-09-06)

**Layer A freeze.** First numbered core release of the DuckDB Apple Health **scanner** (C, stable C API).

### Table functions

| Function | Role |
|----------|------|
| `read_apple_health(path)` | Top-level Health records |
| `apple_health_workouts(path)` | Workouts |
| `apple_health_activity_summaries(path)` | Daily activity rings |
| `apple_health_workout_routes(path)` | WorkoutRoute + FileReference (`gpx_path`) |
| `apple_health_workout_route_points(path)` | GPX track points |

`path` may be `export.zip`, a directory containing `export.xml`, or `export.xml`.

### Install / load

```bash
just bootstrap   # or: just configure && just debug && just fixture
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
```

Community `INSTALL apple_health FROM community` is **not** available yet. Migration plan: [CREATE_COMM_EXT.md](CREATE_COMM_EXT.md).

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
