#!/usr/bin/env python3
"""Sync root VERSION into pyproject.toml; print extension/python versions."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "pyproject.toml"
EXT_VERSION_FILE = ROOT / "configure" / "extension_version.txt"


def read_version() -> str:
    if not VERSION_FILE.is_file():
        raise SystemExit(f"Missing {VERSION_FILE}")
    v = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?", v):
        raise SystemExit(f"Invalid VERSION: {v!r}")
    return v


def sync_pyproject(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new, n = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit("Could not find version = \"...\" in pyproject.toml")
    PYPROJECT.write_text(new, encoding="utf-8")


def git_tag_at_head() -> str | None:
    r = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tags = [t for t in r.stdout.splitlines() if t.strip()]
    return tags[0] if tags else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sync", action="store_true", help="Write VERSION into pyproject.toml")
    args = ap.parse_args()
    version = read_version()
    if args.sync:
        sync_pyproject(version)
        print(f"pyproject.toml version → {version}")

    # report
    py_v = None
    m = re.search(r'(?m)^version\s*=\s*"([^"]*)"', PYPROJECT.read_text(encoding="utf-8"))
    if m:
        py_v = m.group(1)
    ext = EXT_VERSION_FILE.read_text(encoding="utf-8").strip() if EXT_VERSION_FILE.is_file() else "(run just configure)"
    tag = git_tag_at_head() or "(none at HEAD)"
    print(f"VERSION file:     {version}")
    print(f"pyproject:        {py_v}")
    print(f"git tag @ HEAD:   {tag}")
    print(f"extension meta:   {ext}")
    print(f"release tag form: v{version}")
    if py_v != version:
        print("WARNING: pyproject version != VERSION (run: just version-sync)")


if __name__ == "__main__":
    main()
