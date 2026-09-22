"""Federal Register → BIS Entity List additions and USTR tariff actions.

Fixture titles are the real ones from the 90 days before 2026-09-22 (the
measurement that justified the source). The API is JSON with a stable
contract, but the classification is by title, so the skip list — comment
requests, hearings, quota allocations, initiations, removals — is what these
tests pin.
"""

import asyncio
from datetime import datetime, timezone

from backend.services.geo import sentinel
from backend.services.geo.ingest import fedreg
from backend.services.geo.ingest.types import FedRegDocument
from backend.services.geo.rules import match_rules

BIS = {"slug": "industry-and-security-bureau", "name": "Industry and Security Bureau"}
USTR = {"slug": "trade-representative-office-of-united-states",
        "name": "Trade Representative, Office of United States"}
TODAY = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _doc(title, agency, date="2026-09-21", abstract="", number=None):
    return {
        "title": title, "abstract": abstract, "publication_date": date,
        "document_number": number or f"2026-{abs(hash(title)) % 100000:05d}",
        "html_url": "https://www.federalregister.gov/d/x", "agencies": [agency],
    }


def test_classification_by_title():
    assert fedreg.classify("bis", "Additions to the Entity List") == "sanctions"
    assert fedreg.classify("bis", "Additions and Revisions to the Entity List") == "sanctions"
    assert fedreg.classify("bis", "Revisions to the Entity List") is None
    assert fedreg.classify("bis", "Removal From the Entity List") is None
    assert fedreg.classify("bis", "Additions to the Unverified List") is None
    assert fedreg.classify(
        "ustr", "Notice of Conforming Amendments to Product Exclusions: China's Acts, Policies, "
        "and Practices Related to Technology Transfer, Intellectual Property, and Innovation",
    ) == "trade_dispute"
    assert fedreg.classify(
        "ustr", "Notice of Actions in Section 301 Investigations of Acts, Policies, and "
        "Practices of Certain Trading Partners",
    ) == "trade_dispute"
    assert fedreg.classify(
        "ustr", "Notice of Action: Brazil's Acts, Policies, and Practices Related to Digital "
        "Trade and Electronic Payment Services",
    ) == "trade_dispute"
    for skipped in (
        "Request for Comments on Significant Foreign Trade Barriers for the 2027 National "
        "Trade Estimate Report",
        "Request for Comments and Notice of Public Hearing Concerning China's Compliance",
        "2026 Review of Notorious Markets for Counterfeiting and Piracy: Request for Comments",
        "Fiscal Year 2027 Tariff-Rate Quota Allocations for Raw Cane Sugar",
        "Initiation of Section 301 Investigation; Hearing; and Request for Public Comments",
    ):
        assert fedreg.classify("ustr", skipped) is None, skipped
    assert fedreg.classify("fda", "Additions to the Entity List") is None


def test_countries_come_from_title_and_abstract_in_text_order():
    assert fedreg.countries_in("China's Acts, Policies, and Practices") == ("china",)
    assert fedreg.countries_in(
        "BIS adds entities located in Russia, the United Arab Emirates and China."
    ) == ("russia", "uae", "china")
    assert fedreg.countries_in("Brazil's Acts") == ("brazil",)
    assert fedreg.countries_in("Certain Trading Partners") == ()


def test_parse_payload_keeps_actions_in_the_window():
    payload = {"count": 4, "results": [
        _doc("Additions to the Entity List", BIS, "2026-09-20",
             "BIS adds 12 entities under the destinations of China and Russia."),
        _doc("Removal From the Entity List", BIS, "2026-09-20", "removes an entity in Turkey"),
        _doc("Notice of Action: Brazil's Acts, Policies, and Practices", USTR, "2026-09-21"),
        _doc("Notice of Actions in Section 301 Investigations", USTR, "2026-09-01"),  # old
        {"title": "no number or date"},
        "not a dict",
    ]}
    docs = fedreg.parse_payload(payload, TODAY)
    assert [(d.agency, d.category, d.countries) for d in docs] == [
        ("bis", "sanctions", ("china", "russia")),
        ("ustr", "trade_dispute", ("brazil",)),
    ]


def test_unusable_payloads_yield_nothing():
    for payload in (None, "html", {"results": "nope"}, {"count": 0}, [], {"results": [None]}):
        assert fedreg.parse_payload(payload, TODAY) == []


def _fd(category="trade_dispute", agency="ustr", countries=("china",), date="2026-09-21",
        number="2026-00001", title="Notice of Action"):
    return FedRegDocument(document_number=number, publication_date=date, title=title,
                         abstract="a", url="u", agency=agency, category=category,
                         countries=tuple(countries))


def test_one_event_per_document_and_country():
    events = sentinel.analyze_fedreg_documents([
        _fd(countries=("china", "brazil", "cyprus")),
        _fd(category="sanctions", agency="bis", countries=("russia",), number="2026-00002",
            title="Additions to the Entity List"),
    ])
    assert [e.id for e in events] == [
        "fedreg-2026-00001-china", "fedreg-2026-00001-brazil", "fedreg-2026-00001-cyprus",
        "fedreg-2026-00002-russia",
    ]
    china, brazil, _, russia = events
    assert china.type == "trade_dispute" and china.source == "fedreg"
    assert china.title.startswith("USTR: ")
    assert china.region == "china_industrial"
    assert china.timestamp == int(
        datetime(2026, 9, 21, 13, 45, tzinfo=timezone.utc).timestamp() * 1000
    )
    assert russia.type == "sanctions" and russia.title.startswith("BIS: ")
    assert brazil.raw_data["country"] == "brazil"


def test_the_trade_and_sanctions_rules_finally_have_a_source():
    china, brazil = sentinel.analyze_fedreg_documents([_fd(countries=("china", "brazil"))])
    assert "gdelt-trade-dispute-china" in [r.id for r in match_rules(china)]
    assert [r.id for r in match_rules(brazil)] == ["fedreg-trade-brazil"]
    (russia,) = sentinel.analyze_fedreg_documents([
        _fd(category="sanctions", agency="bis", countries=("russia",))
    ])
    assert [r.id for r in match_rules(russia)] == ["ofac-sanctions-russia"]
    (bis_china,) = sentinel.analyze_fedreg_documents([
        _fd(category="sanctions", agency="bis", countries=("china",))
    ])
    assert "gdelt-sanctions-china" in [r.id for r in match_rules(bis_china)]


def test_unparseable_date_skips_the_document():
    assert sentinel.analyze_fedreg_documents([_fd(date="yesterday")]) == []


def test_fetch_degrades_to_the_stale_payload(monkeypatch):
    cache = fedreg.TTLCache()
    cache.set([_fd()])
    monkeypatch.setattr(fedreg, "_cache", cache)
    monkeypatch.setattr(fedreg, "_CACHE_TTL", 0)

    async def down(url, **kw):
        return None

    monkeypatch.setattr(fedreg, "fetch_json", down)
    assert [d.document_number for d in asyncio.run(fedreg.fetch_fedreg())] == ["2026-00001"]

    async def garbage(url, **kw):
        return {"error": "rate limited"}

    monkeypatch.setattr(fedreg, "fetch_json", garbage)
    assert [d.document_number for d in asyncio.run(fedreg.fetch_fedreg())] == ["2026-00001"]


def test_fetch_queries_both_agencies_and_caches(monkeypatch):
    monkeypatch.setattr(fedreg, "_cache", fedreg.TTLCache())
    seen: list[dict] = []

    async def fake(url, *, params=None, **kw):
        seen.append(params)
        return {"count": 1, "results": [_doc(
            "Notice of Action: Brazil's Acts, Policies, and Practices", USTR,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )]}

    monkeypatch.setattr(fedreg, "fetch_json", fake)
    first = asyncio.run(fedreg.fetch_fedreg())
    second = asyncio.run(fedreg.fetch_fedreg())
    assert [d.countries for d in first] == [("brazil",)]
    assert second == first and len(seen) == 1
    assert sorted(seen[0]["conditions[agencies][]"]) == sorted(fedreg.AGENCY_SLUGS)
