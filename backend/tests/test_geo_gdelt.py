"""GDELT: the source that ingested every cycle and emitted nothing, ever.

Two independent defects, both silent:

1. ``ingest/gdelt.py`` stamped ``num_mentions=5, num_sources=3`` on every article
   because the Doc API's ``artlist`` mode returns no counts — and the sentinel's
   floors asked for 8–15 mentions and 3–5 sources. ``5 < 8`` on every row, so
   ``analyze_gdelt_events`` returned an empty list for its entire life. Prod: 0
   GDELT-sourced signals out of 1700, with 25 of the rules depending on the source.
2. ``_classify_gdelt`` matched raw substrings, so ``"BAN"`` claimed *Lebanon*,
   *Albania*, *Bangladesh* and *central bank* for ``sanctions`` and ``"STRIKE"``
   claimed every *airstrike* for ``protest``.

Nothing failed loudly: the fetch worked, the rules were well-formed, and the two
halves disagreed only about numbers that one of them invented. So the assertions
live across the seam — realistic articles in at the ``fetch_gdelt`` boundary,
GeoEvents out of the sentinel — plus the wall-clock property that made the old
ingest cost ~44s of every cycle.
"""

import asyncio
import json
import time

import pytest

from backend.services.geo import sentinel
from backend.services.geo.ingest import gdelt
from backend.services.geo.ingest.types import GdeltEvent

# Ten articles in the exact shape the Doc API returns them (artlist mode): no
# mention counts, no source counts, no per-article Goldstein — only a headline,
# a source country and a URL.
_ARTICLES: list[dict] = [
    {"title": "EU imposes new sanctions on Russia over Baltic cable incident",
     "sourcecountry": "Germany", "url": "https://ex.test/a1", "seendate": "20260920T101500Z"},
    {"title": "Washington widens export restrictions on advanced chipmaking tools",
     "sourcecountry": "United States", "url": "https://ex.test/a2", "seendate": "20260920T094500Z"},
    {"title": "Truckers strike paralyses Buenos Aires for a third day",
     "sourcecountry": "Argentina", "url": "https://ex.test/a3", "seendate": "20260920T090000Z"},
    {"title": "Riot police clear protesters from the port of Lagos",
     "sourcecountry": "Nigeria", "url": "https://ex.test/a4", "seendate": "20260920T083000Z"},
    {"title": "US airstrike on Houthi positions near Hodeidah",
     "sourcecountry": "United States", "url": "https://ex.test/a5", "seendate": "20260920T081000Z"},
    {"title": "Navy deploys second carrier group to the eastern Mediterranean",
     "sourcecountry": "Israel", "url": "https://ex.test/a6", "seendate": "20260920T075500Z"},
    {"title": "Lebanon ceasefire talks resume in Beirut",
     "sourcecountry": "Lebanon", "url": "https://ex.test/a7", "seendate": "20260920T072000Z"},
    {"title": "Bangladesh garment exports rebound after the monsoon",
     "sourcecountry": "Bangladesh", "url": "https://ex.test/a8", "seendate": "20260920T070000Z"},
    {"title": "Missile tests reported off the North Korean coast",
     "sourcecountry": "South Korea", "url": "https://ex.test/a9", "seendate": "20260920T064000Z"},
    {"title": "Farmers block the A1 motorway over the new tariff schedule",
     "sourcecountry": "France", "url": "https://ex.test/a10", "seendate": "20260920T061000Z"},
]


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    """The module cache is process-global; a leftover value would fake a pass."""
    monkeypatch.setattr(gdelt._cache, "_value", None)
    monkeypatch.setattr(gdelt._cache, "_ts", 0.0)
    yield
    monkeypatch.setattr(gdelt._cache, "_value", None)


def _stub_fetch(monkeypatch, *, latency: float = 0.0):
    """Replace the HTTP call; record the params each query was issued with."""
    calls: list[dict] = []
    body = json.dumps({"articles": _ARTICLES})

    async def fake_fetch_text(url, *, params=None, **kw):
        calls.append({"url": url, "params": params or {}, **kw})
        if latency:
            await asyncio.sleep(latency)
        return body

    monkeypatch.setattr(gdelt, "fetch_text", fake_fetch_text)
    return calls


def _event(title: str, goldstein: float, *, actor1: str = "United States") -> GdeltEvent:
    return GdeltEvent(
        id="gdelt-test", title=title, event_code="", goldstein_scale=goldstein,
        avg_tone=goldstein * 1.2, latitude=38.9, longitude=-77.0,
        actor1=actor1, actor2="", date_added="20260920T120000Z", source_url="",
    )


# ── The seam: articles in, GeoEvents out ─────────────────────────────


def test_realistic_articles_produce_events(monkeypatch):
    """THE regression. Returned [] for every input before the floors came out."""
    _stub_fetch(monkeypatch)
    raw = asyncio.run(gdelt.fetch_gdelt())
    assert raw, "fetch_gdelt dropped every article"

    events = sentinel.analyze_gdelt_events(raw)
    assert events, "analyze_gdelt_events emitted nothing — the source is dead again"

    types = {e.type for e in events}
    assert {"sanctions", "mass_protest", "military_escalation"} <= types, (
        f"expected all three categories, got {sorted(types)}"
    )
    assert all(e.source == "gdelt" for e in events)
    assert any("sanctions on Russia" in e.title for e in events)


def test_ingest_invents_no_counts():
    """The fabricated mention/source constants must not come back."""
    sample = GdeltEvent("i", "t", "", -6.0, -7.2, 0.0, 0.0, "", "", "", "")
    assert not hasattr(sample, "num_mentions")
    assert not hasattr(sample, "num_sources")
    for category, spec in sentinel._GDELT_FILTERS.items():
        assert len(spec) == 3, f"mention/source floors are back on {category}: {spec}"


# ── Classifier: word boundaries, not substrings ──────────────────────


def test_lebanon_is_not_sanctions():
    """`"BAN" in "LEBANON"` — the substring match that ate the feed."""
    assert sentinel._classify_gdelt(_event("Lebanon ceasefire talks resume", -4.0)) != "sanctions"


def test_bangladesh_and_central_bank_are_not_sanctions():
    assert sentinel._classify_gdelt(
        _event("Bangladesh garment exports rebound", -3.0)) != "sanctions"
    assert sentinel._classify_gdelt(
        _event("Central bank holds rates steady", -3.0)) != "sanctions"


def test_airstrike_is_not_protest():
    """`"STRIKE" in "AIRSTRIKE"` — an air raid filed as a labour action."""
    category = sentinel._classify_gdelt(_event("US airstrike on Houthi positions", -6.0))
    assert category != "protest"
    assert category == "armed_conflict"


def test_sanctions_headline_is_sanctions():
    assert sentinel._classify_gdelt(
        _event("EU imposes new sanctions on Russia", -4.0)) == "sanctions"


def test_strike_headline_is_protest():
    assert sentinel._classify_gdelt(
        _event("Truckers strike paralyses Buenos Aires", -3.0)) == "protest"


# ── Fetch: three queries, concurrent ─────────────────────────────────


def test_queries_do_not_run_serially(monkeypatch):
    """Old code: 6s sleep between queries = ~44s of a 59s ingest, every cycle."""
    _stub_fetch(monkeypatch, latency=0.2)
    monkeypatch.setattr(gdelt, "_STAGGER_DELAY", 0.0)  # the stagger is not the point here
    started = time.monotonic()
    asyncio.run(gdelt.fetch_gdelt())
    elapsed = time.monotonic() - started
    assert elapsed < 2.0, f"fetch_gdelt took {elapsed:.1f}s — the queries are serial again"


def test_queries_ask_for_the_newest_of_a_short_window(monkeypatch):
    """An unsorted 24h digest re-read every 30 min is a digest, not a change feed."""
    calls = _stub_fetch(monkeypatch)
    asyncio.run(gdelt.fetch_gdelt())
    assert len(calls) == len(gdelt._QUERIES)
    for call in calls:
        assert call["params"]["sort"] == "DateDesc"
        assert call["params"]["timespan"] != "24h"
        assert 0 < call["timeout"] <= 15.0


def test_rate_limited_response_degrades_to_stale(monkeypatch):
    """A 429 answers HTML, not JSON: keep the last good payload, never raise."""
    _stub_fetch(monkeypatch)
    first = asyncio.run(gdelt.fetch_gdelt())
    assert first

    async def rate_limited(url, *, params=None, **kw):
        return "<html>rate limited</html>"

    monkeypatch.setattr(gdelt, "fetch_text", rate_limited)
    monkeypatch.setattr(gdelt._cache, "_ts", 0.0)  # expire the TTL, keep the value
    assert asyncio.run(gdelt.fetch_gdelt()) == first


# ── Review findings 2026-09-20: goldstein is a per-query constant ─────

from backend.services.geo.sentinel import _classify_gdelt, analyze_gdelt_events  # noqa: E402


def test_every_query_prior_can_produce_an_event():
    """The floors gate on the query's constant, so each query must be able to
    yield its own category. armed_conflict shipped with a -7 floor against a
    -6 constant: unreachable, in the branch meant to unblock GDELT."""
    from backend.services.geo.ingest.gdelt import _QUERIES

    for query, prior in _QUERIES:
        word = query.split("(")[1].split()[0]
        events = analyze_gdelt_events([_event(f"Breaking: {word} in the capital", prior)])
        assert events, f"query {query!r} at prior {prior} produces nothing"


def test_conflict_query_without_a_keyword_is_still_armed_conflict():
    events = analyze_gdelt_events([_event("Ukraine war: day 900 update", -6.0)])
    assert events and events[0].type == "armed_conflict"


def test_protest_query_never_yields_armed_conflict():
    """A coup headline mentioning shelling comes from the -3 query; the
    armed_conflict floor (-6) says that query may not supply it."""
    assert analyze_gdelt_events([_event("Coup leaders shelling the palace", -3.0)]) == []


def test_sanctions_on_the_military_are_sanctions():
    assert _classify_gdelt(_event("US sanctions Russian military exporters", -4.0)) == "sanctions"


def test_airstrike_is_armed_conflict_not_protest_or_escalation():
    assert _classify_gdelt(_event("Airstrikes hit Sanaa overnight", -6.0)) == "armed_conflict"


def test_task_force_and_deployment_are_not_military_escalation():
    assert _classify_gdelt(_event("Trade task force deploys new tariff plan", -3.0)) != "military_escalation"
    assert _classify_gdelt(_event("Police forces disperse protesters", -3.0)) == "protest"


def test_query_constants_never_produce_red_severity():
    events = analyze_gdelt_events([_event("Airstrikes hit Sanaa overnight", -6.0)])
    assert events[0].severity == "orange"


def test_many_articles_about_one_story_are_one_event():
    """One GeoEvent per article with a colliding id let the compound tally count
    article volume as simultaneous events."""
    articles = [_event(f"Airstrikes hit Sanaa, report {i}", -6.0) for i in range(10)]
    events = analyze_gdelt_events(articles)
    assert [e.type for e in events] == ["armed_conflict", "geopolitical_escalation"]
    # The cluster is the one place article volume legitimately counts — and it
    # is still not "red": that severity would read as evidence in the rules.
    assert all(e.severity == "orange" for e in events)


def test_one_failing_query_does_not_lose_the_others(monkeypatch):
    from backend.services.geo.ingest import gdelt as g

    body = json.dumps({"articles": _ARTICLES})

    async def flaky(url, *, params=None, **kw):
        if params["query"] == g._QUERIES[1][0]:
            raise RuntimeError("boom")
        return body

    monkeypatch.setattr(g, "fetch_text", flaky)
    monkeypatch.setattr(g, "_STAGGER_DELAY", 0.0)
    monkeypatch.setattr(g._cache, "_value", None)
    assert asyncio.run(g.fetch_gdelt())


def test_rate_limit_page_is_logged_not_silent(monkeypatch, caplog):
    from backend.services.geo.ingest import gdelt as g

    async def rate_limited(url, *, params=None, **kw):
        return "Your request has been rate limited. Please try again later."

    monkeypatch.setattr(g, "fetch_text", rate_limited)
    monkeypatch.setattr(g, "_STAGGER_DELAY", 0.0)
    monkeypatch.setattr(g._cache, "_value", None)
    assert asyncio.run(g.fetch_gdelt()) == []
    assert "rate limited" in caplog.text

