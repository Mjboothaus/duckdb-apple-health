"""Match Apple Photos to walks via Photos.sqlite + DuckDB; export thumbs."""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import duckdb
import pandas as pd

from .store import DEFAULT_DB_PATH, repo_root

# Cocoa (Core Data) seconds since 2001-01-01 → Unix
_COCOA_UNIX_OFFSET = 978_307_200

DEFAULT_PHOTOS_LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"
DEFAULT_THUMB_DIR = repo_root() / "output" / "photo_thumbs"
DEFAULT_WEB_THUMB_DIR = repo_root() / "output" / "photo_web_thumbs"


@dataclass
class PhotoMatchStats:
    walks_considered: int
    rows_written: int
    thumbs_copied: int
    photos_library: Path


def default_photos_sqlite(library: Path | None = None) -> Path:
    lib = Path(library or DEFAULT_PHOTOS_LIBRARY).expanduser()
    return lib / "database" / "Photos.sqlite"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def find_derivative_jpeg(
    library: Path,
    directory: str,
    uuid: str,
    *,
    prefer: str = "thumb",
) -> Path | None:
    """Find a JPEG derivative from the Photos library.

    prefer:
      - "thumb": small UI/map filmstrip image
      - "full": larger masters derivative for click/lightbox (not original HEIC)
    """
    lib = Path(library)
    dir_s = str(directory)
    small = [
        lib / "resources" / "derivatives" / dir_s / f"{uuid}_1_105_c.jpeg",
        lib / "resources" / "derivatives" / dir_s / f"{uuid}_1_105_c.jpg",
    ]
    large: list[Path] = []
    masters = lib / "resources" / "derivatives" / "masters" / dir_s
    if masters.is_dir():
        large.extend(sorted(masters.glob(f"{uuid}_*_c.jpeg"), reverse=True))
        large.extend(sorted(masters.glob(f"{uuid}_*_c.jpg"), reverse=True))
    # also any other mid-size derivatives
    mid_dir = lib / "resources" / "derivatives" / dir_s
    if mid_dir.is_dir():
        for pth in sorted(mid_dir.glob(f"{uuid}_*_c.jpeg"), reverse=True):
            if pth not in small:
                large.append(pth)
    order = large + small if prefer == "full" else small + large
    for pth in order:
        if pth.is_file():
            return pth
    return None


def match_photos_to_walks(
    *,
    health_db: Path | str | None = None,
    photos_sqlite: Path | str | None = None,
    gpx_paths: Sequence[str] | None = None,
    pad_minutes: float = 5.0,
    max_dist_m: float = 120.0,
    require_gps: bool = True,
    limit_walks: int | None = None,
    max_photos_per_walk: int = 40,
) -> pd.DataFrame:
    """SQL-join Photos.sqlite assets to health routes; snap to nearest map point.

    Returns a DataFrame ready to write into ``walk_photos``.
    """
    health = Path(health_db or DEFAULT_DB_PATH).expanduser().resolve()
    psql = Path(photos_sqlite or default_photos_sqlite()).expanduser().resolve()
    if not health.is_file():
        raise FileNotFoundError(f"Health DB not found: {health}")
    if not psql.is_file():
        raise FileNotFoundError(f"Photos.sqlite not found: {psql}")

    con = duckdb.connect()
    try:
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute(f"ATTACH '{psql.as_posix()}' AS photos (TYPE sqlite, READ_ONLY)")
        con.execute(f"ATTACH '{health.as_posix()}' AS health (READ_ONLY)")

        path_filter = ""
        if gpx_paths:
            ins = ", ".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in gpx_paths if p)
            path_filter = f"AND r.gpx_path IN ({ins})"

        limit_sql = f"LIMIT {int(limit_walks)}" if limit_walks else ""
        pad = float(pad_minutes)

        # Match by time window first (fast). GPS filter applied in Python with route points.
        matched = con.execute(
            f"""
            WITH assets AS (
              SELECT
                a.ZUUID AS photo_id,
                a.ZDIRECTORY AS directory,
                a.ZFILENAME AS filename,
                to_timestamp(epoch(a.ZDATECREATED) + {_COCOA_UNIX_OFFSET}) AS taken_at,
                a.ZLATITUDE AS lat,
                a.ZLONGITUDE AS lon
              FROM photos.ZASSET a
              WHERE coalesce(a.ZTRASHEDSTATE, 0) = 0
                AND a.ZKIND = 0
                AND a.ZLATITUDE IS NOT NULL
                AND a.ZLONGITUDE IS NOT NULL
                AND abs(a.ZLATITUDE) <= 90
                AND abs(a.ZLONGITUDE) <= 180
            ),
            walks AS (
              SELECT
                r.gpx_path,
                r.workout_start_date AS start_ts,
                r.workout_end_date AS end_ts
              FROM health.routes r
              WHERE 1=1 {path_filter}
              ORDER BY r.workout_start_date DESC NULLS LAST
              {limit_sql}
            )
            SELECT
              w.gpx_path,
              w.start_ts,
              w.end_ts,
              a.photo_id,
              a.directory,
              a.filename,
              a.taken_at,
              a.lat AS photo_lat,
              a.lon AS photo_lon
            FROM walks w
            JOIN assets a
              ON a.taken_at BETWEEN w.start_ts - (INTERVAL 1 SECOND * {int(pad * 60)})
                               AND w.end_ts   + (INTERVAL 1 SECOND * {int(pad * 60)})
            ORDER BY w.gpx_path, a.taken_at
            """
        ).df()
    finally:
        con.close()

    if matched.empty:
        return matched

    # Load route points for candidate walks and snap / distance-filter
    paths = matched["gpx_path"].dropna().unique().tolist()
    hcon = duckdb.connect(str(health), read_only=True)
    try:
        in_gpx = ", ".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in paths)
        pts = hcon.execute(
            f"""
            SELECT gpx_path, point_index, lat, lon, point_time
            FROM route_points_map
            WHERE gpx_path IN ({in_gpx})
            ORDER BY gpx_path, point_index
            """
        ).df()
    finally:
        hcon.close()

    if pts.empty:
        matched["snap_lat"] = matched["photo_lat"]
        matched["snap_lon"] = matched["photo_lon"]
        matched["distance_m"] = None
        matched["match_quality"] = "time_only"
        return _cap_per_walk(matched, max_photos_per_walk)

    pts_by_gpx = {g: gdf for g, gdf in pts.groupby("gpx_path", sort=False)}

    snap_lat: list[float] = []
    snap_lon: list[float] = []
    dist_m: list[float | None] = []
    quality: list[str] = []
    keep: list[bool] = []

    for row in matched.itertuples(index=False):
        gdf = pts_by_gpx.get(row.gpx_path)
        plat, plon = float(row.photo_lat), float(row.photo_lon)
        if gdf is None or gdf.empty:
            snap_lat.append(plat)
            snap_lon.append(plon)
            dist_m.append(None)
            quality.append("time_only")
            keep.append(not require_gps)
            continue
        # nearest point
        best_i = 0
        best_d = float("inf")
        lats = gdf["lat"].to_numpy()
        lons = gdf["lon"].to_numpy()
        for i in range(len(gdf)):
            d = _haversine_m(plat, plon, float(lats[i]), float(lons[i]))
            if d < best_d:
                best_d = d
                best_i = i
        snap_lat.append(float(lats[best_i]))
        snap_lon.append(float(lons[best_i]))
        dist_m.append(best_d)
        if best_d <= max_dist_m:
            quality.append("gps_time")
            keep.append(True)
        else:
            quality.append("time_far")
            keep.append(not require_gps)

    matched = matched.copy()
    matched["snap_lat"] = snap_lat
    matched["snap_lon"] = snap_lon
    matched["distance_m"] = dist_m
    matched["match_quality"] = quality
    matched = matched[keep].reset_index(drop=True)
    return _cap_per_walk(matched, max_photos_per_walk)


def _cap_per_walk(df: pd.DataFrame, max_photos_per_walk: int) -> pd.DataFrame:
    if df.empty or max_photos_per_walk <= 0:
        return df
    frames: list[pd.DataFrame] = []
    for _, grp in df.groupby("gpx_path", sort=False):
        g = grp.sort_values("taken_at")
        if len(g) > max_photos_per_walk:
            # even sample keeping ends
            idx = [
                int(round(i * (len(g) - 1) / (max_photos_per_walk - 1)))
                for i in range(max_photos_per_walk)
            ]
            g = g.iloc[sorted(set(idx))]
        frames.append(g)
    return pd.concat(frames, ignore_index=True) if frames else df.iloc[0:0]


def export_thumbs(
    matched: pd.DataFrame,
    *,
    library: Path | str | None = None,
    thumb_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Copy derivative JPEGs into output/photo_thumbs/{gpx_slug}/{uuid}.jpg."""
    if matched is None or matched.empty:
        return matched
    lib = Path(library or DEFAULT_PHOTOS_LIBRARY).expanduser()
    out_root = Path(thumb_dir or DEFAULT_THUMB_DIR)
    out_root.mkdir(parents=True, exist_ok=True)

    thumb_paths: list[str | None] = []
    full_paths: list[str | None] = []
    copied = 0
    for row in matched.itertuples(index=False):
        uuid = str(row.photo_id)
        directory = str(row.directory) if pd.notna(getattr(row, "directory", None)) else ""
        gpx = str(row.gpx_path).strip("/").replace("/", "_")
        dest_dir = out_root / gpx
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid}.jpg"
        dest_full = dest_dir / f"{uuid}_full.jpg"

        # thumb
        if dest.is_file():
            thumb_paths.append(str(dest.relative_to(repo_root())))
        else:
            src = find_derivative_jpeg(lib, directory, uuid, prefer="thumb")
            if src is None:
                thumb_paths.append(None)
            else:
                try:
                    shutil.copy2(src, dest)
                    copied += 1
                    thumb_paths.append(str(dest.relative_to(repo_root())))
                except OSError:
                    thumb_paths.append(None)

        # larger full for lightbox/click
        if dest_full.is_file():
            full_paths.append(str(dest_full.relative_to(repo_root())))
        else:
            src_f = find_derivative_jpeg(lib, directory, uuid, prefer="full")
            if src_f is None:
                # fall back to thumb path
                full_paths.append(thumb_paths[-1])
            else:
                try:
                    shutil.copy2(src_f, dest_full)
                    copied += 1
                    full_paths.append(str(dest_full.relative_to(repo_root())))
                except OSError:
                    full_paths.append(thumb_paths[-1])

    out = matched.copy()
    out["thumb_path"] = thumb_paths
    out["full_path"] = full_paths
    out.attrs["thumbs_copied"] = copied
    return out




def ensure_web_thumb(
    source: Path | str,
    *,
    dest_dir: Path | str | None = None,
    photo_id: str | None = None,
    max_edge: int = 280,
    jpeg_quality: int = 65,
) -> Path | None:
    """Create/return a small web JPEG for maps (cached on disk).

    Source may be a Photos derivative or ``output/photo_thumbs/...`` copy.
    Uses macOS ``sips`` when available (no Pillow required); otherwise copies
    only if the source is already under ~80 KiB.

    Cache layout: ``output/photo_web_thumbs/{photo_id}.jpg``
    """
    import subprocess

    src = Path(source).expanduser()
    if not src.is_file():
        return None
    root = repo_root()
    out_root = Path(dest_dir or DEFAULT_WEB_THUMB_DIR)
    out_root.mkdir(parents=True, exist_ok=True)
    pid = photo_id or src.stem.replace("_full", "")
    dest = out_root / f"{pid}.jpg"

    # Fresh enough if exists and not older than source and small enough
    if dest.is_file():
        try:
            if dest.stat().st_mtime >= src.stat().st_mtime and dest.stat().st_size > 0:
                return dest
        except OSError:
            pass

    # Prefer sips (always on macOS developer machines)
    sips = shutil.which("sips")
    if sips:
        try:
            # -Z max edge; formatOptions is 0-100
            subprocess.run(
                [
                    sips,
                    "-Z",
                    str(int(max_edge)),
                    "-s",
                    "format",
                    "jpeg",
                    "-s",
                    "formatOptions",
                    str(int(jpeg_quality)),
                    str(src),
                    "--out",
                    str(dest),
                ],
                check=True,
                capture_output=True,
            )
            if dest.is_file() and dest.stat().st_size > 0:
                return dest
        except (subprocess.CalledProcessError, OSError):
            pass

    # Optional Pillow
    try:
        from PIL import Image  # type: ignore

        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((int(max_edge), int(max_edge)))
            im.save(dest, format="JPEG", quality=int(jpeg_quality), optimize=True)
        if dest.is_file():
            return dest
    except Exception:
        pass

    # Last resort: only reuse tiny sources
    if src.stat().st_size <= 80_000:
        try:
            shutil.copy2(src, dest)
            return dest
        except OSError:
            return None
    return None


def prepare_photos_for_map(
    photos: pd.DataFrame,
    *,
    max_edge: int = 280,
    jpeg_quality: int = 65,
    prefer_full_as_source: bool = False,
) -> pd.DataFrame:
    """Attach ``web_thumb_path`` (repo-relative) for map/filmstrip use.

    Builds a per-photo cache under ``output/photo_web_thumbs/``. Idempotent.
    Full-size files stay on disk for optional on-demand ``file://`` links;
    they are **not** inlined into HTML.
    """
    if photos is None or photos.empty:
        return photos
    root = repo_root()
    out = photos.copy()
    web_paths: list[str | None] = []
    for row in out.itertuples(index=False):
        pid = str(getattr(row, "photo_id", "") or "")
        candidates: list[Path] = []
        thumb = getattr(row, "thumb_path", None)
        full = getattr(row, "full_path", None)
        order = (full, thumb) if prefer_full_as_source else (thumb, full)
        for cand in order:
            if cand is None or str(cand) in ("None", "nan", ""):
                continue
            tp = Path(str(cand))
            if not tp.is_file():
                tp = root / str(cand)
            if tp.is_file():
                candidates.append(tp)
        web = None
        for src in candidates:
            web = ensure_web_thumb(
                src,
                photo_id=pid or src.stem,
                max_edge=max_edge,
                jpeg_quality=jpeg_quality,
            )
            if web is not None:
                break
        if web is None:
            web_paths.append(None)
        else:
            try:
                web_paths.append(str(web.resolve().relative_to(root.resolve())))
            except ValueError:
                web_paths.append(str(web))
    out["web_thumb_path"] = web_paths
    return out



def materialise_walk_photos(
    *,
    health_db: Path | str | None = None,
    photos_library: Path | str | None = None,
    gpx_paths: Sequence[str] | None = None,
    pad_minutes: float = 5.0,
    max_dist_m: float = 120.0,
    limit_walks: int | None = None,
    max_photos_per_walk: int = 40,
    export_thumbnails: bool = True,
) -> PhotoMatchStats:
    """Match photos, optional thumbs, write ``gps.walk_photos`` in the health DB."""
    health = Path(health_db or DEFAULT_DB_PATH).expanduser().resolve()
    lib = Path(photos_library or DEFAULT_PHOTOS_LIBRARY).expanduser()
    psql = default_photos_sqlite(lib)

    matched = match_photos_to_walks(
        health_db=health,
        photos_sqlite=psql,
        gpx_paths=gpx_paths,
        pad_minutes=pad_minutes,
        max_dist_m=max_dist_m,
        limit_walks=limit_walks,
        max_photos_per_walk=max_photos_per_walk,
    )
    thumbs_copied = 0
    if export_thumbnails and not matched.empty:
        matched = export_thumbs(matched, library=lib)
        thumbs_copied = int(matched.attrs.get("thumbs_copied", 0))
    elif not matched.empty and "thumb_path" not in matched.columns:
        matched = matched.copy()
        matched["thumb_path"] = None

    walks_n = matched["gpx_path"].nunique() if not matched.empty else 0

    con = duckdb.connect(str(health), read_only=False)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gps")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS gps.walk_photos (
              photo_id VARCHAR,
              gpx_path VARCHAR,
              taken_at TIMESTAMPTZ,
              photo_lat DOUBLE,
              photo_lon DOUBLE,
              snap_lat DOUBLE,
              snap_lon DOUBLE,
              distance_m DOUBLE,
              match_quality VARCHAR,
              directory VARCHAR,
              filename VARCHAR,
              thumb_path VARCHAR,
              full_path VARCHAR,
              ingested_at TIMESTAMPTZ,
              PRIMARY KEY (photo_id, gpx_path)
            )
            """
        )
        con.execute(
            "CREATE OR REPLACE VIEW walk_photos AS SELECT * FROM gps.walk_photos"
        )

        if matched.empty:
            return PhotoMatchStats(0, 0, 0, lib)

        # replace rows for these gpx_paths
        paths = matched["gpx_path"].dropna().unique().tolist()
        con.executemany(
            "DELETE FROM gps.walk_photos WHERE gpx_path = ?",
            [(p,) for p in paths],
        )

        rows = []
        for r in matched.itertuples(index=False):
            rows.append(
                (
                    str(r.photo_id),
                    str(r.gpx_path),
                    r.taken_at,
                    float(r.photo_lat) if pd.notna(r.photo_lat) else None,
                    float(r.photo_lon) if pd.notna(r.photo_lon) else None,
                    float(r.snap_lat) if pd.notna(r.snap_lat) else None,
                    float(r.snap_lon) if pd.notna(r.snap_lon) else None,
                    float(r.distance_m) if pd.notna(getattr(r, "distance_m", None)) else None,
                    str(r.match_quality),
                    str(r.directory) if pd.notna(r.directory) else None,
                    str(r.filename) if pd.notna(r.filename) else None,
                    str(r.thumb_path) if pd.notna(getattr(r, "thumb_path", None)) else None,
                    str(r.full_path) if pd.notna(getattr(r, "full_path", None)) else None,
                )
            )
        con.executemany(
            """
            INSERT INTO gps.walk_photos (
              photo_id, gpx_path, taken_at, photo_lat, photo_lon,
              snap_lat, snap_lon, distance_m, match_quality,
              directory, filename, thumb_path, full_path, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            """,
            rows,
        )
        written = len(rows)
    finally:
        con.close()

    return PhotoMatchStats(
        walks_considered=walks_n,
        rows_written=written,
        thumbs_copied=thumbs_copied,
        photos_library=lib,
    )
