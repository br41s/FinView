"""NASA FIRMS wildfire hotspots → FireHotspot list, as a rolling 24 hours.

FIRMS's ``DAY_RANGE`` counts UTC calendar days, not hours: ``world/1`` is
*today's* file, which is empty at 00:00 UTC and fills as passes are processed.
Measured in prod (2026-09-20/22): the source read 0 hotspots from midnight to
about 03:30 UTC every night, with no error to log — the fire clusters simply
vanished from Ideas for three hours a night. The fix asks for two days and
keeps the hotspots acquired in the last 24 hours, which is what "last day"
meant all along. A row whose acquisition time cannot be read is kept: the
window is a precision on top of a valid hotspot, not a gate, and a format
change must not silently empty the feed.
"""

import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings

from .base import TTLCache, fetch_text
from .types import FireHotspot

logger = logging.getLogger(__name__)

_FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_DAY_RANGE = 2  # two calendar days: enough to always contain the last 24 hours
_WINDOW = timedelta(hours=24)
# Two world-wide day files are ~10 MB; the ingest default of 15 s was sized
# for one.
_REQUEST_TIMEOUT = 30.0
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


def acquired_at(hotspot: FireHotspot) -> datetime | None:
    """UTC acquisition time from FIRMS's ``acq_date`` (YYYY-MM-DD) and
    ``acq_time`` (HHMM, zero-padded to four digits by FIRMS, not always by us)."""
    try:
        return datetime.strptime(
            f"{hotspot.acq_date} {hotspot.acq_time.zfill(4)}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def last_24h(hotspots: list[FireHotspot], now: datetime | None = None) -> list[FireHotspot]:
    floor = (now or datetime.now(timezone.utc)) - _WINDOW
    kept: list[FireHotspot] = []
    unreadable = 0
    for h in hotspots:
        at = acquired_at(h)
        if at is None:
            unreadable += 1
            kept.append(h)
        elif at >= floor:
            kept.append(h)
    if unreadable:
        logger.warning("firms: %d hotspots with an unreadable acquisition time kept", unreadable)
    return kept


async def fetch_fires() -> list[FireHotspot]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    api_key = settings.firms_map_key
    if not api_key:
        logger.info("FIRMS_MAP_KEY not set — skipping wildfire source")
        return _cache.stale or []

    url = f"{_FIRMS_URL}/{api_key}/VIIRS_SNPP_NRT/world/{_DAY_RANGE}"
    text = await fetch_text(url, timeout=_REQUEST_TIMEOUT)
    if text is None:
        return _cache.stale or []

    data = last_24h(_parse_csv(text))
    _cache.set(data)
    return data
