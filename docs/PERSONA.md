# Persona and onboarding path

Last updated: 2026-09-05.

## Product frame

**duckdb-apple-health** is for people in the **Apple ecosystem** (Health, and optionally Photos) who are **reasonably technical** and want to **unlock their own health data** — locally, with SQL and optional maps/stories — without handing PHI to a cloud product.

One-line positioning:

> Your Apple Health export → local SQL (and, if you want, maps and walk stories) — data never required to leave your machine.

## Primary persona

### “Technical Apple self-quantifier”

| | |
|--|--|
| **Has** | iPhone/Watch Health history; can export `export.zip`; often a Photos library; Mac (Apple Silicon typical) |
| **Can** | Use Terminal, install Homebrew tools, run `just`/`uv`, write or paste SQL in the DuckDB CLI |
| **Wants** | Query HR/steps/workouts/GPS themselves; keep data private; eventually nice maps of multi-day walks |
| **Does not need** | App Store polish, live HealthKit sync, or a hosted dashboard |
| **Tolerates** | Unsigned extension load, multi-minute first scan of a large zip, reading docs |

### Secondary personas (supported, not primary)

- **SQL-only analyst** — extension + Parquet/`COPY` only; never opens marimo or Photos.
- **Trail storyteller** — cares about journeys (GNW, Camino, Abel Tasman); uses the local DB and walk-stories UI heavily after the DB exists.
- **Future:** less-technical partner viewing a shared HTML map export (no Terminal) — export only, not the build path.

## What we promise this user

1. **Unlock** — Health zip becomes typed tables in DuckDB.
2. **Own** — processing is local; no telemetry in the extension; real exports stay out of git.
3. **Deepen (optional)** — one local DB file, places, photos, multi-day journeys, marimo walk stories.
4. **Honest limits** — first full scan can be slow/RAM-heavy; community `INSTALL` not yet; macOS-first.

## Capability ladder (onboarding path)

Each rung is optional after the previous; **stopping early is success**.

### Rung 0 — Orient (~10 min)

- Read README positioning + privacy blurb.
- Confirm Mac + Xcode CLT + DuckDB CLI + `just`/`uv` ([QUICKSTART.md](QUICKSTART.md) requirements).
- **Done when:** they understand “scanner extension, unsigned `LOAD`, no real zip in repo.”

### Rung 1 — Core unlock: SQL on a fixture (~20–40 min)

```bash
git clone --recurse-submodules git@github.com:DataBooth/duckdb-apple-health.git
cd duckdb-apple-health
just bootstrap          # or: just configure && just debug
just demo
just demo-workouts
```

```sql
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
FROM read_apple_health('test/data/export.zip');
FROM apple_health_workouts('test/data/export.zip');
```

- **Done when:** fixture queries return rows; they trust the build.
- **Layer:** A (core extension) only.

### Rung 2 — Core unlock: their export (30–90+ min, size-dependent)

```bash
# Keep export.zip outside the repo
duckdb -unsigned
```

```sql
LOAD 'build/debug/extension/apple_health/apple_health.duckdb_extension';
SELECT type_short, count(*) AS n
FROM read_apple_health('/path/to/export.zip')
GROUP BY 1
ORDER BY n DESC
LIMIT 20;
```

Fast path they should learn immediately:

```sql
COPY (
  SELECT *
  FROM read_apple_health('/path/to/export.zip')
  WHERE type_short = 'HeartRate'
) TO 'hr.parquet' (FORMAT parquet);
```

- **Done when:** they see their type histogram / workout counts; zip stays private.
- **Layer:** A only.
- **Doc need:** clear note on RAM/time for multi-GB zips.

### Rung 3 — Local database (~15 min + build time)

```bash
just build-db export_zip=/path/to/export.zip
just list-walks 20
duckdb output/apple_health.duckdb
```

```sql
SHOW TABLES;
SELECT * FROM ingest_manifest;
```

- **Done when:** `output/apple_health.duckdb` exists; walks list without re-scanning the zip.
- **Mental model:** extension scans; **DB is the daily driver**.
- **Layer:** B (enriched local DB).

### Rung 4 — Enrichment (optional)

```bash
just geocode-places -- --limit 50
just photos-for-walks -- --limit-walks 40    # Mac + Photos library
just journey-import path/to/journey.yml
just journey-list
```

- **Done when:** SQL shows `route_places` / `walk_photos` / `journeys` as they choose to enable.
- **Privacy:** Photos access + precise GPS; artefacts under gitignored `output/`.
- **Layer:** B.

### Rung 5 — Stories (optional)

```bash
just walk-stories    # journey picker, map, filmstrip, full-size photo on pin click
# or lighter:
just map-walks
```

- **Done when:** they open Camino / Abel Tasman / a personal journey and browse sections + photos.
- **Export path (secondary):** HTML under `output/maps/` for sharing a snapshot without Terminal.
- **Layer:** C (add-ons).

## Messaging by surface

| Surface | Message |
|---------|---------|
| README hero | Technical Apple users; local SQL unlock; optional maps/stories |
| QUICKSTART | Rungs 1–2 only (fixture → own zip → Parquet tip) |
| ERD / this file + RELEASE_PLAN | Layers A/B/C |
| RELEASE_NOTES | “Core v0.1.0” vs “Add-ons preview” |
| `walk_stories` header | Already-unlocked DB users; journeys + Photos |

## Success metrics (qualitative for v0.1)

- Persona can complete **Rungs 1–2** from docs alone on a clean Mac.
- Persona understands they may stop at SQL and still have “unlocked” data.
- Persona who continues to Rung 5 does not need to understand C extension internals.
- No doc path requires committing Health or Photos data.

## Non-goals (keep explicit)

- One-click App Store app
- Windows-first or iPhone-only workflow
- Live HealthKit / background sync
- Automatic cloud backup of the DuckDB file
- Guaranteed community extension install before the DuckDB 2.0 ecosystem is ready

## Related

- Initial release plan (layers, phases, PR order): [RELEASE_PLAN.md](RELEASE_PLAN.md)
- Data model: [ERD.md](ERD.md)
- Longer roadmap: [ROADMAP.md](ROADMAP.md)
- Design constraints: [DESIGN.md](DESIGN.md)
