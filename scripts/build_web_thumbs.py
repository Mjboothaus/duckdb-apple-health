#!/usr/bin/env python3
"""Pre-build small web thumbs for maps/marimo (on-demand cache warmer)."""

from __future__ import annotations

import sys
from pathlib import Path

from health_data_store import HealthDataStore
from health_data_store.photos import prepare_photos_for_map

def main() -> None:
    journey_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else None
    store = HealthDataStore()
    store.connect()
    if journey_id:
        ph = store.photos_for_journey(journey_id)
        label = journey_id
    else:
        ph = store.photos_for_gpx()
        label = "all walk_photos"
    store.close()
    if ph is None or ph.empty:
        print(f"No photos for {label}")
        return
    out = prepare_photos_for_map(ph)
    n = out["web_thumb_path"].notna().sum() if "web_thumb_path" in out.columns else 0
    print(f"{label}: {n}/{len(out)} web thumbs ready under output/photo_web_thumbs/")

if __name__ == "__main__":
    main()
