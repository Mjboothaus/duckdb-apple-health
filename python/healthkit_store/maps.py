"""Map construction helpers (Folium) — no marimo dependency."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import folium
import pandas as pd

def _format_taken_at(value: object) -> str:
    """Human-friendly stamp: Wed 4-Dec-2024 07:15."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    try:
        import pandas as pd

        ts = pd.Timestamp(value)
        if ts is pd.NaT:
            return ""
        if getattr(ts, "tz", None) is not None:
            ts = ts.tz_localize(None)
        # Avoid %-d (GNU) / %#d (MSVC); build day without leading zero portably
        day = str(ts.day)
        return f"{ts.strftime('%a')} {day}-{ts.strftime('%b-%Y %H:%M')}"
    except Exception:
        s = str(value).strip()
        if "T" in s:
            s = s.replace("T", " ")
        if "." in s:
            s = s.split(".")[0]
        if "+" in s:
            s = s.split("+")[0].strip()
        return s[:22]


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
    max_photos: int = 40,
    max_embed_bytes: int = 80_000,
    image_mode: str = "data_uri",
    prepare_web_thumbs: bool = True,
    place_labels: str = "numbers",
) -> tuple[folium.Map | None, pd.DataFrame, str]:
    """Build a Folium map for selected routes.

    Returns ``(map_or_none, drawn_points, status_message)``.

    Photo handling (avoids multi‑100 MB marimo outputs):
    - Builds/caches small web thumbs via ``prepare_photos_for_map`` (default).
    - ``image_mode="data_uri"``: inline only tiny web thumbs (marimo-safe).
    - ``image_mode="file"``: ``file://`` URLs so the browser loads on demand
      (best for standalone HTML exports opened locally).
    - Full JPEGs are never bulk-inlined; optional link when ``full_path`` exists.
    - ``place_labels``: ``"numbers"`` (default, section index chips), ``"places"``
      (start/end place-name pills), or ``"off"`` (coloured dots + tooltips only).
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
        width="100%",
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
        start_place = end_place = None
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
        folium.PolyLine(coords, color=colour, weight=4.5, opacity=0.88, tooltip=label).add_to(m)
        # Endpoint dots (always) — place names live in tooltips, not big white ovals
        folium.CircleMarker(
            coords[0],
            radius=5,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=1.0,
            weight=2,
            tooltip=start_tip,
        ).add_to(m)
        folium.CircleMarker(
            coords[-1],
            radius=5,
            color=colour,
            fill=True,
            fill_color="#ffffff",
            fill_opacity=0.95,
            weight=2,
            tooltip=end_tip,
        ).add_to(m)

        def _short_place(name, n=28):
            if name is None or (isinstance(name, float) and name != name):
                return ""
            s = str(name).strip()
            if not s or s in ("None", "nan"):
                return ""
            s = s.split(",")[0].strip()
            return (s[: n - 1] + "…") if len(s) > n else s

        mode_lbl = (place_labels or "numbers").strip().lower()
        if mode_lbl == "numbers":
            # Compact section index chip at leg start (journey mode) or "S"
            badge = "S"
            if not meta_rows.empty and "section_index" in meta_rows.columns:
                try:
                    badge = str(int(meta_rows.iloc[0]["section_index"]))
                except (TypeError, ValueError):
                    badge = "S"
            elif sec_lab is not None and "section_index" in g.columns and pd.notna(g["section_index"].iloc[0]):
                badge = str(int(g["section_index"].iloc[0]))
            folium.Marker(
                coords[0],
                icon=folium.DivIcon(
                    html=(
                        f'<div style="width:22px;height:22px;border-radius:50%;'
                        f'background:{colour};color:#fff;font:700 11px/22px system-ui,sans-serif;'
                        f'text-align:center;border:2px solid #fff;'
                        f'box-shadow:0 1px 4px rgba(0,0,0,.35);'
                        f'transform:translate(-50%,-50%);">{badge}</div>'
                    ),
                    icon_size=(22, 22),
                    icon_anchor=(0, 0),
                ),
                tooltip=start_tip,
            ).add_to(m)
        elif mode_lbl == "places":
            sp_txt = _short_place(start_place)
            ep_txt = _short_place(end_place)
            if sp_txt:
                folium.Marker(
                    coords[0],
                    icon=folium.DivIcon(
                        html=(
                            f'<div style="font:600 10px/1.2 system-ui,sans-serif;color:#0f172a;'
                            f'background:rgba(255,255,255,0.92);padding:2px 6px;border-radius:4px;'
                            f'border:1px solid {colour};box-shadow:0 1px 3px rgba(0,0,0,.15);'
                            f'white-space:nowrap;transform:translate(-50%,-120%);">{sp_txt}</div>'
                        ),
                        icon_size=(1, 1),
                        icon_anchor=(0, 0),
                    ),
                ).add_to(m)
            if ep_txt:
                folium.Marker(
                    coords[-1],
                    icon=folium.DivIcon(
                        html=(
                            f'<div style="font:600 10px/1.2 system-ui,sans-serif;color:#0f172a;'
                            f'background:rgba(255,255,255,0.92);padding:2px 6px;border-radius:4px;'
                            f'border:1px solid {colour};box-shadow:0 1px 3px rgba(0,0,0,.15);'
                            f'white-space:nowrap;transform:translate(-50%,20%);">{ep_txt}</div>'
                        ),
                        icon_size=(1, 1),
                        icon_anchor=(0, 0),
                    ),
                ).add_to(m)
        # mode_lbl == "off": dots + tooltips only
        bounds.extend(coords)

    n_photos = 0
    n_photos_skipped = 0
    if photos is not None and not photos.empty:
        import base64
        import html as _html
        from pathlib import Path as _Path
        from urllib.parse import quote

        from .photos import prepare_photos_for_map

        fg = folium.FeatureGroup(name="Photos", show=True)
        root = _Path(__file__).resolve().parents[2]
        mode = (image_mode or "data_uri").strip().lower()
        ph = photos
        if prepare_web_thumbs:
            ph = prepare_photos_for_map(ph)

        ordered = ph
        if "taken_at" in ph.columns:
            ordered = ph.sort_values("taken_at")
        cap = max(0, int(max_photos))
        if cap and len(ordered) > cap:
            step = max(1, len(ordered) // cap)
            ordered = ordered.iloc[::step].head(cap)
            n_photos_skipped = len(ph) - len(ordered)
        max_b = int(max_embed_bytes)

        def _resolve(rel: object) -> _Path | None:
            if rel is None or str(rel) in ("None", "nan", ""):
                return None
            tp = _Path(str(rel))
            if not tp.is_file():
                tp = root / str(rel)
            return tp if tp.is_file() else None

        for row in ordered.itertuples(index=False):
            lat = getattr(row, "snap_lat", None)
            lon = getattr(row, "snap_lon", None)
            if lat is None or lon is None or (isinstance(lat, float) and lat != lat):
                continue
            tip = _html.escape(_format_taken_at(getattr(row, "taken_at", None)) or "photo")
            popup_html = f'<div style="font:13px system-ui">{tip}</div>'

            web = _resolve(getattr(row, "web_thumb_path", None))
            full = _resolve(getattr(row, "full_path", None))
            thumb = _resolve(getattr(row, "thumb_path", None))
            display = web or thumb

            img_tag = ""
            if display is not None:
                if mode == "file":
                    # Browser loads on demand — HTML stays small (local file open).
                    href = display.resolve().as_uri()
                    img_tag = (
                        f'<img src="{href}" loading="lazy" '
                        'style="max-width:100%;max-height:50vh;width:auto;height:auto;'
                        'border-radius:10px;display:block;object-fit:contain"/>'
                    )
                elif display.stat().st_size <= max_b:
                    b64 = base64.b64encode(display.read_bytes()).decode("ascii")
                    img_tag = (
                        f'<img src="data:image/jpeg;base64,{b64}" loading="lazy" '
                        'style="max-width:100%;max-height:50vh;width:auto;height:auto;'
                        'border-radius:10px;display:block;object-fit:contain"/>'
                    )
            full_link = ""
            if full is not None and mode == "file":
                full_link = (
                    f'<div style="margin-top:6px"><a href="{full.resolve().as_uri()}" '
                    'target="_blank" rel="noopener" '
                    'style="font:12px system-ui;color:#2563eb">Open larger JPEG</a></div>'
                )

            if img_tag or full_link:
                popup_html = (
                    '<div style="max-width:min(92vw,420px)">'
                    f"{img_tag}"
                    f'<div style="margin-top:8px;font:13px/1.35 system-ui;color:#0f172a">{tip}</div>'
                    f"{full_link}"
                    "</div>"
                )

            folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=5,
                color="#f59e0b",
                fill=True,
                fill_opacity=0.95,
                tooltip=f"Photo · {tip}",
                popup=folium.Popup(popup_html, max_width=440),
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
        if n_photos_skipped:
            msg += f" (sampled; {n_photos_skipped} more not drawn)"
    msg += "."
    return m, draw, msg


def filmstrip_html(
    photos: pd.DataFrame,
    *,
    title: str = "Photos",
    thumb_height: int = 96,
    repo: Path | None = None,
    max_items: int = 36,
    max_embed_bytes: int = 80_000,
    image_mode: str = "data_uri",
    prepare_web_thumbs: bool = True,
) -> str:
    """Horizontal filmstrip HTML (web thumbs; capped).

    Prefer ``prepare_web_thumbs`` so each frame is a small cached JPEG (~10–30 KiB).
    ``image_mode="file"`` uses on-demand ``file://`` loads (HTML export).
    ``image_mode="data_uri"`` inlines only files under ``max_embed_bytes`` (marimo).
    """
    import base64
    from pathlib import Path as _Path

    from .photos import prepare_photos_for_map

    if photos is None or photos.empty:
        return (
            f'<div style="padding:12px;color:#64748b;font-family:system-ui">'
            f'No photos matched for this walk yet. '
            f'Run <code>just photos-for-walks</code>.</div>'
        )
    root = _Path(repo) if repo else _Path(__file__).resolve().parents[2]
    ph = prepare_photos_for_map(photos) if prepare_web_thumbs else photos
    cards: list[str] = []
    ordered = ph.sort_values("taken_at") if "taken_at" in ph.columns else ph
    total = len(ordered)
    cap = max(0, int(max_items))
    if cap and total > cap:
        step = max(1, total // cap)
        ordered = ordered.iloc[::step].head(cap)
    max_b = int(max_embed_bytes)
    mode = (image_mode or "data_uri").strip().lower()
    for row in ordered.itertuples(index=False):
        tip = _format_taken_at(getattr(row, "taken_at", None))
        sub = tip
        img = ""
        rel = getattr(row, "web_thumb_path", None) or getattr(row, "thumb_path", None)
        if rel and str(rel) not in ("None", "nan"):
            tp = _Path(str(rel))
            if not tp.is_file():
                tp = root / str(rel)
            if tp.is_file():
                if mode == "file":
                    img = (
                        f'<img src="{tp.resolve().as_uri()}" loading="lazy" '
                        f'style="height:{int(thumb_height)}px;width:auto;border-radius:10px;'
                        f'display:block;border:2px solid #334155"/>'
                    )
                elif tp.stat().st_size <= max_b:
                    b64 = base64.b64encode(tp.read_bytes()).decode("ascii")
                    img = (
                        f'<img src="data:image/jpeg;base64,{b64}" loading="lazy" '
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
    shown = len(cards)
    more = f" of {total}" if total > shown else ""
    return (
        f'<div style="font-family:system-ui">'
        f'<div style="font-size:13px;font-weight:600;margin-bottom:8px;color:#e2e8f0">'
        f"{title} · {shown}{more}</div>"
        f'<div style="display:flex;gap:12px;overflow-x:auto;padding:4px 0 12px">'
        f'{"".join(cards)}</div></div>'
    )


def render_journey_page(
    *,
    title: str,
    subtitle: str,
    fmap: folium.Map,
    photos: pd.DataFrame | None = None,
    sections: pd.DataFrame | None = None,
) -> str:
    """Full HTML page: title, section list, map, filmstrip."""
    import html as _html

    map_html = fmap.get_root().render()
    strip = filmstrip_html(photos, title="Along the way") if photos is not None else ""
    sec_html = ""
    if sections is not None and not sections.empty:
        items = []
        for r in sections.sort_values("section_index").itertuples(index=False):
            lab = getattr(r, "section_label", None) or f"Section {r.section_index}"
            mins = getattr(r, "duration_min", None)
            mins_s = f" · {mins:.0f} min" if mins is not None and mins == mins else ""
            items.append(
                f"<li><strong>{_html.escape(str(r.section_index))}.</strong> "
                f"{_html.escape(str(lab))}{_html.escape(mins_s)}</li>"
            )
        sec_html = (
            '<ol style="margin:0 0 16px;padding-left:1.25rem;color:#cbd5e1;'
            f'font:14px/1.45 system-ui">{"".join(items)}</ol>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_html.escape(title)}</title>
<style>
  body {{ margin:0; background:#0b1220; color:#e2e8f0; font-family:system-ui,-apple-system,sans-serif; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 20px 18px 40px; }}
  h1 {{ font-size: 1.65rem; font-weight: 700; margin: 0 0 6px; letter-spacing: -0.02em; }}
  .sub {{ color:#94a3b8; margin: 0 0 18px; font-size: 0.95rem; }}
  .map {{ border-radius: 14px; overflow: hidden; border: 1px solid #1e293b;
         box-shadow: 0 12px 40px rgba(0,0,0,.35); }}
  .film {{ margin-top: 18px; padding: 14px 16px; border-radius: 14px;
           background: #111827; border: 1px solid #1e293b; }}
</style>
</head><body>
<div class="wrap">
  <h1>{_html.escape(title)}</h1>
  <p class="sub">{_html.escape(subtitle)}</p>
  {sec_html}
  <div class="map">{map_html}</div>
  <div class="film">{strip}</div>
</div>
</body></html>
"""


def wrap_map_html(fmap: folium.Map, *, height: int | str = 720) -> str:
    """Standalone map document suitable for an iframe ``srcdoc`` / data-URI.

    Marimo often greys out or clips raw Folium HTML in edit mode; embedding a
    full HTML document in an iframe is reliable in both ``marimo run`` (app)
    and ``marimo edit``.
    """
    h_px = int(height) if not isinstance(height, str) else int(str(height).rstrip("px") or 720)
    h = f"{h_px}px"
    # Folium already emits a full HTML document when rendered this way
    inner = fmap.get_root().render()
    # If Folium returned a fragment, wrap it
    if "<html" not in inner.lower():
        inner = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
            f"<style>html,body{{margin:0;height:100%;}}"
            f".folium-map,.leaflet-container{{width:100%!important;height:{h}!important;}}"
            f"</style></head><body>{inner}</body></html>"
        )
    return inner


def map_iframe_html(
    fmap: folium.Map,
    *,
    height: int = 900,
    write_path: Path | str | None = None,
) -> str:
    """Marimo-safe map embed.

    Prefer a real file + relative/file URL when ``write_path`` is set (more
    reliable than huge data-URIs inside marimo). Falls back to base64 data-URI.
    """
    import base64
    from pathlib import Path as _Path

    doc = wrap_map_html(fmap, height=height)
    h = int(height)
    src = None
    if write_path is not None:
        out = _Path(write_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
        # file:// works in desktop browsers for local marimo
        src = out.resolve().as_uri()
    if src is None:
        b64 = base64.b64encode(doc.encode("utf-8")).decode("ascii")
        src = f"data:text/html;base64,{b64}"
    return (
        f'<div style="width:100%;min-height:{h}px">'
        f'<iframe title="route-map" src="{src}" '
        f'style="width:100%;max-width:100%;height:{h}px;min-height:{h}px;'
        f'border:0;border-radius:12px;display:block;background:#0b1220" '
        f'></iframe></div>'
    )
