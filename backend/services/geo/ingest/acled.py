"""ACLED armed-conflict / protest events → AcledEvent list.

Expert-coded, precise geolocation, weekly cadence. Fetches the trailing 30 days,
sorted by date then fatalities.

**Auth is OAuth2, not an API key.** ACLED retired the ``key``+``email`` query
parameters and the ``api.acleddata.com`` host; there is no key anywhere in a
myACLED account (2026-09-20 audit). The current API takes a bearer token from
``https://acleddata.com/oauth/token`` via the *password* grant with the account's
email and password and ``client_id=acled`` (access token 24 h, refresh token 14 d).
So ``FINVIEW_ACLED_EMAIL`` + ``FINVIEW_ACLED_PASSWORD`` are the credentials, and the
token is cached process-locally like OpenSky's — with ``--min-instances=0`` that
means roughly one login per cold start, which ACLED's documented lifetimes allow.

Ordering: a 30-day global window holds tens of thousands of events and we ask for 500,
so *which* 500 the server picks decides whether this source sees last week or last
month. ACLED's API User Guide states the endpoint returns rows "in date order DESC
(starting with the latest)", which is the order we want — and no page of ACLED's
documentation (getting-started, elements-of-the-api, acled-endpoint) documents any
`order`/`sort`/`order_by` parameter to ask for it explicitly. The endpoint's convention
is that a query parameter *is* a filter on the column of that name, so sending a guessed
ordering parameter risks filtering on a column that does not exist and killing the source
outright. We therefore rely on the documented default and make the truncation loud
instead: a full page is logged at WARNING so an operator can see the window was cut.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from backend.config import settings

from .base import TTLCache, fetch_json
from .types import AcledEvent

logger = logging.getLogger(__name__)

_ACLED_URL = "https://acleddata.com/api/acled/read"
_TOKEN_URL = "https://acleddata.com/oauth/token"
_CLIENT_ID = "acled"
_TOKEN_MARGIN = 300  # refresh this many seconds before the access token expires
_DEFAULT_TOKEN_TTL = 24 * 3600
_CACHE_TTL = 30 * 60
_LIMIT = 500
_WINDOW_DAYS = 30
_cache = TTLCache()
# (access_token, monotonic deadline, refresh_token). Process-local.
_token: tuple[str, float, str | None] | None = None

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


async def _grant(data: dict) -> tuple[str, float, str | None] | None:
    body = await fetch_json(_TOKEN_URL, method="POST", data={**data, "client_id": _CLIENT_ID})
    if not isinstance(body, dict):
        return None
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        logger.warning("ACLED token response carried no access_token (keys=%s)", sorted(body))
        return None
    try:
        ttl = float(body.get("expires_in") or _DEFAULT_TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = _DEFAULT_TOKEN_TTL
    refresh = body.get("refresh_token")
    return token, time.monotonic() + max(ttl - _TOKEN_MARGIN, 60), (
        refresh if isinstance(refresh, str) else None
    )


async def _access_token() -> str | None:
    """Bearer token via the password grant, refreshed with the refresh grant when
    it expires; a failed refresh falls back to the password grant once.

    Returns None when no grant yields a usable token — the caller then degrades
    to the stale cache. A token failure must never raise into the cycle.
    """
    global _token
    if _token is not None and time.monotonic() < _token[1]:
        return _token[0]
    fresh = None
    if _token is not None and _token[2]:
        fresh = await _grant({"grant_type": "refresh_token", "refresh_token": _token[2]})
    if fresh is None:
        fresh = await _grant({
            "grant_type": "password",
            "username": settings.acled_email,
            "password": settings.acled_password,
        })
    if fresh is None:
        logger.warning("ACLED token exchange failed — source degrades to its stale cache")
        _token = None
        return None
    _token = fresh
    return fresh[0]


async def fetch_acled() -> list[AcledEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    if not (settings.acled_email and settings.acled_password):
        logger.info("ACLED_EMAIL/ACLED_PASSWORD not set — skipping ACLED source")
        return _cache.stale or []
    token = await _access_token()
    if not token:
        return _cache.stale or []

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=_WINDOW_DAYS)).date().isoformat()
    today = now.date().isoformat()
    params = {
        "event_date": start,
        "event_date_where": ">",
        "limit": str(_LIMIT),
        "fields": _FIELDS,
        "_format": "json",
    }

    data = await fetch_json(
        _ACLED_URL, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20.0
    )
    if data is None:
        return _cache.stale or []
    if not data.get("success") or not isinstance(data.get("data"), list):
        logger.warning("ACLED unexpected response format: %s", data.get("status"))
        return _cache.stale or []

    rows = data["data"]
    if len(rows) >= _LIMIT:
        dates = [str(r.get("event_date") or "") for r in rows if r.get("event_date")]
        logger.warning(
            "ACLED returned a full page (%d rows = limit) for %s..%s — the window is "
            "truncated; oldest kept event_date=%s, newest=%s. Everything older than the "
            "oldest kept date is invisible to the sentinel this cycle.",
            len(rows), start, today,
            min(dates) if dates else "?", max(dates) if dates else "?",
        )

    events: list[AcledEvent] = []
    for row in rows:
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
