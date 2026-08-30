# Data model (export → scanner → local DuckDB)

How an Apple Health **export.zip** becomes tables you can query and map.

See also: [DESIGN.md](DESIGN.md), [ROADMAP.md](ROADMAP.md).

Last updated: 2026-08-30.

---

## Big picture

```text
export.zip  (full snapshot, outside git)
    │
    ▼
extension table functions   (scan; occasional, can be slow)
    │
    ▼
output/apple_health.duckdb  (local database; gitignored)
    │
    ▼
SQL / map notebook          (fast, everyday)
```

| Piece | What it is |
|---|---|
| **Extension** | C scanner: reads a zip/xml path, returns rows. No permanent storage. |
| **Local database** | One DuckDB file with clear table names. Built by `just build-db`. |
| **Notebooks** | Explore metrics *or* map walks — they should prefer the database, not re-scan the zip. |

---

## What is inside the zip

```mermaid
flowchart TB
  subgraph zip["export.zip"]
    XML["export.xml"]
    GPX["workout-routes/*.gpx"]
  end
  XML --> WO["Workout rows"]
  XML --> WR["WorkoutRoute + FileReference gpx_path"]
  XML --> REC["Records / activity summaries / …"]
  WR --> GPX
  GPX --> PT["Track points trkpt"]
```

- Each export is usually a **full dump**, not a “only new data” package.
- Outdoor walks/hikes often have a GPX; indoor workouts often do not.

---

## Scanner (table functions)

No persistent schema — each call scans `path`:

| Function | One row means |
|---|---|
| `apple_health_workouts(path)` | A workout summary (type, duration, distance, energy, dates) |
| `apple_health_workout_routes(path)` | A GPS route index (`gpx_path` + parent workout dates/type) |
| `apple_health_workout_route_points(path)` | One GPS point (`lat`/`lon`/…) |
| `read_apple_health(path)` | A Health record sample |
| `apple_health_activity_summaries(path)` | One day of rings |

```mermaid
erDiagram
  WORKOUT ||--o| ROUTE : "soft match type+start"
  ROUTE ||--|{ POINT : "gpx_path"

  WORKOUT {
    string activity_type_short
    timestamptz start_date
    double duration
    double total_distance
  }
  ROUTE {
    string gpx_path
    string activity_type_short
    timestamptz workout_start_date
  }
  POINT {
    string gpx_path
    bigint point_index
    double lat
    double lon
    timestamptz time
  }
```

**Joins**

| From → to | Key | Notes |
|---|---|---|
| Route → points | **`gpx_path`** | Strong — use for maps |
| Workout → route | type + start/end (+ source) | Soft — good enough for UI |

---

## Local database layout

**File:** `output/apple_health.duckdb` (under gitignored `output/`)

```mermaid
erDiagram
  workouts ||--o| routes : "soft"
  routes ||--|{ route_points : "gpx_path"
  routes ||--|{ route_points_map : "gpx_path"
  ingest_manifest ||--o{ workouts : "load batch"

  workouts {
    string activity_type_short
    timestamptz start_date
    timestamptz end_date
    double duration
    double total_distance
    double total_energy
    string source_name
  }
  routes {
    string gpx_path PK
    string activity_type_short
    timestamptz workout_start_date
    timestamptz workout_end_date
    string source_name
  }
  route_points {
    string gpx_path FK
    bigint point_index
    double lat
    double lon
    double ele
    timestamptz point_time
  }
  route_points_map {
    string gpx_path FK
    bigint point_index
    double lat
    double lon
  }
  ingest_manifest {
    timestamp built_at
    string source_path
    string note
    bigint workouts_n
    bigint routes_n
    bigint route_points_n
    bigint route_points_map_n
  }
```

| Table / view | Purpose |
|---|---|
| `workouts` | Workout summaries loaded into the DB |
| `routes` | Routes that have a `gpx_path` |
| `route_points` | Full GPS detail |
| `route_points_map` | **Downsampled** points for drawing maps (~≤1500 points per route) |
| `ingest_manifest` | When the DB was built and from what |

Default `just build-db` loads **Walking** and **Hiking** (override with `activities=`). Other activity types can be added the same way later.

---

## How to build and use it

```bash
# Build / rebuild the local database from a real export (outside the repo)
just build-db export_zip=/path/to/export.zip

# Optional: only some activities (comma-separated)
just build-db export_zip=/path/to/export.zip activities=Walking,Hiking,Running

# Open it
duckdb output/apple_health.duckdb
SHOW TABLES;
SELECT * FROM ingest_manifest;
SELECT activity_type_short, workout_start_date, gpx_path
FROM routes ORDER BY workout_start_date DESC LIMIT 10;

# Map walks (reads the DB only — no zip scan)
just map-walks
```

```sql
-- Points for one route (map layer)
SELECT point_index, lat, lon, ele, point_time
FROM route_points_map
WHERE gpx_path = '/workout-routes/route_….gpx'
ORDER BY point_index;
```

---

## Incremental exports (later)

Apple still gives **full** zips. Updating over time means **merge into this database** (append new `gpx_path`s, replace points if a GPX changed), not “diff zip format”. Options are spelled out in [ROADMAP.md](ROADMAP.md) (*Progressive exports & local database*).

---

## Python helper

Reusable (non-notebook) API:

```text
python/apple_health_data/
  store.py   # HealthDataStore — open DB, list_routes, route_points, build_from_export
  maps.py    # build_route_map, downsample_points (Folium, no marimo)
```

`notebooks/map_walks.py` is UI-only. `scripts/build_health_db.py` calls `HealthDataStore.build_from_export`.

## Privacy

- Real zips and `output/apple_health.duckdb` stay **off git**.
- GPS is precise location — treat carefully.
