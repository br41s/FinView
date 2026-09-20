"""GDELT 2.0 Doc API → GdeltEvent list.

Free, no key. The three thematic queries run concurrently, staggered by half a
second so the burst still looks polite; serializing them with a 6s spacer cost
~44s of every cycle's ingest wall and bought nothing (GDELT answered 16% of prod
cycles either way). Articles are geolocated by source-country centroid.

``artlist`` returns headlines only — no mention or source counts, no per-article
Goldstein score. Those fields are not invented here: the per-query Goldstein
constant is the query's own severity prior, and the mention/source floors that
used to gate on fabricated counts are gone from the sentinel.
"""

import asyncio
import json
import logging

from .base import TTLCache, fetch_text
from .types import GdeltEvent

logger = logging.getLogger(__name__)

_CACHE_TTL = 15 * 60
# Stagger between the three concurrent queries, not a serial spacer. 2 s, not
# 0.5: GDELT rate-limits per IP (prod logged 1700 429/5xx lines in 7 days even
# with 6 s serial spacing) and three requests inside one second is the shape
# most likely to trip it. Total added latency is 4 s, against the 44 s it was.
_STAGGER_DELAY = 2.0
_REQUEST_TIMEOUT = 12.0
# The cron runs every 30 min and dedup is by external_id, so re-reading a 24h
# digest every cycle was pure latency: 6h still covers a long 429 streak (GDELT
# answered 168/1010 prod cycles) while DateDesc keeps the 25 records the newest.
_TIMESPAN = "6h"
_cache = TTLCache()

_QUERIES = [
    ("(military OR conflict OR escalation OR airstrike OR invasion) sourcelang:english", -6.0),
    ("(sanctions OR embargo OR tariff) sourcelang:english", -4.0),
    ("(protest OR riot OR unrest OR coup) sourcelang:english", -3.0),
]

_COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "United States": (38.9, -77.0), "United Kingdom": (51.5, -0.1), "Russia": (55.8, 37.6),
    "China": (39.9, 116.4), "Iran": (35.7, 51.4), "Israel": (31.8, 35.2),
    "Ukraine": (50.4, 30.5), "Taiwan": (25.0, 121.5), "South Korea": (37.6, 127.0),
    "North Korea": (39.0, 125.8), "Japan": (35.7, 139.7), "India": (28.6, 77.2),
    "Pakistan": (33.7, 73.1), "Turkey": (39.9, 32.9), "Saudi Arabia": (24.7, 46.7),
    "Iraq": (33.3, 44.4), "Syria": (33.5, 36.3), "Lebanon": (33.9, 35.5),
    "Egypt": (30.0, 31.2), "Germany": (52.5, 13.4), "France": (48.9, 2.3),
    "Italy": (41.9, 12.5), "Poland": (52.2, 21.0), "Romania": (44.4, 26.1),
    "Spain": (40.4, -3.7), "Brazil": (-15.8, -47.9), "Mexico": (19.4, -99.1),
    "Canada": (45.4, -75.7), "Australia": (-33.9, 151.2), "South Africa": (-33.9, 18.4),
    "Nigeria": (9.1, 7.5), "Kenya": (-1.3, 36.8), "Ethiopia": (9.0, 38.7),
    "Venezuela": (10.5, -66.9), "Colombia": (4.6, -74.1), "Argentina": (-34.6, -58.4),
    "Indonesia": (-6.2, 106.8), "Malaysia": (3.1, 101.7), "Philippines": (14.6, 121.0),
    "Thailand": (13.8, 100.5), "Vietnam": (21.0, 105.9), "Myanmar": (19.8, 96.2),
    "Afghanistan": (34.5, 69.2), "Yemen": (15.4, 44.2), "Libya": (32.9, 13.2),
    "Sudan": (15.6, 32.5), "Somalia": (2.0, 45.3), "Niger": (13.5, 2.1),
    "Mali": (12.6, -8.0), "Burkina Faso": (12.4, -1.5), "Bangladesh": (23.8, 90.4),
    "Sri Lanka": (6.9, 79.9), "Georgia": (41.7, 44.8), "Moldova": (47.0, 28.8),
    "Belarus": (53.9, 27.6), "Estonia": (59.4, 24.7), "Latvia": (56.9, 24.1),
    "Lithuania": (54.7, 25.3), "Finland": (60.2, 25.0), "Sweden": (59.3, 18.1),
    "Norway": (59.9, 10.8), "Hungary": (47.5, 19.0), "Ireland": (53.3, -6.3),
    "Greece": (37.9, 23.7), "Czech Republic": (50.1, 14.4), "Austria": (48.2, 16.4),
    "Switzerland": (46.9, 7.4), "Netherlands": (52.4, 4.9), "Belgium": (50.8, 4.4),
    "Portugal": (38.7, -9.1), "Denmark": (55.7, 12.6), "New Zealand": (-41.3, 174.8),
    "Singapore": (1.4, 103.8), "Qatar": (25.3, 51.5), "United Arab Emirates": (24.5, 54.7),
    "Kuwait": (29.4, 47.9), "Bahrain": (26.2, 50.6), "Oman": (23.6, 58.5),
    "Jordan": (31.9, 35.9), "Morocco": (33.6, -7.6), "Tunisia": (36.8, 10.2),
    "Algeria": (36.8, 3.1),
}

def _hash_code(s: str) -> str:
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    # emulate JS 32-bit signed wrap then abs
    if h >= 0x80000000:
        h -= 0x100000000
    return format(abs(h), "x")


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]*>", "", s).strip()


async def _fetch_query(index: int, query: str, goldstein: float) -> list[GdeltEvent]:
    if index:
        await asyncio.sleep(_STAGGER_DELAY * index)
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": 25,
        "format": "json",
        "sort": "DateDesc",
        "timespan": _TIMESPAN,
    }
    text = await fetch_text(url, params=params, timeout=_REQUEST_TIMEOUT)
    if not text or not text.startswith("{"):
        # GDELT answers rate limits with a plain-text page, so this is the
        # branch prod actually takes — it must not be the silent one.
        logger.warning(
            "gdelt query %d returned no JSON (rate limited?): %r", index, (text or "")[:120]
        )
        return []
    try:
        data = json.loads(text)
    except ValueError:
        logger.warning("gdelt query %d returned malformed JSON: %r", index, text[:120])
        return []

    events: list[GdeltEvent] = []
    for art in data.get("articles", []) or []:
        country = art.get("sourcecountry") or ""
        coords = _COUNTRY_CENTROIDS.get(country)
        if not coords:
            continue
        title = _strip_html(str(art.get("title") or ""))
        if len(title) < 10:
            continue
        url_ = art.get("url") or ""
        events.append(
            GdeltEvent(
                id=f"gdelt-{_hash_code(url_ or title)}",
                title=title[:200],
                event_code="",
                goldstein_scale=goldstein,
                avg_tone=goldstein * 1.2,
                latitude=coords[0],
                longitude=coords[1],
                actor1=country,
                actor2="",
                date_added=art.get("seendate") or "",
                source_url=url_,
            )
        )
    return events


async def fetch_gdelt() -> list[GdeltEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    results = await asyncio.gather(
        *(_fetch_query(i, q, g) for i, (q, g) in enumerate(_QUERIES)),
        return_exceptions=True,
    )
    events: list[GdeltEvent] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("gdelt query failed: %s", result)
            continue
        events.extend(result)

    # Dedup by title prefix.
    seen: set[str] = set()
    deduped: list[GdeltEvent] = []
    for e in events:
        key = e.title[:50].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    if not deduped and _cache.stale is not None:
        return _cache.stale

    _cache.set(deduped)
    return deduped
