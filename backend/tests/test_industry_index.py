"""AI exposure by industry: FinView's own calculation, and how a company inherits it.

The table is built offline from two openly licensed sources (Eloundou et al. 2024
occupation scores, BLS OEWS staffing) with the Felten-Raj-Seamans weighting. These
tests pin that arithmetic, the committed table's provenance, the model step that
places a segment in an industry (held to the table's codes, never cached on
failure) and the revenue weighting that turns industries into a company score.
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import AiMentionCheck, Base, SegmentCheck, SegmentReport
from backend.services.segments.refresh import READERS
from backend.services import llm_envelope
from backend.services.portfolio_service import Position
from backend.services.segments import ai_mentions as am
from backend.services.segments import industry_index as ii
from backend.services.segments.classify import ClassificationError


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


TABLE = {
    "sources": {"occupations": {"commit": "abc"}, "employment": {"release": "May 2025"}},
    "industries": {
        "513200": {"title": "Software Publishers", "score": 0.5, "coverage": 0.98},
        "221100": {"title": "Electric Power Generation", "score": 0.3, "coverage": 0.98},
    },
}


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setattr(ii, "load", lambda: TABLE)


# ── building the table ───────────────────────────────────────────────


def test_onet_detail_codes_are_averaged_into_their_soc_occupation():
    rows = [
        {"O*NET-SOC Code": "11-1011.00", "b": "0.4"},
        {"O*NET-SOC Code": "11-1011.03", "b": "0.6"},
        {"O*NET-SOC Code": "15-1252.00", "b": "0.9"},
    ]
    assert ii.occupation_scores(rows, "b") == pytest.approx({"11-1011": 0.5, "15-1252": 0.9})


def test_an_oews_aggregate_code_takes_the_mean_of_the_codes_under_it():
    scores = {"31-1121": 0.2, "31-1122": 0.4, "51-9198": 0.1}
    assert ii.score_for("31-1121", scores) == 0.2
    assert ii.score_for("31-1120", scores) == pytest.approx(0.3)
    assert ii.score_for("51-9199", scores) is None  # not covered: left out, never guessed


def _oews(naics, occ, group, emp):
    return {"NAICS": naics, "NAICS_TITLE": "Software", "OCC_CODE": occ, "O_GROUP": group,
            "TOT_EMP": emp}


def test_an_industry_score_is_weighted_by_employment_and_reports_its_coverage():
    rows = [
        _oews("513200", "00-0000", "total", 1000),
        _oews("513200", "15-0000", "major", 700),  # not detailed: not counted twice
        _oews("513200", "15-1252", "detailed", 600),
        _oews("513200", "43-9061", "detailed", 200),
        _oews("513200", "51-9199", "detailed", 100),  # no score
        _oews("513200", "13-1111", "detailed", "**"),  # suppressed by BLS
    ]
    out = ii.industry_scores(rows, {"15-1252": 0.6, "43-9061": 0.2, "13-1111": 0.9})
    assert out == {"513200": {"title": "Software", "score": 0.5, "coverage": 0.8}}


def test_the_committed_table_records_its_sources_and_is_in_range():
    data = ii.load()
    occ, emp = data["sources"]["occupations"], data["sources"]["employment"]
    assert data["sources"]["method"]["doi"] == "10.1002/smj.3286"  # Felten, Raj & Seamans
    assert len(occ["commit"]) == 40 and occ["license"] == "MIT"
    assert occ["column"] == "human_rating_beta" and occ["doi"] == "10.1126/science.adj0998"
    assert emp["release"] and emp["url"].startswith("https://www.bls.gov/")
    assert len(data["industries"]) > 200
    assert all(0 <= i["score"] <= 1 and 0 < i["coverage"] <= 1
               for i in data["industries"].values())
    licence = (ii.DATA.parent / "LICENSE-GPTs-are-GPTs.txt").read_text()
    assert "MIT License" in licence and "Copyright (c) 2024 OpenAI" in licence


# ── mapping segments to industries ───────────────────────────────────


def _model_says(monkeypatch, content, error=None):
    monkeypatch.setattr(llm_envelope, "chat", lambda messages, **kw: (content, error))


def test_the_mapper_is_held_to_the_table_codes(monkeypatch, table):
    _model_says(monkeypatch, json.dumps({"Software": "513200", "Cloud": "518200",
                                         "Redes": "221100"}))
    assert ii.map_industries("X", ["Software", "Cloud", "Redes", "Otros"]) == {
        "Software": "513200",
        "Cloud": "unassigned",  # a real NAICS code, but not in the table
        "Redes": "221100",
        "Otros": "unassigned",  # the model left it out
    }


@pytest.mark.parametrize(
    "content, error", [(None, None), (None, "OpenRouter HTTP 502"), ("no", None), ("[]", None)]
)
def test_a_mapper_failure_raises(monkeypatch, table, content, error):
    _model_says(monkeypatch, content, error)
    with pytest.raises(ClassificationError):
        ii.map_industries("X", ["Software"])


def test_the_mapper_prompt_lists_every_code(table):
    assert "513200: Software Publishers" in ii._system()
    assert "221100: Electric Power Generation" in ii._system()


# ── a company's score ────────────────────────────────────────────────


def _line(label, value, industry="__missing__", axis="business"):
    line = {"axis": axis, "label": label, "value": str(value), "category": "x"}
    if industry != "__missing__":
        line["industry"] = industry
    return line


def test_a_company_score_is_weighted_by_segment_revenue(table):
    out = ii.company_exposure([
        _line("Software", 75, "513200"),
        _line("Redes", 25, "221100"),
        _line("Ajustes", -10, "unassigned"),
        _line("España", 100, axis="geography"),
    ])
    assert out["score"] == Decimal("0.45")
    assert out["revenue_share"] == 1


def test_unassigned_revenue_lowers_the_share_covered_not_the_score(table):
    out = ii.company_exposure([_line("Software", 60, "513200"), _line("Otros", 40, "unassigned")])
    assert out["score"] == Decimal("0.5")
    assert out["revenue_share"] == Decimal("0.6")


def test_no_score_before_the_lines_are_mapped_or_without_business_lines(table):
    assert ii.company_exposure([_line("Software", 60), _line("Redes", 40, "221100")]) is None
    assert ii.company_exposure([_line("España", 100, axis="geography")]) is None


# ── refresh and page ─────────────────────────────────────────────────


def _segment_report(db, isin, lines):
    db.add(SegmentReport(
        isin=isin, fiscal_year=2024, period_end=date(2024, 12, 31), source="esef",
        filing_id=isin, source_url="https://filings.xbrl.org/v.html", currency="EUR",
        total_revenue=Decimal(100), axis_status="{}", lines=json.dumps(lines),
    ))
    db.add(SegmentCheck(isin=isin, outcome="ok", filing_id=isin,
                        reader=READERS[SegmentCheck]))
    db.commit()


@pytest.fixture
def nothing_due(db, monkeypatch):
    """Annual-report reading is out of the way: only the industry step runs."""
    monkeypatch.setattr(am.settings, "openrouter_api_key", "test-key")
    for isin in ("ES1", "ES2"):
        db.add(AiMentionCheck(isin=isin, outcome="no_filing", reader=READERS[AiMentionCheck]))
    db.commit()


HOLDINGS = {"ES1": ("A", "Iberdrola"), "ES2": ("B", "Otra")}


def test_unmapped_business_lines_are_mapped_and_stored(db, table, nothing_due, monkeypatch):
    _segment_report(db, "ES1", [_line("Redes", 100), _line("España", 100, axis="geography")])
    monkeypatch.setattr(ii, "map_industries", lambda company, labels: {"Redes": "221100"})
    assert am.refresh(db, HOLDINGS, 30) == {"checked": 1, "pending": 0}
    lines = json.loads(db.query(SegmentReport).one().lines)
    assert lines[0]["industry"] == "221100" and "industry" not in lines[1]


def test_a_mapper_failure_is_not_cached(db, table, nothing_due, monkeypatch):
    _segment_report(db, "ES1", [_line("Redes", 100)])

    def _down(company, labels):
        raise ClassificationError("OpenRouter HTTP 502")

    monkeypatch.setattr(ii, "map_industries", _down)
    assert am.refresh(db, HOLDINGS, 30) == {"checked": 0, "pending": 1}
    assert "industry" not in json.loads(db.query(SegmentReport).one().lines)[0]


def test_mapped_reports_are_not_sent_to_the_model_again(db, table, nothing_due, monkeypatch):
    _segment_report(db, "ES1", [_line("Redes", 100, "221100")])
    monkeypatch.setattr(ii, "map_industries", lambda *a: pytest.fail("must not map again"))
    assert am.refresh(db, HOLDINGS, 30) == {"checked": 0, "pending": 0}


def _position(isin, value):
    return Position(isin=isin, ticker=None, name=isin, country=None, broker="X", account_id=1,
                    quantity=Decimal(1), market_value_eur=Decimal(value))


def test_the_portfolio_index_is_weighted_by_value_and_covered_revenue(db, table):
    _segment_report(db, "ES1", [_line("Software", 50, "513200"), _line("Otros", 50, "unassigned")])
    _segment_report(db, "ES2", [_line("Redes", 100, "221100")])
    out = am.build(db, [_position("ES1", 600), _position("ES2", 200), _position("ES3", 200)])

    index = out["industry_index"]
    # Covered value: 600 x 50% software + 200 x 100% power = 500, of 1000.
    assert index["value_pct"] == 50.0
    assert index["score"] == pytest.approx((300 * 0.5 + 200 * 0.3) / 500)
    assert [(i["code"], i["value_pct"]) for i in index["industries"]] == [
        ("513200", 30.0), ("221100", 20.0),
    ]
    assert index["sources"] == TABLE["sources"]

    by_isin = {h["isin"]: h for h in out["holdings"]}
    assert by_isin["ES1"]["industry"]["revenue_pct"] == 50.0
    assert by_isin["ES1"]["industry"]["parts"][0]["title"] in {"Software Publishers", None}
    assert by_isin["ES3"]["industry"] is None
    assert by_isin["ES3"]["industry_detail"] == am.INDUSTRY_DETAIL["no_report"]
