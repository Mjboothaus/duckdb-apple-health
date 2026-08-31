# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.13.0",
#     "duckdb>=1.2.0",
#     "pandas>=2.2.0",
#     "folium>=0.20.0",
# ]
# ///
"""Walks/hikes map UI.

Data access and map construction live in ``python/apple_health_data/``.
This notebook only wires marimo controls.

```bash
just build-db export_zip=/path/to/export.zip
just map-walks
```
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo

    _repo = Path(__file__).resolve().parents[1]
    _python = str(_repo / "python")
    if _python not in sys.path:
        sys.path.insert(0, _python)

    from apple_health_data import DEFAULT_DB_PATH, HealthDataStore, build_route_map

    return DEFAULT_DB_PATH, HealthDataStore, Path, build_route_map, mo


@app.cell
def _(DEFAULT_DB_PATH, mo):
    db_path = mo.ui.text(
        value=str(DEFAULT_DB_PATH),
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
    map_height = mo.ui.slider(
        400, 1200, value=820, step=20, label="Map height (px)", show_value=True
    )
    geocode_places = mo.ui.checkbox(
        value=True, label="Resolve start/end place names (Nominatim, cached)"
    )
    header = mo.vstack(
        [
            mo.md(
                r"""
                # Walks & hikes map

                UI only — data via **`HealthDataStore`** (`python/apple_health_data/`).

                ```bash
                just build-db export_zip=/path/to/export.zip
                just map-walks
                ```
                """
            ),
            db_path,
            activity_filter,
            max_list,
            max_points,
            map_height,
            geocode_places,
        ]
    )
    return activity_filter, db_path, geocode_places, header, map_height, max_list, max_points


@app.cell
def _(header):
    header
    return


@app.cell
def _(HealthDataStore, Path, db_path, mo):
    path = Path(db_path.value).expanduser()
    store = None
    if not path.is_file():
        db_panel = mo.md(
            rf"""
            ### Database not found

            `{path}`

            ```bash
            just build-db export_zip=/path/to/your/export.zip
            ```
            """
        )
    else:
        try:
            store = HealthDataStore(path)
            store.connect()
            db_panel = mo.vstack(
                [
                    mo.md(f"### Database\n\n`{path}`"),
                    mo.ui.table(store.manifest(), selection=None),
                    mo.ui.table(store.summary(), selection=None),
                ]
            )
        except Exception as e:
            if store is not None:
                store.close()
            store = None
            db_panel = mo.md(f"**Could not open DB:** `{e}`")
    return db_panel, store


@app.cell
def _(db_panel):
    db_panel
    return


@app.cell
def _(activity_filter, geocode_places, max_list, mo, store):
    catalogue = None
    route_picker = mo.ui.multiselect(options=[], value=[], label="Select walk(s) / hike(s)")

    if store is None:
        routes_panel = mo.md("_Open a valid database above._")
    else:
        types = list(activity_filter.value) or ["Walking", "Hiking"]
        catalogue = store.list_routes(activities=types, limit=int(max_list.value))
        if not catalogue.empty and geocode_places.value:
            # Network only for cache misses; results land in output/geocode_cache.json.
            catalogue = store.enrich_with_places(catalogue, fetch=True)
        if catalogue.empty:
            routes_panel = mo.md(f"No mapped routes for **{', '.join(types)}**.")
        else:
            labels = catalogue["label"].tolist()
            route_picker = mo.ui.multiselect(
                options=labels,
                value=labels[: min(3, len(labels))],
                label="Select walk(s) / hike(s)",
            )
            cols = [
                c
                for c in (
                    "activity",
                    "start_date",
                    "duration_min",
                    "start_place",
                    "end_place",
                    "n_points",
                    "gpx_path",
                )
                if c in catalogue.columns
            ]
            routes_panel = mo.vstack(
                [
                    mo.md(f"### Routes ({len(catalogue)} listed)"),
                    mo.ui.table(catalogue[cols], selection=None, page_size=12),
                    route_picker,
                ]
            )
    return catalogue, route_picker, routes_panel


@app.cell
def _(routes_panel):
    routes_panel
    return


@app.cell
def _(build_route_map, catalogue, map_height, max_points, mo, route_picker, store):
    map_panel = mo.md("### Map\n\nNothing to draw yet.")

    if store is not None and catalogue is not None and not catalogue.empty:
        selected = list(route_picker.value)
        if not selected:
            map_panel = mo.md("### Map\n\nSelect one or more routes.")
        else:
            chosen, pts = store.points_for_labels(catalogue, selected)
            fmap, _drawn, status = build_route_map(
                chosen,
                pts,
                max_total_points=int(max_points.value),
                height=int(map_height.value),
            )
            if fmap is None:
                map_panel = mo.md(f"### Map\n\n{status}")
            else:
                map_panel = mo.vstack(
                    [
                        mo.md(f"### Map\n\n{status}"),
                        mo.Html(fmap._repr_html_()),
                    ]
                )
    return (map_panel,)


@app.cell
def _(map_panel):
    map_panel
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ### Commands

        ```bash
        just build-db export_zip=/path/to/export.zip
        just list-walks 10
        just map-walks
        ```

        Helper package: `python/apple_health_data/` (`HealthDataStore`, `build_route_map`, place labels).
        Model: `docs/ERD.md`. Place cache: `output/geocode_cache.json`.
        """
    )
    return


if __name__ == "__main__":
    app.run()
