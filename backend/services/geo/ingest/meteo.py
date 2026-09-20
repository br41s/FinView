"""Windy GFS point forecasts at the regions the weather rules watch → MeteoPoint list.

Same philosophy as ``flights.py``'s ``_SCAN_BOXES``: sample only where a rule can
actually fire. This source used to hit an arbitrary global 6×6 grid (36 points);
27 of those fell outside every ``GEO_REGIONS`` box, and ``analyze_weather_extremes``
drops any point with no region match — so 75% of the API budget bought nothing,
while four weather rules (texas / mediterranean / us_northeast / china_industrial)
had no sample point at all and were structurally unable to ever fire.

The sample set is **derived from the rules** rather than hand-listed, so it cannot
silently drift when someone adds a weather rule — see ``_rule_regions()``.
"""

import asyncio
import logging
import math
import re

from backend.config import settings

from ..rules import FAST_RULES, GEO_REGIONS
from .base import TTLCache, fetch_json
from .types import MeteoPoint

logger = logging.getLogger(__name__)

_WINDY_URL = "https://api.windy.com/api/point-forecast/v2"
_CACHE_TTL = 30 * 60
_CONCURRENCY = 6
_cache = TTLCache()

# Event types analyze_weather_extremes can emit — i.e. the rule categories this
# source feeds. A rule on any other category is served by a different ingest.
_WEATHER_CATEGORIES = frozenset(
    {"extreme_heat", "extreme_cold", "severe_storm", "heavy_precipitation", "deep_cyclone"}
)
_RE_REGION = re.compile(r"region=(\w+)")

# Representative points for regions whose centroid would defeat the rule.
#
# The sentinel thresholds are severe (45°C / -30°C / 50mm per 3h), so "the point
# is inside the box" is NOT sufficient — the number has to be physically
# reachable there. A centroid that lands on water or in a mild sub-climate keeps
# the rule just as dead as no point at all. Only regions listed here deviate from
# the centroid; each entry documents why.
_REGION_POINTS: dict[str, tuple[tuple[float, float], ...]] = {
    # Centroid (42.5, -73.5) is the Albany area, where -30°C is a once-in-decades
    # record. Northern Maine / Québec border clears -30°C in most winters.
    "us_northeast": ((45.5, -70.5),),
    # Two rules with different geographies, so this region gets two points:
    # Finnish Lapland for the -30°C cold rule, and the North Sea storm track for
    # the 90km/h wind rule. The centroid (61, 9) — inland Norwegian highlands —
    # is mediocre for both.
    "northern_europe": ((68.0, 25.0), (58.0, 2.0)),
}


def _centroid(box: tuple[float, float, float, float]) -> tuple[float, float]:
    lat_min, lat_max, lon_min, lon_max = box
    return (lat_min + lat_max) / 2, (lon_min + lon_max) / 2


def _rule_regions() -> list[str]:
    """Regions referenced by a weather rule, in FAST_RULES order (deduped)."""
    out: list[str] = []
    for rule in FAST_RULES:
        if rule.category not in _WEATHER_CATEGORIES:
            continue
        m = _RE_REGION.search(rule.condition)
        if not m:
            continue
        region = m.group(1)
        if region in out:
            continue
        if region not in GEO_REGIONS:
            # Unreachable by construction, not just unsampled — surface it.
            logger.warning("meteo: rule %s targets unknown region %s", rule.id, region)
            continue
        out.append(region)
    return out


def _build_sample_points() -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for region in _rule_regions():
        for pt in _REGION_POINTS.get(region) or (_centroid(GEO_REGIONS[region]),):
            if pt not in points:  # regions can overlap; one call per coordinate
                points.append(pt)
    return points


# Built once at import: ~10 points vs the old 36. With _CACHE_TTL at 30 min and
# the geo cron every 10 min the source really fetches ~48×/day, so this is ~480
# calls/day (was ~1728, ~1300 of them wasted).
SAMPLE_POINTS: list[tuple[float, float]] = _build_sample_points()


async def _fetch_point(lat: float, lon: float, key: str) -> MeteoPoint | None:
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

    coords = SAMPLE_POINTS
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
