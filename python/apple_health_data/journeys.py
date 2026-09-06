"""Named multi-section journeys (e.g. Great North Walk) over route gpx_paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import duckdb
import pandas as pd
import yaml



def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "journey"


@dataclass
class JourneyInfo:
    journey_id: str
    title: str
    notes: str
    sections_n: int


def ensure_journey_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta.journeys (
          journey_id VARCHAR PRIMARY KEY,
          title VARCHAR NOT NULL,
          notes VARCHAR,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta.journey_sections (
          journey_id VARCHAR NOT NULL,
          section_index INTEGER NOT NULL,
          gpx_path VARCHAR NOT NULL,
          section_label VARCHAR,
          PRIMARY KEY (journey_id, section_index),
          UNIQUE (journey_id, gpx_path)
        )
        """
    )
    con.execute("CREATE OR REPLACE VIEW journeys AS SELECT * FROM meta.journeys")
    con.execute(
        "CREATE OR REPLACE VIEW journey_sections AS SELECT * FROM meta.journey_sections"
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW journey_overview AS
        SELECT
          j.journey_id,
          j.title,
          j.notes,
          count(s.section_index)::BIGINT AS sections_n,
          min(r.workout_start_date) AS first_start,
          max(r.workout_end_date) AS last_end,
          round(
            sum(
              date_diff('second', r.workout_start_date, r.workout_end_date) / 3600.0
            ),
            2
          ) AS total_hours
        FROM meta.journeys j
        LEFT JOIN meta.journey_sections s ON j.journey_id = s.journey_id
        LEFT JOIN routes r ON s.gpx_path = r.gpx_path
        GROUP BY j.journey_id, j.title, j.notes
        """
    )


def create_journey(
    con: duckdb.DuckDBPyConnection,
    journey_id: str,
    title: str,
    notes: str = "",
) -> str:
    ensure_journey_tables(con)
    jid = _slug(journey_id)
    con.execute(
        """
        INSERT INTO meta.journeys (journey_id, title, notes, created_at, updated_at)
        VALUES (?, ?, ?, now(), now())
        ON CONFLICT (journey_id) DO UPDATE SET
          title = excluded.title,
          notes = excluded.notes,
          updated_at = now()
        """,
        [jid, title.strip() or jid, notes or ""],
    )
    return jid


def set_sections(
    con: duckdb.DuckDBPyConnection,
    journey_id: str,
    sections: Sequence[dict[str, Any]],
) -> int:
    """Replace all sections. Each item: gpx_path, optional index/label."""
    ensure_journey_tables(con)
    jid = _slug(journey_id)
    exists = con.execute(
        "SELECT count(*) FROM meta.journeys WHERE journey_id = ?", [jid]
    ).fetchone()[0]
    if not exists:
        raise KeyError(f"Unknown journey_id: {jid} (create it first)")

    con.execute("DELETE FROM meta.journey_sections WHERE journey_id = ?", [jid])
    rows = []
    for i, sec in enumerate(sections, start=1):
        gpx = str(sec.get("gpx_path") or "").strip()
        if not gpx:
            continue
        idx = int(sec.get("index") or sec.get("section_index") or i)
        label = sec.get("label") or sec.get("section_label") or None
        rows.append((jid, idx, gpx, label))
    if rows:
        con.executemany(
            """
            INSERT INTO meta.journey_sections
              (journey_id, section_index, gpx_path, section_label)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
    con.execute(
        "UPDATE meta.journeys SET updated_at = now() WHERE journey_id = ?", [jid]
    )
    return len(rows)


def import_manifest(con: duckdb.DuckDBPyConnection, path: Path | str) -> JourneyInfo:
    p = Path(path).expanduser().resolve()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Journey manifest must be a mapping: {p}")
    jid = _slug(str(data.get("id") or data.get("journey_id") or p.stem))
    title = str(data.get("title") or jid)
    notes = str(data.get("notes") or "")
    create_journey(con, jid, title, notes)
    sections = data.get("sections") or []
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    n = set_sections(con, jid, sections)
    return JourneyInfo(journey_id=jid, title=title, notes=notes, sections_n=n)


def list_journeys(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    ensure_journey_tables(con)
    return con.execute(
        """
        SELECT * FROM journey_overview
        ORDER BY first_start NULLS LAST, journey_id
        """
    ).df()


def journey_sections_df(con: duckdb.DuckDBPyConnection, journey_id: str) -> pd.DataFrame:
    ensure_journey_tables(con)
    jid = _slug(journey_id)
    return con.execute(
        """
        SELECT
          s.section_index,
          s.gpx_path,
          s.section_label,
          r.activity_type_short AS activity,
          r.workout_start_date AS start_date,
          r.workout_end_date AS end_date,
          round(
            date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 1
          ) AS duration_min,
          pl.start_place,
          pl.end_place
        FROM meta.journey_sections s
        LEFT JOIN routes r ON s.gpx_path = r.gpx_path
        LEFT JOIN route_places pl ON s.gpx_path = pl.gpx_path
        WHERE s.journey_id = ?
        ORDER BY s.section_index
        """,
        [jid],
    ).df()
