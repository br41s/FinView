"""Segment revenue from annual reports: the checks that decide what gets published.

The pipeline reads two kinds of source. SEC 10-K instances are tagged number by
number; ESEF segment notes are HTML that a model reads. In both cases nothing is
stored unless the lines add up to the report's tagged total revenue, and from a
note nothing is stored unless every amount appears in it as printed. These tests
pin those gates, the caching rules (an outage is never cached, a definite answer
is) and how a portfolio's value is spread over what the reports say.
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, ListingProfile, SegmentCheck, SegmentReport
from backend.services import llm_envelope
from backend.services.portfolio_service import Position
from backend.services.segments import classify as classify_mod
from backend.services.segments import esef, exposure, listing, refresh, sec
from backend.services.segments.numbers import (
    appears_in,
    parse_amount,
    pick_partition,
    reconciles,
    scale_to_total,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── amounts and sums ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("16.982", Decimal("16982")),  # Spanish thousands separator
        ("1,234", Decimal("1234")),  # US thousands separator
        ("1.234.567", Decimal("1234567")),
        ("1.234,5", Decimal("1234.5")),
        ("1,234.5", Decimal("1234.5")),
        ("2,5", Decimal("2.5")),
        ("(448)", Decimal("-448")),
        ("-448", Decimal("-448")),
        ("−448", Decimal("-448")),
        ("44 739", Decimal("44739")),
        ("—", None),
        ("n/a", None),
        ("", None),
    ],
)
def test_amounts_are_read_as_printed_in_either_convention(raw, expected):
    assert parse_amount(raw) == expected


def test_an_amount_must_be_printed_as_a_whole_number_in_the_note():
    note = "España | 16.982 | Brasil | 9.139 | Total | 44.739"
    assert appears_in("16.982", note)
    assert not appears_in("6.982", note)  # inside 16.982
    assert not appears_in("16.98", note)  # prefix of 16.982
    assert not appears_in("17.000", note)


def test_reconciles_within_rounding_and_not_beyond():
    total = Decimal("44739")
    assert reconciles(Decimal("44739"), total)
    assert reconciles(Decimal("44700"), total)  # lines rounded to millions
    assert not reconciles(Decimal("44000"), total)
    assert not reconciles(Decimal("0"), Decimal("0"))


def test_the_scale_is_the_one_under_which_the_lines_add_up():
    total = Decimal("44739000000")
    values = [Decimal("16982"), Decimal("27757")]
    assert scale_to_total(values, total) == Decimal(1_000_000)
    assert scale_to_total([Decimal("1"), Decimal("2")], total) is None


def test_the_finest_partition_wins_when_an_axis_mixes_levels():
    """Apple tags Product+Service and iPhone/Mac/iPad/Wearables+Service on one axis."""
    values = {
        "Product": Decimal("307003"),
        "Service": Decimal("109158"),
        "iPhone": Decimal("209586"),
        "Mac": Decimal("33708"),
        "iPad": Decimal("28023"),
        "Wearables": Decimal("35686"),
    }
    assert sorted(pick_partition(values, Decimal("416161"))) == sorted(
        ["Service", "iPhone", "Mac", "iPad", "Wearables"]
    )


def test_no_partition_when_nothing_adds_up():
    assert pick_partition({"A": Decimal(1), "B": Decimal(2)}, Decimal(100)) is None


def test_a_single_member_equal_to_the_total_is_not_a_breakdown():
    values = {"Total": Decimal(100), "A": Decimal(30), "B": Decimal(30)}
    assert pick_partition(values, Decimal(100)) is None


# ── SEC instance ─────────────────────────────────────────────────────

_INSTANCE = """<?xml version="1.0"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:us-gaap="http://fasb.org/us-gaap/2025"
      xmlns:dei="http://xbrl.sec.gov/dei/2025">
  <context id="fy"><entity><identifier>1</identifier></entity>
    <period><startDate>2024-09-29</startDate><endDate>2025-09-27</endDate></period></context>
  <context id="prior"><entity><identifier>1</identifier></entity>
    <period><startDate>2023-10-01</startDate><endDate>2024-09-28</endDate></period></context>
  <context id="q4"><entity><identifier>1</identifier></entity>
    <period><startDate>2025-06-29</startDate><endDate>2025-09-27</endDate></period></context>
  <context id="eu"><entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">us-gaap:OperatingSegmentsMember</xbrldi:explicitMember>
      <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:EuropeSegmentMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2024-09-29</startDate><endDate>2025-09-27</endDate></period></context>
  <context id="us"><entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:AmericasSegmentMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2024-09-29</startDate><endDate>2025-09-27</endDate></period></context>
  <context id="two"><entity><identifier>1</identifier><segment>
      <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:AmericasSegmentMember</xbrldi:explicitMember>
      <xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">x:PhoneMember</xbrldi:explicitMember>
    </segment></entity>
    <period><startDate>2024-09-29</startDate><endDate>2025-09-27</endDate></period></context>
  <unit id="usd"><measure>iso4217:USD</measure></unit>
  <unit id="shares"><measure>xbrli:shares</measure></unit>
  <dei:DocumentPeriodEndDate contextRef="fy">2025-09-27</dei:DocumentPeriodEndDate>
  <us-gaap:Revenues contextRef="fy" unitRef="usd" decimals="-6">1000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="prior" unitRef="usd" decimals="-6">900</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="q4" unitRef="usd" decimals="-6">250</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="eu" unitRef="usd" decimals="-6">400</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="us" unitRef="usd" decimals="-6">600</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="two" unitRef="usd" decimals="-6">333</us-gaap:Revenues>
</xbrl>"""


def test_the_instance_yields_the_full_year_total_and_one_axis_members():
    inst = sec.parse_instance(_INSTANCE)
    assert inst.currency == "USD"
    assert inst.total == Decimal(1000)
    assert inst.period_end == date(2025, 9, 27)
    # The prior year, the quarter and the two-dimension fact are all ignored; the
    # segment fact tagged with OperatingSegmentsMember counts as one dimension.
    assert inst.axes == {
        "us-gaap:StatementBusinessSegmentsAxis": {
            "x:EuropeSegmentMember": Decimal(400),
            "x:AmericasSegmentMember": Decimal(600),
        }
    }


def test_an_instance_without_a_revenue_total_is_none():
    assert sec.parse_instance(_INSTANCE.replace(">1000<", ">bad<").replace(
        'contextRef="fy" unitRef="usd"', 'contextRef="fy" unitRef="shares"'
    )) is None


def test_labels_come_from_the_filing_linkbase():
    xml = """<linkbase xmlns="http://www.xbrl.org/2003/linkbase"
                       xmlns:xlink="http://www.w3.org/1999/xlink">
      <labelLink>
        <loc xlink:href="aapl-20250927.xsd#aapl_IPhoneMember" xlink:label="loc_1"/>
        <label xlink:label="lab_1" xlink:role="http://www.xbrl.org/2003/role/label">iPhone [Member]</label>
        <label xlink:label="lab_1t" xlink:role="http://www.xbrl.org/2003/role/terseLabel">Phones</label>
        <labelArc xlink:from="loc_1" xlink:to="lab_1"/>
        <labelArc xlink:from="loc_1" xlink:to="lab_1t"/>
      </labelLink></linkbase>"""
    assert sec.parse_labels(xml) == {"aapl:IPhoneMember": "iPhone"}


def test_member_names_fall_back_to_a_readable_form():
    assert sec.member_label("aapl:GreaterChinaSegmentMember") == "Greater China"
    assert sec.member_label("country:US") == "US"


# ── ESEF report ──────────────────────────────────────────────────────

_NOTE_HTML = (
    "<div><p>Expresadas en millones de euros</p><table>"
    "<tr><td>Ejercicio 2024</td><td>España</td><td>Brasil</td><td>Ajustes</td><td>Total</td></tr>"
    "<tr><td>Importe neto de la cifra de negocios</td><td>16.982</td><td>27.757</td>"
    "<td>(448)</td><td>44.291</td></tr></table></div>"
)


def _esef_json(note=_NOTE_HTML, revenue=44291000000.0):
    core = {"entity": "scheme:LEI", "unit": "iso4217:EUR"}
    return {
        "facts": {
            "f1": {
                "value": revenue,
                "dimensions": {
                    **core,
                    "concept": "ifrs-full:Revenue",
                    "period": "2024-01-01T00:00:00/2025-01-01T00:00:00",
                },
            },
            "f2": {  # prior year, ignored
                "value": 1.0,
                "dimensions": {
                    **core,
                    "concept": "ifrs-full:Revenue",
                    "period": "2023-01-01T00:00:00/2024-01-01T00:00:00",
                },
            },
            "f3": {  # a dimensioned revenue fact is not the total
                "value": 2.0,
                "dimensions": {
                    **core,
                    "concept": "ifrs-full:Revenue",
                    "period": "2024-01-01T00:00:00/2025-01-01T00:00:00",
                    "ifrs-full:SegmentsAxis": "x:Member",
                },
            },
            "f4": {
                "value": note,
                "dimensions": {
                    "concept": "ifrs-full:DisclosureOfEntitysReportableSegmentsExplanatory",
                    "entity": "scheme:LEI",
                    "period": "2024-01-01T00:00:00/2025-01-01T00:00:00",
                },
            },
        }
    }


def test_the_report_gives_the_tagged_total_and_the_note_as_table_text():
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    assert report.currency == "EUR"
    assert report.total == Decimal("44291000000.0")
    assert "Importe neto de la cifra de negocios | 16.982 | 27.757 | (448) | 44.291" in report.note


def test_a_report_without_a_revenue_total_is_none():
    data = _esef_json()
    del data["facts"]["f1"]
    assert esef.parse_report(data, date(2024, 12, 31)) is None


def test_verified_lines_are_scaled_to_the_total_with_adjustments_kept():
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    rows = [("España", "16.982"), ("Brasil", "27.757"), ("Ajustes", "(448)")]
    lines, status = esef.verify(rows, report)
    assert status == "ok"
    assert lines == [
        ("España", Decimal("16982000000")),
        ("Brasil", Decimal("27757000000")),
        ("Ajustes", Decimal("-448000000")),
    ]


def test_an_amount_not_printed_in_the_note_rejects_the_whole_breakdown():
    """The model may not invent or 'correct' a figure, even one that would add up."""
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    rows = [("España", "16.534"), ("Brasil", "27.757")]  # 16.534 = 16.982 - 448
    assert esef.verify(rows, report) == (None, "not_in_note")


def test_lines_that_do_not_add_up_are_rejected():
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    rows = [("España", "16.982"), ("Brasil", "27.757")]  # the adjustment left out
    assert esef.verify(rows, report) == (None, "unreconciled")


def test_a_total_line_copied_in_by_mistake_fails_the_check():
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    rows = [("España", "16.982"), ("Brasil", "27.757"), ("Ajustes", "(448)"), ("Total", "44.291")]
    assert esef.verify(rows, report) == (None, "unreconciled")


def test_one_line_is_not_a_breakdown():
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    assert esef.verify([("Total", "44.291")], report) == (None, "absent")


# ── totals for issuers that tag no revenue ───────────────────────────


def _facts(*facts, period="2024-01-01T00:00:00/2025-01-01T00:00:00"):
    """An xBRL-JSON report from (concept, value) pairs, plus an optional dimension."""
    out = {}
    for i, (concept, value, *dims) in enumerate(facts):
        out[f"t{i}"] = {
            "value": value,
            "dimensions": {
                "concept": concept, "entity": "scheme:LEI", "unit": "iso4217:EUR",
                "period": period, **(dims[0] if dims else {}),
            },
        }
    return {"facts": out}


def _total(data):
    report = esef.parse_report(data, date(2024, 12, 31))
    return None if report is None else (report.measure, report.total)


def test_a_bank_is_checked_against_its_margen_bruto():
    """Sabadell and BBVA tag margen bruto as GrossProfit, next to net interest income."""
    data = _facts(("ifrs-full:GrossProfit", 6337362000.0),
                  ("ifrs-full:InterestRevenueExpense", 5021335000.0))
    assert _total(data) == ("bank_gross_income", Decimal("6337362000.0"))


def test_gross_profit_without_net_interest_income_is_not_a_total():
    """Outside a bank's income statement GrossProfit is revenue minus cost of sales."""
    assert _total(_facts(("ifrs-full:GrossProfit", 1000.0))) is None


def test_net_interest_income_from_another_year_does_not_make_a_bank():
    data = _facts(("ifrs-full:GrossProfit", 1000.0))
    data["facts"].update(_facts(("ifrs-full:InterestRevenueExpense", 800.0),
                                period="2023-01-01T00:00:00/2024-01-01T00:00:00")["facts"])
    assert _total(data) is None


def test_revenue_wins_over_every_fallback():
    data = _facts(("ifrs-full:InsuranceRevenue", 3.0), ("ifrs-full:GrossProfit", 2.0),
                  ("ifrs-full:InterestRevenueExpense", 1.0), ("ifrs-full:Revenue", 10.0))
    assert _total(data) == ("revenue", Decimal("10.0"))


def test_an_insurer_with_rental_income_is_checked_against_insurance_revenue():
    """Línea Directa tags both; its segment note breaks down insurance revenue."""
    data = _facts(("ifrs-full:RentalIncomeFromInvestmentProperty", 4293000.0),
                  ("ifrs-full:InsuranceRevenue", 991329000.0))
    assert _total(data) == ("insurance_revenue", Decimal("991329000.0"))


@pytest.mark.parametrize("concept", [
    "ifrs-full:RentalIncomeFromInvestmentProperty", "ifrs-full:RentalIncome",
])
def test_a_property_company_is_checked_against_rental_income(concept):
    assert _total(_facts((concept, 395577000.0))) == ("rental_income", Decimal("395577000.0"))


def test_a_fallback_tagged_only_by_segment_is_not_a_total():
    data = _facts(("ifrs-full:InsuranceRevenue", 5.0, {"ifrs-full:SegmentsAxis": "x:Member"}))
    assert _total(data) is None


def test_a_proportionate_breakdown_does_not_add_up_to_the_ifrs_rental_total():
    """URW prints gross rental income twice: proportionate (2,817.0) just above IFRS (2,328.2)."""
    note = (
        "Gross Rental Income by segments on a proportionate basis | 2025\n"
        "Shopping Centres | 2,526.4\nOffices & Others | 86.6\nConvention & Exhibition | 203.9\n"
        "Total | 2,817.0\n"
        "Gross Rental Income by segments on an IFRS basis | 2025\n"
        "Shopping Centres | 2,052.9\nOffices & Others | 74.4\nConvention & Exhibition | 201.0\n"
        "Total | 2,328.2"
    )
    report = esef.Report(currency="EUR", total=Decimal("2328200000"), note=note,
                         period_end=date(2025, 12, 31), measure="rental_income")
    wrong = [("Shopping Centres", "2,526.4"), ("Offices & Others", "86.6"),
             ("Convention & Exhibition", "203.9")]
    right = [("Shopping Centres", "2,052.9"), ("Offices & Others", "74.4"),
             ("Convention & Exhibition", "201.0")]
    assert esef.verify(wrong, report) == (None, "unreconciled")
    assert esef.verify(right, report)[1] == "ok"


# ── the report's own year, not the listing's ─────────────────────────

FY24 = (date(2024, 1, 1), date(2024, 12, 31))
FY23 = (date(2023, 1, 1), date(2023, 12, 31))


def test_the_year_is_the_most_common_full_year_in_the_report():
    """Aviva's FY2025 report is listed at 2026-03-02; its facts say 2025."""
    periods = [FY24] * 5 + [FY23] * 3 + [(date(2024, 7, 1), date(2024, 12, 31))] * 9
    assert esef.fiscal_year_end(periods, date(2026, 3, 2)) == date(2024, 12, 31)


def test_on_a_tie_the_later_year_wins():
    assert esef.fiscal_year_end([FY24, FY23], date(2026, 3, 2)) == date(2024, 12, 31)


def test_without_a_full_year_period_the_listing_stands():
    half = [(date(2024, 7, 1), date(2024, 12, 31))]
    assert esef.fiscal_year_end(half, date(2024, 12, 31)) == date(2024, 12, 31)
    assert esef.fiscal_year_end([], date(2024, 12, 31)) == date(2024, 12, 31)


def test_a_52_week_year_counts_as_a_full_year():
    week52 = (date(2025, 3, 30), date(2026, 3, 28))
    assert esef.fiscal_year_end([week52], date(2026, 3, 28)) == date(2026, 3, 28)


def test_a_mislisted_report_keeps_its_total_and_its_own_year():
    """Every fact failed the period check against a wrong listing: `no_revenue`."""
    report = esef.parse_report(_esef_json(), date(2026, 3, 2))
    assert report.period_end == date(2024, 12, 31)
    assert report.total == Decimal("44291000000.0")


def test_a_correct_listing_is_unchanged():
    assert esef.parse_report(_esef_json(), date(2024, 12, 31)).period_end == date(2024, 12, 31)


def test_malformed_periods_are_skipped():
    data = _esef_json()
    data["facts"]["bad"] = {"value": 1.0, "dimensions": {"concept": "x", "period": "soon/later"}}
    data["facts"]["instant"] = {"value": 1.0, "dimensions": {"concept": "y", "period": "2024-12-31"}}
    assert esef.parse_report(data, date(2026, 3, 2)).period_end == date(2024, 12, 31)


# ── model answers ────────────────────────────────────────────────────


def _model_says(monkeypatch, content, error=None):
    calls = []

    def _chat(messages, **kwargs):
        calls.append(messages)
        return content, error

    monkeypatch.setattr(llm_envelope, "chat", _chat)
    return calls


def test_the_classifier_is_held_to_the_taxonomy(monkeypatch):
    _model_says(
        monkeypatch,
        json.dumps({
            "business": {"iPhone": "technology", "Services": "software"},  # not a key
            "geography": {"Europe": "europe"},
        }),
    )
    out = classify_mod.classify("Apple", ["iPhone", "Services", "Other"], ["Europe"])
    assert out == {
        "business": {"iPhone": "technology", "Services": "unassigned", "Other": "unassigned"},
        "geography": {"Europe": "europe"},
    }


@pytest.mark.parametrize("content, error", [(None, "OpenRouter HTTP 502"), ("not json", None)])
def test_a_classifier_failure_raises(monkeypatch, content, error):
    _model_says(monkeypatch, content, error)
    with pytest.raises(classify_mod.ClassificationError):
        classify_mod.classify("X", ["A"], [])


def test_the_reader_keeps_only_well_formed_rows(monkeypatch):
    _model_says(
        monkeypatch,
        "```json\n"
        + json.dumps({
            "business": [{"label": "Redes", "amount": "1.000"}, {"label": "", "amount": "2"}],
            "geography": "none",
        })
        + "\n```",
    )
    report = esef.Report(currency="EUR", total=Decimal(1), note="x", period_end=date(2024, 12, 31))
    out = esef.extract("Iberdrola", report, date(2024, 12, 31))
    assert out == {"business": [("Redes", "1.000")], "geography": []}


@pytest.mark.parametrize("measure, words", [
    ("revenue", "importe neto de la cifra de negocios"),
    ("bank_gross_income", "margen bruto"),
    ("insurance_revenue", "ingresos de las actividades ordinarias de seguros"),
    ("rental_income", "not a proportionate basis"),
])
def test_the_reader_is_told_which_figure_to_copy(monkeypatch, measure, words):
    calls = _model_says(monkeypatch, json.dumps({"business": [], "geography": []}))
    report = esef.Report(currency="EUR", total=Decimal(1), note="x",
                         period_end=date(2024, 12, 31), measure=measure)
    esef.extract("X", report, date(2024, 12, 31))
    system = calls[0][0]["content"]
    assert words in system
    assert '{"business": [{"label": "...", "amount": "..."}]' in system


# ── refresh ──────────────────────────────────────────────────────────


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def no_http(monkeypatch):
    monkeypatch.setattr(sec, "client", _NullClient)
    monkeypatch.setattr(esef, "client", _NullClient)
    monkeypatch.setattr(refresh.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(listing, "refresh", lambda db, holdings, seconds: (0, 0))


def _esef_source(monkeypatch, *, lei="LEI", filing_id="F-2024", rows=None, fail=None):
    filing = esef.Filing(filing_id, date(2024, 12, 31), "/f.json", "/viewer.html")
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    calls = {"extract": 0}

    def _isin_to_lei(http, isin):
        if fail:
            raise fail
        return lei

    def _extract(company, rep, period_end):
        calls["extract"] += 1
        return rows or {
            "business": [],
            "geography": [("España", "16.982"), ("Brasil", "27.757"), ("Ajustes", "(448)")],
        }

    monkeypatch.setattr(esef, "isin_to_lei", _isin_to_lei)
    monkeypatch.setattr(esef, "latest_filing", lambda http, lei: filing)
    monkeypatch.setattr(esef, "fetch_report", lambda http, f: report)
    monkeypatch.setattr(esef, "extract", _extract)
    monkeypatch.setattr(
        refresh,
        "classify",
        lambda company, business, geography: {
            "business": {},
            "geography": {"España": "spain", "Brasil": "latin_america", "Ajustes": "unassigned"},
        },
    )
    return calls


HOLDING = {"ES0000000001": ("IBE.MC", "Iberdrola")}


def test_a_report_that_adds_up_is_stored_with_its_source(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    assert refresh.refresh(db, HOLDING, 30) == {"checked": 1, "pending": 0}

    report = db.query(SegmentReport).one()
    assert (report.fiscal_year, report.source, report.filing_id) == (2024, "esef", "F-2024")
    assert report.source_url == "https://filings.xbrl.org/viewer.html"
    lines = json.loads(report.lines)
    assert {line["label"]: line["category"] for line in lines} == {
        "España": "spain", "Brasil": "latin_america", "Ajustes": "unassigned"
    }
    assert json.loads(report.axis_status) == {"business": "absent", "geography": "ok"}
    assert db.query(SegmentCheck).one().outcome == "ok"


def test_a_mislisted_filing_is_stored_under_the_reports_own_year(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    listed = esef.Filing("F-2024", date(2026, 3, 2), "/f.json", "/viewer.html")
    monkeypatch.setattr(esef, "latest_filing", lambda http, lei: listed)
    monkeypatch.setattr(
        esef, "fetch_report", lambda http, f: esef.parse_report(_esef_json(), f.period_end)
    )
    refresh.refresh(db, HOLDING, 30)
    row = db.query(SegmentReport).one()
    assert (row.fiscal_year, row.period_end) == (2024, date(2024, 12, 31))


def test_the_measure_is_stored_with_the_report(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    report = esef.parse_report(_esef_json(), date(2024, 12, 31))
    report.measure = "bank_gross_income"
    monkeypatch.setattr(esef, "fetch_report", lambda http, f: report)
    refresh.refresh(db, HOLDING, 30)
    assert db.query(SegmentReport).one().measure == "bank_gross_income"


def test_a_filing_without_a_total_is_read_again_at_the_recheck(db, no_http, monkeypatch):
    """`no_revenue` says what FinView could read: a new fallback total must reach it."""
    calls = _esef_source(monkeypatch)
    monkeypatch.setattr(esef, "fetch_report", lambda http, f: None)
    refresh.refresh(db, HOLDING, 30)
    assert db.query(SegmentCheck).one().outcome == "no_revenue"
    db.query(SegmentCheck).one().checked_at = datetime(2020, 1, 1)
    db.commit()

    monkeypatch.setattr(
        esef, "fetch_report", lambda http, f: esef.parse_report(_esef_json(), date(2024, 12, 31))
    )
    refresh.refresh(db, HOLDING, 30)
    assert calls["extract"] == 1
    assert db.query(SegmentCheck).one().outcome == "ok"


def test_an_unchanged_filing_is_not_read_again(db, no_http, monkeypatch):
    calls = _esef_source(monkeypatch)
    refresh.refresh(db, HOLDING, 30)
    check = db.query(SegmentCheck).one()
    check.checked_at = datetime.now(timezone.utc) - timedelta(days=refresh.RECHECK_DAYS + 1)
    db.commit()

    refresh.refresh(db, HOLDING, 30)
    assert calls["extract"] == 1
    assert refresh.due_isins(db, HOLDING) == []


def test_a_new_filing_adds_a_year(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    refresh.refresh(db, HOLDING, 30)
    db.query(SegmentCheck).one().checked_at = datetime(2020, 1, 1)
    db.commit()

    newer = esef.Filing("F-2025", date(2025, 12, 31), "/f.json", "/viewer.html")
    fy2025 = json.loads(
        json.dumps(_esef_json()).replace("2025-01-01T00:00:00", "2026-01-01T00:00:00")
        .replace("2024-01-01T00:00:00", "2025-01-01T00:00:00")
    )
    monkeypatch.setattr(esef, "latest_filing", lambda http, lei: newer)
    monkeypatch.setattr(esef, "fetch_report", lambda http, f: esef.parse_report(fy2025, f.period_end))
    refresh.refresh(db, HOLDING, 30)
    assert sorted(r.fiscal_year for r in db.query(SegmentReport)) == [2024, 2025]


def test_an_outage_is_not_cached(db, no_http, monkeypatch):
    _esef_source(monkeypatch, fail=sec.SourceUnavailable("HTTP 503"))
    assert refresh.refresh(db, HOLDING, 30) == {"checked": 0, "pending": 1}
    assert db.query(SegmentCheck).count() == 0


def test_a_model_failure_is_not_cached(db, no_http, monkeypatch):
    _esef_source(monkeypatch)

    def _down(*a):
        raise esef.ExtractionError("OpenRouter HTTP 502")

    monkeypatch.setattr(esef, "extract", _down)
    assert refresh.refresh(db, HOLDING, 30)["pending"] == 1
    assert db.query(SegmentCheck).count() == 0


def test_an_issuer_without_a_filing_is_cached_as_such(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    monkeypatch.setattr(esef, "latest_filing", lambda http, lei: None)
    refresh.refresh(db, HOLDING, 30)
    check = db.query(SegmentCheck).one()
    assert check.outcome == "no_filing"
    assert refresh.due_isins(db, HOLDING) == []


def test_a_breakdown_that_does_not_add_up_is_recorded_not_stored(db, no_http, monkeypatch):
    _esef_source(
        monkeypatch,
        rows={"business": [], "geography": [("España", "16.982"), ("Brasil", "27.757")]},
    )
    refresh.refresh(db, HOLDING, 30)
    assert db.query(SegmentReport).count() == 0
    assert db.query(SegmentCheck).one().outcome == "unreconciled"


def test_a_breakdown_that_did_not_add_up_is_read_again_at_the_recheck(db, no_http, monkeypatch):
    """A failed read says how FinView read the note, not what the note says."""
    calls = _esef_source(
        monkeypatch,
        rows={"business": [], "geography": [("España", "16.982"), ("Brasil", "27.757")]},
    )
    refresh.refresh(db, HOLDING, 30)
    check = db.query(SegmentCheck).one()
    check.checked_at = datetime.now(timezone.utc) - timedelta(days=refresh.RECHECK_DAYS + 1)
    db.commit()

    refresh.refresh(db, HOLDING, 30)
    assert calls["extract"] == 2  # same filing id, read again
    assert refresh.refresh(db, HOLDING, 30)["checked"] == 0  # but only once per recheck


def test_an_answer_from_an_older_reader_is_due_at_once_and_read_again(db, no_http, monkeypatch):
    """A fix must reach yesterday's cached `no_revenue`, not wait out RECHECK_DAYS."""
    calls = _esef_source(monkeypatch)
    refresh.refresh(db, HOLDING, 30)
    assert calls["extract"] == 1 and refresh.due_isins(db, HOLDING) == []

    db.query(SegmentCheck).one().reader = None  # written before readers were versioned
    db.commit()
    assert refresh.due_isins(db, HOLDING) == ["ES0000000001"]
    refresh.refresh(db, HOLDING, 30)
    assert calls["extract"] == 2  # same filing id, read again
    assert db.query(SegmentCheck).one().reader == refresh.READERS[SegmentCheck]
    assert refresh.due_isins(db, HOLDING) == []


def test_a_row_stored_under_the_listings_wrong_year_is_replaced(db, no_http, monkeypatch):
    """Carrefour's FY2025 was listed as 2026: the 2026 row would win as the latest."""
    _esef_source(monkeypatch)
    db.add(SegmentReport(
        isin="ES0000000001", fiscal_year=2026, period_end=date(2026, 3, 2), source="esef",
        filing_id="F-2024", source_url="https://example.org", currency="EUR",
        total_revenue=Decimal(1), lines="[]", axis_status="{}",
    ))
    db.add(SegmentReport(  # another filing's year is kept
        isin="ES0000000001", fiscal_year=2023, period_end=date(2023, 12, 31), source="esef",
        filing_id="F-2023", source_url="https://example.org", currency="EUR",
        total_revenue=Decimal(1), lines="[]", axis_status="{}",
    ))
    db.commit()
    refresh.refresh(db, HOLDING, 30)
    assert sorted(r.fiscal_year for r in db.query(SegmentReport)) == [2023, 2024]


def test_a_cell_split_into_divs_stays_on_its_row():
    """PDF-converted reports wrap each figure in <div>s (Naturgy, Endesa, Enagás...)."""
    fragment = (
        "<div>Información por segmentos</div><p>Millones de euros</p>"
        "<table><tr><td><div><div>INCN consolidado</div></div></td>"
        "<td><div><span>903</span></div></td><td><p>671</p><br/></td>"
        "<td><div>1.574</div></td></tr>"
        "<tr><td><div>INCN entre segmentos</div></td><td><div>84</div></td>"
        "<td>—</td><td><div>84</div></td></tr></table>"
    )
    assert esef.note_text(fragment) == (
        "Información por segmentos\nMillones de euros\n"
        "INCN consolidado | 903 | 671 | 1.574\n"
        "INCN entre segmentos | 84 | — | 84"
    )


def test_without_a_model_key_nothing_is_fetched(db, no_http, monkeypatch):
    monkeypatch.setattr(refresh.settings, "openrouter_api_key", "")
    _esef_source(monkeypatch, fail=AssertionError("must not fetch"))
    assert refresh.refresh(db, HOLDING, 30) == {"checked": 0, "pending": 1}
    assert db.query(SegmentCheck).count() == 0


def test_the_budget_stops_the_loop(db, no_http, monkeypatch):
    _esef_source(monkeypatch)
    holdings = {f"ES000000000{i}": (None, f"Co {i}") for i in range(3)}
    assert refresh.refresh(db, holdings, 0) == {"checked": 0, "pending": 3}


def test_never_checked_isins_come_before_stale_ones(db):
    old = datetime.now(timezone.utc) - timedelta(days=30)
    reader = refresh.READERS[SegmentCheck]
    db.add(SegmentCheck(isin="ES0000000002", outcome="ok", checked_at=old, reader=reader))
    db.add(SegmentCheck(isin="ES0000000003", outcome="ok", checked_at=datetime.now(timezone.utc),
                        reader=reader))
    db.commit()
    assert refresh.due_isins(db, ["ES0000000003", "ES0000000002", "ES0000000001"]) == [
        "ES0000000001",
        "ES0000000002",
    ]


def test_the_breakdown_that_places_the_most_revenue_wins():
    """Apple's regional segments place nothing in a sector; its products place all."""
    regions = [("Americas", Decimal(60)), ("Europe", Decimal(40))]
    products = [("iPhone", Decimal(70)), ("Services", Decimal(30))]
    cats = {"Americas": "unassigned", "Europe": "unassigned", "iPhone": "technology",
            "Services": "technology"}
    assert min([regions, products], key=lambda lines: refresh._unassigned_share(lines, cats)) is products


# ── exposure ─────────────────────────────────────────────────────────


def _position(isin, value, name="Co"):
    return Position(
        isin=isin, ticker=None, name=name, country=None, broker="X", account_id=1,
        quantity=Decimal(1), market_value_eur=None if value is None else Decimal(value),
    )


def _report(db, isin, year, lines):
    db.add(SegmentReport(
        isin=isin, fiscal_year=year, period_end=date(year, 12, 31), source="esef",
        filing_id=f"{isin}-{year}", source_url="https://example.org", currency="EUR",
        total_revenue=Decimal(100), axis_status="{}",
        lines=json.dumps([
            {"axis": a, "label": label, "value": str(v), "category": c}
            for a, label, v, c in lines
        ]),
    ))
    db.add(SegmentCheck(isin=isin, outcome="ok"))
    db.commit()


def test_value_is_spread_by_revenue_share_and_adjustments_are_left_out(db):
    _report(db, "ES1", 2024, [
        ("geography", "España", 75, "spain"),
        ("geography", "Brasil", 25, "latin_america"),
        ("geography", "Ajustes", -10, "unassigned"),
        ("business", "Redes", 100, "utilities"),
    ])
    out = exposure.build(db, [_position("ES1", "1000"), _position("ES2", "500", "ETF")])

    geo = {row["key"]: row for row in out["geography"]}
    assert geo["spain"]["value_eur"] == 750.0
    assert geo["latin_america"]["value_eur"] == 250.0
    assert "unassigned" not in geo
    assert geo["no_data"]["value_eur"] == 500.0
    assert round(sum(r["pct"] for r in out["geography"]), 1) == 100.0
    assert [r["key"] for r in out["sector"]] == ["utilities", "no_data"]
    assert geo["spain"]["holdings"][0]["segments"] == [{"label": "España", "pct": 75.0}]


def test_the_measure_reaches_the_holding_and_the_source(db):
    _report(db, "ES1", 2024, [("geography", "España", 60, "spain"),
                              ("geography", "México", 40, "latin_america")])
    db.query(SegmentReport).one().measure = "bank_gross_income"
    _report(db, "ES2", 2024, [("geography", "España", 100, "spain")])  # written before: NULL
    db.commit()
    out = exposure.build(db, [_position("ES1", "100"), _position("ES2", "100")])

    spain = {h["isin"]: h for h in next(r for r in out["geography"] if r["key"] == "spain")["holdings"]}
    assert spain["ES1"]["measure"] == "bank_gross_income"
    assert spain["ES2"]["measure"] == "revenue"
    assert [s["measure"] for s in out["sources"]] == ["bank_gross_income", "revenue"]


def test_the_latest_year_is_used(db):
    _report(db, "ES1", 2023, [("geography", "España", 100, "spain")])
    db.query(SegmentCheck).delete()
    _report(db, "ES1", 2024, [("geography", "Brasil", 100, "latin_america")])
    out = exposure.build(db, [_position("ES1", "100")])
    assert [r["key"] for r in out["geography"]] == ["latin_america"]
    assert out["sources"][0]["fiscal_year"] == 2024


def test_an_unpriced_position_is_listed_apart_and_not_spread(db):
    out = exposure.build(db, [_position("ES1", None, "Sin precio"), _position("ES2", "200")])
    assert out["unpriced"] == [{"isin": "ES1", "name": "Sin precio"}]
    assert out["total_value_eur"] == 200.0
    assert out["geography"] == [
        {"key": "no_data", "label": "Sin datos", "value_eur": 200.0, "pct": 100.0,
         "holdings": [{"isin": "ES2", "name": "Co", "ticker": None, "value_eur": 200.0,
                       "basis": None, "measure": None, "segments": []}]},
    ]
    assert out["pending"] == 2


def test_the_api_route_is_registered():
    from backend.app import app

    paths = {route.path for route in app.routes}
    assert {"/api/portfolio/exposure", "/api/portfolio/exposure/refresh"} <= paths


def test_sources_are_reported_per_position(db):
    db.add(SegmentCheck(isin="ES2", outcome="no_filing"))
    db.commit()
    out = exposure.build(db, [_position("ES2", "1")])
    assert out["sources"] == [{
        "isin": "ES2", "name": "Co", "status": "no_filing",
        "detail": refresh.OUTCOME_DETAIL["no_filing"],
        "fiscal_year": None, "source": None, "measure": None, "url": None, "axis_status": None,
        "estimated": [], "listing_sector": None,
    }]
    assert out["pending"] == 0



# ── listing fallback: ISIN country and Yahoo sector ──────────────────


def _profile(db, isin, quote_type="EQUITY", sector="Financial Services", ticker="T",
             checked_at=None):
    db.add(ListingProfile(isin=isin, ticker=ticker, quote_type=quote_type, sector=sector,
                          checked_at=checked_at or datetime.now(timezone.utc)))
    db.commit()


class _Ticker:
    def __init__(self, info=None, error=None):
        self._info, self._error = info, error

    @property
    def info(self):
        if self._error:
            raise self._error
        return self._info


@pytest.mark.parametrize("info, error, expected", [
    ({"quoteType": "EQUITY", "sector": "Healthcare"}, None, ("EQUITY", "Healthcare")),
    ({"quoteType": "ETF"}, None, ("ETF", None)),
    ({"trailingPegRatio": None}, None, None),  # what Yahoo returns for an unknown ticker
    (None, ValueError("no data"), None),
    ("not a dict", None, None),
])
def test_yahoo_answers_are_read_or_refused(monkeypatch, info, error, expected):
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda t: _Ticker(info, error))
    assert listing.fetch("X") == expected


def test_a_stock_without_a_report_is_its_isin_country_and_listed_sector(db):
    _profile(db, "ES1234567890")
    out = exposure.build(db, [_position("ES1234567890", "100")])
    sector, region = out["sector"][0], out["geography"][0]
    assert (sector["key"], sector["value_eur"]) == ("financials", 100.0)
    assert (region["key"], region["value_eur"]) == ("spain", 100.0)
    holding = region["holdings"][0]
    assert holding["basis"] == "listing" and holding["measure"] is None
    assert holding["segments"] == [{"label": "España", "pct": 100.0}]
    assert sector["holdings"][0]["segments"] == [{"label": "Financial Services", "pct": 100.0}]
    assert out["sources"][0]["estimated"] == ["sector", "geography"]
    assert out["sources"][0]["listing_sector"] == "Financial Services"


def test_an_etf_stays_without_data_in_both_axes(db):
    """Its ISIN country is the fund's domicile, not what it holds."""
    _profile(db, "IE00B4L5Y983", quote_type="ETF", sector=None)
    out = exposure.build(db, [_position("IE00B4L5Y983", "100")])
    assert [r["key"] for r in out["sector"]] == ["no_data"]
    assert [r["key"] for r in out["geography"]] == ["no_data"]
    assert out["sources"][0]["estimated"] == []


def test_the_report_wins_axis_by_axis(db):
    """BBVA's report gives regions only: only its sector comes from the listing."""
    _report(db, "ES0113211835", 2024, [("geography", "España", 30, "spain"),
                                       ("geography", "México", 70, "latin_america")])
    _profile(db, "ES0113211835")
    out = exposure.build(db, [_position("ES0113211835", "100")])
    assert {r["key"]: r["value_eur"] for r in out["geography"]} == {
        "spain": 30.0, "latin_america": 70.0,
    }
    assert out["geography"][0]["holdings"][0]["basis"] == "report"
    assert out["sector"][0]["key"] == "financials"
    assert out["sector"][0]["holdings"][0]["basis"] == "listing"
    assert out["sources"][0]["estimated"] == ["sector"]


def test_an_unknown_sector_or_an_offshore_prefix_gives_nothing_for_that_axis(db):
    _profile(db, "XS0000000001", sector="Conglomerates")
    out = exposure.build(db, [_position("XS0000000001", "100")])
    assert [r["key"] for r in out["sector"]] == ["no_data"]
    assert [r["key"] for r in out["geography"]] == ["no_data"]


def _yahoo(monkeypatch, answers):
    asked = []

    def _fetch(ticker):
        asked.append(ticker)
        return answers.get(ticker)

    monkeypatch.setattr(listing, "fetch", _fetch)
    return asked


def test_only_uncovered_isins_with_a_ticker_are_looked_up(db, monkeypatch):
    _report(db, "ES1", 2024, [("geography", "España", 100, "spain"),
                              ("business", "Redes", 100, "utilities")])
    asked = _yahoo(monkeypatch, {"B.MC": ("EQUITY", "Utilities")})
    holdings = {"ES1": ("A.MC", "Covered"), "ES2": ("B.MC", "Stock"), "ES3": (None, "No ticker")}
    assert listing.refresh(db, holdings, 30) == (1, 0)
    assert asked == ["B.MC"]
    assert db.query(ListingProfile).one().sector == "Utilities"
    assert listing.refresh(db, holdings, 30) == (0, 0)  # cached for RECHECK_DAYS


def test_no_answer_from_yahoo_is_asked_again_a_day_later_not_on_every_load(db, monkeypatch):
    asked = _yahoo(monkeypatch, {})
    holdings = {"ES2": ("B.MC", "Stock")}
    listing.refresh(db, holdings, 30)
    listing.refresh(db, holdings, 30)
    assert asked == ["B.MC"]
    assert db.query(ListingProfile).one().quote_type is None
    db.query(ListingProfile).one().checked_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db.commit()
    listing.refresh(db, holdings, 30)
    assert asked == ["B.MC", "B.MC"]


def test_a_new_ticker_is_looked_up_again(db, monkeypatch):
    _profile(db, "ES2", ticker="OLD.MC")
    asked = _yahoo(monkeypatch, {"NEW.MC": ("EQUITY", "Energy")})
    listing.refresh(db, {"ES2": ("NEW.MC", "Stock")}, 30)
    assert asked == ["NEW.MC"]
    assert db.query(ListingProfile).one().sector == "Energy"


def test_the_yahoo_budget_stops_the_listing_loop(db, monkeypatch):
    asked = _yahoo(monkeypatch, {"B.MC": ("EQUITY", "Energy")})
    assert listing.refresh(db, {"ES2": ("B.MC", "Stock")}, 0) == (0, 1)
    assert asked == []


def test_the_listing_runs_without_a_model_key(db, monkeypatch):
    monkeypatch.setattr(refresh.settings, "openrouter_api_key", "")
    _yahoo(monkeypatch, {"B.MC": ("EQUITY", "Energy")})
    holdings = {"ES2": ("B.MC", "Stock")}
    out = refresh.refresh(db, holdings, 30)
    assert out["checked"] == 1
    assert db.query(ListingProfile).count() == 1
