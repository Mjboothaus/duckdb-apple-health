# LinkedIn announcement — duckdb-apple-health

*Short posts you can paste. Tweak voice/length. No PHI. Last updated: 2026-09-07.*

**When to post:** **v0.1.0 is tagged** — good time to announce. Community install is **under review** (not live yet); say “submitted / pending review,” not “available via `INSTALL … FROM community`” until that PR merges.

**Repo:** https://github.com/Mjboothaus/duckdb-apple-health  
**Release:** https://github.com/Mjboothaus/duckdb-apple-health/releases/tag/v0.1.0  
**Community PR (review):** https://github.com/duckdb/community-extensions/pull/2653  

---

## Primary post (recommended)

I tagged **v0.1.0** of **duckdb-apple-health** — a DuckDB **scanner** that turns an Apple Health `export.zip` into typed SQL tables, **in-process**.

No cloud. No warehouse. No telemetry in the extension. Your export stays on your machine.

```sql
-- duckdb -unsigned (local build / release binary for now)
LOAD '…/apple_health.duckdb_extension';

FROM read_apple_health('export.zip');
FROM apple_health_workouts('export.zip');
FROM apple_health_activity_summaries('export.zip');
FROM apple_health_workout_routes('export.zip');
FROM apple_health_workout_route_points('export.zip');
```

**Who it’s for**

Technical people in the **Apple** ecosystem who already live in SQL/DuckDB and want to **unlock their own Health data** locally — not another dashboard that needs your PHI.

**Why it exists**

- **webbed** — excellent generic XML/HTML in DuckDB  
- **healthkit-to-sqlite** — excellent batch zip → SQLite  

The gap: **HealthKit-shaped, in-process DuckDB SQL** (typed dates, numeric vs category values, zip layout, workouts, routes/GPX).

**v0.1.0**

- Core C extension on DuckDB’s **stable C API** (not the unstable C++ template)  
- Fixture tests + SQLLogic green on freeze  
- Honest design: raw XML is a **scan**; Parquet / a local DuckDB file is the **fast path**  
- Optional Python helpers in the same repo (`health-data-store`, maps/stories) — **not** required to unlock data in SQL  

**Community extension**

I’ve submitted **`apple_health`** to the DuckDB community extensions repo for review (**macOS first**). Until that lands, you build/load **unsigned** from the GitHub release / source.

Repo: https://github.com/Mjboothaus/duckdb-apple-health  
Release: https://github.com/Mjboothaus/duckdb-apple-health/releases/tag/v0.1.0  
Community review: https://github.com/duckdb/community-extensions/pull/2653  

#DuckDB #AppleHealth #HealthKit #OpenSource #DataEngineering #Analytics #Privacy #LocalFirst

---

## Shorter variant

**v0.1.0** of **duckdb-apple-health** is out: Apple Health `export.zip` → DuckDB SQL **in-process** (C, stable C API).

```sql
FROM read_apple_health('export.zip');
FROM apple_health_workouts('export.zip');
FROM apple_health_workout_route_points('export.zip');
```

Scan once → Parquet or a local DB for the fast path. Synthetic fixtures in git; your real export never has to leave the laptop.

Community `INSTALL` is **submitted for review** (macOS first) — until then, load unsigned from the release.

https://github.com/Mjboothaus/duckdb-apple-health/releases/tag/v0.1.0  
https://github.com/duckdb/community-extensions/pull/2653  

---

## Ultra-short

Shipped **v0.1.0** of a DuckDB extension so Apple Health exports become local SQL — C, stable C API, no telemetry. Community extension under review (macOS first).

https://github.com/Mjboothaus/duckdb-apple-health/releases/tag/v0.1.0  

#DuckDB #AppleHealth #OpenSource

---

## Comment you can add under the post

Table functions in v0.1.0: records, workouts, activity summaries, workout routes, GPX route points.  

Fast path: `COPY … TO '….parquet'` (or optional local DB helpers in the same repo).  

Community PR for `INSTALL apple_health FROM community` (macOS first): https://github.com/duckdb/community-extensions/pull/2653 — not merged yet; feedback welcome if you try the unsigned build.  

Docs: README performance section · PERSONA onboarding · CREATE_COMM_EXT for the install path.  

---

## What not to claim (checklist)

- [ ] Not “App Store app” or one-click for non-technical users  
- [ ] Not `INSTALL apple_health FROM community` **until** the community PR is merged  
- [ ] Not multi-platform community binaries yet (macOS-first submission)  
- [ ] Not live HealthKit sync  
- [ ] Not medical advice / clinical decision support  
- [ ] Do not paste personal HR, GPS, or photo paths in the post or comments  
