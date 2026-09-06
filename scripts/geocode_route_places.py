#!/usr/bin/env python3
"""Batch reverse-geocode route start/end points into gps.route_places."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "python"))

from health_data_store import DEFAULT_DB_PATH, HealthDataStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DuckDB path")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max routes to geocode this run (default: all missing)",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Re-geocode even when place labels already exist",
    )
    ap.add_argument(
        "--cache-only",
        action="store_true",
        help="Do not call Nominatim; only use output/geocode_cache.json",
    )
    args = ap.parse_args()

    db = Path(args.db).expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"Database not found: {db}")

    print(f"database: {db}")
    print(
        f"mode:     {'all' if args.all else 'missing only'}; "
        f"fetch={'no' if args.cache_only else 'nominatim+cache'}; "
        f"limit={args.limit or 'none'}",
        flush=True,
    )

    store = HealthDataStore(db, read_only=False)
    try:
        stats = store.materialise_route_places(
            only_missing=not args.all,
            fetch=not args.cache_only,
            limit=args.limit,
        )
    finally:
        store.close()

    print(
        f"done: considered={stats['considered']} written={stats['written']} "
        f"failed={stats['failed']}"
    )
    print("Query: SELECT * FROM route_places LIMIT 10;")
    print("List:  just list-walks 10")


if __name__ == "__main__":
    main()
