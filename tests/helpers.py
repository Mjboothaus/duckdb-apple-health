"""Helpers for comparing apple_health extension output to healthkit-to-sqlite."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import duckdb
from healthkit_to_sqlite.utils import convert_xml_to_sqlite
from sqlite_utils import Database


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def duck_records(con: duckdb.DuckDBPyConnection, path: Path):
    return con.execute(
        f"""
        SELECT type, type_short, unit, value, value_text,
               start_date, end_date, source_name, source_version
        FROM read_apple_health('{sql_path(path)}')
        ORDER BY start_date, type_short, value NULLS FIRST, value_text
        """
    ).fetchdf()


def duck_workouts(con: duckdb.DuckDBPyConnection, path: Path):
    return con.execute(
        f"""
        SELECT activity_type, activity_type_short, duration, duration_unit,
               total_distance, total_distance_unit, total_energy, total_energy_unit,
               source_name
        FROM apple_health_workouts('{sql_path(path)}')
        ORDER BY start_date, activity_type_short
        """
    ).fetchdf()


def duck_workout_routes(con: duckdb.DuckDBPyConnection, path: Path):
    return con.execute(
        f"""
        SELECT workout_activity_type_short, gpx_path, source_name
        FROM apple_health_workout_routes('{sql_path(path)}')
        ORDER BY start_date, gpx_path
        """
    ).fetchdf()


def duck_route_points(con: duckdb.DuckDBPyConnection, path: Path):
    return con.execute(
        f"""
        SELECT gpx_path, point_index, lat, lon, ele, time
        FROM apple_health_workout_route_points('{sql_path(path)}')
        ORDER BY gpx_path, point_index
        """
    ).fetchdf()


def duck_summaries(con: duckdb.DuckDBPyConnection, path: Path):
    return con.execute(
        f"""
        SELECT date_components,
               active_energy_burned,
               apple_move_minutes,
               apple_move_time,
               apple_exercise_time,
               apple_stand_hours
        FROM apple_health_activity_summaries('{sql_path(path)}')
        ORDER BY date_components
        """
    ).fetchdf()


def healthkit_sqlite_from_xml(xml_path: Path) -> Path:
    """Run healthkit-to-sqlite conversion into a temp SQLite file; return path."""
    tmp = tempfile.NamedTemporaryFile(prefix="hk2sqlite_", suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    with xml_path.open("rb") as fp:
        convert_xml_to_sqlite(fp, db, progress_callback=None, zipfile=None)
    return db_path


def hk_record_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'r%' ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


def hk_all_records(conn: sqlite3.Connection) -> list[dict]:
    """Flatten healthkit-to-sqlite per-type tables into a list of record dicts."""
    out: list[dict] = []
    for table in hk_record_tables(conn):
        type_short = table[1:]  # strip leading 'r'
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for row in conn.execute(f"SELECT * FROM {table}").fetchall():
            rec = dict(zip(cols, row))
            rec["type_short"] = type_short
            out.append(rec)
    return out


def approx_equal(a, b, tol: float = 1e-9) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return str(a) == str(b)
