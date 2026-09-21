"""OFAC recent actions → sanctions events, matched by country or by box.

The fixture entries are verbatim from the 2026-09-17 action (Iran, Cuba,
Belarus removals) plus a Russia entry in the same canonical format. The ugly
paths are covered on purpose: the source is a web page with no contract, and
every failure must cost the cycle nothing.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from backend.services.geo import sentinel
from backend.services.geo.ingest import ofac
from backend.services.geo.ingest.types import OfacAction, OfacEntry
from backend.services.geo.rules import match_rules

IRAN_INDIVIDUAL = (
    "HEIDARI, Seyed Adel (Arabic: سید عادل حیدری), KH Shari'ati KH Va'zi P40 Vahda 3, "
    "Tehran, Iran; DOB 22 Nov 1974; POB Shahrekord, Iran; nationality Iran; Additional "
    "Sanctions Information - Subject to Secondary Sanctions; Gender Male; National ID No. "
    "4621551825 (Iran) (individual) [IRAN] [IRAN-EO13902] (Linked To: DOT ONE VALUE "
    "CREATION GROUP)."
)
CUBA_INDIVIDUAL = (
    "CANCIO MONTEAGUDO, Joaquin Francisco, 58 #2906 Eyrpto, Playa, Havana, Cuba; DOB 16 Sep "
    "1945; nationality Cuba; Gender Male; Passport E493203 (Cuba) expires 20 May 2031 "
    "(individual) [CUBA-EO14404]."
)
IRAN_ENTITY = (
    "BITBANK (Arabic: بیتبانک) (a.k.a. BITBANK3), No. 2, 35th Street, Alvand Street, "
    "Argentina Square, Tehran, Iran; Website www.bitbank3.com; alt. Website www.bitbank.com; "
    "Additional Sanctions Information - Subject to Secondary Sanctions; Organization "
    "Established Date 2024; Organization Type: Financial and Insurance Activities [IRAN] "
    "[IRAN-EO13902]."
)
CUBA_ENTITY = (
    'CENTRO DE INVESTIGACION Y DESARROLLO DE ARMAMENTO DE INFANTERIA (a.k.a. "CIDAI"), '
    "Circunvalacion Norte, Km 8 ½, Camaguey, Cuba; Organization Established Date 11 Apr 2010; "
    "Organization Type: Research and experimental development on natural sciences and "
    "engineering; alt. Organization Type: Defense activities; Target Type State-Owned "
    "Enterprise; Entity Code 14124 (Cuba) [CUBA-EO14404]."
)
RUSSIA_ENTITY = (
    "VTB BANK PUBLIC JOINT STOCK COMPANY (a.k.a. BANK VTB PAO), 43 Bolshaya Morskaya Str., "
    "St. Petersburg 190000, Russia; Registration Number 1027739609391 (Russia) "
    "[RUSSIA-EO14024] [IRAN-EO13902]."
)
BELARUS_REMOVED = (
    "LAKOKRASKA OAO (a.k.a. LAKOKRASKA OPEN JOINT-STOCK COMPANY), 71 Ignatova Street, "
    "Grodnenskaya Region, Lida 231300, Belarus; ul. Ignatova, 71, Grodnenskaya oblast, Lida "
    "231300, Belarus [BELARUS]."
)
DUBAI_IRANIAN = (
    "ZAKER HOSSEIN, Hossein Ali, Business Bay, Dubai, United Arab Emirates; DOB 01 Jan 1980; "
    "nationality Iran; Gender Male (individual) [IRAN-EO13902]."
)


def _page(individuals=(), entities=(), removed=(), title="Iran-related Designations"):
    def ul(items):
        return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"

    body = "<script>var x = '[NOT-A-TAG]';</script><h1>Recent Actions</h1>"
    if individuals:
        body += "<p>The following individuals have been added to OFAC's SDN List:</p>"
        body += ul(individuals)
    if entities:
        body += "<p>The following entities have been added to OFAC's SDN List:</p>"
        body += ul(entities)
    if removed:
        body += "<p>The following deletions have been made to OFAC's SDN List:</p>"
        body += ul(removed)
    body += "<p>The following changes have been made to OFAC's SDN List:</p>"
    body += ul(["SOME ENTITY, Somewhere, Iran [IRAN]."])  # modification: parsed by nobody
    return f"<html><head><title> {title} | Office of Foreign Assets Control </title></head><body>{body}</body></html>"


def test_parses_the_canonical_entry_format():
    action = ofac.parse_action_page(
        _page([IRAN_INDIVIDUAL, CUBA_INDIVIDUAL], [IRAN_ENTITY, CUBA_ENTITY], [BELARUS_REMOVED]),
        "20260917", "u",
    )
    assert action.title == "Iran-related Designations | Office of Foreign Assets Control"
    assert [(e.name, e.kind, e.country, e.action) for e in action.entries] == [
        ("HEIDARI", "individual", "iran", "added"),
        ("CANCIO MONTEAGUDO", "individual", "cuba", "added"),
        ("BITBANK", "entity", "iran", "added"),
        ("CENTRO DE INVESTIGACION Y DESARROLLO DE ARMAMENTO DE INFANTERIA", "entity", "cuba", "added"),
        ("LAKOKRASKA OAO", "entity", "belarus", "removed"),
    ]
    assert action.entries[0].programs == ("IRAN", "IRAN-EO13902")
    assert action.entries[4].programs == ("BELARUS",)


def test_nationality_beats_the_address_country():
    entry = ofac.parse_entry(DUBAI_IRANIAN, "added")
    assert entry.country == "iran"
    assert entry.kind == "individual"


def test_a_line_without_a_program_tag_is_not_an_entry():
    assert ofac.parse_entry("Some prose about the SDN List, Iran.", "added") is None
    action = ofac.parse_action_page(_page(["Just prose, Iran; no tags here."]), "20260917", "u")
    assert action.entries == []


def test_garbage_html_yields_an_empty_action_not_an_error(monkeypatch):
    for payload in ("", "<html><body><p>Maintenance", "\x00\x01 not html", "<<<>>>"):
        action = ofac.parse_action_page(payload, "20260917", "u")
        assert action.entries == []

    def boom(self, data):  # html.parser does not raise on markup; prove the guard anyway
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(ofac._TextExtractor, "feed", boom)
    assert ofac.parse_action_page(_page([IRAN_INDIVIDUAL]), "20260917", "u").entries == []


def test_a_country_word_in_the_name_does_not_win_over_the_address():
    entry = ofac.parse_entry(
        "BANK OF CHINA (MOSCOW BRANCH) (a.k.a. BOC RUSSIA, LLC), 20/1 Prospekt Mira, Moscow "
        "129090, Russia; Registration Number 1027739026543 (Russia) [RUSSIA-EO14024].",
        "added",
    )
    assert entry.name == "BANK OF CHINA"
    assert entry.country == "russia"


def _action(date, *entries):
    return OfacAction(date=date, url=f"https://ofac.treasury.gov/recent-actions/{date}",
                      title="t", entries=list(entries))


def _entry(country, kind="entity", action="added", name="X", programs=("IRAN",)):
    return OfacEntry(name=name, kind=kind, programs=tuple(programs), country=country,
                     action=action)


def test_one_event_per_country_with_additions():
    events = sentinel.analyze_ofac_actions([_action(
        "20260917",
        _entry("iran", "individual", name="HEIDARI"), _entry("iran", name="BITBANK"),
        _entry("cuba", name="CIDAI", programs=("CUBA-EO14404",)),
        _entry("belarus", action="removed"),
        _entry(None, name="NOWHERE"),
    )])
    by_id = {e.id: e for e in events}
    assert set(by_id) == {"ofac-20260917-iran", "ofac-20260917-cuba"}
    iran = by_id["ofac-20260917-iran"]
    assert iran.type == "sanctions" and iran.source == "ofac"
    assert iran.region == "iran"
    assert iran.raw_data["added"] == 2
    assert iran.raw_data["individuals"] == 1 and iran.raw_data["entities"] == 1
    assert iran.raw_data["names"] == ["BITBANK"]  # organisations first
    assert "OFAC designations: 2 added in Iran" in iran.title
    assert iran.timestamp == int(datetime(2026, 9, 17, 12, tzinfo=timezone.utc).timestamp() * 1000)
    # Havana happens to sit in the gulf_of_mexico box; no sanctions rule lives there,
    # so the Cuba event is tracked by nothing and starts no thesis.
    assert match_rules(by_id["ofac-20260917-cuba"]) == []


def test_iran_lands_in_the_box_and_matches_the_existing_rule():
    (event,) = sentinel.analyze_ofac_actions([_action("20260917", _entry("iran"))])
    assert "gdelt-sanctions-iran" in [r.id for r in match_rules(event)]


def test_russia_matches_through_the_country_atom_with_no_box():
    (event,) = sentinel.analyze_ofac_actions([_action("20260914", _entry("russia", name="VTB"))])
    assert event.region is None
    ids = [r.id for r in match_rules(event)]
    assert ids == ["ofac-sanctions-russia"]


def test_the_country_atom_does_not_fire_on_a_sanctions_event_without_a_country():
    news = sentinel.GeoEvent(
        id="gdelt-sanctions-x", type="sanctions", title="t", latitude=55.75, longitude=37.62,
        source="gdelt", timestamp=0, raw_data={},
    )
    assert not [r for r in match_rules(news) if r.id.startswith("ofac-")]


def test_a_package_is_red_and_a_single_designation_is_not():
    single = sentinel.analyze_ofac_actions([_action("20260914", _entry("russia"))])[0]
    package = sentinel.analyze_ofac_actions([_action(
        "20260915", *[_entry("russia", name=f"E{i}") for i in range(sentinel._OFAC_RED_ADDITIONS)]
    )])[0]
    assert single.severity == "orange"
    assert package.severity == "red"


def test_unparseable_date_skips_the_action():
    assert sentinel.analyze_ofac_actions([_action("not-a-date", _entry("iran"))]) == []


def test_listing_keeps_the_window_newest_first_and_capped():
    today = datetime(2026, 9, 21, tzinfo=timezone.utc)
    html = "".join(
        f'<a href="/recent-actions/{d}">x</a>'
        for d in ("20260921", "20260920", "20260920", "20260919", "20260918", "20260910")
    ) + '<a href="https://ofac.treasury.gov/recent-actions/20260919">abs</a>'
    assert ofac.parse_listing(html, today) == ["20260921", "20260920", "20260919", "20260918"]
    old = (today - timedelta(days=ofac._WINDOW_DAYS + 1)).strftime("%Y%m%d")
    assert ofac.parse_listing(f'<a href="/recent-actions/{old}">', today) == []
    assert ofac.parse_listing("", today) == []


def test_fetch_degrades_when_the_listing_is_down(monkeypatch):
    monkeypatch.setattr(ofac, "_cache", ofac.TTLCache())

    async def down(url, **kw):
        return None

    monkeypatch.setattr(ofac, "fetch_text", down)
    assert asyncio.run(ofac.fetch_ofac()) == []


def test_fetch_returns_the_stale_payload_when_the_listing_fails_later(monkeypatch):
    cache = ofac.TTLCache()
    cache.set([_action("20260917", _entry("iran"))])
    monkeypatch.setattr(ofac, "_cache", cache)
    monkeypatch.setattr(ofac, "_CACHE_TTL", 0)

    async def down(url, **kw):
        return None

    monkeypatch.setattr(ofac, "fetch_text", down)
    assert [a.date for a in asyncio.run(ofac.fetch_ofac())] == ["20260917"]


def test_fetch_skips_a_missing_detail_page_and_reads_the_rest(monkeypatch):
    monkeypatch.setattr(ofac, "_cache", ofac.TTLCache())
    monkeypatch.setattr(ofac, "_WINDOW_DAYS", 10_000)
    pages = {
        ofac._LISTING_URL: '<a href="/recent-actions/20260917">a</a><a href="/recent-actions/20260916">b</a>',
        ofac._ACTION_URL.format(date="20260917"): _page([IRAN_INDIVIDUAL]),
        ofac._ACTION_URL.format(date="20260916"): None,
    }

    async def fake(url, **kw):
        return pages[url]

    monkeypatch.setattr(ofac, "fetch_text", fake)
    actions = asyncio.run(ofac.fetch_ofac())
    assert [(a.date, len(a.entries)) for a in actions] == [("20260917", 1)]
    assert actions[0].entries[0].country == "iran"


def test_fetch_keeps_the_stale_payload_when_every_action_page_is_down(monkeypatch):
    """The listing answering while the pages 5xx is an outage, not a quiet week."""
    cache = ofac.TTLCache()
    cache.set([_action("20260917", _entry("iran"))])
    monkeypatch.setattr(ofac, "_cache", cache)
    monkeypatch.setattr(ofac, "_CACHE_TTL", 0)
    monkeypatch.setattr(ofac, "_WINDOW_DAYS", 10_000)

    async def fake(url, **kw):
        return '<a href="/recent-actions/20260918">a</a>' if url == ofac._LISTING_URL else None

    monkeypatch.setattr(ofac, "fetch_text", fake)
    assert [a.date for a in asyncio.run(ofac.fetch_ofac())] == ["20260917"]


def test_a_listing_with_no_recent_actions_is_a_quiet_week_not_an_outage(monkeypatch):
    cache = ofac.TTLCache()
    cache.set([_action("20260901", _entry("iran"))])
    monkeypatch.setattr(ofac, "_cache", cache)
    monkeypatch.setattr(ofac, "_CACHE_TTL", 0)

    async def fake(url, **kw):
        return "<html>no links in the window</html>"

    monkeypatch.setattr(ofac, "fetch_text", fake)
    assert asyncio.run(ofac.fetch_ofac()) == []
