# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.13.0",
#     "duckdb>=1.2.0",
#     "pandas>=2.2.0",
#     "folium>=0.20.0",
# ]
# ///
"""Walk stories — map + photos UI (helpers live under python/apple_health_data/).

```bash
just build-db export_zip=/path/to/export.zip
just photos-for-walks -- --limit-walks 40
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
    from apple_health_data.maps import filmstrip_html

    return DEFAULT_DB_PATH, HealthDataStore, Path, build_route_map, filmstrip_html, mo


@app.cell
def _(DEFAULT_DB_PATH, mo):
    db_path = mo.ui.text(
        value=str(DEFAULT_DB_PATH),
        label="Local DuckDB",
        full_width=True,
    )
    activity_filter = mo.ui.multiselect(
        options=["Walking", "Hiking", "Running", "Cycling", "TrailRunning"],
        value=["Walking", "Hiking"],
        label="Activities",
    )
    max_list = mo.ui.slider(20, 300, value=80, step=10, label="Routes listed", show_value=True)
    prefer_photos = mo.ui.checkbox(value=True, label="Prefer walks that already have photos")
    show_photos = mo.ui.checkbox(value=True, label="Show photo pins + filmstrip")
    map_height = mo.ui.slider(500, 1200, value=860, step=20, label="Map height", show_value=True)
    max_points = mo.ui.slider(
        500, 20_000, value=6_000, step=500, label="Track points drawn", show_value=True
    )
    options = mo.accordion(
        {
            "Options": mo.vstack([db_path, max_list, max_points, map_height]),
        }
    )
    controls = mo.vstack(
        [
            mo.hstack(
                [activity_filter, prefer_photos, show_photos],
                justify="start",
                gap=1.5,
                wrap=True,
            ),
            options,
        ]
    )
    return (
        activity_filter,
        controls,
        db_path,
        map_height,
        max_list,
        max_points,
        prefer_photos,
        show_photos,
    )


@app.cell
def _(HealthDataStore, Path, db_path, mo):
    path = Path(db_path.value).expanduser()
    store = None
    status_line = ""
    if not path.is_file():
        shell = mo.md(
            rf"""
            # Walk stories
            Database not found: `{path}`

            ```bash
            just build-db export_zip=/path/to/export.zip
            ```
            """
        )
    else:
        try:
            store = HealthDataStore(path)
            store.connect()
            summary = store.summary()
            counts = {r.t: int(r.n) for r in summary.itertuples()}
            n_photos = counts.get("walk_photos", 0)
            status_line = (
                f"`{path.name}` · **{counts.get('routes', 0):,}** routes · "
                f"**{counts.get('route_points_map', 0):,}** map pts · "
                f"**{n_photos:,}** walk photos"
            )
            shell = mo.md(
                f"""
                # Walk stories
                {status_line}

                Local only — GPS from Health, places from Nominatim cache, photos from Apple Photos derivatives.
                """
            )
        except Exception as e:
            if store is not None:
                store.close()
            store = None
            shell = mo.md(f"# Walk stories\n\n**Could not open DB:** `{e}`")
    return shell, status_line, store


@app.cell
def _(shell):
    shell
    return


@app.cell
def _(controls):
    controls
    return


@app.cell
def _(activity_filter, max_list, mo, prefer_photos, store):
    catalogue = None
    route_picker = mo.ui.dropdown(options=[], value=None, label="Walk")

    if store is None:
        rail = mo.md("_Open a database to pick a walk._")
    else:
        types = list(activity_filter.value) or ["Walking", "Hiking"]
        catalogue = store.list_routes(activities=types, limit=int(max_list.value))
        # Prefer DB places (already on catalogue when route_places exists)
        if catalogue.empty:
            rail = mo.md(f"No mapped routes for **{', '.join(types)}**.")
        else:
            photos_all = store.photos_for_gpx()
            photo_counts = (
                photos_all.groupby("gpx_path").size()
                if photos_all is not None and not photos_all.empty
                else None
            )
            if photo_counts is not None:
                catalogue = catalogue.copy()
                catalogue["n_photos"] = catalogue["gpx_path"].map(photo_counts).fillna(0).astype(int)
            else:
                catalogue = catalogue.copy()
                catalogue["n_photos"] = 0

            labels = catalogue["label"].tolist()
            default = labels[0]
            if prefer_photos.value and (catalogue["n_photos"] > 0).any():
                top = catalogue.sort_values(["n_photos", "start_date"], ascending=[False, False])
                default = top.iloc[0]["label"]

            route_picker = mo.ui.dropdown(
                options=labels,
                value=default,
                label="Walk",
                full_width=True,
            )
            card_cols = [
                c
                for c in (
                    "activity",
                    "start_date",
                    "duration_min",
                    "start_place",
                    "end_place",
                    "n_photos",
                    "n_points",
                )
                if c in catalogue.columns
            ]
            rail = mo.vstack(
                [
                    mo.md("### Choose a walk"),
                    route_picker,
                    mo.ui.table(
                        catalogue[card_cols],
                        selection=None,
                        page_size=8,
                    ),
                    mo.md(
                        "_Tip: `just photos-for-walks -- --limit-walks 40` fills "
                        "`walk_photos` + thumbs._"
                    ),
                ]
            )
    return catalogue, rail, route_picker


@app.cell
def _(
    build_route_map,
    catalogue,
    filmstrip_html,
    map_height,
    max_points,
    mo,
    route_picker,
    show_photos,
    store,
):
    stage = mo.md("Select a walk.")
    if store is None or catalogue is None or catalogue.empty:
        stage = mo.md("_Nothing to show yet._")
    else:
        label = route_picker.value
        if not label:
            stage = mo.md("Select a walk from the list.")
        else:
            chosen, pts = store.points_for_labels(catalogue, [label])
            photos = None
            if show_photos.value and not chosen.empty:
                photos = store.photos_for_gpx(chosen["gpx_path"].tolist())
            fmap, _drawn, status = build_route_map(
                chosen,
                pts,
                max_total_points=int(max_points.value),
                height=int(map_height.value),
                photos=photos if show_photos.value else None,
            )
            strip = ""
            if show_photos.value:
                strip = filmstrip_html(
                    photos if photos is not None else None,
                    title="Along the way",
                )
            if fmap is None:
                stage = mo.md(status)
            else:
                stage = mo.vstack(
                    [
                        mo.md(status),
                        mo.Html(fmap._repr_html_()),
                        mo.Html(strip) if strip else mo.md(""),
                    ]
                )
    return (stage,)


@app.cell
def _(mo, rail, stage):
    mo.hstack([rail, stage], widths=[0.32, 0.68], gap=1.2, align="start")
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ```bash
        just build-db export_zip=/path/to/export.zip
        just geocode-places -- --limit 100
        just photos-for-walks -- --limit-walks 40
        just map-walks
        ```
        Helpers: `python/apple_health_data/` · model: `docs/ERD.md`
        """
    )
    return


if __name__ == "__main__":
    app.run()
