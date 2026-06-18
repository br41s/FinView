"""EONET + GDACS natural events → NaturalEvent list."""

import asyncio
import logging

from .base import TTLCache, fetch_text
from .types import NaturalEvent

logger = logging.getLogger(__name__)

_EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open"
_GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"
_CACHE_TTL = 15 * 60
_cache = TTLCache()

# Categories already covered by dedicated layers (FIRMS / USGS).
_EONET_SKIP = {"Wildfires"}
_GDACS_SKIP = {"EQ"}

_EONET_CATEGORY = {
    "Volcanoes": "volcano",
    "Sea and Lake Ice": "iceberg",
    "Severe Storms": "storm",
    "Floods": "flood",
}
_GDACS_CATEGORY = {
    "TC": "cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
    "TS": "storm",
}
_GDACS_SEVERITY = {"Red": "red", "Orange": "orange", "Green": "green"}


def _parse_eonet(text: str) -> list[NaturalEvent]:
    import json

    out: list[NaturalEvent] = []
    try:
        d = json.loads(text)
    except ValueError:
        return out
    for e in d.get("events", []) or []:
        cats = e.get("categories") or [{}]
        cat_title = cats[0].get("title", "")
        if cat_title in _EONET_SKIP:
            continue
        geo = (e.get("geometry") or [{}])[0]
        coords = geo.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        out.append(
            NaturalEvent(
                id=f"eonet-{e.get('id')}",
                title=e.get("title") or "",
                category=_EONET_CATEGORY.get(cat_title, "other"),
                latitude=float(lat),
                longitude=float(lon),
                date=geo.get("date") or "",
                source="EONET",
                severity=None,
                url=e.get("link") or "",
            )
        )
    return out


def _parse_gdacs(text: str) -> list[NaturalEvent]:
    import json

    out: list[NaturalEvent] = []
    try:
        d = json.loads(text)
    except ValueError:
        return out
    for f in d.get("features", []) or []:
        p = f.get("properties") or {}
        if p.get("eventtype") in _GDACS_SKIP:
            continue
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        lon = lat = None
        if geom.get("type") == "Point" and isinstance(coords, list):
            lon, lat = coords[0], coords[1]
        elif isinstance(coords, list) and coords and isinstance(coords[0], list):
            ring = coords[0][0] if isinstance(coords[0][0], list) else coords[0]
            lon, lat = ring[0], ring[1]
        else:
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue

        category = _GDACS_CATEGORY.get(p.get("eventtype"), "other")
        if category == "wildfire":  # FIRMS is more granular
            continue
        out.append(
            NaturalEvent(
                id=f"gdacs-{p.get('eventid') or f.get('id')}",
                title=p.get("name") or p.get("eventname") or "",
                category=category,
                latitude=float(lat),
                longitude=float(lon),
                date=p.get("fromdate") or "",
                source="GDACS",
                severity=_GDACS_SEVERITY.get(p.get("alertlevel")),
                url=p.get("url") or "",
            )
        )
    return out


async def fetch_events() -> list[NaturalEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    eonet_text, gdacs_text = await asyncio.gather(
        fetch_text(_EONET_URL),
        fetch_text(_GDACS_URL),
    )

    events: list[NaturalEvent] = []
    if eonet_text:
        events.extend(_parse_eonet(eonet_text))
    if gdacs_text:
        events.extend(_parse_gdacs(gdacs_text))

    if not events and _cache.stale is not None:
        return _cache.stale

    _cache.set(events)
    return events
