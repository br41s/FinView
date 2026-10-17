"""What annual reports say about AI: the checks that decide what gets published.

A count is computed in code; quotes come from a model and are published only if
every one of them is in the filing word for word and names AI itself. These tests
pin those gates, the bad answers a model gives (null, not JSON, invented or
edited quotes), the caching rules (an outage is never cached, a definite answer
is) and the reading of 10-K and ESEF documents as text.
"""

import json
from datetime import date

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import AiMentionCheck, AiMentionReport, Base
from backend.services import llm_envelope
from backend.services.portfolio_service import Position
from backend.services.segments import ai_mentions as am
from backend.services.segments import esef, sec


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


FILLER = "Our business depends on many factors that are described in this section. " * 40
RISK_TEXT = (
    FILLER + "\nCompetitors may use artificial intelligence to offer cheaper products. "
    "Our use of AI may expose us to new regulation and liability. "
    "The word Gaia and the word said do not count.\n" + FILLER
)
QUOTE = "Our use of AI may expose us to new regulation and liability."


# ── counting ─────────────────────────────────────────────────────────


def test_acronyms_count_only_as_whole_upper_case_words():
    assert am.count("AI, GenAI, ai, said, Gaia, IA, KI, kite")[0] == 4


@pytest.mark.parametrize(
    "phrase",
    [
        "artificial intelligence",
        "Inteligencia Artificial",
        "intelligence artificielle",
        "künstliche Intelligenz",
        "machine learning",
        "large language models",
    ],
)
def test_the_languages_reports_are_filed_in_are_counted(phrase):
    assert am.count(f"El grupo usa {phrase} en sus procesos.")[0] == 1


def test_passages_merge_overlapping_windows_and_are_capped(monkeypatch):
    text = "x" * 1000 + " AI and AI " + "y" * 1000 + " AI " + "z" * 1000
    out = am.passages(text)
    assert len(out) == 2  # the first two mentions share a window
    monkeypatch.setattr(am, "MAX_CONTEXT_CHARS", 10)
    assert len(am.passages(text)) == 1


# ── reading documents ────────────────────────────────────────────────


def test_embedded_images_and_tags_are_dropped_across_chunk_boundaries():
    doc = (
        b'<html><head><style>.AI{color:red}</style></head><body>'
        b'<p>Before</p><img src="data:image/png;base64,' + b"QUFB" * 5000 + b'"/>'
        b'<div>Our <span class="x">AI</span> &amp; data</div><p>After</p></body></html>'
    )
    stream = am.TextStream()
    for i in range(0, len(doc), 7):  # chunks split every tag, entity and marker
        stream.feed(doc[i : i + 7])
    assert stream.close() == "Before\nOur AI & data\nAfter"


def test_inline_xbrl_periods_are_kept_across_chunk_boundaries():
    doc = (
        b"<html><body><ix:header><xbrli:context id='c1'><xbrli:period>"
        b"<xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate>"
        b"</xbrli:period></xbrli:context><xbrli:context id='c2'><xbrli:period>"
        b"<xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>"
        b"<xbrli:context id='c3'><xbrli:period><xbrli:startDate>soon</xbrli:startDate>"
        b"<xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>"
        b"</ix:header><p>Our AI</p></body></html>"
    )
    for size in (7, len(doc)):  # 7 splits every date and tag
        stream = am.TextStream()
        for i in range(0, len(doc), size):
            stream.feed(doc[i : i + size])
        stream.close()
        assert stream.periods == [(date(2025, 1, 1), date(2025, 12, 31))]


def _ten_k(*headings: str) -> str:
    return "\n".join(headings)


def test_item_1a_is_the_section_not_the_table_of_contents():
    text = _ten_k(
        "Item 1A. Risk Factors", "14", "Item 1B. Unresolved Staff Comments", "29",
        "PART I", "ITEM 1A. RIS K FACTORS", RISK_TEXT,
        "ITEM 1B. UNRESOLVE D STAFF COMMENTS", "None.",
    )
    section = am.risk_factors(text)
    assert section is not None and QUOTE in section and "None." not in section


def test_a_heading_split_over_two_lines_is_found():
    text = _ten_k("Item 1A.", "Risk Factors", RISK_TEXT, "Item 1C.", "Cybersecurity")
    assert QUOTE in am.risk_factors(text)


def test_a_risk_factor_cross_reference_is_no_section():
    text = _ten_k("Item 1A. Risk Factors", "Not applicable.", "Item 2. Properties")
    assert am.risk_factors(text) is None


class _Response:
    def __init__(self, status, chunks):
        self.status_code, self._chunks = status, chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self, size):
        yield from self._chunks


class _StreamClient:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error

    def stream(self, method, url):
        if self.error:
            raise self.error
        return self.response


def test_a_report_over_the_size_cap_is_too_large(monkeypatch):
    monkeypatch.setattr(am, "MAX_REPORT_BYTES", 10)
    http = _StreamClient(_Response(200, [b"<p>12345</p>", b"<p>67890</p>"]))
    with pytest.raises(am.TooLarge):
        am.read_text(http, "https://filings.xbrl.org/r.xhtml", 30)


@pytest.mark.parametrize(
    "http",
    [
        _StreamClient(_Response(503, [])),
        _StreamClient(error=httpx.ReadTimeout("slow")),
    ],
)
def test_a_failed_read_is_a_source_outage(http):
    with pytest.raises(sec.SourceUnavailable):
        am.read_text(http, "https://www.sec.gov/x.htm", 30)


# ── model answers ────────────────────────────────────────────────────


def _answer(quotes, summary="La empresa señala que la IA trae regulación."):
    return json.dumps({"quotes": quotes, "summary": summary})


def test_a_verbatim_quote_is_kept_with_its_theme():
    quotes, summary, status = am.verify(
        _answer([{"text": QUOTE, "theme": "regulation"}]), RISK_TEXT
    )
    assert status == "ok"
    assert quotes == [{"text": QUOTE, "theme": "regulation"}]
    assert summary.startswith("La empresa señala")


def test_quotes_are_compared_with_typography_and_line_breaks_normalized():
    text = "Competitors may use artificial\nintelligence to offer cheaper products — fast."
    quote = "Competitors may use artificial intelligence to offer cheaper products - fast."
    assert am.verify(_answer([{"text": quote, "theme": "x"}]), text)[2] == "ok"


@pytest.mark.parametrize(
    "quote",
    [
        # Invented: the filing never says this.
        "AI will make our products obsolete within five years.",
        # Edited: one word changed from the filing.
        "Our use of AI may expose us to strict regulation and liability.",
        # In the filing, but does not name AI itself.
        "Our business depends on many factors that are described in this section.",
        # Too short to stand as a quote.
        "AI",
    ],
)
def test_one_quote_that_is_not_in_the_filing_rejects_all_of_them(quote):
    answer = _answer([{"text": QUOTE, "theme": "regulation"}, {"text": quote, "theme": "other"}])
    assert am.verify(answer, RISK_TEXT) == ([], None, "unverified")


def test_a_theme_outside_the_list_becomes_other():
    quotes, _, _ = am.verify(_answer([{"text": QUOTE, "theme": "doom"}]), RISK_TEXT)
    assert quotes[0]["theme"] == "other"


def test_no_quote_means_no_summary():
    assert am.verify(_answer([], "La IA lo cambiará todo."), RISK_TEXT) == ([], None, "none")


@pytest.mark.parametrize(
    "content", ["not json", "[1, 2]", json.dumps({"quotes": "AI", "summary": None})]
)
def test_unusable_answers_are_errors_or_unverified(content):
    if content.startswith("{"):
        assert am.verify(content, RISK_TEXT)[2] == "unverified"
    else:
        with pytest.raises(am.AiReadError):
            am.verify(content, RISK_TEXT)


@pytest.mark.parametrize("content, error", [(None, None), (None, "OpenRouter HTTP 502")])
def test_a_null_or_failed_model_call_raises(monkeypatch, content, error):
    monkeypatch.setattr(llm_envelope, "chat", lambda messages, **kw: (content, error))
    with pytest.raises(am.AiReadError):
        am.ask("Apple", RISK_TEXT)


# ── refresh ──────────────────────────────────────────────────────────


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def source(monkeypatch):
    """An ESEF issuer whose report is RISK_TEXT, and a model that quotes it."""
    monkeypatch.setattr(sec, "client", _NullClient)
    monkeypatch.setattr(esef, "client", _NullClient)
    monkeypatch.setattr(am.settings, "openrouter_api_key", "test-key")
    state = {
        "text": RISK_TEXT,
        "fail": None,
        "answer": _answer([{"text": QUOTE, "theme": "regulation"}]),
        "filing": esef.Filing("F-2024", date(2024, 12, 31), "/f.json", "/v.html", "/r.xhtml"),
        "reads": 0,
        "asks": 0,
        "periods": [],
    }

    def _isin_to_lei(http, isin):
        if state["fail"]:
            raise state["fail"]
        return "LEI"

    def _read_text(http, url, seconds):
        state["reads"] += 1
        return am.Document(state["text"], state["periods"])

    def _ask(company, text):
        state["asks"] += 1
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(esef, "isin_to_lei", _isin_to_lei)
    monkeypatch.setattr(esef, "latest_filing", lambda http, lei: state["filing"])
    monkeypatch.setattr(am, "read_text", _read_text)
    monkeypatch.setattr(am, "ask", _ask)
    return state


HOLDING = {"ES0000000001": ("IBE.MC", "Iberdrola")}


def test_a_report_is_stored_with_its_count_quotes_and_link(db, source):
    assert am.refresh(db, HOLDING, 30) == {"checked": 1, "pending": 0}
    row = db.query(AiMentionReport).one()
    assert (row.fiscal_year, row.scope, row.mentions, row.quotes_status) == (
        2024, "annual_report", 2, "ok",
    )
    assert json.loads(row.quotes) == [{"text": QUOTE, "theme": "regulation"}]
    assert row.source_url == "https://filings.xbrl.org/v.html"
    assert db.query(AiMentionCheck).one().filing_id == "F-2024"


def test_a_mislisted_esef_report_is_stored_under_its_own_year(db, source):
    """Carrefour's FY2025 report is listed at 2026-12-31; its contexts say 2025."""
    source["filing"] = esef.Filing("F-2025", date(2026, 12, 31), "/f.json", "/v.html", "/r.xhtml")
    fy25, fy24 = (date(2025, 1, 1), date(2025, 12, 31)), (date(2024, 1, 1), date(2024, 12, 31))
    source["periods"] = [fy25, fy25, fy24]
    am.refresh(db, HOLDING, 30)
    row = db.query(AiMentionReport).one()
    assert (row.fiscal_year, row.period_end) == (2025, date(2025, 12, 31))


def test_an_unchanged_filing_is_not_read_again(db, source):
    am.refresh(db, HOLDING, 30)
    db.query(AiMentionCheck).one().checked_at = date(2000, 1, 1)
    db.commit()
    am.refresh(db, HOLDING, 30)
    assert (source["reads"], source["asks"]) == (1, 1)


@pytest.mark.parametrize(
    "where, error",
    [
        ("fail", sec.SourceUnavailable("HTTP 503")),
        ("answer", am.AiReadError("The model returned no text")),
    ],
)
def test_an_outage_or_a_null_answer_is_not_cached(db, source, where, error):
    source[where] = error
    assert am.refresh(db, HOLDING, 30) == {"checked": 0, "pending": 1}
    assert db.query(AiMentionCheck).count() == 0
    assert db.query(AiMentionReport).count() == 0


def test_invented_quotes_keep_the_count_and_are_retried_at_the_next_recheck(db, source):
    source["answer"] = _answer([{"text": "AI will end our business.", "theme": "competition"}])
    am.refresh(db, HOLDING, 30)
    row = db.query(AiMentionReport).one()
    assert (row.mentions, row.quotes, row.quotes_status, row.summary) == (
        2, "[]", "unverified", None,
    )
    check = db.query(AiMentionCheck).one()
    assert check.filing_id is None  # so the same filing is read again when due
    assert am.refresh(db, HOLDING, 30)["checked"] == 0  # but not on every page load


def test_a_report_without_mentions_needs_no_model(db, source):
    source["text"] = FILLER
    source["answer"] = AssertionError("must not ask")
    am.refresh(db, HOLDING, 30)
    row = db.query(AiMentionReport).one()
    assert (row.mentions, row.quotes_status) == (0, "none")
    assert source["asks"] == 0


def test_a_filing_without_a_report_document_is_cached_as_such(db, source):
    source["filing"] = esef.Filing("F-2024", date(2024, 12, 31), "/f.json", "/v.html", None)
    am.refresh(db, HOLDING, 30)
    assert db.query(AiMentionCheck).one().outcome == "no_section"
    assert source["reads"] == 0


def test_a_report_too_large_to_read_is_cached_as_such(db, source, monkeypatch):
    def _too_large(http, url, seconds):
        raise am.TooLarge("big")

    monkeypatch.setattr(am, "read_text", _too_large)
    am.refresh(db, HOLDING, 30)
    assert db.query(AiMentionCheck).one().outcome == "too_large"


def test_without_a_model_key_nothing_is_fetched(db, source, monkeypatch):
    monkeypatch.setattr(am.settings, "openrouter_api_key", "")
    source["fail"] = AssertionError("must not fetch")
    assert am.refresh(db, HOLDING, 30) == {"checked": 0, "pending": 1}


# ── what the page shows ──────────────────────────────────────────────


def _position(isin, value, name="Co"):
    return Position(
        isin=isin, ticker=None, name=name, country=None, broker="X", account_id=1,
        quantity=1, market_value_eur=None if value is None else value,
    )


def test_the_portfolio_view_weights_by_value_and_reports_each_holding(db):
    from decimal import Decimal

    for isin, mentions, quotes in (
        ("US1", 12, [{"text": QUOTE, "theme": "regulation"}]),
        ("ES1", 0, []),
    ):
        db.add(AiMentionReport(
            isin=isin, fiscal_year=2025, period_end=date(2025, 12, 31), source="sec",
            scope="risk_factors", filing_id=isin, source_url="https://www.sec.gov/x",
            mentions=mentions, words=4000, quotes=json.dumps(quotes),
            quotes_status="ok" if quotes else "none", summary=None,
        ))
        db.add(AiMentionCheck(isin=isin, outcome="ok", filing_id=isin))
    db.add(AiMentionCheck(isin="IE1", outcome="no_filing"))
    db.commit()

    out = am.build(db, [
        _position("US1", Decimal(600)), _position("ES1", Decimal(200)),
        _position("IE1", Decimal(200), "ETF"), _position("XX1", None, "Sin precio"),
    ])
    assert (out["read_pct"], out["mentioning_pct"]) == (80.0, 60.0)
    assert out["themes"] == [{"key": "regulation", "label": "Regulación y litigios", "pct": 60.0}]
    first = out["holdings"][0]
    assert (first["isin"], first["per_10k_words"], first["scope_label"]) == (
        "US1", 30.0, "Factores de riesgo (10-K, Item 1A)",
    )
    assert first["quotes"][0]["theme_label"] == "Regulación y litigios"
    etf = next(h for h in out["holdings"] if h["isin"] == "IE1")
    assert etf["detail"] == am.OUTCOME_DETAIL["no_filing"] and etf["mentions"] is None
    assert out["pending"] == 1  # XX1 never checked


def test_the_api_routes_are_registered():
    from backend.app import app

    paths = {route.path for route in app.routes}
    assert {"/api/portfolio/ai-exposure", "/api/portfolio/ai-exposure/refresh"} <= paths
