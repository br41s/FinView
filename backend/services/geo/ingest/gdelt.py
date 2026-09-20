"""GDELT 2.0 event export files → GdeltEvent list.

Free, no key, and **not** the DOC 2.0 API this replaced. Measured 2026-09-20 from
Google Cloud: ``api.gdeltproject.org/api/v2/doc/doc`` answers HTTP 429 to a
*single* request (prod: available in 17% of cycles, ~1700 rate-limit lines a
week), while ``data.gdeltproject.org/gdeltv2/`` — a static file host — answers
200 in under 0.5 s. The API also returned no Goldstein score, no mention counts
and no coordinates, so the old module fabricated a per-query Goldstein constant
and a capital centroid; the export carries all three per event.

Shape: ``lastupdate.txt`` is three lines (``<size> <md5> <url>`` for export /
mentions / gkg) naming the newest 15-minute batch. Each export zip holds one
headerless 61-column TSV, ~600–4000 rows. We read the newest batch plus the 3
before it (filenames step back 15 min): the cron runs every 30 min, dedup is by
GlobalEventID, so the overlap is free and a skipped cycle is bridged. A missing
older file is normal, not an error.
"""

import asyncio
import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta

from .base import TTLCache, fetch_bytes, fetch_text
from .types import GdeltEvent

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.gdeltproject.org/gdeltv2"
_LASTUPDATE_URL = f"{_BASE_URL}/lastupdate.txt"
_CACHE_TTL = 15 * 60
_REQUEST_TIMEOUT = 20.0
# Real batches are 30–200 KB zipped, single-digit MB unzipped. A wrong file
# behind the name (or a hostile one) must not be decompressed into a 1 GiB
# container: the download and the member are both capped.
_MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
# 4 batches × 15 min. The cron is every 30 min, so this bridges exactly one
# missed cycle without re-reading a day of history every run.
_BATCH_COUNT = 4
_BATCH_MINUTES = 15
# data.gdeltproject.org is a static host with no documented rate limit, but four
# requests inside one second is the shape that got us blocked on the API.
_FETCH_PAUSE = 0.3

# Pre-filter only. QuadClass 3/4 are verbal/material conflict; the root codes are
# CAMEO's conflict half (14 protest … 20 mass violence). The real gates — mention
# floors, Goldstein bands, region matching — live in the sentinel.
_CONFLICT_QUAD = {3, 4}
_CONFLICT_ROOTS = {"14", "15", "16", "17", "18", "19", "20"}

# Column indexes in the 61-column GDELT 2.0 export record (0-based), verified
# against a real batch and the CAMEO 1.1b3 codebook.
_C_GLOBAL_ID = 0
_C_ACTOR1 = 6
_C_ACTOR2 = 16
_C_EVENT_CODE = 26
_C_ROOT_CODE = 28
_C_QUAD_CLASS = 29
_C_GOLDSTEIN = 30
_C_MENTIONS = 31
_C_SOURCES = 32
_C_ARTICLES = 33
_C_AVG_TONE = 34
_C_GEO_NAME = 52
_C_GEO_LAT = 56
_C_GEO_LON = 57
_C_DATE_ADDED = 59
_C_SOURCE_URL = 60
_EXPORT_COLUMNS = 61

# CAMEO root → human description, used to build the title the export omits.
_ROOT_DESCRIPTIONS = {
    "14": "protest",
    "15": "exhibit force posture",
    "16": "reduce relations",
    "17": "coerce",
    "18": "unconventional violence",
    "19": "conventional military force",
    "20": "mass violence",
}
# A handful of sub-codes worth naming exactly; everything else falls back to the
# root description above.
_CODE_DESCRIPTIONS = {
    "141": "demonstrate or rally",
    "143": "strike or boycott",
    "145": "violent protest, riot",
    "152": "increase military alert status",
    "154": "mobilize or increase armed forces",
    "161": "reduce or break diplomatic relations",
    "1621": "stop economic assistance",
    "1622": "stop military assistance",
    "163": "impose embargo, boycott or sanctions",
    "164": "halt negotiations",
    "172": "impose administrative sanctions",
    "173": "arrest or detain",
    "174": "expel or deport",
    "175": "use repression",
    "176": "cyber attack",
    "181": "abduct, hijack, take hostage",
    "183": "bombing",
    "186": "assassinate",
    "190": "use conventional military force",
    "191": "impose blockade, restrict movement",
    "192": "occupy territory",
    "193": "fight with small arms",
    "194": "fight with artillery and tanks",
    "195": "employ aerial weapons",
    "196": "violate ceasefire",
    "202": "mass killings",
    "203": "ethnic cleansing",
}

_cache = TTLCache()


def _parse_lastupdate(text: str) -> str | None:
    """Return the export URL from ``lastupdate.txt``, or None if it isn't one.

    Three lines of ``<size> <md5> <url>``; only the ``.export.CSV.zip`` one is
    ours. A rate-limit or error page is HTML and simply has no such line.
    """
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].endswith(".export.CSV.zip"):
            return parts[2].replace("http://", "https://", 1)
    return None


def _batch_urls(latest_url: str, count: int = _BATCH_COUNT) -> list[str]:
    """Derive the latest N export URLs by stepping the filename back 15 min.

    The timestamp is the filename, so the arithmetic is on a real datetime —
    subtracting 15 from the minute field alone breaks on every hour and day
    boundary, which is four times an hour.
    """
    name = latest_url.rsplit("/", 1)[-1]
    stamp = name.split(".", 1)[0]
    try:
        ts = datetime.strptime(stamp, "%Y%m%d%H%M%S")
    except ValueError:
        logger.warning("gdelt lastupdate URL has no parseable timestamp: %r", latest_url)
        return [latest_url]
    return [
        f"{_BASE_URL}/{(ts - timedelta(minutes=_BATCH_MINUTES * i)):%Y%m%d%H%M%S}.export.CSV.zip"
        for i in range(count)
    ]


def _title_for(actor1: str, actor2: str, event_code: str, root_code: str) -> str:
    description = _CODE_DESCRIPTIONS.get(event_code) or _ROOT_DESCRIPTIONS.get(
        root_code, "conflict event"
    )
    return f"{actor1 or '?'} → {actor2 or '?'}: {description}"


def _parse_row(row: list[str]) -> GdeltEvent | None:
    if len(row) < _EXPORT_COLUMNS or not row[_C_GLOBAL_ID].strip():
        return None
    lat_raw, lon_raw = row[_C_GEO_LAT], row[_C_GEO_LON]
    if not lat_raw or not lon_raw:
        return None
    root_code = row[_C_ROOT_CODE]
    try:
        quad_class = int(row[_C_QUAD_CLASS] or 0)
        latitude = float(lat_raw)
        longitude = float(lon_raw)
        goldstein = float(row[_C_GOLDSTEIN] or 0.0)
        mentions = int(row[_C_MENTIONS] or 0)
        sources = int(row[_C_SOURCES] or 0)
        articles = int(row[_C_ARTICLES] or 0)
        avg_tone = float(row[_C_AVG_TONE] or 0.0)
    except ValueError:
        return None
    if quad_class not in _CONFLICT_QUAD and root_code not in _CONFLICT_ROOTS:
        return None

    actor1 = row[_C_ACTOR1].strip()
    actor2 = row[_C_ACTOR2].strip()
    event_code = row[_C_EVENT_CODE].strip()
    return GdeltEvent(
        id=f"gdelt-{row[_C_GLOBAL_ID]}",
        title=_title_for(actor1, actor2, event_code, root_code),
        event_code=event_code,
        event_root_code=root_code,
        quad_class=quad_class,
        goldstein_scale=goldstein,
        num_mentions=mentions,
        num_sources=sources,
        num_articles=articles,
        avg_tone=avg_tone,
        latitude=latitude,
        longitude=longitude,
        location=row[_C_GEO_NAME].strip(),
        actor1=actor1,
        actor2=actor2,
        date_added=row[_C_DATE_ADDED].strip(),
        source_url=row[_C_SOURCE_URL].strip(),
    )


def _parse_export_zip(payload: bytes) -> list[GdeltEvent]:
    """Unzip in memory and parse the single TSV inside. Never raises."""
    events: list[GdeltEvent] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos:
                return []
            if infos[0].file_size > _MAX_MEMBER_BYTES:
                logger.warning(
                    "gdelt export member is %d bytes, over the %d cap — skipped",
                    infos[0].file_size, _MAX_MEMBER_BYTES,
                )
                return []
            raw = archive.read(infos[0])
        text = raw.decode("utf-8", errors="replace")
        # No header row, and the fields are raw text that contains unbalanced
        # quotes (headlines do) — QUOTE_NONE keeps csv from swallowing the rest
        # of the file. csv.Error (an oversized field: a truncated or wrong file)
        # is inside the try on purpose: it used to escape fetch_gdelt and cost
        # the cycle its stale cache.
        reader = csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            event = _parse_row(row)
            if event is not None:
                events.append(event)
    except (zipfile.BadZipFile, OSError, csv.Error, ValueError) as exc:
        logger.warning(
            "gdelt export payload unreadable (%d bytes): %s", len(payload), exc
        )
        return []
    return events


async def fetch_gdelt() -> list[GdeltEvent]:
    cached = _cache.get(_CACHE_TTL)
    if cached is not None:
        return cached

    text = await fetch_text(_LASTUPDATE_URL, timeout=_REQUEST_TIMEOUT)
    latest = _parse_lastupdate(text) if text else None
    if not latest:
        logger.warning("gdelt lastupdate.txt unusable: %r", (text or "")[:120])
        return _cache.stale or []

    events: list[GdeltEvent] = []
    seen: set[str] = set()
    for index, url in enumerate(_batch_urls(latest)):
        if index:
            await asyncio.sleep(_FETCH_PAUSE)
        # Only the newest batch is guaranteed to exist; the older filenames are
        # derived, and GDELT does skip batches.
        payload = await fetch_bytes(
            url, timeout=_REQUEST_TIMEOUT, missing_ok=index > 0, max_bytes=_MAX_DOWNLOAD_BYTES,
        )
        if not payload:
            continue
        for event in _parse_export_zip(payload):
            if event.id in seen:
                continue
            seen.add(event.id)
            events.append(event)

    if not events:
        logger.warning("gdelt export batches yielded no conflict events")
        if _cache.stale is not None:
            return _cache.stale

    _cache.set(events)
    return events
