"""ACLED armed-conflict / protest events → AcledEvent list.

Expert-coded, precise geolocation, weekly cadence. Requires ACLED_EMAIL + ACLED_KEY
(free academic access). Fetches the trailing 30 days, sorted by date then fatalities.
"""

import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings

from .base import TTLCache, fetch_json
from .types import AcledEvent

logger = logging.getLogger(__name__)

_ACLED_URL = "https://api.acleddata.com/acled/read"
_CACHE_TTL = 30 * 60
_cache = TTLCache()

_FIELDS = (
    "event_id_cnty|event_date|event_type|sub_event_type|actor1|assoc_actor_1|"
    "actor2|assoc_actor_2|country|admin1|location|latitude|longitude|fatalities|"
    "notes|source|source_scale|tags"
)


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _to_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


async def fetch_acled() -> list[AcledEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    email = settings.acled_email
    key = settings.acled_key
    if not email or not key:
        logger.info("ACLED_EMAIL/ACLED_KEY not set — skipping ACLED source")
        return _cache.stale or []

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=30)).date().isoformat()
    today = now.date().isoformat()
    params = {
        "key": key,
        "email": email,
        "event_date": f"{start}|{today}",
        "event_date_where": "BETWEEN",
        "limit": "500",
        "fields": _FIELDS,
    }

    data = await fetch_json(_ACLED_URL, params=params, timeout=20.0)
    if data is None:
        return _cache.stale or []
    if not data.get("success") or not isinstance(data.get("data"), list):
        logger.warning("ACLED unexpected response format: %s", data.get("status"))
        return _cache.stale or []

    events: list[AcledEvent] = []
    for row in data["data"]:
        lat = _to_float(row.get("latitude"))
        lon = _to_float(row.get("longitude"))
        ev_id = str(row.get("event_id_cnty") or "")
        if lat == 0 or lon == 0 or not ev_id:
            continue
        events.append(
            AcledEvent(
                id=ev_id,
                event_date=str(row.get("event_date") or ""),
                event_type=str(row.get("event_type") or ""),
                sub_event_type=str(row.get("sub_event_type") or ""),
                actor1=str(row.get("actor1") or ""),
                actor2=str(row.get("actor2") or ""),
                country=str(row.get("country") or ""),
                admin1=str(row.get("admin1") or ""),
                location=str(row.get("location") or ""),
                latitude=lat,
                longitude=lon,
                fatalities=_to_int(row.get("fatalities")),
                notes=str(row.get("notes") or "")[:500],
                source=str(row.get("source") or ""),
                source_scale=str(row.get("source_scale") or ""),
                tags=str(row.get("tags") or ""),
            )
        )

    events.sort(key=lambda e: (e.event_date, e.fatalities), reverse=True)

    _cache.set(events)
    return events
