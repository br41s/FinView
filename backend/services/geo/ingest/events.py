"""EONET + GDACS natural events → NaturalEvent list."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from .base import TTLCache, fetch_text
from .types import NaturalEvent

logger = logging.getLogger(__name__)

_EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open"
# `geteventlist/MAP` used to answer with every current event. It now answers
# 400 "Eventtype is required." and takes one type per request, so this half of
# the source was silently empty: EONET shares its counter and carries no alert
# level, which left the pipeline without a single natural-event severity.
# SEARCH takes the types and a date window in one request and returns one
# feature per event, with the alert level and the countries affected.
_GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
_GDACS_TYPES = "TC;FL;VO;DR"  # EQ is USGS's and WF is FIRMS's (see the skips below)
# Without `alertlevel` SEARCH returns orange and red only; the rules gate on a
# region box as well, so green events are still wanted.
_GDACS_LEVELS = "green;orange;red"
# The window is on activity, not on the start date: a drought that began in
# December is returned while it lasts. Three days bridges a missed cycle.
_GDACS_WINDOW = timedelta(days=3)
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
# TS is GDACS for tsunami, not storm, and is deliberately absent: no rule reads
# a tsunami. Unmapped it is "other", which the sentinel drops.
_GDACS_CATEGORY = {
    "TC": "cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
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


def _gdacs_params(today: date) -> dict[str, str]:
    return {
        "eventlist": _GDACS_TYPES,
        "alertlevel": _GDACS_LEVELS,
        "fromDate": (today - _GDACS_WINDOW).isoformat(),
        "toDate": (today + timedelta(days=1)).isoformat(),
    }


def _parse_gdacs(text: str) -> list[NaturalEvent]:
    import json

    out: list[NaturalEvent] = []
    try:
        d = json.loads(text)
    except ValueError:
        return out
    # A 200 is not a payload: the error body is an object with no features,
    # and `null` or a bare list would raise on `.get`.
    if not isinstance(d, dict):
        return out
    for f in d.get("features", []) or []:
        p = f.get("properties") or {}
        if p.get("eventtype") in _GDACS_SKIP:
            continue
        # SEARCH also returns events that ended inside the window. Only an
        # explicit "false" drops one: a missing or renamed flag must not empty
        # the feed.
        if str(p.get("iscurrent")).lower() == "false":
            continue
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        lon = lat = None
        if geom.get("type") == "Point" and isinstance(coords, list):
            lon, lat = coords[0], coords[1]
        elif isinstance(coords, list) and coords and isinstance(coords[0], list):
            try:
                ring = coords[0][0] if isinstance(coords[0][0], list) else coords[0]
                lon, lat = ring[0], ring[1]
            except IndexError:
                continue  # an empty ring: this feature, not the whole feed
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
                url=_gdacs_url(p.get("url")),
                countries=tuple(
                    str(c["iso3"]).upper()
                    for c in p.get("affectedcountries") or []
                    if isinstance(c, dict) and c.get("iso3")
                ),
            )
        )
    return out


def _gdacs_url(value: object) -> str:
    """The event's report page. SEARCH nests the links in an object; MAP sent a string."""
    if isinstance(value, dict):
        value = value.get("report") or value.get("details")
    return value if isinstance(value, str) else ""


async def fetch_events() -> list[NaturalEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    eonet_text, gdacs_text = await asyncio.gather(
        fetch_text(_EONET_URL),
        fetch_text(_GDACS_URL, params=_gdacs_params(datetime.now(timezone.utc).date())),
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
