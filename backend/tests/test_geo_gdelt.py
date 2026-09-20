"""GDELT: the source that ingested every cycle and emitted nothing, ever.

The Doc API era is over (see ``ingest/gdelt.py``): from Google Cloud that API
answers HTTP 429 to a single request, and it carried no Goldstein score, no
mention counts and no coordinates — so the ingest invented a per-query Goldstein
constant and a capital centroid, the sentinel's mention floors had to be deleted
because nothing could meet them, and "red" severity was banned because it would
have been fabricated. Prod: 0 GDELT-sourced signals out of 1700, with 25 rules
depending on the source.

The 15-minute ``export.CSV`` batches carry all of it per event, so the floors and
the severity bands are back and these tests hold them to it. The assertions live
across the seam — a real-shaped export zip in at the ``fetch_gdelt`` boundary,
GeoEvents out of the sentinel — plus the two properties the ingest owns alone:
the batch URLs it derives, and what it does when GDELT answers with something
that is not a zip.
"""

import asyncio
import io
import zipfile

import pytest

from backend.services.geo import sentinel
from backend.services.geo.ingest import gdelt
from backend.services.geo.ingest.types import GdeltEvent

_LATEST = "20260920083000"
_LASTUPDATE = (
    "33027 1ef84b0fc90980e3518b820f139d2f56 "
    f"http://data.gdeltproject.org/gdeltv2/{_LATEST}.export.CSV.zip\n"
    "52613 823363a65e626a77c178d9a7de1aa3b4 "
    f"http://data.gdeltproject.org/gdeltv2/{_LATEST}.mentions.CSV.zip\n"
    "2644532 b41fb306fc8acd03a53867d589beecf3 "
    f"http://data.gdeltproject.org/gdeltv2/{_LATEST}.gkg.csv.zip\n"
)


def _row(
    global_id: str,
    *,
    event_code: str,
    root_code: str,
    quad: str,
    goldstein: str,
    mentions: str,
    sources: str = "1",
    lat: str,
    lon: str,
    geo_name: str,
    actor1: str = "",
    actor2: str = "",
    url: str = "https://ex.test/a",
) -> str:
    """One 61-column export record. Only the columns the parser reads are set."""
    cols = [""] * 61
    cols[0] = global_id
    cols[1] = "20260920"
    cols[6] = actor1
    cols[16] = actor2
    cols[26] = event_code
    cols[27] = event_code[:3]
    cols[28] = root_code
    cols[29] = quad
    cols[30] = goldstein
    cols[31] = mentions
    cols[32] = sources
    cols[33] = mentions
    cols[34] = "-6.5"
    cols[52] = geo_name
    cols[56] = lat
    cols[57] = lon
    cols[59] = f"{_LATEST}"
    cols[60] = url
    return "\t".join(cols)


# Twelve synthetic rows in the exact shape of a live batch: coordinates inside
# real GEO_REGIONS boxes, CAMEO codes and Goldstein values copied from the
# codebook's own table (19x = -10, 18x = -9, 15x = -7.2, 14x = -6.5, 17x = -5).
_ROWS = [
    # Gaza — 190 conventional force, well covered. suez_red_sea/middle_east_oil.
    _row("101", event_code="190", root_code="19", quad="4", goldstein="-10.0",
         mentions="40", lat="31.5", lon="34.5", geo_name="Gaza, Israel",
         actor1="ISRAEL", actor2="PALESTINIAN"),
    # A second Gaza row about the same story — must collapse into one event.
    _row("102", event_code="193", root_code="19", quad="4", goldstein="-10.0",
         mentions="12", lat="31.4", lon="34.4", geo_name="Gaza City, Israel",
         actor1="ISRAELI", actor2="HAMAS"),
    # Ukraine — 193 fight with small arms.
    _row("103", event_code="193", root_code="19", quad="4", goldstein="-10.0",
         mentions="21", sources="4", lat="50.4", lon="30.5", geo_name="Kyiv, Ukraine",
         actor1="UKRAINE", actor2="RUSSIA"),
    # Ukraine — 154 mobilize armed forces, a different category, same region.
    _row("104", event_code="154", root_code="15", quad="3", goldstein="-7.2",
         mentions="10", lat="49.9", lon="36.2", geo_name="Kharkiv, Ukraine",
         actor1="RUSSIA", actor2="FIGHTER"),
    # Ukraine — 173 arrest: diplomatic_tension, the third story of the cluster.
    _row("105", event_code="173", root_code="17", quad="4", goldstein="-5.0",
         mentions="8", lat="50.5", lon="30.6", geo_name="Kyiv, Ukraine",
         actor1="POLICE", actor2="JOURNALIST"),
    # Taiwan — 154 exhibit force posture.
    _row("106", event_code="154", root_code="15", quad="3", goldstein="-7.2",
         mentions="16", lat="24.0", lon="121.0", geo_name="Taiwan",
         actor1="CHINA", actor2="AIR FORCE"),
    # Tehran — 141 demonstrate or rally.
    _row("107", event_code="141", root_code="14", quad="3", goldstein="-6.5",
         mentions="14", lat="35.7", lon="51.4", geo_name="Tehran, Iran",
         actor1="STUDENT", actor2="GOVERNMENT"),
    # Tehran — 163 impose embargo/boycott/sanctions.
    _row("108", event_code="163", root_code="16", quad="3", goldstein="-8.0",
         mentions="9", lat="35.6", lon="51.3", geo_name="Tehran, Iran",
         actor1="UNITED STATES", actor2="IRAN"),
    # 163 between economic actors → trade dispute, not a security thesis.
    _row("109", event_code="163", root_code="16", quad="3", goldstein="-8.0",
         mentions="9", lat="31.2", lon="121.5", geo_name="Shanghai, China",
         actor1="CHINA", actor2="EXPORTER"),
    # A single-mention 190 that the floors must drop.
    _row("110", event_code="190", root_code="19", quad="4", goldstein="-10.0",
         mentions="1", lat="6.5", lon="3.4", geo_name="Lagos, Nigeria",
         actor1="POLICE", actor2="PROTESTER"),
    # No coordinates — the ingest drops it before the sentinel ever sees it.
    _row("111", event_code="190", root_code="19", quad="4", goldstein="-10.0",
         mentions="30", lat="", lon="", geo_name="", actor1="RUSSIA", actor2="NATO"),
    # QuadClass 1 cooperation, root 05 — outside the conflict pre-filter.
    _row("112", event_code="050", root_code="05", quad="1", goldstein="3.5",
         mentions="20", lat="48.9", lon="2.3", geo_name="Paris, France",
         actor1="FRANCE", actor2="GERMANY"),
]


def _zip_of(rows: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{_LATEST}.export.CSV", "\n".join(rows) + "\n")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    """The module cache is process-global; a leftover value would fake a pass."""
    monkeypatch.setattr(gdelt._cache, "_value", None)
    monkeypatch.setattr(gdelt._cache, "_ts", 0.0)
    monkeypatch.setattr(gdelt, "_FETCH_PAUSE", 0.0)
    yield
    monkeypatch.setattr(gdelt._cache, "_value", None)


def _stub(monkeypatch, *, lastupdate: str = _LASTUPDATE, payloads=None):
    """Replace both HTTP helpers; record every URL the ingest asked for."""
    fetched: list[str] = []
    default = _zip_of(_ROWS)

    async def fake_fetch_text(url, **kw):
        fetched.append(url)
        return lastupdate

    async def fake_fetch_bytes(url, **kw):
        fetched.append(url)
        if payloads is None:
            return default
        return payloads.get(url)

    monkeypatch.setattr(gdelt, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(gdelt, "fetch_bytes", fake_fetch_bytes)
    return fetched


def _event(
    title: str,
    goldstein: float,
    *,
    actor1: str = "UNITED STATES",
    event_code: str = "",
    root_code: str = "",
    mentions: int = 20,
) -> GdeltEvent:
    return GdeltEvent(
        id="gdelt-test", title=title, event_code=event_code, event_root_code=root_code,
        quad_class=4, goldstein_scale=goldstein, num_mentions=mentions, num_sources=1,
        num_articles=mentions, avg_tone=goldstein * 1.2, latitude=38.9, longitude=-77.0,
        location="Washington, DC", actor1=actor1, actor2="",
        date_added=f"{_LATEST}", source_url="",
    )


# ── Ingest: lastupdate parsing and the batch window ──────────────────


def test_lastupdate_picks_the_export_line():
    url = gdelt._parse_lastupdate(_LASTUPDATE)
    assert url == f"https://data.gdeltproject.org/gdeltv2/{_LATEST}.export.CSV.zip"
    assert "mentions" not in url and "gkg" not in url


def test_lastupdate_rejects_a_non_listing():
    """Rate limits and outages answer with HTML, which has no export line."""
    assert gdelt._parse_lastupdate("<html><body>Too Many Requests</body></html>") is None
    assert gdelt._parse_lastupdate("") is None


def test_batch_urls_step_back_fifteen_minutes():
    urls = gdelt._batch_urls(f"{gdelt._BASE_URL}/20260920083000.export.CSV.zip")
    assert [u.rsplit("/", 1)[-1].split(".", 1)[0] for u in urls] == [
        "20260920083000", "20260920081500", "20260920080000", "20260920074500",
    ]


def test_batch_urls_cross_the_hour_and_the_day():
    """Subtracting 15 from the minute field alone breaks 4× an hour."""
    hour = gdelt._batch_urls(f"{gdelt._BASE_URL}/20260920090000.export.CSV.zip")
    assert [u.rsplit("/", 1)[-1].split(".", 1)[0] for u in hour] == [
        "20260920090000", "20260920084500", "20260920083000", "20260920081500",
    ]
    day = gdelt._batch_urls(f"{gdelt._BASE_URL}/20260921001500.export.CSV.zip")
    assert [u.rsplit("/", 1)[-1].split(".", 1)[0] for u in day] == [
        "20260921001500", "20260921000000", "20260920234500", "20260920233000",
    ]


def test_fetch_reads_four_batches(monkeypatch):
    fetched = _stub(monkeypatch)
    asyncio.run(gdelt.fetch_gdelt())
    exports = [u for u in fetched if u.endswith(".export.CSV.zip")]
    assert len(exports) == gdelt._BATCH_COUNT == 4


def test_dedup_is_by_global_event_id(monkeypatch):
    """The 4 batches overlap by design; the same event must not arrive twice."""
    _stub(monkeypatch)
    events = asyncio.run(gdelt.fetch_gdelt())
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))
    assert "gdelt-101" in ids


def test_an_older_batch_that_is_not_published_is_tolerated(monkeypatch):
    """Only the newest filename is guaranteed to exist — the rest are derived."""
    latest = f"{gdelt._BASE_URL}/{_LATEST}.export.CSV.zip"
    _stub(monkeypatch, payloads={latest: _zip_of(_ROWS)})
    events = asyncio.run(gdelt.fetch_gdelt())
    assert events, "one 404 on an older batch emptied the whole cycle"


def test_pre_filter_drops_rows_without_coordinates_or_conflict(monkeypatch):
    _stub(monkeypatch)
    ids = {e.id for e in asyncio.run(gdelt.fetch_gdelt())}
    assert "gdelt-111" not in ids, "a row with no ActionGeo coordinates got through"
    assert "gdelt-112" not in ids, "a QuadClass 1 cooperation row got through"


def test_columns_are_read_off_the_right_indexes(monkeypatch):
    _stub(monkeypatch)
    gaza = next(e for e in asyncio.run(gdelt.fetch_gdelt()) if e.id == "gdelt-101")
    assert gaza.event_code == "190"
    assert gaza.event_root_code == "19"
    assert gaza.quad_class == 4
    assert gaza.goldstein_scale == -10.0
    assert gaza.num_mentions == 40
    assert gaza.num_sources == 1
    assert (gaza.latitude, gaza.longitude) == (31.5, 34.5)
    assert gaza.location == "Gaza, Israel"
    assert gaza.actor1 == "ISRAEL" and gaza.actor2 == "PALESTINIAN"
    assert gaza.date_added == _LATEST
    assert gaza.source_url == "https://ex.test/a"


def test_title_is_synthesized_from_actors_and_cameo(monkeypatch):
    """The export carries no headline — only a source URL."""
    _stub(monkeypatch)
    events = asyncio.run(gdelt.fetch_gdelt())
    assert next(e for e in events if e.id == "gdelt-101").title == (
        "ISRAEL → PALESTINIAN: use conventional military force"
    )
    assert next(e for e in events if e.id == "gdelt-104").title == (
        "RUSSIA → FIGHTER: mobilize or increase armed forces"
    )


# ── Ingest: degradation ──────────────────────────────────────────────


def test_rate_limited_lastupdate_degrades_to_stale_cache(monkeypatch):
    _stub(monkeypatch)
    first = asyncio.run(gdelt.fetch_gdelt())
    assert first

    _stub(monkeypatch, lastupdate="<html>429 Too Many Requests</html>")
    monkeypatch.setattr(gdelt._cache, "_ts", 0.0)  # expire the TTL, keep the value
    assert asyncio.run(gdelt.fetch_gdelt()) == first


def test_an_html_body_where_a_zip_belongs_does_not_raise(monkeypatch):
    latest = f"{gdelt._BASE_URL}/{_LATEST}.export.CSV.zip"
    _stub(monkeypatch, payloads={latest: b"<html>Service Unavailable</html>"})
    assert asyncio.run(gdelt.fetch_gdelt()) == []


def test_cache_is_served_before_any_request(monkeypatch):
    fetched = _stub(monkeypatch)
    asyncio.run(gdelt.fetch_gdelt())
    before = len(fetched)
    asyncio.run(gdelt.fetch_gdelt())
    assert len(fetched) == before, "the TTL cache was bypassed"


# ── Classification: CAMEO first ──────────────────────────────────────


def test_cameo_roots_map_to_categories():
    assert sentinel._classify_by_cameo("141", "14") == "protest"
    assert sentinel._classify_by_cameo("154", "15") == "military_escalation"
    assert sentinel._classify_by_cameo("163", "16") == "sanctions"
    assert sentinel._classify_by_cameo("1621", "16") == "sanctions"
    assert sentinel._classify_by_cameo("1622", "16") == "sanctions"
    assert sentinel._classify_by_cameo("161", "16") == "diplomatic_tension"
    assert sentinel._classify_by_cameo("164", "16") == "diplomatic_tension"
    assert sentinel._classify_by_cameo("181", "18") == "armed_conflict"
    assert sentinel._classify_by_cameo("193", "19") == "armed_conflict"
    assert sentinel._classify_by_cameo("202", "20") == "armed_conflict"


def test_coercion_is_not_armed_conflict():
    """173 arrest/detain is the most common conflict code in a live batch.

    Routing it to ``armed_conflict`` would fire the oil and defense theses on a
    routine arrest — the class of fabrication this rewrite exists to remove.
    """
    assert sentinel._classify_by_cameo("173", "17") == "diplomatic_tension"
    assert sentinel._classify_by_cameo("174", "17") == "diplomatic_tension"
    assert sentinel._classify_by_cameo("1723", "17") == "diplomatic_tension"
    # State force against a population is unrest; a cyber attack escalates.
    assert sentinel._classify_by_cameo("175", "17") == "protest"
    assert sentinel._classify_by_cameo("1711", "17") == "protest"
    assert sentinel._classify_by_cameo("176", "17") == "military_escalation"


def test_economic_actors_turn_sanctions_into_a_trade_dispute():
    embargo = _event("x", -8.0, actor1="CHINA", event_code="163", root_code="16")
    assert sentinel._classify_gdelt(embargo) == "sanctions"
    embargo.actor2 = "EXPORTER"
    assert sentinel._classify_gdelt(embargo) == "trade_dispute"


def test_keyword_fallback_only_runs_when_cameo_says_nothing():
    """Roots 09–13 reach the sentinel via the QuadClass 3 pre-filter."""
    threat = _event("x", -4.4, actor1="RUSSIAN ARMY", event_code="130", root_code="13")
    assert sentinel._classify_gdelt(threat) == "military_escalation"
    assert sentinel._classify_gdelt(_event("x", -2.0, actor1="FARMER",
                                           event_code="110", root_code="11")) is None


def test_keyword_fallback_matches_words_not_substrings():
    """"BAN" used to claim Lebanon, Albania, Bangladesh and *central bank*."""
    for actor in ("LEBANON", "ALBANIA", "BANGLADESH", "CENTRAL BANK"):
        assert sentinel._classify_gdelt(
            _event("x", -4.0, actor1=actor, event_code="110", root_code="11")
        ) != "sanctions"
    assert sentinel._classify_gdelt(
        _event("x", -4.0, actor1="EU BANS RUSSIAN OIL", event_code="110", root_code="11")
    ) == "sanctions"


def test_airstrike_is_not_a_protest():
    """"STRIKE" as a substring claimed every airstrike for protest."""
    assert sentinel._classify_gdelt(
        _event("x", -6.0, actor1="US AIRSTRIKE FORCE", event_code="110", root_code="11")
    ) == "armed_conflict"


# ── Sentinel: floors, severity, dedupe ───────────────────────────────


def _analyzed(monkeypatch):
    _stub(monkeypatch)
    return sentinel.analyze_gdelt_events(asyncio.run(gdelt.fetch_gdelt()))


def test_the_seam_produces_events(monkeypatch):
    """THE regression: returned [] for every input for the source's whole life."""
    events = _analyzed(monkeypatch)
    assert events, "analyze_gdelt_events emitted nothing — the source is dead again"
    assert all(e.source == "gdelt" for e in events)


def test_floors_drop_the_single_mention_row(monkeypatch):
    """Real counts, so the floors mean what they say again.

    Measured over 3 live batches: NumMentions runs 1 / median 3 / p90 10, and
    ~40% of conflict rows are one or two mentions.
    """
    events = _analyzed(monkeypatch)
    # Row 110 is the only one in nigeria_oil and it carries a single mention.
    assert not any(e.region == "nigeria_oil" for e in events)
    assert all(e.raw_data.get("numMentions", 99) >= 4 for e in events
               if e.type != "geopolitical_escalation")

    # …and it is the floor that drops it, not the pre-filter: the ingest keeps it.
    assert "gdelt-110" in {e.id for e in asyncio.run(gdelt.fetch_gdelt())}


def test_min_sources_is_one_because_a_fifteen_minute_slice_has_one(monkeypatch):
    """NumSources was 1 for ~98% of rows across 3 live batches (32/1790 had ≥2).

    The original design's 3–5 source floor would drop the entire feed.
    """
    assert all(f[4] <= 1 for f in sentinel._GDELT_FILTERS.values())


def test_severity_comes_from_the_real_goldstein(monkeypatch):
    events = {e.type: e for e in _analyzed(monkeypatch)}
    # 19x fight = -10 in CAMEO's own table.
    assert events["armed_conflict"].severity == "red"
    # 14x protest = -6.5 → orange, not red.
    assert events["mass_protest"].severity == "orange"
    # 15x exhibit force posture = -7.2 → red.
    assert events["military_escalation"].severity == "red"


def test_many_rows_about_one_story_are_one_event(monkeypatch):
    """Rows 101 and 102 are the same Gaza story, one region, one day."""
    events = _analyzed(monkeypatch)
    suez = [e for e in events if e.region == "suez_red_sea" and e.type == "armed_conflict"]
    assert len(suez) == 1
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))


def test_escalation_cluster_is_red_when_the_measured_average_earns_it(monkeypatch):
    """Ukraine: armed_conflict (-10) + military_escalation (-7.2) + tension (-5).

    Average -7.4 ≤ -7, so the cluster is red — and it is red on evidence now,
    which is what ``rules.severity_headroom`` reads.
    """
    clusters = [e for e in _analyzed(monkeypatch) if e.type == "geopolitical_escalation"]
    ukraine = next(e for e in clusters if e.region == "ukraine_black_sea")
    assert ukraine.raw_data["eventCount"] == 3
    assert ukraine.raw_data["avgGoldstein"] <= -7
    assert ukraine.severity == "red"


def test_escalation_cluster_counts_stories_not_rows():
    """A region with one story told 22 ways is not "≥3 simultaneous events".

    The Doc API capped the feed at 75 articles a cycle so the distinction did not
    bite; an hour of export batches passes ~90 rows of the floors.
    """
    rows = [
        GdeltEvent(
            id=f"gdelt-{i}", title="t", event_code="193", event_root_code="19",
            quad_class=4, goldstein_scale=-10.0, num_mentions=20, num_sources=1,
            num_articles=20, avg_tone=-8.0, latitude=50.4, longitude=30.5,
            location="Kyiv, Ukraine", actor1="UKRAINE", actor2="RUSSIA",
            date_added=_LATEST, source_url="",
        )
        for i in range(22)
    ]
    assert [e for e in sentinel.analyze_gdelt_events(rows)
            if e.type == "geopolitical_escalation"] == []


def test_raw_data_contract(monkeypatch):
    """orchestrator.py and the frontend read these keys."""
    event = next(e for e in _analyzed(monkeypatch) if e.type == "armed_conflict")
    assert set(event.raw_data) >= {
        "goldsteinScale", "actor1", "category", "numMentions", "eventCode", "sourceUrl",
    }
    assert event.raw_data["eventCode"].startswith("19")
    assert event.raw_data["sourceUrl"].startswith("https://")


def test_event_ids_are_region_and_day_keyed(monkeypatch):
    for event in _analyzed(monkeypatch):
        assert event.id.startswith("gdelt-")
        assert event.source == "gdelt"


def test_escalation_cluster_only_forms_where_geopolitics_is_the_thesis():
    """Three 19x events over Ohio are a police story, not a geopolitical cluster.
    The per-event armed_conflict events still exist (no rule covers us_midwest);
    the cluster — which matches gdelt-escalation-cluster everywhere — does not."""
    # Three categories, as a real escalation reads: a fight, a show of force, coercion.
    codes = (("190", "19", -10.0), ("154", "15", -7.2), ("172", "17", -5.0))
    def rows(lat, lon, loc):
        return [
            GdeltEvent(
                id=f"gdelt-{loc}-{i}", title="t", event_code=code, event_root_code=root,
                quad_class=4, goldstein_scale=gs, num_mentions=20, num_sources=1,
                num_articles=20, avg_tone=-8.0, latitude=lat, longitude=lon + i * 0.5,
                location=loc, actor1="POLICE", actor2="SUSPECT",
                date_added=_LATEST, source_url=f"https://ex.test/{loc}/{i}",
            )
            for i, (code, root, gs) in enumerate(codes)
        ]
    ohio = sentinel.analyze_gdelt_events(rows(40.0, -83.0, "Columbus, Ohio"))
    assert [e for e in ohio if e.type == "geopolitical_escalation"] == []
    red_sea = sentinel.analyze_gdelt_events(rows(20.0, 38.0, "Red Sea"))
    assert [e for e in red_sea if e.type == "geopolitical_escalation"]
