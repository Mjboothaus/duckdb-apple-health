"""Local DuckDB health store and optional map / Photos / journey helpers.

Companion to the duckdb-apple-health C extension (not required to LOAD the
extension). Install extras as needed::

    uv add 'health-data-store[maps]'
    uv sync --extra maps --extra notebooks
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .store import (
    DEFAULT_DB_PATH,
    ExtensionLoadInfo,
    HealthDataStore,
    connect_with_apple_health,
    find_extension,
    load_apple_health,
    repo_root,
)

__version__ = "0.1.1"

__all__ = [
    "DEFAULT_DB_PATH",
    "ExtensionLoadInfo",
    "HealthDataStore",
    "ReverseGeocoder",
    "build_route_map",
    "connect_with_apple_health",
    "create_journey",
    "downsample_points",
    "filmstrip_html",
    "find_extension",
    "format_nominatim_address",
    "import_journey_manifest",
    "load_apple_health",
    "materialise_walk_photos",
    "match_photos_to_walks",
    "repo_root",
]

if TYPE_CHECKING:
    from .journeys import create_journey as create_journey
    from .journeys import import_manifest as import_journey_manifest
    from .maps import build_route_map, downsample_points, filmstrip_html
    from .photos import materialise_walk_photos, match_photos_to_walks
    from .places import ReverseGeocoder, format_nominatim_address


def __getattr__(name: str) -> Any:
    if name in {"build_route_map", "downsample_points", "filmstrip_html"}:
        from . import maps as _maps

        return getattr(_maps, name)
    if name in {"materialise_walk_photos", "match_photos_to_walks"}:
        from . import photos as _photos

        return getattr(_photos, name)
    if name in {"ReverseGeocoder", "format_nominatim_address"}:
        from . import places as _places

        return getattr(_places, name)
    if name == "create_journey":
        from .journeys import create_journey as _cj

        return _cj
    if name == "import_journey_manifest":
        from .journeys import import_manifest as _im

        return _im
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
