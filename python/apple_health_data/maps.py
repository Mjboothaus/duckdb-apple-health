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
    photos: pd.DataFrame | None = None,
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
        if "section_index" in g.columns and pd.notna(g["section_index"].iloc[0]):
            # Distinct section colours (journey mode)
            _sec_palette = [
                "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c",
                "#0891b2", "#ca8a04", "#db2777", "#4f46e5", "#059669",
            ]
            si = int(g["section_index"].iloc[0])
            colour = _sec_palette[(si - 1) % len(_sec_palette)]
            sec_lab = (
                str(g["section_label"].iloc[0])
                if "section_label" in g.columns and pd.notna(g["section_label"].iloc[0])
                else f"Section {si}"
            )
        else:
            colour = palette.get(act, "#334155")
            sec_lab = None
        meta_rows = chosen[chosen["gpx_path"] == gpx]
        if meta_rows.empty:
            label = f"{sec_lab} · {gpx}" if sec_lab else f"{act} · {gpx}"
            start_tip, end_tip = "Start", "End"
        else:
            meta = meta_rows.iloc[0]
            start_place = meta["start_place"] if "start_place" in meta.index and pd.notna(meta.get("start_place")) else None
            end_place = meta["end_place"] if "end_place" in meta.index and pd.notna(meta.get("end_place")) else None
            label = f"{meta['activity']} · {meta['start_date']} · {meta['duration_min']} min"
            if sec_lab:
                label = f"{sec_lab} · {label}"
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

    n_photos = 0
    if photos is not None and not photos.empty:
        import base64
        from pathlib import Path as _Path

        fg = folium.FeatureGroup(name="Photos", show=True)
        root = _Path(__file__).resolve().parents[2]
        for row in photos.itertuples(index=False):
            lat = getattr(row, "snap_lat", None)
            lon = getattr(row, "snap_lon", None)
            if lat is None or lon is None or (isinstance(lat, float) and lat != lat):
                continue
            tip = str(getattr(row, "taken_at", "photo"))
            popup_html = tip
            thumb = getattr(row, "thumb_path", None)
            if thumb and str(thumb) not in ("None", "nan"):
                tp = root / str(thumb)
                if tp.is_file():
                    b64 = base64.b64encode(tp.read_bytes()).decode("ascii")
                    popup_html = (
                        '<div style="min-width:160px">'
                        f'<img src="data:image/jpeg;base64,{b64}" '
                        'style="max-width:220px;border-radius:8px;display:block"/>'
                        f'<div style="margin-top:6px;font-size:12px">{tip}</div></div>'
                    )
            folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=4,
                color="#f59e0b",
                fill=True,
                fill_opacity=0.9,
                tooltip=tip,
                popup=folium.Popup(popup_html, max_width=260),
            ).add_to(fg)
            n_photos += 1
        fg.add_to(m)

    if bounds:
        m.fit_bounds(bounds, padding=(24, 24))
    folium.LayerControl(collapsed=True).add_to(m)

    msg = (
        f"**{n_routes}** route(s), "
        f"**{len(points):,}** map-layer points / **{len(draw):,}** drawn"
    )
    if n_photos:
        msg += f", **{n_photos}** photo pin(s)"
    msg += "."
    return m, draw, msg


def filmstrip_html(
    photos: pd.DataFrame,
    *,
    title: str = "Photos",
    thumb_height: int = 120,
    repo: Path | None = None,
) -> str:
    """Horizontal filmstrip HTML for marimo (data-URI thumbs)."""
    import base64
    from pathlib import Path as _Path

    if photos is None or photos.empty:
        return (
            f'<div style="padding:12px;color:#64748b;font-family:system-ui">'
            f'No photos matched for this walk yet. '
            f'Run <code>just photos-for-walks</code>.</div>'
        )
    root = _Path(repo) if repo else _Path(__file__).resolve().parents[2]
    cards: list[str] = []
    ordered = photos.sort_values("taken_at") if "taken_at" in photos.columns else photos
    for row in ordered.itertuples(index=False):
        tip = str(getattr(row, "taken_at", ""))
        dist = getattr(row, "distance_m", None)
        sub = tip
        if dist is not None and dist == dist:
            sub = f"{tip} · {float(dist):.0f} m"
        img = ""
        thumb = getattr(row, "thumb_path", None)
        if thumb and str(thumb) not in ("None", "nan"):
            tp = root / str(thumb)
            if tp.is_file():
                b64 = base64.b64encode(tp.read_bytes()).decode("ascii")
                img = (
                    f'<img src="data:image/jpeg;base64,{b64}" '
                    f'style="height:{int(thumb_height)}px;width:auto;border-radius:10px;'
                    f'display:block;border:2px solid #334155"/>'
                )
        if not img:
            continue
        cards.append(
            f'<div style="flex:0 0 auto;text-align:center">'
            f"{img}"
            f'<div style="font-size:11px;color:#94a3b8;margin-top:6px;max-width:160px">'
            f"{sub}</div></div>"
        )
    if not cards:
        return f'<div style="padding:12px;color:#64748b">Photos listed but no thumbs on disk.</div>'
    return (
        f'<div style="font-family:system-ui">'
        f'<div style="font-size:13px;font-weight:600;margin-bottom:8px;color:#e2e8f0">'
        f"{title} · {len(cards)}</div>"
        f'<div style="display:flex;gap:12px;overflow-x:auto;padding:4px 0 12px">'
        f'{"".join(cards)}</div></div>'
    )
