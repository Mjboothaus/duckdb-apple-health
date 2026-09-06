#!/usr/bin/env python3
"""Match Apple Photos (Photos.sqlite) to walks; write walk_photos + thumbs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "python"))

from apple_health_data.photos import materialise_walk_photos  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--library", type=Path, default=None, help="Photos Library.photoslibrary")
    ap.add_argument("--limit-walks", type=int, default=None)
    ap.add_argument("--max-per-walk", type=int, default=40)
    ap.add_argument("--pad-minutes", type=float, default=5.0)
    ap.add_argument("--max-dist-m", type=float, default=120.0)
    ap.add_argument("--no-thumbs", action="store_true")
    args = ap.parse_args()

    stats = materialise_walk_photos(
        health_db=args.db,
        photos_library=args.library,
        limit_walks=args.limit_walks,
        max_photos_per_walk=args.max_per_walk,
        pad_minutes=args.pad_minutes,
        max_dist_m=args.max_dist_m,
        export_thumbnails=not args.no_thumbs,
    )
    print(f"library:  {stats.photos_library}")
    print(f"walks:    {stats.walks_considered}")
    print(f"rows:     {stats.rows_written}")
    print(f"thumbs:   {stats.thumbs_copied}")
    print("Query: SELECT * FROM walk_photos LIMIT 10;")


if __name__ == "__main__":
    main()
