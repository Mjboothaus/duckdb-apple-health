"""Local DuckDB access and (re)build from an Apple Health export."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import duckdb
import pandas as pd

# python/apple_health_data/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = _REPO_ROOT / "output" / "apple_health.duckdb"
_EXT_CANDIDATES = [
    _REPO_ROOT / "build/debug/extension/apple_health/apple_health.duckdb_extension",
    _REPO_ROOT / "build/debug/apple_health.duckdb_extension",
    _REPO_ROOT / "build/release/extension/apple_health/apple_health.duckdb_extension",
]


def repo_root() -> Path:
    return _REPO_ROOT


def find_extension() -> Path:
    for path in _EXT_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "apple_health.duckdb_extension not found. Run `just debug` first."
    )


def _sql_str(value: str) -> str:
    return value.replace("'", "''")


def _activity_in_list(activities: Sequence[str]) -> str:
    cleaned = [a.strip() for a in activities if a and a.strip()]
    if not cleaned:
        raise ValueError("activities must be a non-empty list")
    return ", ".join(f"'{_sql_str(a)}'" for a in cleaned)


@dataclass
class BuildResult:
    db_path: Path
    elapsed_seconds: float
    workouts_n: int
    routes_n: int
    route_points_n: int
    route_points_map_n: int
    activities: list[str]
    source_path: str


class HealthDataStore:
    """Read/query (and optionally rebuild) ``output/apple_health.duckdb``."""

    def __init__(self, db_path: Path | str | None = None, *, read_only: bool = True):
        self.db_path = Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()
        self.read_only = read_only
        self._con: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> "HealthDataStore":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def exists(self) -> bool:
        return self.db_path.is_file()

    def connect(self) -> duckdb.DuckDBPyConnection:
        if self._con is not None:
            return self._con
        if not self.exists:
            raise FileNotFoundError(
                f"Database not found: {self.db_path}. "
                "Run: just build-db export_zip=/path/to/export.zip"
            )
        self._con = duckdb.connect(str(self.db_path), read_only=self.read_only)
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def summary(self) -> pd.DataFrame:
        con = self.connect()
        parts = [
            "SELECT 'workouts' AS t, count(*)::BIGINT AS n FROM workouts",
            "SELECT 'routes', count(*) FROM routes",
            "SELECT 'route_points', count(*) FROM route_points",
            "SELECT 'route_points_map', count(*) FROM route_points_map",
        ]
        has_places = con.execute(
            """
            SELECT count(*)::BIGINT FROM information_schema.tables
            WHERE table_schema IN ('main', 'gps') AND table_name = 'route_places'
            """
        ).fetchone()[0]
        if has_places:
            parts.append("SELECT 'route_places', count(*) FROM route_places")
        return con.execute(" UNION ALL ".join(parts)).df()

    def manifest(self) -> pd.DataFrame:
        return self.connect().execute("SELECT * FROM ingest_manifest").df()

    def _has_route_places(self) -> bool:
        con = self.connect()
        row = con.execute(
            """
            SELECT count(*)::BIGINT
            FROM information_schema.tables
            WHERE table_schema IN ('main', 'gps')
              AND table_name = 'route_places'
            """
        ).fetchone()
        return bool(row and row[0] > 0)

    def list_routes(
        self,
        *,
        activities: Sequence[str] | None = None,
        limit: int = 60,
        require_points: bool = True,
    ) -> pd.DataFrame:
        """Catalogue of routes with point counts and UI labels (most recent first)."""
        con = self.connect()
        acts = list(activities) if activities else ["Walking", "Hiking"]
        in_list = _activity_in_list(acts)
        limit = max(1, int(limit))
        having = "HAVING count(p.point_index) >= 2" if require_points else ""
        join = "JOIN" if require_points else "LEFT JOIN"
        places_join = ""
        place_cols = "NULL::VARCHAR AS start_place, NULL::VARCHAR AS end_place,"
        place_group = ""
        label_place = ""
        if self._has_route_places():
            places_join = "LEFT JOIN route_places pl ON r.gpx_path = pl.gpx_path"
            place_cols = "any_value(pl.start_place) AS start_place, any_value(pl.end_place) AS end_place,"
            # Rebuild label with places when available
            label_place = """
              CASE
                WHEN any_value(pl.start_place) IS NOT NULL OR any_value(pl.end_place) IS NOT NULL THEN
                  strftime(r.workout_start_date, '%Y-%m-%d %H:%M')
                    || ' · ' || r.activity_type_short
                    || ' · ' || coalesce(any_value(pl.start_place), '?')
                    || ' → ' || coalesce(any_value(pl.end_place), '?')
                    || ' · ' || coalesce(
                         round(
                           date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 0
                         )::INT, 0
                       )::VARCHAR || ' min'
                ELSE
            """
            label_place_end = " END"
        else:
            label_place_end = ""
        return con.execute(
            f"""
            SELECT
              r.activity_type_short AS activity,
              r.workout_start_date AS start_date,
              r.workout_end_date AS end_date,
              r.gpx_path,
              r.source_name,
              round(
                date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 1
              ) AS duration_min,
              count(p.point_index)::BIGINT AS n_points,
              {place_cols}
              {label_place}
              strftime(r.workout_start_date, '%Y-%m-%d %H:%M')
                || ' · ' || r.activity_type_short
                || ' · ' || coalesce(
                     round(
                       date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 0
                     )::INT,
                     0
                   )::VARCHAR || ' min'
                || ' · ' || count(p.point_index)::VARCHAR || ' pts'
              {label_place_end}
                AS label
            FROM routes r
            {join} route_points_map p USING (gpx_path)
            {places_join}
            WHERE r.activity_type_short IN ({in_list})
            GROUP BY 1, 2, 3, 4, 5, r.workout_end_date
            {having}
            ORDER BY r.workout_start_date DESC NULLS LAST
            LIMIT {limit}
            """
        ).df()

    def route_points(
        self,
        gpx_paths: Iterable[str],
        *,
        map_layer: bool = True,
    ) -> pd.DataFrame:
        paths = [p for p in gpx_paths if p]
        if not paths:
            return pd.DataFrame(
                columns=[
                    "gpx_path",
                    "point_index",
                    "lat",
                    "lon",
                    "ele",
                    "point_time",
                    "activity",
                ]
            )
        table = "route_points_map" if map_layer else "route_points"
        in_gpx = ", ".join(f"'{_sql_str(p)}'" for p in paths)
        return self.connect().execute(
            f"""
            SELECT
              gpx_path,
              point_index,
              lat,
              lon,
              ele,
              point_time,
              activity_type_short AS activity
            FROM {table}
            WHERE gpx_path IN ({in_gpx})
            ORDER BY gpx_path, point_index
            """
        ).df()


    def route_endpoints(self, gpx_paths: Iterable[str] | None = None) -> pd.DataFrame:
        """First/last map-layer coordinates per route (for reverse geocoding)."""
        con = self.connect()
        if gpx_paths is None:
            where = ""
        else:
            paths = [p for p in gpx_paths if p]
            if not paths:
                return pd.DataFrame(
                    columns=[
                        "gpx_path",
                        "start_lat",
                        "start_lon",
                        "end_lat",
                        "end_lon",
                    ]
                )
            in_gpx = ", ".join(f"'{_sql_str(p)}'" for p in paths)
            where = f"WHERE gpx_path IN ({in_gpx})"
        return con.execute(
            f"""
            WITH ordered AS (
              SELECT gpx_path, point_index, lat, lon,
                     row_number() OVER (PARTITION BY gpx_path ORDER BY point_index) AS rn_asc,
                     row_number() OVER (PARTITION BY gpx_path ORDER BY point_index DESC) AS rn_desc
              FROM route_points_map
              {where}
            )
            SELECT
              gpx_path,
              max(CASE WHEN rn_asc = 1 THEN lat END) AS start_lat,
              max(CASE WHEN rn_asc = 1 THEN lon END) AS start_lon,
              max(CASE WHEN rn_desc = 1 THEN lat END) AS end_lat,
              max(CASE WHEN rn_desc = 1 THEN lon END) AS end_lon
            FROM ordered
            GROUP BY gpx_path
            """
        ).df()

    def enrich_with_places(
        self,
        catalogue: pd.DataFrame,
        *,
        fetch: bool = True,
        cache_path: Path | str | None = None,
        geocoder: object | None = None,
    ) -> pd.DataFrame:
        """Add start_place / end_place via reverse geocode (cached Nominatim).

        Does not rewrite the DuckDB file — labels are derived and cached under
        ``output/geocode_cache.json``. Pass ``fetch=False`` to use cache only
        (missing coords fall back to lat/lon text).
        """
        if catalogue is None or catalogue.empty:
            return catalogue.copy() if catalogue is not None else pd.DataFrame()

        from .places import ReverseGeocoder

        out = catalogue.copy()
        paths = out["gpx_path"].dropna().unique().tolist() if "gpx_path" in out.columns else []

        # Prefer materialised DuckDB places when present.
        start_map: dict[str, str] = {}
        end_map: dict[str, str] = {}
        if self._has_route_places() and paths:
            in_gpx = ", ".join(f"'{_sql_str(p)}'" for p in paths)
            stored = self.connect().execute(
                f"""
                SELECT gpx_path, start_place, end_place
                FROM route_places
                WHERE gpx_path IN ({in_gpx})
                """
            ).df()
            for row in stored.itertuples(index=False):
                if row.start_place:
                    start_map[row.gpx_path] = str(row.start_place)
                if row.end_place:
                    end_map[row.gpx_path] = str(row.end_place)

        missing = [p for p in paths if p not in start_map or p not in end_map]
        if missing:
            ends = self.route_endpoints(missing)
            if not ends.empty:
                geo = geocoder or ReverseGeocoder(
                    cache_path=Path(cache_path) if cache_path else None
                )
                for row in ends.itertuples(index=False):
                    gpx = row.gpx_path
                    if gpx not in start_map and row.start_lat is not None and row.start_lon is not None:
                        start_map[gpx] = geo.lookup(
                            float(row.start_lat), float(row.start_lon), fetch=fetch
                        ).label
                    if gpx not in end_map and row.end_lat is not None and row.end_lon is not None:
                        end_map[gpx] = geo.lookup(
                            float(row.end_lat), float(row.end_lon), fetch=fetch
                        ).label

        if not start_map and not end_map:
            out["start_place"] = None
            out["end_place"] = None
            return out

        out["start_place"] = out["gpx_path"].map(start_map)
        out["end_place"] = out["gpx_path"].map(end_map)
        # Prefer place-aware labels when available.
        if "label" in out.columns:
            def _relabel(r: pd.Series) -> str:
                base = str(r.get("label") or "")
                # Strip trailing " · N pts" noise stays; insert place after activity when present.
                sp, ep = r.get("start_place"), r.get("end_place")
                if pd.isna(sp) and pd.isna(ep):
                    return base
                place = f"{sp or '?'} → {ep or '?'}"
                # Rebuild a compact label for pickers.
                act = r.get("activity") or ""
                start = r.get("start_date")
                try:
                    start_s = pd.Timestamp(start).strftime("%Y-%m-%d %H:%M") if start is not None else ""
                except (TypeError, ValueError):
                    start_s = str(start) if start is not None else ""
                mins = r.get("duration_min")
                mins_s = f"{int(round(float(mins)))} min" if mins is not None and not pd.isna(mins) else ""
                bits = [b for b in (start_s, str(act), place, mins_s) if b]
                return " · ".join(bits) if bits else base

            out["label"] = out.apply(_relabel, axis=1)
        return out


    def materialise_route_places(
        self,
        *,
        gpx_paths: Iterable[str] | None = None,
        only_missing: bool = True,
        fetch: bool = True,
        cache_path: Path | str | None = None,
        geocoder: object | None = None,
        limit: int | None = None,
        progress_every: int = 25,
    ) -> dict[str, int]:
        """Batch reverse-geocode route endpoints into ``gps.route_places``.

        Creates/updates table columns: gpx_path, start/end lat/lon + place labels,
        geocoded_at. Main-schema view ``route_places`` is refreshed. JSON cache under
        ``output/geocode_cache.json`` still applies for Nominatim.

        Returns counts: considered, written, skipped, failed.
        """
        from .places import ReverseGeocoder

        # Need write access; reopen if currently read-only.
        if self.read_only or self._con is not None:
            self.close()
            self.read_only = False
        con = self.connect()
        con.execute("CREATE SCHEMA IF NOT EXISTS gps")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS gps.route_places (
              gpx_path VARCHAR PRIMARY KEY,
              start_lat DOUBLE,
              start_lon DOUBLE,
              end_lat DOUBLE,
              end_lon DOUBLE,
              start_place VARCHAR,
              end_place VARCHAR,
              geocoded_at TIMESTAMPTZ
            )
            """
        )
        con.execute(
            "CREATE OR REPLACE VIEW route_places AS SELECT * FROM gps.route_places"
        )

        ends = self.route_endpoints(gpx_paths)
        if ends.empty:
            return {"considered": 0, "written": 0, "skipped": 0, "failed": 0}

        # Prefer most recent workouts when limiting.
        order = con.execute(
            """
            SELECT gpx_path
            FROM routes
            ORDER BY workout_start_date DESC NULLS LAST
            """
        ).df()
        if not order.empty:
            rank = {g: i for i, g in enumerate(order["gpx_path"].tolist())}
            ends = ends.assign(_rank=ends["gpx_path"].map(lambda g: rank.get(g, 10**9)))
            ends = ends.sort_values("_rank").drop(columns="_rank")

        if only_missing:
            existing = {
                r[0]
                for r in con.execute(
                    """
                    SELECT gpx_path FROM gps.route_places
                    WHERE start_place IS NOT NULL AND end_place IS NOT NULL
                    """
                ).fetchall()
            }
            ends = ends[~ends["gpx_path"].isin(existing)].copy()

        if limit is not None:
            ends = ends.head(max(0, int(limit))).copy()

        considered = len(ends)
        if considered == 0:
            return {"considered": 0, "written": 0, "skipped": 0, "failed": 0}

        geo = geocoder or ReverseGeocoder(
            cache_path=Path(cache_path) if cache_path else None
        )
        written = 0
        failed = 0
        rows: list[tuple] = []
        for i, row in enumerate(ends.itertuples(index=False), start=1):
            try:
                sp = ep = None
                if row.start_lat is not None and row.start_lon is not None:
                    sp = geo.lookup(float(row.start_lat), float(row.start_lon), fetch=fetch).label
                if row.end_lat is not None and row.end_lon is not None:
                    ep = geo.lookup(float(row.end_lat), float(row.end_lon), fetch=fetch).label
                rows.append(
                    (
                        row.gpx_path,
                        float(row.start_lat) if row.start_lat is not None else None,
                        float(row.start_lon) if row.start_lon is not None else None,
                        float(row.end_lat) if row.end_lat is not None else None,
                        float(row.end_lon) if row.end_lon is not None else None,
                        sp,
                        ep,
                    )
                )
            except Exception:
                failed += 1
            if progress_every and i % progress_every == 0:
                print(f"  geocoded {i}/{considered}…", flush=True)

        if rows:
            # DuckDB upsert: delete keys then insert (portable across versions).
            keys = [r[0] for r in rows]
            con.executemany("DELETE FROM gps.route_places WHERE gpx_path = ?", [(k,) for k in keys])
            con.executemany(
                """
                INSERT INTO gps.route_places
                  (gpx_path, start_lat, start_lon, end_lat, end_lon,
                   start_place, end_place, geocoded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, now())
                """,
                rows,
            )
            written = len(rows)

        # Keep main view in sync (already created).
        n = con.execute("SELECT count(*) FROM gps.route_places").fetchone()[0]
        print(f"route_places rows in DB: {n}", flush=True)
        return {
            "considered": considered,
            "written": written,
            "skipped": 0,
            "failed": failed,
        }

    def points_for_labels(
        self,
        catalogue: pd.DataFrame,
        labels: Sequence[str],
        *,
        map_layer: bool = True,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (chosen_rows, points) for selected catalogue labels."""
        if catalogue is None or catalogue.empty or not labels:
            empty = pd.DataFrame()
            return empty, empty
        chosen = catalogue[catalogue["label"].isin(list(labels))].copy()
        paths = chosen["gpx_path"].dropna().unique().tolist()
        return chosen, self.route_points(paths, map_layer=map_layer)

    @classmethod
    def build_from_export(
        cls,
        export_path: Path | str,
        *,
        db_path: Path | str | None = None,
        activities: Sequence[str] = ("Walking", "Hiking"),
        map_points_per_route: int = 1500,
    ) -> BuildResult:
        """Scan export with the extension and (re)create the local database."""
        export = Path(export_path).expanduser().resolve()
        if not export.exists():
            raise FileNotFoundError(f"Export not found: {export}")

        out = Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()

        acts = [a.strip() for a in activities if a and str(a).strip()]
        in_list = _activity_in_list(acts)
        max_pts = max(10, int(map_points_per_route))
        ext = find_extension()

        path_sql = _sql_str(export.as_posix())
        db_sql = _sql_str(out.as_posix())
        ext_sql = _sql_str(ext.as_posix())

        t0 = time.perf_counter()
        con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
        try:
            con.execute(f"LOAD '{ext_sql}'")
            con.execute(f"ATTACH '{db_sql}' AS health")
            con.execute("CREATE SCHEMA IF NOT EXISTS health.gps")
            con.execute("CREATE SCHEMA IF NOT EXISTS health.meta")

            con.execute(
                f"""
                CREATE OR REPLACE TABLE health.gps.workouts AS
                SELECT
                  activity_type, activity_type_short, duration, duration_unit,
                  total_distance, total_distance_unit, total_energy, total_energy_unit,
                  start_date, end_date, creation_date, source_name, source_version,
                  device, filename AS export_member
                FROM apple_health_workouts('{path_sql}')
                WHERE activity_type_short IN ({in_list})
                """
            )
            con.execute(
                f"""
                CREATE OR REPLACE TABLE health.gps.routes AS
                SELECT
                  workout_activity_type,
                  workout_activity_type_short AS activity_type_short,
                  workout_start_date, workout_end_date,
                  start_date AS route_start_date, end_date AS route_end_date,
                  creation_date, source_name, source_version, device,
                  gpx_path, filename AS export_member
                FROM apple_health_workout_routes('{path_sql}')
                WHERE workout_activity_type_short IN ({in_list})
                  AND gpx_path IS NOT NULL AND length(gpx_path) > 0
                """
            )
            con.execute(
                f"""
                CREATE OR REPLACE TABLE health.gps.route_points AS
                SELECT
                  gpx_path, gpx_member,
                  workout_activity_type_short AS activity_type_short,
                  workout_start_date, workout_end_date, point_index,
                  lat, lon, ele, time AS point_time,
                  speed, course, h_acc, v_acc, filename AS export_member
                FROM apple_health_workout_route_points('{path_sql}')
                WHERE workout_activity_type_short IN ({in_list})
                """
            )
            con.execute(
                f"""
                CREATE OR REPLACE TABLE health.gps.route_points_map AS
                WITH ranked AS (
                  SELECT *,
                    row_number() OVER (PARTITION BY gpx_path ORDER BY point_index) AS rn,
                    count(*) OVER (PARTITION BY gpx_path) AS n
                  FROM health.gps.route_points
                )
                SELECT
                  gpx_path, gpx_member, activity_type_short,
                  workout_start_date, workout_end_date, point_index,
                  lat, lon, ele, point_time, speed, course, h_acc, v_acc, export_member
                FROM ranked
                WHERE rn = 1 OR rn = n
                   OR (rn % greatest(CAST(ceil(n / {max_pts}.0) AS BIGINT), 1)) = 0
                """
            )
            con.execute("DROP TABLE IF EXISTS health.meta.ingest_manifest")
            con.execute(
                """
                CREATE TABLE health.meta.ingest_manifest AS
                SELECT
                  now() AS built_at,
                  ? AS source_path,
                  ? AS note,
                  (SELECT count(*) FROM health.gps.workouts) AS workouts_n,
                  (SELECT count(*) FROM health.gps.routes) AS routes_n,
                  (SELECT count(*) FROM health.gps.route_points) AS route_points_n,
                  (SELECT count(*) FROM health.gps.route_points_map) AS route_points_map_n
                """,
                [
                    str(export),
                    f"activities={','.join(acts)}; map_points_per_route={max_pts}",
                ],
            )
            con.execute("DETACH health")
        finally:
            con.close()

        # Main-schema views for simple notebook SQL
        con2 = duckdb.connect(str(out))
        try:
            for name in ("workouts", "routes", "route_points", "route_points_map"):
                con2.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM gps.{name}")
            con2.execute(
                "CREATE OR REPLACE VIEW ingest_manifest AS SELECT * FROM meta.ingest_manifest"
            )
            row = con2.execute(
                """
                SELECT workouts_n, routes_n, route_points_n, route_points_map_n
                FROM ingest_manifest
                """
            ).fetchone()
        finally:
            con2.close()

        return BuildResult(
            db_path=out,
            elapsed_seconds=time.perf_counter() - t0,
            workouts_n=int(row[0]),
            routes_n=int(row[1]),
            route_points_n=int(row[2]),
            route_points_map_n=int(row[3]),
            activities=list(acts),
            source_path=str(export),
        )
