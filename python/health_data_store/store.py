"""Local DuckDB access and (re)build from an Apple Health export."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import duckdb
import pandas as pd

# python/health_data_store/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = _REPO_ROOT / "output" / "apple_health.duckdb"
_EXT_CANDIDATES = [
    _REPO_ROOT / "build/debug/extension/healthkit_export/healthkit_export.duckdb_extension",
    _REPO_ROOT / "build/debug/healthkit_export.duckdb_extension",
    _REPO_ROOT / "build/release/extension/healthkit_export/healthkit_export.duckdb_extension",
    _REPO_ROOT / "build/release/healthkit_export.duckdb_extension",
]


def repo_root() -> Path:
    return _REPO_ROOT


def find_extension() -> Path:
    """Locate a locally built unsigned extension binary (developer builds)."""
    for path in _EXT_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "healthkit_export.duckdb_extension not found. "
        "Prefer: INSTALL healthkit_export FROM community (DuckDB 1.5.5+, macOS), "
        "or run `just debug` / `just release` for a local unsigned build."
    )


@dataclass(frozen=True)
class ExtensionLoadInfo:
    """How ``healthkit_export`` was loaded into a connection."""

    source: str  # "community" | "local"
    path: Path | None
    duckdb_version: str
    detail: str = ""


def load_healthkit_export(
    con: duckdb.DuckDBPyConnection,
    *,
    prefer_community: bool = True,
    allow_local: bool = True,
) -> ExtensionLoadInfo:
    """LOAD ``healthkit_export`` on an existing connection.

    Tries community install first (signed, no ``-unsigned``). Falls back to a
    local ``build/…`` binary when present. The connection must already allow
    unsigned extensions if only a local binary is available
    (``allow_unsigned_extensions=true`` at connect time).
    """
    version = str(con.execute("SELECT version()").fetchone()[0])
    errors: list[str] = []

    if prefer_community:
        try:
            con.execute("INSTALL healthkit_export FROM community")
            con.execute("LOAD healthkit_export")
            return ExtensionLoadInfo(
                source="community",
                path=None,
                duckdb_version=version,
                detail="INSTALL healthkit_export FROM community",
            )
        except Exception as exc:  # noqa: BLE001 — try local next
            errors.append(f"community: {exc}")

    if allow_local:
        ext = find_extension()
        try:
            con.execute(f"LOAD '{_sql_str(ext.as_posix())}'")
            return ExtensionLoadInfo(
                source="local",
                path=ext,
                duckdb_version=version,
                detail=str(ext),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"local ({ext}): {exc}")

    joined = "; ".join(errors) if errors else "no sources tried"
    raise RuntimeError(
        "Could not LOAD healthkit_export. "
        "Need DuckDB **1.5.5+** on **macOS** for community install, "
        "or a local unsigned build (`just debug`). "
        f"Details: {joined}"
    )


def connect_with_healthkit_export(
    *,
    prefer_community: bool = True,
    allow_local: bool = True,
) -> tuple[duckdb.DuckDBPyConnection, ExtensionLoadInfo]:
    """Open an in-memory DuckDB connection with ``healthkit_export`` loaded.

    Community path uses a normal connection. Local fallback reconnects with
    ``allow_unsigned_extensions`` so developer builds still work.
    """
    if prefer_community:
        con = duckdb.connect()
        try:
            info = load_healthkit_export(
                con, prefer_community=True, allow_local=False
            )
            return con, info
        except Exception:
            con.close()

    if not allow_local:
        raise RuntimeError(
            "Community INSTALL healthkit_export failed and local fallback is disabled."
        )

    ext = find_extension()
    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    try:
        con.execute(f"LOAD '{_sql_str(ext.as_posix())}'")
    except Exception:
        con.close()
        raise
    version = str(con.execute("SELECT version()").fetchone()[0])
    return con, ExtensionLoadInfo(
        source="local",
        path=ext,
        duckdb_version=version,
        detail=str(ext),
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
        has_photos = con.execute(
            """
            SELECT count(*)::BIGINT FROM information_schema.tables
            WHERE table_schema IN ('main', 'gps') AND table_name = 'walk_photos'
            """
        ).fetchone()[0]
        if has_photos:
            parts.append("SELECT 'walk_photos', count(*) FROM walk_photos")
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



    def _write_con(self) -> duckdb.DuckDBPyConnection:
        """Reopen read-write if needed for meta tables."""
        if self.read_only or self._con is None:
            self.close()
            self.read_only = False
        return self.connect()

    def list_journeys(self) -> pd.DataFrame:
        from .journeys import ensure_journey_tables, list_journeys as _list

        con = self._write_con()
        ensure_journey_tables(con)
        return _list(con)

    def journey_sections(self, journey_id: str) -> pd.DataFrame:
        from .journeys import ensure_journey_tables, journey_sections_df

        con = self._write_con()
        ensure_journey_tables(con)
        df = journey_sections_df(con, journey_id)
        if df.empty:
            return df
        # One row per section (guard join fan-out)
        if "section_index" in df.columns:
            df = df.drop_duplicates(subset=["section_index"], keep="first")
        elif "gpx_path" in df.columns:
            df = df.drop_duplicates(subset=["gpx_path"], keep="first")
        # Fill place chips from "Section N: Start → End" labels when route_places missing
        def _split_label(lab: object) -> tuple[object, object]:
            if lab is None or (isinstance(lab, float) and lab != lab):
                return None, None
            s = str(lab)
            if "→" in s:
                left, right = s.split("→", 1)
                left = left.split(":", 1)[-1].strip() if ":" in left else left.strip()
                return left or None, right.strip() or None
            return None, None

        if "start_place" not in df.columns:
            df["start_place"] = None
        if "end_place" not in df.columns:
            df["end_place"] = None
        for i, row in df.iterrows():
            sp0, ep0 = row.get("start_place"), row.get("end_place")
            need = sp0 is None or (isinstance(sp0, float) and sp0 != sp0) or str(sp0) in ("", "None", "nan")
            need = need or ep0 is None or (isinstance(ep0, float) and ep0 != ep0) or str(ep0) in ("", "None", "nan")
            if need and "section_label" in df.columns:
                a, b = _split_label(row.get("section_label"))
                if need and a:
                    df.at[i, "start_place"] = a
                if b:
                    df.at[i, "end_place"] = b
        return df

    def import_journey_manifest(self, path: Path | str):
        from .journeys import import_manifest

        con = self._write_con()
        return import_manifest(con, path)

    def points_for_journey(self, journey_id: str, *, map_layer: bool = True) -> pd.DataFrame:
        """Route points for all sections, tagged with section_index."""
        sec = self.journey_sections(journey_id)
        if sec.empty:
            return pd.DataFrame()
        paths = sec["gpx_path"].dropna().tolist()
        pts = self.route_points(paths, map_layer=map_layer)
        if pts.empty:
            return pts
        idx_map = {r.gpx_path: int(r.section_index) for r in sec.itertuples(index=False)}
        pts = pts.copy()
        pts["section_index"] = pts["gpx_path"].map(idx_map)
        label_map = {
            r.gpx_path: (r.section_label or f"Section {int(r.section_index)}")
            for r in sec.itertuples(index=False)
        }
        pts["section_label"] = pts["gpx_path"].map(label_map)
        return pts.sort_values(["section_index", "point_index"])

    def photos_for_journey(self, journey_id: str) -> pd.DataFrame:
        sec = self.journey_sections(journey_id)
        if sec.empty:
            return self.photos_for_gpx([])
        ph = self.photos_for_gpx(sec["gpx_path"].dropna().tolist())
        if ph.empty:
            return ph
        idx_map = {r.gpx_path: int(r.section_index) for r in sec.itertuples(index=False)}
        ph = ph.copy()
        ph["section_index"] = ph["gpx_path"].map(idx_map)
        return ph.sort_values(["section_index", "taken_at"])

    def photos_for_gpx(self, gpx_paths: Iterable[str] | None = None) -> pd.DataFrame:
        """Return walk_photos rows (empty frame if table missing)."""
        con = self.connect()
        exists = con.execute(
            """
            SELECT count(*)::BIGINT FROM information_schema.tables
            WHERE table_schema IN ('main', 'gps') AND table_name = 'walk_photos'
            """
        ).fetchone()[0]
        if not exists:
            return pd.DataFrame(
                columns=[
                    "photo_id",
                    "gpx_path",
                    "taken_at",
                    "snap_lat",
                    "snap_lon",
                    "thumb_path",
                    "match_quality",
                    "distance_m",
                ]
            )
        if gpx_paths is None:
            return con.execute(
                """
                SELECT photo_id, gpx_path, taken_at, photo_lat, photo_lon,
                       snap_lat, snap_lon, distance_m, match_quality, thumb_path, full_path
                FROM walk_photos
                ORDER BY gpx_path, taken_at
                """
            ).df()
        paths = [p for p in gpx_paths if p]
        if not paths:
            return pd.DataFrame()
        in_gpx = ", ".join(f"'{_sql_str(p)}'" for p in paths)
        return con.execute(
            f"""
            SELECT photo_id, gpx_path, taken_at, photo_lat, photo_lon,
                   snap_lat, snap_lon, distance_m, match_quality, thumb_path, full_path
            FROM walk_photos
            WHERE gpx_path IN ({in_gpx})
            ORDER BY gpx_path, taken_at
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
        path_sql = _sql_str(export.as_posix())
        db_sql = _sql_str(out.as_posix())

        t0 = time.perf_counter()
        con, _ext_info = connect_with_healthkit_export(prefer_community=True, allow_local=True)
        try:
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
                FROM healthkit_workouts('{path_sql}')
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
                FROM healthkit_workout_routes('{path_sql}')
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
                FROM healthkit_workout_route_points('{path_sql}')
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
