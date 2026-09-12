"""Smoke / golden tests for the apple_health DuckDB extension (no external tool)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.helpers import duck_records, duck_summaries, duck_route_points, duck_workout_routes, duck_workouts, sql_path


def test_extension_loads(con, fixture_zip):
    # Table function is registered and callable
    n = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{fixture_zip.as_posix()}')"
    ).fetchone()[0]
    assert n == 7


def test_fixture_record_count_zip_and_xml(con, fixture_zip, fixture_xml):
    n_zip = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{sql_path(fixture_zip)}')"
    ).fetchone()[0]
    n_xml = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{sql_path(fixture_xml)}')"
    ).fetchone()[0]
    assert n_zip == 7
    assert n_xml == 7


def test_fixture_matches_golden_csv(con, fixture_zip, golden_records_csv):
    golden = pd.read_csv(golden_records_csv, dtype=str).fillna("")
    got = duck_records(con, fixture_zip)

    assert len(got) == len(golden) == 7

    # Match on type + source + value/value_text (two HeartRate rows share source).
    remaining = got.copy()
    for _, grow in golden.iterrows():
        gval = grow["value"]
        subset = remaining[
            (remaining["type"] == grow["type"])
            & (remaining["type_short"] == grow["type_short"])
            & (remaining["source_name"] == grow["source_name"])
        ]
        if gval == "":
            subset = subset[subset["value"].isna() & (subset["value_text"].fillna("") == grow["value_text"])]
        else:
            subset = subset[subset["value"].notna()]
            subset = subset[subset["value"].astype(float).sub(float(gval)).abs() < 1e-9]
        assert not subset.empty, f"missing golden row {grow.to_dict()}"
        idx = subset.index[0]
        row = remaining.loc[idx]
        assert (row["unit"] or "") == (grow["unit"] or "")
        remaining = remaining.drop(index=idx)
    assert remaining.empty


def test_fixture_sleep_value_text(con, fixture_zip):
    sleep = con.execute(
        f"""
        SELECT value, value_text FROM read_healthkit_export('{sql_path(fixture_zip)}')
        WHERE type_short = 'SleepAnalysis'
        """
    ).fetchdf()
    assert len(sleep) == 1
    assert pd.isna(sleep.loc[0, "value"])
    assert sleep.loc[0, "value_text"] == "HKCategoryValueSleepAnalysisAsleepCore"


def test_fixture_cafe_source_name(con, fixture_zip):
    n = con.execute(
        f"""
        SELECT count(*) FROM read_healthkit_export('{sql_path(fixture_zip)}')
        WHERE source_name = 'Café Run Club'
        """
    ).fetchone()[0]
    assert n == 1


def test_fixture_dates_are_timestamptz(con, fixture_zip):
    t = con.execute(
        f"""
        SELECT typeof(start_date) FROM read_healthkit_export('{sql_path(fixture_zip)}') LIMIT 1
        """
    ).fetchone()[0]
    assert t == "TIMESTAMP WITH TIME ZONE"


def test_fixture_filename_from_zip_member(con, fixture_zip):
    name = con.execute(
        f"SELECT DISTINCT filename FROM read_healthkit_export('{sql_path(fixture_zip)}')"
    ).fetchone()[0]
    assert name.endswith("export.xml")
    assert "apple_health_export" in name or name == "export.xml"


def test_fixture_workouts(con, fixture_zip):
    w = duck_workouts(con, fixture_zip)
    assert len(w) == 1
    assert w.iloc[0]["activity_type_short"] == "Running"
    assert float(w.iloc[0]["duration"]) == pytest.approx(25.0)
    assert float(w.iloc[0]["total_distance"]) == pytest.approx(4.2)
    assert float(w.iloc[0]["total_energy"]) == pytest.approx(280.0)


def test_fixture_activity_summaries_old_and_new_attrs(con, fixture_xml):
    s = duck_summaries(con, fixture_xml)
    assert len(s) == 2
    old = s[s["date_components"] == "2020-06-01"].iloc[0]
    new = s[s["date_components"] == "2026-01-15"].iloc[0]
    assert float(old["apple_move_minutes"]) == pytest.approx(32.0)
    assert pd.isna(old["apple_move_time"])
    assert pd.isna(new["apple_move_minutes"])
    assert float(new["apple_move_time"]) == pytest.approx(41.0)
    assert float(old["active_energy_burned"]) == pytest.approx(410.0)
    assert float(new["active_energy_burned"]) == pytest.approx(520.0)


def test_directory_path(con, fixture_xml, repo_root):
    data_dir = fixture_xml.parent
    n = con.execute(
        f"SELECT count(*) FROM read_healthkit_export('{sql_path(data_dir)}')"
    ).fetchone()[0]
    assert n == 7


def test_fixture_workout_routes(con, fixture_zip):
    r = duck_workout_routes(con, fixture_zip)
    assert len(r) == 1
    assert r.iloc[0]["workout_activity_type_short"] == "Running"
    assert r.iloc[0]["gpx_path"] == "/workout-routes/route_2026-01-15_7.25am.gpx"
    assert r.iloc[0]["source_name"] == "Demo Phone"


def test_fixture_route_points(con, fixture_zip):
    p = duck_route_points(con, fixture_zip)
    assert len(p) == 3
    assert p.iloc[0]["gpx_path"] == "/workout-routes/route_2026-01-15_7.25am.gpx"
    assert float(p.iloc[0]["lat"]) == pytest.approx(-33.8688)
    assert float(p.iloc[0]["lon"]) == pytest.approx(151.2093)
    assert float(p.iloc[0]["ele"]) == pytest.approx(12.0)
    assert list(p["point_index"].astype(int)) == [0, 1, 2]
