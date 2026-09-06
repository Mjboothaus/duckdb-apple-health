#!/usr/bin/env python3
"""Create / import / list multi-section journeys in the local health DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "python"))

from apple_health_data import DEFAULT_DB_PATH, HealthDataStore  # noqa: E402
from apple_health_data.journeys import create_journey, set_sections  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List journeys")
    p_imp = sub.add_parser("import", help="Import YAML manifest")
    p_imp.add_argument("manifest", type=Path)
    p_new = sub.add_parser("create", help="Create empty journey")
    p_new.add_argument("journey_id")
    p_new.add_argument("title")
    p_new.add_argument("--notes", default="")
    p_sec = sub.add_parser("sections", help="Show sections")
    p_sec.add_argument("journey_id")
    p_set = sub.add_parser("set-sections", help="Replace sections from gpx paths file (one per line)")
    p_set.add_argument("journey_id")
    p_set.add_argument("paths_file", type=Path, help="Text file: one gpx_path per line")

    args = ap.parse_args()
    store = HealthDataStore(args.db, read_only=False)
    try:
        con = store._write_con()
        if args.cmd == "list":
            df = store.list_journeys()
            if df.empty:
                print("(no journeys yet)")
            else:
                print(df.to_string(index=False))
        elif args.cmd == "import":
            info = store.import_journey_manifest(args.manifest)
            print(f"imported {info.journey_id!r} — {info.sections_n} sections — {info.title}")
        elif args.cmd == "create":
            jid = create_journey(con, args.journey_id, args.title, args.notes)
            print(f"created {jid}")
        elif args.cmd == "sections":
            df = store.journey_sections(args.journey_id)
            print(df.to_string(index=False) if not df.empty else "(no sections)")
        elif args.cmd == "set-sections":
            lines = [
                ln.strip()
                for ln in Path(args.paths_file).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            create_journey(con, args.journey_id, args.journey_id)
            n = set_sections(
                con,
                args.journey_id,
                [{"gpx_path": p, "index": i} for i, p in enumerate(lines, start=1)],
            )
            print(f"set {n} sections on {args.journey_id}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
