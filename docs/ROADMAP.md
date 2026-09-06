# Roadmap

Living product direction for [duckdb-apple-health](https://github.com/Mjboothaus/duckdb-apple-health).
Operational checklist: [RELEASE_PLAN.md](RELEASE_PLAN.md). Audience: [PERSONA.md](PERSONA.md).
Versioning: [VERSIONING.md](VERSIONING.md).

## Product layers

| Layer | What | Ships when |
|-------|------|------------|
| **A — Core extension** | C + stable C API: zip/XML → typed table functions | **v0.1.0** (first public release) |
| **B — Enriched local store** | Optional Python: `build-db`, Parquet, `HealthDataStore`, views | usable now; package polish with / after v0.1 |
| **C — Experience add-ons** | Photos ATTACH, journeys YAML, Folium maps, marimo walk-stories | optional; not required for extension release |

Core first. Add-ons must not block the extension binary or community-extension path.

## Cousins (positioning)

- **[webbed](https://github.com/teaguesterling/duckdb_webbed)** — generic XML/HTML in DuckDB ([docs](https://duckdb.org/community_extensions/extensions/webbed.html)). We specialise for HealthKit exports.
- **[healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite)** — zip → SQLite batch tool. We keep analysis **in DuckDB** with SQL table functions.

## Performance stance

Raw XML scan is intentionally the **slow path**; Parquet / local DuckDB is the **fast path** (see README).

**v0.1 honesty:** bind-time parse + buffering can use large RAM on multi‑GB exports; full GPS ingest is minutes-scale. Documented so users materialise early.

**Post-v0.1 performance work (priority order):**

1. Stream rows in **execute** (chunked emission; lower peak RAM)
2. Streaming inflate from zip (avoid full XML extract when possible)
3. Named parameters / pushdown: `types`, `start`, `end` (and document vs `WHERE` after scan)
4. String interning for repeated type/source strings
5. Incremental `build-db` (skip GPX already present by path)
6. Optional progress / estimated row counts for long scans

## Shipped on main (baseline)

- Table functions: records, workouts (+ stats/events), activity summary, clinical records, workout routes, route GPX points
- Fixture zip + `just` / `uv` developer path; CI smoke
- Python: local DuckDB builder, maps (selected journeys), Photos helpers, marimo apps
- Docs: architecture, privacy, persona, release plan, versioning; repo under **Mjboothaus**

## Near-term (toward v0.1.0)

- [ ] Phase 0 wrap: walk-stories polish on main; docs complete (this cycle)
- [ ] Phase 1: core freeze — `just bootstrap`, `pytest-ext`, README/USAGE contract, tag **v0.1.0**
- [ ] Decide community extension submission timing (may be v0.1 or shortly after)
- [ ] Python tree: keep as **optional supplementary package** (`python/apple_health_data`); same VERSION line of sight; no PyPI required for v0.1

## After v0.1

- Streaming + filter pushdown (performance list above)
- Workout route ↔ workout join helpers (SQL examples / optional view)
- Clinical / ECG depth only if fixture + tests exist
- Community extension packaging + multi-arch CI
- Optional: publish supplementary Python package (name TBD, e.g. aligned with repo)

## Explicit non-goals (for now)

- Replacing Apple Health or clinical decision support
- Shipping personal exports, Photos libraries, or map HTML with PII in git
- Supporting every HealthKit type edge-case in v0.1
- Requiring Python to use the extension

## Open product questions

- Default recommended path for newcomers: SQL-only vs `build-db` first?
- PyPI name and scope for the supplementary package (helpers only vs maps too)?
- How aggressive to be on breaking SQL column names before 1.0 (see VERSIONING)?
