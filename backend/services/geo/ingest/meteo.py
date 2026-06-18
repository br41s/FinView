"""Windy GFS point-forecast grid → MeteoPoint list."""

import asyncio
import logging
import math

from backend.config import settings

from .base import TTLCache, fetch_json
from .types import MeteoPoint

logger = logging.getLogger(__name__)

_WINDY_URL = "https://api.windy.com/api/point-forecast/v2"
_CACHE_TTL = 30 * 60
_CONCURRENCY = 6
_cache = TTLCache()

# Global 6×6 grid (36 points).
_GRID_LATS = [-50, -20, 0, 20, 45, 65]
_GRID_LONS = [-150, -90, -30, 30, 90, 150]


async def _fetch_point(lat: int, lon: int, key: str) -> MeteoPoint | None:
    body = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",
        "parameters": ["wind", "temp", "precip", "windGust", "pressure"],
        "levels": ["surface"],
        "key": key,
    }
    d = await fetch_json(_WINDY_URL, method="POST", json_body=body)
    if not d:
        return None
    ts = d.get("ts")
    if not ts:
        return None

    # Pick timestamp closest to now (epoch ms).
    import time

    now_ms = time.time() * 1000
    idx = min(range(len(ts)), key=lambda i: abs(ts[i] - now_ms))

    def at(param: str, default: float = 0.0) -> float:
        arr = d.get(param)
        return float(arr[idx]) if arr and idx < len(arr) else default

    u = at("wind_u-surface")
    v = at("wind_v-surface")
    temp_k = at("temp-surface", 273.15)
    precip = at("past3hprecip-surface")
    gust_ms = at("gust-surface")
    pressure_pa = at("pressure-surface", 101325.0)

    wind_speed = math.sqrt(u * u + v * v) * 3.6  # m/s → km/h
    wind_dir = (math.degrees(math.atan2(-u, -v)) + 360) % 360

    return MeteoPoint(
        latitude=lat,
        longitude=lon,
        temperature=round((temp_k - 273.15) * 10) / 10,
        wind_speed=round(wind_speed * 10) / 10,
        wind_direction=round(wind_dir),
        wind_gust=round(gust_ms * 3.6 * 10) / 10,
        precipitation=round(precip * 100) / 100,
        pressure=round(pressure_pa / 100),
    )


async def fetch_meteo() -> list[MeteoPoint]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    key = settings.windy_api_key
    if not key:
        logger.info("WINDY_API_KEY not set — skipping meteo source")
        return _cache.stale or []

    coords = [(lat, lon) for lat in _GRID_LATS for lon in _GRID_LONS]
    results: list[MeteoPoint] = []
    for i in range(0, len(coords), _CONCURRENCY):
        batch = coords[i : i + _CONCURRENCY]
        settled = await asyncio.gather(
            *(_fetch_point(lat, lon, key) for lat, lon in batch),
            return_exceptions=True,
        )
        for r in settled:
            if isinstance(r, MeteoPoint):
                results.append(r)

    if not results and _cache.stale is not None:
        return _cache.stale

    _cache.set(results)
    return results
