# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "duckdb",
#     "pandas",
#     "folium",
# ]
# ///
"""Map walks / hikes from Apple Health workout GPS.

Separate from ``explore_export.py`` (records / rings / Parquet analytics).

**Design:** materialise routes + track points to Parquet once (bind is expensive
on multi-million-point exports), then select walks with UI controls and draw
polylines on a Folium map. Real exports stay outside git.
"""

from __future__ import annotations

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import math
    import time
    from pathlib import Path

    import duckdb
    import folium
    import marimo as mo
    import pandas as pd

    return Path, duckdb, folium, math, mo, pd, time


@app.cell
def _(Path, mo):
    repo_root = Path(__file__).resolve().parents[1]
    default_export = str(repo_root / "test" / "data" / "export.zip")
    # Real export example (outside git):
    # /Users/mjboothaus/icloud/Data/apple_health_export/export23June2025.zip

    export_path = mo.ui.text(
        value=default_export,
        label="Health export path (.zip / .xml / directory)",
        full_width=True,
    )
    out_subdir = mo.ui.text(
        value="output/maps",
        label="Parquet output directory (under repo, gitignored via output/)",
        full_width=True,
    )
    force_refresh = mo.ui.checkbox(
        value=False,
        label="Re-materialise routes + points from the export (slow on large zips)",
    )
    activity_filter = mo.ui.multiselect(
        options=[
            "Walking",
            "Hiking",
            "Running",
            "Cycling",
            "TrailRunning",
            "CrossCountrySkiing",
            "DownhillSkiing",
            "Snowboarding",
            "Swimming",  # rarely has GPS; still listable
        ],
        value=["Walking", "Hiking", "Running"],
        label="Activity types to list (type_short)",
    )
    max_list = mo.ui.slider(
        start=20,
        stop=500,
        step=10,
        value=80,
        label="Max routes in selector (most recent first)",
        show_value=True,
    )
    max_points_draw = mo.ui.slider(
        start=500,
        stop=50_000,
        step=500,
        value=8_000,
        label="Max track points to draw (downsample if needed)",
        show_value=True,
    )

    mo.vstack(
        [
            mo.md(
                """
# Walks & hikes map

GPS from **`apple_health_workout_routes`** + **`apple_health_workout_route_points`**.

1. Point at an export (fixture by default).
2. Materialise routes/points to Parquet **once** (or reuse existing files).
3. Filter activity types, pick one or more routes, render a map.

**Privacy:** real Health zips and derived Parquet stay local — do not commit them.
**Performance:** full points scan still runs in DuckDB **bind** (~minutes / multi‑GB
exports). Prefer Parquet after the first materialise.
"""
            ),
            export_path,
            out_subdir,
            force_refresh,
            activity_filter,
            max_list,
            max_points_draw,
        ]
    )
    return (
        activity_filter,
        export_path,
        force_refresh,
        max_list,
        max_points_draw,
        out_subdir,
        repo_root,
    )


@app.cell
def _(Path, duckdb, export_path, mo, repo_root):
    def resolve_extension() -> Path:
        candidates = [
            repo_root / "build/debug/extension/apple_health/apple_health.duckdb_extension",
            repo_root / "build/debug/apple_health.duckdb_extension",
            repo_root / "build/release/extension/apple_health/apple_health.duckdb_extension",
        ]
        for p in candidates:
            if p.is_file():
                return p
        raise FileNotFoundError(
            "No apple_health.duckdb_extension found. Run `just debug` first."
        )

    ext_path = resolve_extension()
    zip_path = Path(export_path.value).expanduser()
    if not zip_path.exists():
        raise FileNotFoundError(f"Export not found: {zip_path}")

    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    con.execute(f"LOAD '{ext_path.as_posix()}'")

    try:
        ext_display = ext_path.relative_to(repo_root)
    except ValueError:
        ext_display = ext_path

    mo.md(
        f"""
### Connection

| | |
|---|---|
| Extension | `{ext_display}` |
| Export | `{zip_path}` |
| Size | **{zip_path.stat().st_size / (1024**2):.1f} MiB** |
| DuckDB | `{con.execute("SELECT version()").fetchone()[0]}` |
"""
    )
    return con, zip_path


@app.cell
def _(Path, con, force_refresh, mo, out_subdir, repo_root, time, zip_path):
    out_dir = (repo_root / out_subdir.value).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    routes_pq = out_dir / "workout_routes.parquet"
    points_pq = out_dir / "workout_route_points.parquet"
    path_sql = zip_path.as_posix().replace("'", "''")

    def need(p: Path) -> bool:
        return force_refresh.value or (not p.is_file())

    timings = []

    if need(routes_pq):
        t0 = time.perf_counter()
        con.execute(
            f"""
            COPY (
              SELECT *
              FROM apple_health_workout_routes('{path_sql}')
            ) TO '{routes_pq.as_posix()}' (FORMAT parquet)
            """
        )
        timings.append(("routes ← export", time.perf_counter() - t0, routes_pq.stat().st_size))

    if need(points_pq):
        t0 = time.perf_counter()
        con.execute(
            f"""
            COPY (
              SELECT *
              FROM apple_health_workout_route_points('{path_sql}')
            ) TO '{points_pq.as_posix()}' (FORMAT parquet)
            """
        )
        timings.append(("points ← export", time.perf_counter() - t0, points_pq.stat().st_size))

    n_routes = con.execute(
        f"SELECT count(*) FROM read_parquet('{routes_pq.as_posix()}')"
    ).fetchone()[0]
    n_points = con.execute(
        f"SELECT count(*) FROM read_parquet('{points_pq.as_posix()}')"
    ).fetchone()[0]
    n_with_gps = con.execute(
        f"""
        SELECT count(*) FROM read_parquet('{routes_pq.as_posix()}')
        WHERE gpx_path IS NOT NULL AND length(gpx_path) > 0
        """
    ).fetchone()[0]

    rows = []
    for step, sec, nbytes in timings:
        rows.append(
            {
                "step": step,
                "seconds": round(sec, 2),
                "mib": round(nbytes / (1024**2), 2),
            }
        )
    if not rows:
        rows.append({"step": "(reused existing Parquet)", "seconds": 0.0, "mib": None})

    mo.vstack(
        [
            mo.md("### Materialise (Parquet cache)"),
            mo.md(
                f"""
| | |
|---|---|
| Routes file | `{routes_pq.relative_to(repo_root)}` |
| Points file | `{points_pq.relative_to(repo_root)}` |
| Route rows | **{n_routes:,}** (with `gpx_path`: **{n_with_gps:,}**) |
| Track points | **{n_points:,}** |
"""
            ),
            mo.ui.table(rows, selection=None),
            mo.md(
                "_Uncheck **Re-materialise** on later runs to skip the multi-minute zip scan._"
            ),
        ]
    )
    return n_points, n_routes, points_pq, routes_pq


@app.cell
def _(activity_filter, con, max_list, mo, pd, points_pq, routes_pq):
    types = list(activity_filter.value) or ["Walking", "Hiking", "Running"]
    # SQL IN list
    in_list = ", ".join("'" + t.replace("'", "''") + "'" for t in types)
    limit_n = int(max_list.value)

    catalogue_sql = f"""
    WITH routes AS (
      SELECT
        gpx_path,
        workout_activity_type_short AS activity,
        workout_start_date AS start_date,
        workout_end_date AS end_date,
        source_name,
        date_diff('second', workout_start_date, workout_end_date) AS duration_s
      FROM read_parquet('{routes_pq.as_posix()}')
      WHERE gpx_path IS NOT NULL AND length(gpx_path) > 0
        AND workout_activity_type_short IN ({in_list})
    ),
    pts AS (
      SELECT
        gpx_path,
        count(*)::BIGINT AS n_points,
        min(lat) AS min_lat,
        max(lat) AS max_lat,
        min(lon) AS min_lon,
        max(lon) AS max_lon,
        -- rough path length via successive haversine would need window; use bbox diagonal as hint only
        avg(ele) AS avg_ele
      FROM read_parquet('{points_pq.as_posix()}')
      GROUP BY 1
    )
    SELECT
      r.activity,
      r.start_date,
      r.end_date,
      r.duration_s,
      round(r.duration_s / 60.0, 1) AS duration_min,
      r.source_name,
      r.gpx_path,
      coalesce(p.n_points, 0) AS n_points,
      p.min_lat, p.max_lat, p.min_lon, p.max_lon, p.avg_ele,
      strftime(r.start_date, '%Y-%m-%d %H:%M')
        || ' · ' || r.activity
        || ' · ' || coalesce(round(r.duration_s / 60.0, 0)::INT, 0)::VARCHAR || ' min'
        || ' · ' || coalesce(p.n_points, 0)::VARCHAR || ' pts'
        || ' · ' || r.gpx_path AS label
    FROM routes r
    LEFT JOIN pts p USING (gpx_path)
    WHERE coalesce(p.n_points, 0) > 0
    ORDER BY r.start_date DESC NULLS LAST
    LIMIT {limit_n}
    """
    catalogue = con.execute(catalogue_sql).df()

    if catalogue.empty:
        mo.md(
            f"""
### Route catalogue

No routes with GPS points for types **{', '.join(types)}**.

Try adding more activity types, re-materialise, or confirm the export has
`workout-routes/*.gpx` members.
"""
        )
        route_picker = mo.ui.multiselect(options=[], value=[], label="Routes")
    else:
        labels = catalogue["label"].tolist()
        # default: up to 3 most recent
        default = labels[: min(3, len(labels))]
        route_picker = mo.ui.multiselect(
            options=labels,
            value=default,
            label="Select walk(s) / hike(s) to map",
        )
        mo.vstack(
            [
                mo.md(
                    f"### Route catalogue — **{len(catalogue)}** listed "
                    f"(filter: {', '.join(types)}; cap {limit_n})"
                ),
                mo.ui.table(
                    catalogue[
                        [
                            "activity",
                            "start_date",
                            "duration_min",
                            "n_points",
                            "source_name",
                            "gpx_path",
                        ]
                    ],
                    selection=None,
                    page_size=15,
                ),
                route_picker,
            ]
        )

    return catalogue, route_picker


@app.cell
def _(
    catalogue,
    con,
    folium,
    math,
    max_points_draw,
    mo,
    pd,
    points_pq,
    route_picker,
):
    selected_labels = list(route_picker.value) if route_picker is not None else []
    if catalogue is None or catalogue.empty or not selected_labels:
        mo.md("### Map\n\nSelect one or more routes above to draw GPS tracks.")
        return

    chosen = catalogue[catalogue["label"].isin(selected_labels)].copy()
    gpx_paths = chosen["gpx_path"].dropna().unique().tolist()
    if not gpx_paths:
        mo.md("### Map\n\nSelected rows have no `gpx_path`.")
        return

    in_gpx = ", ".join("'" + g.replace("'", "''") + "'" for g in gpx_paths)
    # Pull points for selected routes only (from Parquet — fast).
    pts = con.execute(
        f"""
        SELECT gpx_path, point_index, lat, lon, ele, time,
               workout_activity_type_short AS activity
        FROM read_parquet('{points_pq.as_posix()}')
        WHERE gpx_path IN ({in_gpx})
        ORDER BY gpx_path, point_index
        """
    ).df()

    if pts.empty:
        mo.md("### Map\n\nNo points for the selected routes in Parquet.")
        return

    # Downsample per route if over budget
    budget = int(max_points_draw.value)
    frames = []
    for gpx, grp in pts.groupby("gpx_path", sort=False):
        g = grp.sort_values("point_index")
        if len(g) > budget // max(len(gpx_paths), 1):
            step = max(1, math.ceil(len(g) / (budget // max(len(gpx_paths), 1))))
            g = g.iloc[::step]
        frames.append(g)
    pts_draw = pd.concat(frames, ignore_index=True)

    # Colour palette by activity
    palette = {
        "Walking": "#2563eb",
        "Hiking": "#16a34a",
        "Running": "#dc2626",
        "Cycling": "#9333ea",
        "TrailRunning": "#ea580c",
    }
    default_colour = "#334155"

    center_lat = float(pts_draw["lat"].mean())
    center_lon = float(pts_draw["lon"].mean())
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")
    folium.TileLayer("CartoDB positron", name="Light").add_to(fmap)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(fmap)

    bounds = []
    legend_bits = []
    for gpx, grp in pts_draw.groupby("gpx_path", sort=False):
        g = grp.sort_values("point_index")
        activity = str(g["activity"].iloc[0]) if "activity" in g.columns else ""
        colour = palette.get(activity, default_colour)
        meta = chosen[chosen["gpx_path"] == gpx].iloc[0]
        label = (
            f"{meta['activity']} · {meta['start_date']} · "
            f"{int(meta['duration_min']) if pd.notna(meta['duration_min']) else '?'} min · "
            f"{int(meta['n_points'])} pts"
        )
        coords = list(zip(g["lat"].tolist(), g["lon"].tolist()))
        if len(coords) < 2:
            continue
        folium.PolyLine(
            coords,
            color=colour,
            weight=4,
            opacity=0.85,
            tooltip=label,
            popup=folium.Popup(
                f"<b>{label}</b><br><code>{gpx}</code>",
                max_width=360,
            ),
        ).add_to(fmap)
        # start / end markers
        folium.CircleMarker(
            location=coords[0],
            radius=5,
            color=colour,
            fill=True,
            fill_opacity=0.9,
            tooltip=f"Start · {label}",
        ).add_to(fmap)
        folium.CircleMarker(
            location=coords[-1],
            radius=5,
            color=colour,
            fill=True,
            fill_opacity=0.4,
            tooltip=f"End · {label}",
        ).add_to(fmap)
        bounds.extend(coords)
        legend_bits.append((activity or "route", colour, label))

    if bounds:
        fmap.fit_bounds(bounds, padding=(24, 24))

    folium.LayerControl(collapsed=True).add_to(fmap)

    summary = (
        f"**{len(gpx_paths)}** route(s), "
        f"**{len(pts):,}** points loaded / **{len(pts_draw):,}** drawn "
        f"(budget {budget:,})."
    )
    mo.vstack(
        [
            mo.md(f"### Map\n\n{summary}"),
            mo.Html(fmap._repr_html_()),
            mo.md(
                """
**Tips**

- Toggle **Re-materialise** only when the export changes.
- Raise **Max track points to draw** for denser lines (heavier browser).
- Join back to summaries later via `workout_start_date` / activity if needed.
- Altair time-series of HR/steps stays in `notebooks/explore_export.py`.
"""
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        """
---
### Run

```bash
just debug
uv sync
uv run marimo edit notebooks/map_walks.py
# or:
uv run marimo run notebooks/map_walks.py
```

Fixture GPS is a short demo loop near Sydney. Point **Health export path** at a
real `export.zip` (outside the repo) for your walks and hikes.
"""
    )
    return


if __name__ == "__main__":
    app.run()
