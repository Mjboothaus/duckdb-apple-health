# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.13.0",
#     "duckdb>=1.2.0",
#     "pandas>=2.2.0",
#     "folium>=0.20.0",
# ]
# ///
"""Map walks/hikes from the local DuckDB file (no zip scan).

Build the DB first:
  just build-db export_zip=/path/to/export.zip

Then:
  just map-walks
"""

from __future__ import annotations

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import math
    from pathlib import Path

    import duckdb
    import folium
    import marimo as mo
    import pandas as pd

    return Path, duckdb, folium, math, mo, pd


@app.cell
def _(Path, mo):
    repo_root = Path(__file__).resolve().parents[1]
    default_db = str(repo_root / "output" / "apple_health.duckdb")

    db_path = mo.ui.text(
        value=default_db,
        label="Local DuckDB file (from just build-db)",
        full_width=True,
    )
    activity_filter = mo.ui.multiselect(
        options=["Walking", "Hiking", "Running", "Cycling", "TrailRunning"],
        value=["Walking", "Hiking"],
        label="Activity types",
    )
    max_list = mo.ui.slider(20, 300, value=60, step=10, label="Max routes listed", show_value=True)
    max_points = mo.ui.slider(
        500, 20_000, value=6_000, step=500, label="Max points drawn (total)", show_value=True
    )

    mo.vstack(
        [
            mo.md(
                """
# Walks & hikes map

Reads **`output/apple_health.duckdb`** only (tables `routes` + `route_points_map`).

```bash
just build-db export_zip=/path/to/export.zip   # once
just map-walks                                 # map
```

No export.zip scan in this notebook.
"""
            ),
            db_path,
            activity_filter,
            max_list,
            max_points,
        ]
    )
    return activity_filter, db_path, max_list, max_points, repo_root


@app.cell
def _(Path, db_path, duckdb, mo):
    path = Path(db_path.value).expanduser()
    if not path.is_file():
        mo.md(
            f"""
### Database not found

`{path}`

Build it first:

```bash
just build-db export_zip=/path/to/your/export.zip
```
"""
        )
        con = None
    else:
        con = duckdb.connect(str(path), read_only=True)
        try:
            man = con.execute("SELECT * FROM ingest_manifest").df()
            counts = con.execute(
                """
                SELECT 'workouts' AS t, count(*)::BIGINT AS n FROM workouts
                UNION ALL SELECT 'routes', count(*) FROM routes
                UNION ALL SELECT 'route_points_map', count(*) FROM route_points_map
                """
            ).df()
            mo.vstack(
                [
                    mo.md(f"### Database\n\n`{path}`"),
                    mo.ui.table(man, selection=None),
                    mo.ui.table(counts, selection=None),
                ]
            )
        except Exception as e:
            mo.md(f"**Could not read DB tables:** `{e}`\n\nRe-run `just build-db`.")
            con = None
    return (con,)


@app.cell
def _(activity_filter, con, max_list, mo):
    if con is None:
        catalogue = None
        route_picker = mo.ui.multiselect(options=[], value=[], label="Routes")
        mo.md("_Open a valid database above._")
    else:
        types = list(activity_filter.value) or ["Walking", "Hiking"]
        in_list = ", ".join("'" + t.replace("'", "''") + "'" for t in types)
        limit_n = int(max_list.value)
        catalogue = con.execute(
            f"""
            SELECT
              r.activity_type_short AS activity,
              r.workout_start_date AS start_date,
              r.gpx_path,
              round(date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 1)
                AS duration_min,
              count(p.point_index)::BIGINT AS n_points,
              strftime(r.workout_start_date, '%Y-%m-%d %H:%M')
                || ' · ' || r.activity_type_short
                || ' · ' || coalesce(
                     round(date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 0)::INT,
                     0
                   )::VARCHAR || ' min'
                || ' · ' || count(p.point_index)::VARCHAR || ' pts'
                AS label
            FROM routes r
            JOIN route_points_map p USING (gpx_path)
            WHERE r.activity_type_short IN ({in_list})
            GROUP BY 1, 2, 3, r.workout_end_date
            HAVING count(p.point_index) >= 2
            ORDER BY r.workout_start_date DESC NULLS LAST
            LIMIT {limit_n}
            """
        ).df()

        if catalogue.empty:
            route_picker = mo.ui.multiselect(options=[], value=[], label="Routes")
            mo.md(f"No mapped routes for **{', '.join(types)}**.")
        else:
            labels = catalogue["label"].tolist()
            route_picker = mo.ui.multiselect(
                options=labels,
                value=labels[: min(3, len(labels))],
                label="Select walk(s) / hike(s)",
            )
            mo.vstack(
                [
                    mo.md(f"### Routes ({len(catalogue)} listed)"),
                    mo.ui.table(
                        catalogue[["activity", "start_date", "duration_min", "n_points", "gpx_path"]],
                        selection=None,
                        page_size=12,
                    ),
                    route_picker,
                ]
            )
    return catalogue, route_picker


@app.cell
def _(catalogue, con, folium, math, max_points, mo, pd, route_picker):
    if con is None or catalogue is None or catalogue.empty:
        mo.md("### Map\n\nNothing to draw yet.")
    else:
        selected = list(route_picker.value)
        if not selected:
            mo.md("### Map\n\nSelect one or more routes.")
        else:
            chosen = catalogue[catalogue["label"].isin(selected)]
            paths = chosen["gpx_path"].dropna().unique().tolist()
            in_gpx = ", ".join("'" + g.replace("'", "''") + "'" for g in paths)
            pts = con.execute(
                f"""
                SELECT gpx_path, point_index, lat, lon, ele, point_time,
                       activity_type_short AS activity
                FROM route_points_map
                WHERE gpx_path IN ({in_gpx})
                ORDER BY gpx_path, point_index
                """
            ).df()

            budget = int(max_points.value)
            frames = []
            n_paths = max(len(paths), 1)
            per = max(budget // n_paths, 50)
            for gpx, grp in pts.groupby("gpx_path", sort=False):
                g = grp.sort_values("point_index")
                if len(g) > per:
                    step = max(1, math.ceil(len(g) / per))
                    g = pd.concat([g.iloc[::step], g.iloc[[-1]]]).drop_duplicates("point_index")
                frames.append(g)
            draw = pd.concat(frames, ignore_index=True) if frames else pts.iloc[0:0]

            if draw.empty:
                mo.md("### Map\n\nNo points for selection.")
            else:
                colours = {
                    "Walking": "#2563eb",
                    "Hiking": "#16a34a",
                    "Running": "#dc2626",
                    "Cycling": "#9333ea",
                }
                m = folium.Map(
                    location=[float(draw["lat"].mean()), float(draw["lon"].mean())],
                    zoom_start=12,
                    tiles="OpenStreetMap",
                )
                folium.TileLayer("CartoDB positron", name="Light").add_to(m)
                bounds = []
                for gpx, grp in draw.groupby("gpx_path", sort=False):
                    g = grp.sort_values("point_index")
                    act = str(g["activity"].iloc[0])
                    colour = colours.get(act, "#334155")
                    meta = chosen[chosen["gpx_path"] == gpx].iloc[0]
                    label = f"{meta['activity']} · {meta['start_date']} · {meta['duration_min']} min"
                    coords = list(zip(g["lat"].tolist(), g["lon"].tolist()))
                    if len(coords) < 2:
                        continue
                    folium.PolyLine(coords, color=colour, weight=4, opacity=0.85, tooltip=label).add_to(m)
                    folium.CircleMarker(coords[0], radius=5, color=colour, fill=True, tooltip="Start").add_to(m)
                    folium.CircleMarker(coords[-1], radius=5, color=colour, fill=True, fill_opacity=0.4, tooltip="End").add_to(m)
                    bounds.extend(coords)
                if bounds:
                    m.fit_bounds(bounds, padding=(24, 24))
                folium.LayerControl(collapsed=True).add_to(m)
                mo.vstack(
                    [
                        mo.md(
                            f"### Map\n\n**{len(paths)}** route(s), "
                            f"**{len(pts):,}** map-layer points / **{len(draw):,}** drawn."
                        ),
                        mo.Html(m._repr_html_()),
                    ]
                )
    return


@app.cell
def _(mo):
    mo.md(
        """
---
### Commands

```bash
just build-db export_zip=/path/to/export.zip
just map-walks
duckdb output/apple_health.duckdb   # SQL on the same file
```

See `docs/ERD.md` for the data model.
"""
    )
    return


if __name__ == "__main__":
    app.run()
