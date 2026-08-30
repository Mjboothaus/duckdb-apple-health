#!/usr/bin/env python3
"""Build output/apple_health.duckdb from an Apple Health export.zip.

Uses the local apple_health extension. Real exports stay outside git.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "output" / "apple_health.duckdb"
EXT_CANDIDATES = [
    REPO / "build/debug/extension/apple_health/apple_health.duckdb_extension",
    REPO / "build/debug/apple_health.duckdb_extension",
    REPO / "build/release/extension/apple_health/apple_health.duckdb_extension",
]


def find_extension() -> Path:
    for p in EXT_CANDIDATES:
        if p.is_file():
            return p
    raise SystemExit(
        "apple_health.duckdb_extension not found. Run `just debug` first."
    )


def sql_str(s: str) -> str:
    return s.replace("'", "''")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "export_zip",
        type=Path,
        help="Path to export.zip / export.xml / export directory (outside repo)",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Output DuckDB path (default: {DEFAULT_DB})",
    )
    ap.add_argument(
        "--activities",
        default="Walking,Hiking",
        help="Comma-separated activity_type_short values (default: Walking,Hiking)",
    )
    ap.add_argument(
        "--map-points-per-route",
        type=int,
        default=1500,
        help="Max points kept per route in route_points_map (default: 1500)",
    )
    args = ap.parse_args()

    export = args.export_zip.expanduser().resolve()
    if not export.exists():
        raise SystemExit(f"Export not found: {export}")

    activities = [a.strip() for a in args.activities.split(",") if a.strip()]
    if not activities:
        raise SystemExit("No activities given")
    in_list = ", ".join(f"'{sql_str(a)}'" for a in activities)

    ext = find_extension()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()

    path_sql = sql_str(export.as_posix())
    db_sql = sql_str(args.db.as_posix())
    ext_sql = sql_str(ext.as_posix())
    max_pts = max(10, int(args.map_points_per_route))

    print(f"extension: {ext}")
    print(f"export:    {export}")
    print(f"database:  {args.db}")
    print(f"activities: {activities}")
    print("Scanning export (this can take several minutes on large zips)…")
    t0 = time.perf_counter()

    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    con.execute(f"LOAD '{ext_sql}'")

    # Build into a temp in-memory then write, or build attached file directly
    con.execute(f"ATTACH '{db_sql}' AS health")
    con.execute("CREATE SCHEMA IF NOT EXISTS health.gps")
    con.execute("CREATE SCHEMA IF NOT EXISTS health.meta")

    print("  → workouts …", flush=True)
    t = time.perf_counter()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE health.gps.workouts AS
        SELECT
          activity_type,
          activity_type_short,
          duration,
          duration_unit,
          total_distance,
          total_distance_unit,
          total_energy,
          total_energy_unit,
          start_date,
          end_date,
          creation_date,
          source_name,
          source_version,
          device,
          filename AS export_member
        FROM apple_health_workouts('{path_sql}')
        WHERE activity_type_short IN ({in_list})
        """
    )
    print(f"     done in {time.perf_counter()-t:.1f}s", flush=True)

    print("  → routes …", flush=True)
    t = time.perf_counter()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE health.gps.routes AS
        SELECT
          workout_activity_type,
          workout_activity_type_short AS activity_type_short,
          workout_start_date,
          workout_end_date,
          start_date AS route_start_date,
          end_date AS route_end_date,
          creation_date,
          source_name,
          source_version,
          device,
          gpx_path,
          filename AS export_member
        FROM apple_health_workout_routes('{path_sql}')
        WHERE workout_activity_type_short IN ({in_list})
          AND gpx_path IS NOT NULL AND length(gpx_path) > 0
        """
    )
    print(f"     done in {time.perf_counter()-t:.1f}s", flush=True)

    print("  → route_points (full GPS; slowest) …", flush=True)
    t = time.perf_counter()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE health.gps.route_points AS
        SELECT
          gpx_path,
          gpx_member,
          workout_activity_type_short AS activity_type_short,
          workout_start_date,
          workout_end_date,
          point_index,
          lat,
          lon,
          ele,
          time AS point_time,
          speed,
          course,
          h_acc,
          v_acc,
          filename AS export_member
        FROM apple_health_workout_route_points('{path_sql}')
        WHERE workout_activity_type_short IN ({in_list})
        """
    )
    print(f"     done in {time.perf_counter()-t:.1f}s", flush=True)

    print("  → route_points_map (downsample) …", flush=True)
    t = time.perf_counter()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE health.gps.route_points_map AS
        WITH ranked AS (
          SELECT
            *,
            row_number() OVER (PARTITION BY gpx_path ORDER BY point_index) AS rn,
            count(*) OVER (PARTITION BY gpx_path) AS n
          FROM health.gps.route_points
        )
        SELECT
          gpx_path, gpx_member, activity_type_short,
          workout_start_date, workout_end_date,
          point_index, lat, lon, ele, point_time,
          speed, course, h_acc, v_acc, export_member
        FROM ranked
        WHERE rn = 1 OR rn = n
           OR (rn % greatest(CAST(ceil(n / {max_pts}.0) AS BIGINT), 1)) = 0
        """
    )
    print(f"     done in {time.perf_counter()-t:.1f}s", flush=True)

    con.execute("DROP TABLE IF EXISTS health.meta.ingest_manifest")
    con.execute(
        """
        CREATE TABLE health.meta.ingest_manifest AS
        SELECT
          now() AS built_at,
          ? AS source_path,
          ? AS note,
          (SELECT count(*) FROM health.gps.workouts) AS workouts_n,
          (SELECT count(*) FROM health.gps.routes) AS routes_n,
          (SELECT count(*) FROM health.gps.route_points) AS route_points_n,
          (SELECT count(*) FROM health.gps.route_points_map) AS route_points_map_n
        """,
        [
            str(export),
            f"activities={','.join(activities)}; map_points_per_route={max_pts}",
        ],
    )

    # Main-schema views for simple notebook SQL
    for name in ("workouts", "routes", "route_points", "route_points_map"):
        con.execute(
            f"CREATE OR REPLACE VIEW health.main.{name} AS SELECT * FROM health.gps.{name}"
        )
    con.execute(
        "CREATE OR REPLACE VIEW health.main.ingest_manifest AS SELECT * FROM health.meta.ingest_manifest"
    )

    # Also expose without schema prefix when opening the file alone:
    # views already on main after ATTACH as health — when opening file directly,
    # gps.* tables exist; create main views on the file via:
    con.execute("DETACH health")
    # Re-open file and ensure main views exist for duckdb path open
    con2 = duckdb.connect(str(args.db))
    for name in ("workouts", "routes", "route_points", "route_points_map"):
        con2.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM gps.{name}")
    con2.execute(
        "CREATE OR REPLACE VIEW ingest_manifest AS SELECT * FROM meta.ingest_manifest"
    )
    rows = con2.execute(
        """
        SELECT 'workouts' AS t, count(*)::BIGINT n FROM workouts
        UNION ALL SELECT 'routes', count(*) FROM routes
        UNION ALL SELECT 'route_points', count(*) FROM route_points
        UNION ALL SELECT 'route_points_map', count(*) FROM route_points_map
        """
    ).fetchall()
    man = con2.execute("SELECT * FROM ingest_manifest").fetchdf()
    con2.close()
    con.close()

    elapsed = time.perf_counter() - t0
    print()
    print(man.to_string(index=False))
    print()
    for t, n in rows:
        print(f"  {t:20s} {n:>12,}")
    print(f"\nBuilt {args.db} in {elapsed:.1f}s")
    print("Map with: just map-walks")


if __name__ == "__main__":
    main()
