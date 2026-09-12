# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "duckdb",
#     "pandas",
#     "altair",
#     "polars",
# ]
# ///
"""Explore an Apple Health export.zip via the apple_health DuckDB extension.

Loads **community** ``healthkit_export`` when available (DuckDB 1.5.5+, macOS),
with fallback to a local unsigned ``just debug`` / ``just release`` build.

Default export path is the synthetic fixture. Point ``export_path`` at a real
Health zip outside the repo for full exploration. Real exports stay local —
do not commit PHI or parquet built from personal data.
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import time
    from pathlib import Path

    import altair as alt
    import duckdb
    import marimo as mo
    import pandas as pd

    return Path, alt, duckdb, mo, pd, time


@app.cell
def _(Path, mo):
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    _python = str(repo_root / "python")
    if _python not in sys.path:
        sys.path.insert(0, _python)

    from healthkit_store import connect_with_healthkit_export

    default_export = str(repo_root / "test" / "data" / "export.zip")
    # Example real export (outside git):
    # /Users/mjboothaus/icloud/Data/apple_health_export/export23June2025.zip

    export_path = mo.ui.text(
        value=default_export,
        label="Health export path (.zip, .xml, or directory)",
        full_width=True,
    )
    materialise = mo.ui.checkbox(
        value=True,
        label="Materialise selected types to Parquet under output/",
    )
    selected_types = mo.ui.multiselect(
        options=[
            "HeartRate",
            "StepCount",
            "ActiveEnergyBurned",
            "BasalEnergyBurned",
            "DistanceWalkingRunning",
            "SleepAnalysis",
        ],
        value=["HeartRate", "StepCount"],
        label="Types to materialise (type_short)",
    )
    mo.vstack(
        [
            mo.md(
                """
    # Apple Health × DuckDB

    Interactive scan of an Apple Health export through the **`healthkit_export`**
    community extension (falls back to a local unsigned build if needed).

    For **walk / hike GPS maps**, use the separate notebook `notebooks/map_walks.py` (`just map-walks`).

    **Privacy:** keep real `export.zip` files outside git. Prefer aggregates and
    Parquet under `output/` (gitignored).
    """
            ),
            export_path,
            selected_types,
            materialise,
        ]
    )
    return connect_with_healthkit_export, export_path, materialise, repo_root, selected_types


@app.cell
def _(Path, connect_with_healthkit_export, export_path, mo, repo_root):
    zip_path = Path(export_path.value).expanduser()
    if not zip_path.exists():
        raise FileNotFoundError(f"Export not found: {zip_path}")

    con, ext_info = connect_with_healthkit_export(prefer_community=True, allow_local=True)

    if ext_info.source == "community":
        ext_display = "community (INSTALL healthkit_export FROM community)"
    elif ext_info.path is not None:
        try:
            ext_display = str(ext_info.path.relative_to(repo_root))
        except ValueError:
            ext_display = str(ext_info.path)
    else:
        ext_display = ext_info.detail or ext_info.source

    mo.md(
        f"""
    ### Connection

    | | |
    |---|---|
    | Extension | `{ext_display}` |
    | Source | **{ext_info.source}** |
    | Export | `{zip_path}` |
    | Size | **{zip_path.stat().st_size / (1024**2):.1f} MiB** |
    | DuckDB | `{ext_info.duckdb_version}` |
    """
    )
    return con, zip_path


@app.cell
def _(con, time):
    def timed(sql: str):
        t0 = time.perf_counter()
        df = con.sql(sql).df()
        return df, time.perf_counter() - t0


    return (timed,)


@app.cell
def _(mo, timed, zip_path):
    path_sql = zip_path.as_posix().replace("'", "''")

    counts_sql = f"""
    SELECT 'records' AS kind, count(*)::BIGINT AS n FROM read_healthkit_export('{path_sql}')
    UNION ALL
    SELECT 'workouts', count(*)::BIGINT FROM healthkit_workouts('{path_sql}')
    UNION ALL
    SELECT 'activity_days', count(*)::BIGINT FROM healthkit_activity_summaries('{path_sql}')
    """
    counts_df, counts_s = timed(counts_sql)

    mo.vstack(
        [
            mo.md(f"### Inventory scan — **{counts_s:.2f}s** wall time"),
            mo.ui.table(counts_df, selection=None),
            mo.md(
                "_Full-table counts currently re-scan the zip once per table function "
                "(bind buffers rows). Large exports: expect multi-minute scans._"
            ),
        ]
    )
    return counts_s, path_sql


@app.cell
def _(mo, path_sql, timed):
    types_sql = f"""
    SELECT type_short, count(*)::BIGINT AS n, count(value)::BIGINT AS n_numeric
    FROM read_healthkit_export('{path_sql}')
    GROUP BY 1
    ORDER BY n DESC
    """
    types_df, types_s = timed(types_sql)

    mo.vstack(
        [
            mo.md(f"### Record types — **{types_s:.2f}s**"),
            mo.ui.table(types_df, selection=None, page_size=25),
        ]
    )
    return types_df, types_s


@app.cell
def _(alt, mo, types_df):
    chart_types = (
        alt.Chart(types_df.head(20))
        .mark_bar()
        .encode(
            x=alt.X("n:Q", title="Rows"),
            y=alt.Y("type_short:N", sort="-x", title="type_short"),
            tooltip=["type_short", "n", "n_numeric"],
        )
        .properties(height=420, title="Top record types")
    )
    mo.ui.altair_chart(chart_types)
    return


@app.cell
def _(mo, path_sql, timed):
    workouts_sql = f"""
    SELECT
      activity_type_short,
      count(*)::BIGINT AS n,
      avg(duration) AS avg_duration,
      avg(total_distance) AS avg_distance,
      avg(total_energy) AS avg_energy
    FROM healthkit_workouts('{path_sql}')
    GROUP BY 1
    ORDER BY n DESC
    """
    workouts_df, workouts_s = timed(workouts_sql)

    mo.vstack(
        [
            mo.md(f"### Workouts by activity — **{workouts_s:.2f}s**"),
            mo.ui.table(workouts_df, selection=None),
        ]
    )
    return (workouts_s,)


@app.cell
def _(mo, path_sql, timed):
    rings_sql = f"""
    SELECT
      count(*)::BIGINT AS days,
      avg(active_energy_burned) AS avg_move_kcal,
      avg(apple_move_minutes) AS avg_move_minutes_legacy,
      avg(apple_move_time) AS avg_move_time_ios14,
      avg(apple_exercise_time) AS avg_exercise,
      avg(apple_stand_hours) AS avg_stand
    FROM healthkit_activity_summaries('{path_sql}')
    """
    rings_df, rings_s = timed(rings_sql)

    sample_rings_sql = f"""
    SELECT date_components,
           active_energy_burned,
           apple_move_minutes,
           apple_move_time,
           apple_exercise_time,
           apple_stand_hours
    FROM healthkit_activity_summaries('{path_sql}')
    ORDER BY date_components DESC
    LIMIT 14
    """
    sample_rings_df, sample_rings_s = timed(sample_rings_sql)

    mo.vstack(
        [
            mo.md(f"### Activity rings (aggregates) — **{rings_s:.2f}s**"),
            mo.ui.table(rings_df, selection=None),
            mo.md(f"### Recent 14 summary days — **{sample_rings_s:.2f}s**"),
            mo.ui.table(sample_rings_df, selection=None),
        ]
    )
    return rings_s, sample_rings_s


@app.cell
def _(con, materialise, mo, path_sql, pd, repo_root, selected_types, time):
    out_dir = repo_root / "output"
    out_dir.mkdir(exist_ok=True)
    timing_rows = []
    written = []

    if materialise.value and selected_types.value:
        for type_short in selected_types.value:
            safe = type_short.replace("/", "_")
            out_path = out_dir / f"{safe}.parquet"
            sql = f"""
            COPY (
              SELECT *
              FROM read_healthkit_export('{path_sql}')
              WHERE type_short = '{type_short.replace("'", "''")}'
            ) TO '{out_path.as_posix()}' (FORMAT parquet)
            """
            t0 = time.perf_counter()
            con.execute(sql)
            dt = time.perf_counter() - t0
            size_mb = out_path.stat().st_size / (1024**2) if out_path.exists() else 0.0
            n = con.execute(
                f"SELECT count(*) FROM read_parquet('{out_path.as_posix()}')"
            ).fetchone()[0]
            timing_rows.append(
                {
                    "type_short": type_short,
                    "seconds": round(dt, 3),
                    "rows": int(n),
                    "parquet_mib": round(size_mb, 3),
                    "path": str(out_path.relative_to(repo_root)),
                }
            )
            written.append(out_path)

    timing_df = (
        pd.DataFrame(timing_rows)
        if timing_rows
        else pd.DataFrame(columns=["type_short", "seconds", "rows", "parquet_mib", "path"])
    )

    mo.vstack(
        [
            mo.md("### Materialise → Parquet"),
            mo.md(
                "Raw XML/zip is a scan. **Parquet is the fast path** for repeat analytics. "
                f"Output directory: `output/` ({'written' if written else 'skipped'})."
            ),
            mo.ui.table(timing_df, selection=None),
        ]
    )
    return timing_df, written


@app.cell
def _(alt, con, mo, written):
    chart_parts = []
    notes = []
    if written:
        hr = next((p for p in written if p.name.lower().startswith("heartrate")), None)
        target = hr or written[0]
        daily = con.execute(
            f"""
            SELECT date_trunc('day', start_date)::DATE AS day,
                   avg(value) AS avg_value,
                   count(*)::BIGINT AS n
            FROM read_parquet('{target.as_posix()}')
            WHERE value IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """
        ).df()
        notes.append(f"Daily series from `{target.name}` ({len(daily)} days).")
        if len(daily):
            daily_chart = (
                alt.Chart(daily)
                .mark_line(point=True)
                .encode(
                    x=alt.X("day:T", title="Day"),
                    y=alt.Y("avg_value:Q", title="Average value"),
                    tooltip=["day", "avg_value", "n"],
                )
                .properties(height=280, title=f"Daily average — {target.stem}")
            )
            chart_parts.append(mo.ui.altair_chart(daily_chart))
    else:
        notes.append("Enable materialise + select types to plot from Parquet.")

    mo.vstack(
        [
            mo.md("### From Parquet (fast path)"),
            mo.md("\n".join(f"- {n}" for n in notes)),
            *chart_parts,
        ]
    )
    return


@app.cell
def _(
    counts_s,
    mo,
    pd,
    rings_s,
    sample_rings_s,
    timing_df,
    types_s,
    workouts_s,
):
    perf = pd.DataFrame(
        [
            {"step": "inventory counts (3 TFs)", "seconds": counts_s},
            {"step": "type histogram (full record scan)", "seconds": types_s},
            {"step": "workouts by activity", "seconds": workouts_s},
            {"step": "activity summary averages", "seconds": rings_s},
            {"step": "activity summary sample", "seconds": sample_rings_s},
        ]
    )
    if len(timing_df):
        extra = pd.DataFrame(
            {
                "step": [f"COPY {t} → parquet" for t in timing_df["type_short"]],
                "seconds": timing_df["seconds"].tolist(),
            }
        )
        perf = pd.concat([perf, extra], ignore_index=True)

    mo.vstack(
        [
            mo.md("### Timing summary"),
            mo.ui.table(perf, selection=None),
            mo.md(
                """
    **Notes**

    - Table functions parse in **bind** and buffer rows — memory scales with export size.
    - Re-running cells re-scans the zip unless you query Parquet instead.
    - Named filters (`types` / `start` / `end`) are planned; filter in SQL or COPY for now.
    - Prefer **DuckDB 1.5.5+** on **macOS** so `INSTALL healthkit_export FROM community` works;
      otherwise build locally with `just debug` / `just release` (unsigned fallback).
    """
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ---
    ### Try it

    ```bash
    # Optional if community install is unavailable for your DuckDB build:
    just debug
    uv sync
    uv run marimo edit notebooks/explore_export.py
    ```

    Community path (CLI, DuckDB **1.5.5+**, macOS):

    ```sql
    INSTALL healthkit_export FROM community;
    LOAD healthkit_export;
    ```

    Point the path field at a real Health export outside the repo, e.g.
    `~/icloud/Data/apple_health_export/export23June2025.zip`.
    """)
    return


if __name__ == "__main__":
    app.run()
