"""Reverse-geocode route start/end points into short place labels.

Uses OpenStreetMap Nominatim (free, no API key) with a local JSON cache under
``output/``. Respects Nominatim's ~1 request/second guidance.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import repo_root

DEFAULT_CACHE_PATH = repo_root() / "output" / "geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "duckdb-apple-health/0.1 (local research; contact: github.com/mjboothaus/duckdb-apple-health)"
# Round coordinates so nearby points share a cache entry (~11 m at equator).
COORD_DECIMALS = 4
MIN_REQUEST_INTERVAL_S = 1.05


@dataclass(frozen=True)
class PlaceLabel:
    lat: float
    lon: float
    label: str
    raw: dict[str, Any] | None = None


def _coord_key(lat: float, lon: float) -> str:
    return f"{round(float(lat), COORD_DECIMALS):.{COORD_DECIMALS}f},{round(float(lon), COORD_DECIMALS):.{COORD_DECIMALS}f}"


def load_cache(path: Path | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_CACHE_PATH)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict[str, Any], path: Path | None = None) -> Path:
    p = Path(path or DEFAULT_CACHE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def format_nominatim_address(payload: dict[str, Any]) -> str:
    """Build a short human label from a Nominatim reverse response."""
    addr = payload.get("address") or {}
    if not isinstance(addr, dict):
        addr = {}

    # Prefer neighbourhood / suburb scale over country-level noise.
    locality_keys = (
        "neighbourhood",
        "suburb",
        "city_district",
        "quarter",
        "village",
        "hamlet",
        "town",
        "city",
        "municipality",
        "county",
    )
    road = addr.get("road") or addr.get("pedestrian") or addr.get("path") or addr.get("footway")
    locality = next((str(addr[k]) for k in locality_keys if addr.get(k)), None)
    state = addr.get("state") or addr.get("region")

    parts: list[str] = []
    if road and locality and road != locality:
        parts.append(f"{road}, {locality}")
    elif locality:
        parts.append(locality)
    elif road:
        parts.append(str(road))
    elif payload.get("display_name"):
        # Fall back to first two comma segments of display_name.
        bits = [b.strip() for b in str(payload["display_name"]).split(",") if b.strip()]
        parts.append(", ".join(bits[:2]) if bits else str(payload["display_name"]))
    else:
        parts.append("Unknown place")

    # Add state when it adds signal (e.g. NSW) and isn't already present.
    label = parts[0]
    if state and str(state) not in label:
        label = f"{label}, {state}"
    return label


class ReverseGeocoder:
    """Cached Nominatim reverse geocoder."""

    def __init__(
        self,
        *,
        cache_path: Path | None = None,
        user_agent: str = USER_AGENT,
        min_interval_s: float = MIN_REQUEST_INTERVAL_S,
        timeout_s: float = 20.0,
    ) -> None:
        self.cache_path = Path(cache_path or DEFAULT_CACHE_PATH)
        self.user_agent = user_agent
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._cache = load_cache(self.cache_path)
        self._last_request_at = 0.0

    def lookup(self, lat: float, lon: float, *, fetch: bool = True) -> PlaceLabel:
        key = _coord_key(lat, lon)
        hit = self._cache.get(key)
        if isinstance(hit, dict) and hit.get("label"):
            return PlaceLabel(lat=float(lat), lon=float(lon), label=str(hit["label"]), raw=hit.get("raw"))

        if not fetch:
            return PlaceLabel(lat=float(lat), lon=float(lon), label=f"{lat:.4f}, {lon:.4f}")

        payload = self._fetch(lat, lon)
        label = format_nominatim_address(payload) if payload else f"{lat:.4f}, {lon:.4f}"
        self._cache[key] = {
            "lat": round(float(lat), COORD_DECIMALS),
            "lon": round(float(lon), COORD_DECIMALS),
            "label": label,
            "raw": payload,
        }
        save_cache(self._cache, self.cache_path)
        return PlaceLabel(lat=float(lat), lon=float(lon), label=label, raw=payload)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

    def _fetch(self, lat: float, lon: float) -> dict[str, Any] | None:
        params = urllib.parse.urlencode(
            {
                "lat": f"{float(lat):.6f}",
                "lon": f"{float(lon):.6f}",
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 16,
            }
        )
        req = urllib.request.Request(
            f"{NOMINATIM_URL}?{params}",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
            method="GET",
        )
        self._throttle()
        self._last_request_at = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            return data if isinstance(data, dict) else None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
            return None
