# LinkedIn announcement — duckdb-apple-health

*Short post you can paste. Tweak voice/length as needed. No PHI.*

---

## Primary post (recommended)

Today we open‑sourced **duckdb-apple-health** — a DuckDB **scanner** that turns an Apple Health `export.zip` into SQL tables, in‑process.

No Python ETL step. No warehouse. No telemetry.

You `LOAD` a local unsigned extension and run:

```sql
FROM read_apple_health('export.zip');
FROM apple_health_workouts('export.zip');
FROM apple_health_activity_summaries('export.zip');
```

**Why it exists**

`webbed` is generic XML. `healthkit-to-sqlite` is a batch convert. The missing piece is HealthKit‑aware, streaming SQL next to the rest of your analytics.

**How we built it**

- **C**, on DuckDB’s **stable C API** (not the unstable C++ template)
- Parser + zip code have **zero** DuckDB headers
- Synthetic fixtures only in git — real exports stay on your machine
- Gate‑by‑gate build: unsigned load → table function → streaming XML → zip → real scan → workouts/rings

**Reality check** on a full personal export (kept offline): **4.3M+** records, **1.6k+** workouts, **2.7k+** activity‑summary days — then `COPY` the slices you care about to Parquet for the fast path.

Status: early **v0.1**, load **unsigned**, not in the community repo yet.

We’re targeting the **DuckDB 2.0** stable C-API extension path for community `INSTALL` when 2.0 GA + C-API CI land — details in `ROADMAP.md` (streaming execute, filter pushdown, and packaging). Built for people who already live in DuckDB and want Health data there too.

Repo: https://github.com/DataBooth/duckdb-apple-health

Write‑up: `BLOG_POST.md` · Roadmap (DuckDB 2.0): `ROADMAP.md` · Release notes: `RELEASE_NOTES.md`

#DuckDB #AppleHealth #HealthKit #OpenSource #DataEngineering #Analytics #Privacy

---

## Shorter variant

Open‑sourcing **duckdb-apple-health**: stream Apple Health `export.zip` → DuckDB SQL in‑process (C, stable C API, unsigned load).

```sql
FROM read_apple_health('export.zip');
```

Synthetic fixtures in git; your real export never has to leave the laptop. v0.1 — records, workouts, activity rings; Parquet for repeat queries.

https://github.com/DataBooth/duckdb-apple-health

---

## Comment you can add under the post

Deep‑dive: `BLOG_POST.md`. Roadmap (performance + DuckDB 2.0 community install): `ROADMAP.md`. Release notes: `RELEASE_NOTES.md`. Marimo notebook: `notebooks/explore_export.py` (timing + Parquet).
