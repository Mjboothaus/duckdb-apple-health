"""Map construction helpers (Folium) — no marimo dependency."""

from __future__ import annotations

import math
from typing import Mapping

import folium
import pandas as pd

DEFAULT_COLOURS: dict[str, str] = {
    "Walking": "#2563eb",
    "Hiking": "#16a34a",
    "Running": "#dc2626",
    "Cycling": "#9333ea",
    "TrailRunning": "#ea580c",
}


def downsample_points(
    points: pd.DataFrame,
    *,
    max_total_points: int = 6000,
    min_per_route: int = 50,
) -> pd.DataFrame:
    """Evenly downsample per ``gpx_path``, always keeping first and last point."""
    if points is None or points.empty:
        return points.iloc[0:0] if points is not None else pd.DataFrame()

    paths = points["gpx_path"].dropna().unique().tolist()
    n_paths = max(len(paths), 1)
    per = max(int(max_total_points) // n_paths, int(min_per_route))
    frames: list[pd.DataFrame] = []
    for _, grp in points.groupby("gpx_path", sort=False):
        g = grp.sort_values("point_index")
        if len(g) > per:
            step = max(1, math.ceil(len(g) / per))
            g = pd.concat([g.iloc[::step], g.iloc[[-1]]]).drop_duplicates("point_index")
        frames.append(g)
    return pd.concat(frames, ignore_index=True) if frames else points.iloc[0:0]


def build_route_map(
    chosen: pd.DataFrame,
    points: pd.DataFrame,
    *,
    max_total_points: int = 6000,
    height: int | str = 720,
    colours: Mapping[str, str] | None = None,
) -> tuple[folium.Map | None, pd.DataFrame, str]:
    """Build a Folium map for selected routes.

    Returns ``(map_or_none, drawn_points, status_message)``.
    Uses free tile layers that do not require API keys.
    ``height`` is pixels (int) or a CSS length string (default 720).
    """
    if chosen is None or chosen.empty:
        return None, pd.DataFrame(), "No routes selected."
    if points is None or points.empty:
        return None, pd.DataFrame(), "No points for selection."

    draw = downsample_points(points, max_total_points=max_total_points)
    if draw.empty or len(draw) < 2:
        return None, draw, "Not enough points to draw."

    palette = dict(DEFAULT_COLOURS if colours is None else colours)
    map_height = height if isinstance(height, str) else int(height)
    m = folium.Map(
        location=[float(draw["lat"].mean()), float(draw["lon"].mean())],
        zoom_start=12,
        tiles=None,
        control_scale=True,
        height=map_height,
    )
    # Free raster tiles only (no Mapbox / Stadia / Google keys).
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        name="OpenStreetMap",
        max_zoom=19,
    ).add_to(m)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles &copy; Esri",
        name="Streets",
        max_zoom=19,
    ).add_to(m)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles &copy; Esri",
        name="Topo",
        max_zoom=19,
    ).add_to(m)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles &copy; Esri",
        name="Satellite",
        max_zoom=19,
    ).add_to(m)

    bounds: list[tuple[float, float]] = []
    n_routes = 0
    for gpx, grp in draw.groupby("gpx_path", sort=False):
        g = grp.sort_values("point_index")
        act = str(g["activity"].iloc[0]) if "activity" in g.columns else ""
        colour = palette.get(act, "#334155")
        meta_rows = chosen[chosen["gpx_path"] == gpx]
        if meta_rows.empty:
            label = f"{act} · {gpx}"
            start_tip, end_tip = "Start", "End"
        else:
            meta = meta_rows.iloc[0]
            start_place = meta["start_place"] if "start_place" in meta.index and pd.notna(meta.get("start_place")) else None
            end_place = meta["end_place"] if "end_place" in meta.index and pd.notna(meta.get("end_place")) else None
            label = f"{meta['activity']} · {meta['start_date']} · {meta['duration_min']} min"
            if start_place or end_place:
                label = f"{label}<br/>{start_place or '?'} → {end_place or '?'}"
            start_tip = f"Start: {start_place}" if start_place else "Start"
            end_tip = f"End: {end_place}" if end_place else "End"
        coords = list(zip(g["lat"].tolist(), g["lon"].tolist()))
        if len(coords) < 2:
            continue
        n_routes += 1
        folium.PolyLine(coords, color=colour, weight=4, opacity=0.85, tooltip=label).add_to(m)
        folium.CircleMarker(coords[0], radius=5, color=colour, fill=True, tooltip=start_tip).add_to(m)
        folium.CircleMarker(
            coords[-1], radius=5, color=colour, fill=True, fill_opacity=0.4, tooltip=end_tip
        ).add_to(m)
        bounds.extend(coords)

    if bounds:
        m.fit_bounds(bounds, padding=(24, 24))
    folium.LayerControl(collapsed=True).add_to(m)

    msg = (
        f"**{n_routes}** route(s), "
        f"**{len(points):,}** map-layer points / **{len(draw):,}** drawn."
    )
    return m, draw, msg
