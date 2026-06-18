"""USGS seismic feed → SeismicEvent list."""

import logging

from .base import TTLCache, fetch_json
from .types import SeismicEvent

logger = logging.getLogger(__name__)

_USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
_CACHE_TTL = 5 * 60  # 5 minutes
_cache = TTLCache()


def _parse(geojson: dict) -> list[SeismicEvent]:
    out: list[SeismicEvent] = []
    for f in geojson.get("features", []) or []:
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None, 0]
        lon, lat = coords[0], coords[1]
        if lon is None or lat is None or props.get("mag") is None:
            continue
        out.append(
            SeismicEvent(
                id=str(f.get("id", "")),
                magnitude=float(props["mag"]),
                place=props.get("place") or "",
                time=int(props.get("time") or 0),
                latitude=float(lat),
                longitude=float(lon),
                depth=float(coords[2]) if len(coords) > 2 and coords[2] is not None else 0.0,
                url=props.get("url") or "",
            )
        )
    return out


async def fetch_seismic() -> list[SeismicEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    geojson = await fetch_json(_USGS_FEED, timeout=10.0)
    if geojson is None:
        return _cache.stale or []

    data = _parse(geojson)
    _cache.set(data)
    return data
