"""Tests for apple_health_data.HealthDataStore (uses local DB if present)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python"))

from apple_health_data import HealthDataStore, downsample_points  # noqa: E402

DB = REPO / "output" / "apple_health.duckdb"


@pytest.mark.skipif(not DB.is_file(), reason="output/apple_health.duckdb not built")
def test_store_lists_routes_and_points():
    with HealthDataStore(DB) as store:
        summary = store.summary()
        assert set(summary["t"]) >= {"workouts", "routes", "route_points_map"}
        cat = store.list_routes(activities=["Walking", "Hiking"], limit=5)
        assert len(cat) >= 1
        assert "label" in cat.columns
        assert "gpx_path" in cat.columns
        chosen, pts = store.points_for_labels(cat, cat["label"].head(1).tolist())
        assert not chosen.empty
        assert not pts.empty
        assert {"lat", "lon", "point_index"} <= set(pts.columns)
        drawn = downsample_points(pts, max_total_points=500)
        assert len(drawn) <= len(pts)
        assert len(drawn) >= 2


def test_downsample_keeps_ends():
    import pandas as pd

    df = pd.DataFrame(
        {
            "gpx_path": ["a"] * 100,
            "point_index": list(range(100)),
            "lat": [0.0] * 100,
            "lon": [1.0] * 100,
            "activity": ["Walking"] * 100,
        }
    )
    out = downsample_points(df, max_total_points=20, min_per_route=10)
    assert out["point_index"].iloc[0] == 0
    assert out["point_index"].iloc[-1] == 99
    assert len(out) < 100


def test_format_nominatim_address_prefers_suburb():
    from apple_health_data import format_nominatim_address

    label = format_nominatim_address(
        {
            "display_name": "Long full name, Sydney, NSW, Australia",
            "address": {
                "road": "Kent Street",
                "suburb": "Sydney",
                "state": "New South Wales",
                "country": "Australia",
            },
        }
    )
    assert "Kent Street" in label
    assert "Sydney" in label


def test_reverse_geocoder_uses_cache(tmp_path):
    from apple_health_data import ReverseGeocoder

    cache = tmp_path / "geo.json"
    cache.write_text(
        '{"-33.8700,151.2100": {"lat": -33.87, "lon": 151.21, "label": "Test Place, NSW"}}\n',
        encoding="utf-8",
    )
    geo = ReverseGeocoder(cache_path=cache, min_interval_s=0)
    hit = geo.lookup(-33.87001, 151.21002, fetch=False)
    assert hit.label == "Test Place, NSW"


@pytest.mark.skipif(not DB.is_file(), reason="output/apple_health.duckdb not built")
def test_route_endpoints_and_enrich_offline():
    class FakeGeo:
        def lookup(self, lat, lon, *, fetch=True):
            from apple_health_data.places import PlaceLabel

            return PlaceLabel(lat=lat, lon=lon, label=f"P({lat:.2f},{lon:.2f})")

    with HealthDataStore(DB) as store:
        cat = store.list_routes(activities=["Walking", "Hiking"], limit=2)
        ends = store.route_endpoints(cat["gpx_path"].tolist())
        assert len(ends) >= 1
        assert {"start_lat", "start_lon", "end_lat", "end_lon"} <= set(ends.columns)
        enriched = store.enrich_with_places(cat, fetch=False, geocoder=FakeGeo())
        assert "start_place" in enriched.columns
        assert enriched["start_place"].notna().any()
