"""NASA FIRMS wildfire hotspots → FireHotspot list."""

import logging

from backend.config import settings

from .base import TTLCache, fetch_text
from .types import FireHotspot

logger = logging.getLogger(__name__)

_FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_CACHE_TTL = 10 * 60
_cache = TTLCache()


def _parse_csv(csv: str) -> list[FireHotspot]:
    # Header: latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,
    #         satellite,instrument,confidence,version,bright_ti5,frp,daynight
    out: list[FireHotspot] = []
    lines = csv.strip().split("\n")
    if len(lines) < 2:
        return out
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) < 14:
            continue
        try:
            lat = float(cols[0])
            lon = float(cols[1])
        except ValueError:
            continue
        try:
            frp = float(cols[12])
        except ValueError:
            frp = 0.0
        conf = cols[9] if cols[9] in ("h", "n") else "l"
        out.append(
            FireHotspot(
                latitude=lat,
                longitude=lon,
                brightness=_safe_float(cols[2]),
                frp=frp,
                confidence=conf,
                acq_date=cols[5],
                acq_time=cols[6],
                daynight=cols[13],
                satellite=cols[7],
            )
        )
    return out


def _safe_float(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return 0.0


async def fetch_fires() -> list[FireHotspot]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    api_key = settings.firms_map_key
    if not api_key:
        logger.info("FIRMS_MAP_KEY not set — skipping wildfire source")
        return _cache.stale or []

    url = f"{_FIRMS_URL}/{api_key}/VIIRS_SNPP_NRT/world/1"
    text = await fetch_text(url)
    if text is None:
        return _cache.stale or []

    data = _parse_csv(text)
    _cache.set(data)
    return data
