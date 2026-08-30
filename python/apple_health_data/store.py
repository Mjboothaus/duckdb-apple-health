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
        return con.execute(
            """
            SELECT 'workouts' AS t, count(*)::BIGINT AS n FROM workouts
            UNION ALL SELECT 'routes', count(*) FROM routes
            UNION ALL SELECT 'route_points', count(*) FROM route_points
            UNION ALL SELECT 'route_points_map', count(*) FROM route_points_map
            """
        ).df()

    def manifest(self) -> pd.DataFrame:
        return self.connect().execute("SELECT * FROM ingest_manifest").df()

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
              strftime(r.workout_start_date, '%Y-%m-%d %H:%M')
                || ' · ' || r.activity_type_short
                || ' · ' || coalesce(
                     round(
                       date_diff('second', r.workout_start_date, r.workout_end_date) / 60.0, 0
                     )::INT,
                     0
                   )::VARCHAR || ' min'
                || ' · ' || count(p.point_index)::VARCHAR || ' pts'
                AS label
            FROM routes r
            {join} route_points_map p USING (gpx_path)
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
