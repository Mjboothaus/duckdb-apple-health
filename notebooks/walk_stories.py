"""Walk stories — multi-day journeys + maps + photos.

Requires a local DB from ``just build-db`` (uses community ``healthkit_export`` when
available, else a local unsigned build).

```bash
just walk-stories          # marimo run (app view)
just walk-stories-edit     # marimo edit
```
"""

from __future__ import annotations

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo

    repo_root = Path(__file__).resolve().parents[1]
    py_path = str(repo_root / "python")
    if py_path not in sys.path:
        sys.path.insert(0, py_path)

    from health_data_store import DEFAULT_DB_PATH, HealthDataStore, build_route_map
    from health_data_store.maps import filmstrip_html, wrap_map_html

    return (
        DEFAULT_DB_PATH,
        HealthDataStore,
        Path,
        build_route_map,
        filmstrip_html,
        mo,
        wrap_map_html,
        repo_root,
    )


@app.cell
def _(DEFAULT_DB_PATH, HealthDataStore, Path, mo):
    path = Path(DEFAULT_DB_PATH).expanduser()
    store = None
    journeys_df = None
    err = None

    if not path.is_file():
        err = f"Missing `{path}`. Run `just build-db` first."
    else:
        try:
            store = HealthDataStore(path, read_only=True)
            store.connect()
            journeys_df = store.list_journeys()
        except Exception as e:  # noqa: BLE001
            err = str(e)
            store = None

    n_j = 0 if journeys_df is None or journeys_df.empty else len(journeys_df)
    n_ph = 0
    if store is not None:
        try:
            n_ph = int(store.summary().set_index("t").loc["walk_photos", "n"])
        except Exception:
            n_ph = 0

    if err:
        header = mo.md(f"# Walk stories\n\n**Error:** {err}")
    else:
        header = mo.md(
            f"""
# Walk stories
`{path.name}` · **{n_j}** journeys · **{n_ph:,}** photos
"""
        )
    header
    return header, journeys_df, path, store


@app.cell
def _(journeys_df, mo, store):
    major = [
        "camino-del-norte",
        "abel-tasman",
        "three-capes",
        "six-foot-track",
        "great-north-walk",
    ]
    opts: list[str] = []
    default = None
    if store is not None and journeys_df is not None and not journeys_df.empty:
        ids = journeys_df["journey_id"].tolist()
        titles = dict(zip(journeys_df["journey_id"], journeys_df["title"], strict=False))
        ordered = [j for j in major if j in ids] + [j for j in ids if j not in major]
        opts = [f"{titles.get(j, j)} ({j})" for j in ordered]
        default = opts[0] if opts else None

    journey_picker = mo.ui.dropdown(
        options=opts or ["(no journeys)"],
        value=default,
        label="Journey",
        full_width=True,
    )
    show_photos = mo.ui.checkbox(value=False, label="Show photo pins + filmstrip")
    map_height = mo.ui.slider(700, 1200, value=920, step=20, label="Map height", show_value=True)
    max_points = mo.ui.slider(2000, 20000, value=8000, step=500, label="Track points", show_value=True)
    max_photos = mo.ui.slider(0, 60, value=24, step=4, label="Photo pin cap", show_value=True)

    controls = mo.vstack(
        [
            mo.md("### Controls"),
            journey_picker,
            mo.hstack(
                [show_photos, map_height, max_points, max_photos],
                justify="start",
                gap=1.25,
                wrap=True,
            ),
        ]
    )
    controls
    return controls, journey_picker, map_height, max_photos, max_points, show_photos


@app.cell
def _(journey_picker, mo, store):
    sections = None
    journey_id = None
    focus_opts = ["All sections"]
    meta = "_Choose a journey above._"
    table = mo.md("")

    if store is not None and journey_picker.value and "(" in str(journey_picker.value):
        raw = str(journey_picker.value)
        journey_id = raw.rsplit("(", 1)[-1].rstrip(")").strip()
        sections = store.journey_sections(journey_id)
        if sections is not None and not sections.empty:
            sections = sections.drop_duplicates(subset=["section_index"], keep="first")
            seen: set[str] = set()
            for r in sections.sort_values("section_index").itertuples(index=False):
                lab = r.section_label or f"Section {int(r.section_index)}"
                short = str(lab).split(":", 1)[-1].strip() if ":" in str(lab) else str(lab)
                if len(short) > 42:
                    short = short[:41] + "…"
                opt = f"{int(r.section_index)}. {short}"
                if opt in seen:
                    opt = f"{opt} #{len(seen)}"
                seen.add(opt)
                focus_opts.append(opt)

            overview = store.list_journeys()
            row = overview[overview.journey_id == journey_id]
            if not row.empty:
                r0 = row.iloc[0]
                hrs = r0.get("total_hours")
                hrs_s = f"{float(hrs):.1f} h" if hrs == hrs else ""
                meta = f"**{r0.get('title')}** · {int(r0.get('sections_n') or 0)} legs"
                if hrs_s:
                    meta += f" · {hrs_s}"

            cols = [
                c
                for c in (
                    "section_index",
                    "section_label",
                    "duration_min",
                    "start_place",
                    "end_place",
                    "start_date",
                )
                if c in sections.columns
            ]
            table = mo.ui.table(sections[cols], selection=None, page_size=12)

    focus = mo.ui.dropdown(
        options=focus_opts,
        value="All sections",
        label="Focus section",
        full_width=True,
    )

    journey_panel = mo.vstack(
        [
            mo.md("### Journey"),
            mo.md(meta),
            focus,
            table,
        ]
    )
    journey_panel
    return focus, journey_id, journey_panel, sections


@app.cell
def _(
    Path,
    build_route_map,
    filmstrip_html,
    focus,
    journey_id,
    map_height,
    max_photos,
    max_points,
    mo,
    repo_root,
    sections,
    show_photos,
    store,
    wrap_map_html,
):
    map_panel = mo.md("### Map\n_Waiting for journey…_")

    if store is not None and journey_id and sections is not None and not sections.empty:
        sec = sections.copy()
        fv = focus.value if focus is not None else "All sections"
        if (
            isinstance(fv, str)
            and fv != "All sections"
            and len(fv) > 0
            and fv[0].isdigit()
        ):
            try:
                si = int(fv.split(".", 1)[0])
                sec = sec[sec["section_index"] == si]
            except ValueError:
                pass

        pts = store.points_for_journey(journey_id)
        if pts is None or (hasattr(pts, "empty") and pts.empty):
            map_panel = mo.md(
                f"### Map\nNo GPS points for `{journey_id}`. "
                "Rebuild DB with route points / check journey YAML gpx paths."
            )
        else:
            if not sec.empty and "gpx_path" in sec.columns:
                pts = pts[pts["gpx_path"].isin(sec["gpx_path"].tolist())]

            photos = None
            if show_photos.value:
                photos = store.photos_for_journey(journey_id)
                if photos is not None and not photos.empty and not sec.empty:
                    photos = photos[photos["gpx_path"].isin(sec["gpx_path"].tolist())]

            chosen = sec.copy()
            if "activity" not in chosen.columns:
                chosen["activity"] = "Hiking"
            else:
                chosen["activity"] = chosen["activity"].fillna("Hiking")

            h = int(map_height.value)
            n_pin = int(max_photos.value)

            try:
                fmap, _drawn, status = build_route_map(
                    chosen,
                    pts,
                    max_total_points=int(max_points.value),
                    height=h,
                    photos=photos if show_photos.value else None,
                    max_photos=n_pin,
                    image_mode="data_uri",
                    prepare_web_thumbs=bool(show_photos.value),
                    place_labels="numbers",
                )
            except Exception as e:  # noqa: BLE001
                fmap, status = None, f"**Map build failed:** `{type(e).__name__}: {e}`"

            if fmap is None:
                map_panel = mo.md(f"### Map\n{status}")
            else:
                # mo.Html does not run <script>; Folium needs mo.iframe
                try:
                    doc = wrap_map_html(fmap, height=h)
                    # Quiet debug artefact (not shown in UI)
                    live = Path(repo_root) / "output" / "maps" / "_walk_stories_live.html"
                    live.parent.mkdir(parents=True, exist_ok=True)
                    live.write_text(doc, encoding="utf-8")
                    map_frame = mo.iframe(doc, width="100%", height=f"{h}px")
                except Exception as e:  # noqa: BLE001
                    map_frame = mo.md(f"**Embed failed:** `{e}`")
                    status = f"{status} (embed error)"

                strip = mo.md("")
                if show_photos.value and photos is not None:
                    try:
                        strip = mo.Html(
                            filmstrip_html(
                                photos,
                                title="Along the way",
                                max_items=min(24, max(n_pin, 8)),
                                image_mode="data_uri",
                                prepare_web_thumbs=True,
                            )
                        )
                    except Exception as e:  # noqa: BLE001
                        strip = mo.md(f"Filmstrip error: `{e}`")

                map_panel = mo.vstack(
                    [
                        mo.md(f"### Map\n{status}"),
                        map_frame,
                        strip,
                    ]
                )

    map_panel
    return (map_panel,)


@app.cell
def _(mo):
    footer = mo.md(
        """
---
Hover a coloured track for place names · numbered badges mark each leg · photo pins optional.
"""
    )
    footer
    return (footer,)


if __name__ == "__main__":
    app.run()
