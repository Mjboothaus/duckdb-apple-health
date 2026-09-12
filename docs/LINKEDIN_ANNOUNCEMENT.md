# LinkedIn announcement — duckdb-healthkit-export

*Short posts you can paste when you are ready to announce. Tweak voice/length. No PHI. Last updated: 2026-09-06.*

**When to post:** after **v0.1.0** is tagged (or clearly labelled beta) and the public README matches this draft. Until then treat this as a working copy.

**Repo (public):** https://github.com/Mjboothaus/duckdb-healthkit-export

---

## Primary post (recommended)

I open-sourced **duckdb-healthkit-export** — a DuckDB **scanner** that turns an Apple Health `export.zip` into typed SQL tables, **in-process**.

No cloud. No warehouse. No telemetry in the extension. Your export stays on your machine.

```sql
-- duckdb -unsigned
LOAD '…/healthkit_export.duckdb_extension';

FROM read_healthkit_export('export.zip');
FROM healthkit_workouts('export.zip');
FROM healthkit_activity_summaries('export.zip');
FROM healthkit_workout_routes('export.zip');
FROM healthkit_workout_route_points('export.zip');
```

**Who it's for**

Technical people in the **Apple** ecosystem (Health, optionally Photos) who already live in SQL/DuckDB and want to **unlock their own data** locally — not another dashboard that needs your PHI.

**Why it exists (cousins do different jobs)**

- **[webbed](https://github.com/teaguesterling/duckdb_webbed)** — excellent **generic** XML/HTML in DuckDB
- **[healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite)** — excellent **batch** zip → SQLite

The gap: **HealthKit-aware, in-process DuckDB SQL** (typed dates, numeric vs category values, zip layout, workouts, routes/GPX).

**How it's built**

- **C** on DuckDB's **stable C API** (not the unstable C++ extension template)
- Parser + zip code have **zero** DuckDB headers
- Synthetic fixtures only in git — real exports never required in the repo
- Optional **Python add-ons** (local DuckDB file, maps, Photos, multi-day journeys) if you want stories later — **not** required to unlock data in SQL

**Design honesty**

> Raw XML is a **scan**. Parquet (or a local DuckDB file) is the **fast path**. That is intentional.

First full pass of a multi-year export can be minutes and RAM-heavy; materialise the slices you care about once, then iterate.

**Reality check** on one personal export kept offline (~270 MiB zip / ~2 GiB XML): on the order of **~4.3M** records, **~1.7k** workouts, **~2.7k** activity-summary days — then `COPY` / `build-db` for day-to-day work.

**Status:** developer **v0.1** — local **unsigned** `LOAD`, macOS Apple Silicon proven, **not** in the community extension repo yet. Community `INSTALL` tracks the DuckDB 2.0 / C-API packaging path.

Repo: https://github.com/Mjboothaus/duckdb-healthkit-export

Docs: README · [PERSONA](https://github.com/Mjboothaus/duckdb-healthkit-export/blob/main/docs/PERSONA.md) · [ROADMAP](https://github.com/Mjboothaus/duckdb-healthkit-export/blob/main/docs/ROADMAP.md) · [RELEASE_PLAN](https://github.com/Mjboothaus/duckdb-healthkit-export/blob/main/docs/RELEASE_PLAN.md)

#DuckDB #AppleHealth #HealthKit #OpenSource #DataEngineering #Analytics #Privacy #LocalFirst

---

## Shorter variant

Open-sourcing **duckdb-healthkit-export**: Apple Health `export.zip` → DuckDB SQL **in-process** (C, stable C API, unsigned load).

```sql
FROM read_healthkit_export('export.zip');
FROM healthkit_workouts('export.zip');
FROM healthkit_workout_route_points('export.zip');
```

HealthKit-shaped (not generic XML). Scan once → Parquet or a local DB for the fast path. Synthetic fixtures in git; your real export never has to leave the laptop.

Optional maps / Photos / walk stories via Python add-ons — core is SQL-only.

https://github.com/Mjboothaus/duckdb-healthkit-export

---

## Ultra-short (character-tight)

Built a DuckDB extension so Apple Health exports become local SQL — C, stable C API, no telemetry. Scan → Parquet. Optional maps later. v0.1 unsigned.

https://github.com/Mjboothaus/duckdb-healthkit-export

#DuckDB #AppleHealth #OpenSource

---

## Comment you can add under the post

Deep-dive and design notes live in the repo docs (README performance section, PERSONA onboarding ladder, ROADMAP).

Table functions today: records, workouts (+ stats/events where exposed), activity summaries, clinical records, workout routes, GPX route points.

Fast path: `COPY … TO '….parquet'` or `just build-db` → `output/healthkit_store.duckdb`.

Explore notebooks (optional): `notebooks/explore_export.py`, maps via `just map-walks` / walk-stories after a local DB exists.

Feedback welcome from DuckDB + Apple Health folks — especially on streaming/execute performance and community packaging.

---

## What not to claim (checklist)

- [ ] Not "App Store app" or one-click for non-technical users
- [ ] Not community `INSTALL healthkit_export` yet
- [ ] Not live HealthKit sync
- [ ] Not medical advice / clinical decision support
- [ ] Do not paste personal HR, GPS, or photo paths in the post or comments
