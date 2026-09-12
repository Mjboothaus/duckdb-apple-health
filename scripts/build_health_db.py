#!/usr/bin/env python3
"""CLI: build output/healthkit_store.duckdb from an Apple Health export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without installing the package.
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "python"))

from healthkit_store import HealthkitStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export_zip", type=Path, help="Path to export.zip / xml / directory")
    ap.add_argument("--db", type=Path, default=None, help="Output DuckDB path")
    ap.add_argument(
        "--activities",
        default="Walking,Hiking",
        help="Comma-separated activity_type_short values",
    )
    ap.add_argument("--map-points-per-route", type=int, default=1500)
    args = ap.parse_args()

    activities = [a.strip() for a in args.activities.split(",") if a.strip()]
    print(f"export:     {args.export_zip}")
    print(f"activities: {activities}")
    print("Scanning export (this can take several minutes on large zips)…", flush=True)

    result = HealthkitStore.build_from_export(
        args.export_zip,
        db_path=args.db,
        activities=activities,
        map_points_per_route=args.map_points_per_route,
    )
    print()
    print(f"database:   {result.db_path}")
    print(f"  workouts          {result.workouts_n:>12,}")
    print(f"  routes            {result.routes_n:>12,}")
    print(f"  route_points      {result.route_points_n:>12,}")
    print(f"  route_points_map {result.route_points_map_n:>12,}")
    print(f"Built in {result.elapsed_seconds:.1f}s")
    print("Map with: just map-walks")


if __name__ == "__main__":
    main()
