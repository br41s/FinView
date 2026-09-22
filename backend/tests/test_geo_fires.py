"""FIRMS as a rolling 24 hours, not today's calendar file.

``world/1`` is the current UTC day and is empty from midnight until the first
passes are processed: prod read 0 hotspots from 00:00 to ~03:30 UTC on three
consecutive nights with nothing to log. Two days, filtered to the last 24 h,
is what "last day" was supposed to mean.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from backend.services.geo.ingest import fires

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight"
)
NOW = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)  # just after the UTC rollover


def _row(date, time, lat="-3.10", lon="-60.02", conf="n"):
    return f"{lat},{lon},330.1,0.5,0.4,{date},{time},N,VIIRS,{conf},2.0NRT,290.2,12.3,D"


def test_parse_reads_acquisition_fields():
    csv = "\n".join([HEADER, _row("2026-09-21", "0345"), "garbage,line", _row("x", "y", lat="nan?")])
    (h,) = fires._parse_csv(csv)
    assert (h.acq_date, h.acq_time, h.confidence, h.frp) == ("2026-09-21", "0345", "n", 12.3)


def test_acquired_at_is_utc_and_zero_pads_the_time():
    (h,) = fires._parse_csv("\n".join([HEADER, _row("2026-09-21", "345")]))
    assert fires.acquired_at(h) == datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)


def test_the_window_keeps_yesterday_evening_and_drops_yesterday_morning():
    csv = "\n".join([
        HEADER,
        _row("2026-09-21", "0030"),  # 24.5 h ago — out
        _row("2026-09-21", "0100"),  # exactly 24 h — in
        _row("2026-09-21", "2350"),  # last night — in
        _row("2026-09-22", "0015"),  # today — in
    ])
    kept = fires.last_24h(fires._parse_csv(csv), NOW)
    assert [(h.acq_date, h.acq_time) for h in kept] == [
        ("2026-09-21", "0100"), ("2026-09-21", "2350"), ("2026-09-22", "0015"),
    ]


def test_an_unreadable_acquisition_time_is_kept_not_dropped(caplog):
    csv = "\n".join([HEADER, _row("21/09/2026", "noon"), _row("2026-09-19", "1200")])
    kept = fires.last_24h(fires._parse_csv(csv), NOW)
    assert [h.acq_date for h in kept] == ["21/09/2026"]
    assert "unreadable acquisition time" in caplog.text


def test_fetch_asks_for_two_days_and_filters(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(fires, "_cache", fires.TTLCache())
    monkeypatch.setattr(settings, "firms_map_key", "k")
    urls: list[str] = []
    # fetch_fires reads the wall clock, so the rows sit an hour either side of
    # the window: a wrong _WINDOW (30 h, 2 d) or a wrong clock fails this test.
    now = datetime.now(timezone.utc)
    inside, outside = now - timedelta(hours=23), now - timedelta(hours=25)

    async def fake(url, **kw):
        urls.append(url)
        return "\n".join([
            HEADER,
            _row(inside.strftime("%Y-%m-%d"), inside.strftime("%H%M")),
            _row(outside.strftime("%Y-%m-%d"), outside.strftime("%H%M")),
        ])

    monkeypatch.setattr(fires, "fetch_text", fake)
    got = asyncio.run(fires.fetch_fires())
    assert urls == ["https://firms.modaps.eosdis.nasa.gov/api/area/csv/k/VIIRS_SNPP_NRT/world/2"]
    assert [(h.acq_date, h.acq_time) for h in got] == [
        (inside.strftime("%Y-%m-%d"), inside.strftime("%H%M"))
    ]


def test_fetch_degrades_to_the_stale_payload(monkeypatch):
    from backend.config import settings

    cache = fires.TTLCache()
    stale = fires._parse_csv("\n".join([HEADER, _row("2026-09-21", "2350")]))
    cache.set(stale)
    monkeypatch.setattr(fires, "_cache", cache)
    monkeypatch.setattr(fires, "_CACHE_TTL", 0)
    monkeypatch.setattr(settings, "firms_map_key", "k")

    async def down(url, **kw):
        return None

    monkeypatch.setattr(fires, "fetch_text", down)
    assert asyncio.run(fires.fetch_fires()) == stale
