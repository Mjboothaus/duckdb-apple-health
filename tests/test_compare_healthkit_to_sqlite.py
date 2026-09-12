"""Compare healthkit_export extension output to dogsheep/healthkit-to-sqlite.

Semantic note
-------------
healthkit-to-sqlite's pull-parser yields **every** ``</Record>`` end event, including
``Record`` elements nested under ``Correlation``.

Our extension intentionally emits **top-level** ``Record`` tags only (see
docs/DESIGN.md): Correlation children are skipped because the
same BP samples also appear as top-level Records in real exports and in our fixture.

On the synthetic fixture that means:
  healthkit-to-sqlite record rows = 9  (7 top-level + 2 nested BP)
  read_healthkit_export rows          = 7  (top-level only)

Comparisons below assert equality on the **deduped / top-level** multiset, and
document the nested extras explicitly.
"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from tests.helpers import (
    approx_equal,
    duck_records,
    duck_summaries,
    duck_workouts,
    healthkit_sqlite_from_xml,
    hk_all_records,
    sql_path,
)


def _num_key(v) -> str:
    """Return canonical numeric string, or empty if not a finite number."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if math.isnan(f) or math.isinf(f):
        return ""
    return f"{f:.10g}"


def record_identity(type_short: str, start: str, end: str, value, value_text: str, source: str) -> tuple:
    """Stable identity for multiset comparison (ignores device noise)."""
    vt = value_text or ""
    if _num_key(value):
        vt = ""  # numeric path: ignore empty/non-empty text variance
    return (
        type_short,
        start or "",
        end or "",
        _num_key(value),
        vt,
        source or "",
    )


@pytest.fixture(scope="module")
def hk_db_path(fixture_xml: Path) -> Path:
    path = healthkit_sqlite_from_xml(fixture_xml)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def hk_conn(hk_db_path: Path):
    conn = sqlite3.connect(hk_db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_hk_fixture_import_tables(hk_conn):
    tables = {
        r[0]
        for r in hk_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        )
    }
    assert "workouts" in tables
    assert "activity_summary" in tables
    # per-type record tables
    assert "rHeartRate" in tables
    assert "rStepCount" in tables
    assert "rSleepAnalysis" in tables


def test_record_counts_document_correlation_difference(con, fixture_zip, hk_conn):
    duck_n = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{sql_path(fixture_zip)}')"
    ).fetchone()[0]
    hk_recs = hk_all_records(hk_conn)
    assert duck_n == 7
    assert len(hk_recs) == 9  # +2 nested Correlation BP records

    nested_extra = len(hk_recs) - duck_n
    assert nested_extra == 2


def test_top_level_record_multiset_matches_hk(con, fixture_zip, hk_conn):
    """After removing one nested BP pair from HK, multisets of identities match."""

    def key_from_parts(type_short, value, value_text, source_name, unit) -> tuple:
        numeric = _num_key(value)
        if numeric:
            return (type_short, numeric, "", source_name or "", unit or "")
        return (type_short, "", value_text or "", source_name or "", unit or "")

    duck = duck_records(con, fixture_zip)
    duck_keys = Counter()
    for r in duck.itertuples(index=False):
        val = None if pd.isna(r.value) else r.value
        text = "" if val is not None else (r.value_text or "")
        duck_keys[key_from_parts(r.type_short, val, text, r.source_name, r.unit)] += 1

    hk_keys = Counter()
    for r in hk_all_records(hk_conn):
        raw = r.get("value")
        numeric = _num_key(raw)
        if numeric:
            val, text = raw, ""
        else:
            val, text = None, raw or ""
        hk_keys[
            key_from_parts(r["type_short"], val, text, r.get("sourceName"), r.get("unit"))
        ] += 1

    # Nested Correlation BP duplicates
    bp_sys = ("BloodPressureSystolic", "118", "", "Demo Phone", "mmHg")
    bp_dia = ("BloodPressureDiastolic", "76", "", "Demo Phone", "mmHg")
    assert hk_keys[bp_sys] == 2
    assert hk_keys[bp_dia] == 2
    hk_top = hk_keys.copy()
    hk_top[bp_sys] -= 1
    hk_top[bp_dia] -= 1

    assert duck_keys == hk_top



def test_workout_matches_hk(con, fixture_zip, hk_conn):
    duck = duck_workouts(con, fixture_zip)
    assert len(duck) == 1
    hk = hk_conn.execute("SELECT * FROM workouts").fetchone()
    assert hk is not None
    assert "Running" in hk["workoutActivityType"]
    assert float(hk["duration"]) == pytest.approx(float(duck.iloc[0]["duration"]))
    assert float(hk["totalDistance"]) == pytest.approx(float(duck.iloc[0]["total_distance"]))
    assert float(hk["totalEnergyBurned"]) == pytest.approx(float(duck.iloc[0]["total_energy"]))
    assert (hk["sourceName"] or "") == (duck.iloc[0]["source_name"] or "")


def test_activity_summary_matches_hk(con, fixture_xml, hk_conn):
    duck = duck_summaries(con, fixture_xml)
    hk_rows = list(hk_conn.execute("SELECT * FROM activity_summary ORDER BY dateComponents"))
    assert len(duck) == len(hk_rows) == 2

    for drow, hrow in zip(duck.itertuples(index=False), hk_rows):
        assert drow.date_components == hrow["dateComponents"]
        assert approx_equal(drow.active_energy_burned, hrow["activeEnergyBurned"])
        # old vs new move attrs
        if hrow["dateComponents"] == "2020-06-01":
            assert approx_equal(drow.apple_move_minutes, hrow["appleMoveMinutes"])
            assert drow.apple_move_time is None or (
                isinstance(drow.apple_move_time, float) and math.isnan(drow.apple_move_time)
            )
        if hrow["dateComponents"] == "2026-01-15":
            assert approx_equal(drow.apple_move_time, hrow["appleMoveTime"])


@pytest.mark.slow
def test_optional_real_export_counts_finite(con, real_export_zip):
    """Optional: APPLE_HEALTH_EXPORT_ZIP=/path/to/export.zip pytest -m slow"""
    if real_export_zip is None:
        pytest.skip("Set APPLE_HEALTH_EXPORT_ZIP to run real-export checks")
    n = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{sql_path(real_export_zip)}')"
    ).fetchone()[0]
    w = con.execute(
        f"SELECT count(*) FROM healthkit_workouts('{sql_path(real_export_zip)}')"
    ).fetchone()[0]
    s = con.execute(
        f"SELECT count(*) FROM healthkit_activity_summaries('{sql_path(real_export_zip)}')"
    ).fetchone()[0]
    assert n > 0
    assert w >= 0
    assert s >= 0
