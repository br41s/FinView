"""The generative path: a salient event no rule covers gets one validated LLM thesis."""

import json
import time

import pytest

from backend.services import llm_envelope
from backend.services.geo import analyst, orchestrator
from backend.services.geo.advisor import _pageable
from backend.services.geo.analyst import AnalystResult, _validate_generated, analyze_unmatched
from backend.services.geo.sentinel import GeoEvent


@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(analyst, "_GENERATIVE_CACHE", {})
    monkeypatch.setattr(analyst.settings, "openrouter_api_key", "k")


def _event(**kw) -> GeoEvent:
    base = dict(id="gdelt-armed_conflict-libya", type="armed_conflict", title="Coup in Tripoli",
                latitude=32.9, longitude=13.2, source="gdelt", timestamp=int(time.time() * 1000),
                raw_data={"numMentions": 40, "novelty": {"novel": True}})
    base.update(kw)
    return GeoEvent(**base)


GOOD = {
    "actionable": True,
    "thesis": {"effect": "Libyan export terminals close", "flow": "Brent tightens", "instrument": "USO tracks crude"},
    "tickers": [{"symbol": "USO", "direction": "bullish", "rationale": "crude supply"}],
    "confidence": 80, "riskScore": 7, "narrative": "Ports shut; 1.2 mb/d offline.",
}


def test_validation_accepts_only_a_complete_answer_from_the_universe():
    assert _validate_generated(GOOD)["tickers"] == [
        {"symbol": "USO", "direction": "bullish", "rationale": "crude supply"}
    ]
    assert _validate_generated({**GOOD, "actionable": False}) is None
    assert _validate_generated({**GOOD, "tickers": [{"symbol": "NVDA", "direction": "bullish"}]}) is None
    assert _validate_generated({**GOOD, "tickers": [{"symbol": "USO", "direction": "neutral"}]}) is None
    assert _validate_generated({**GOOD, "confidence": "alto"}) is None
    assert _validate_generated({**GOOD, "thesis": ""}) is None
    assert _validate_generated("not a dict") is None
    capped = _validate_generated({**GOOD, "confidence": 140, "riskScore": 10})
    assert (capped["confidence"], capped["riskScore"]) == (85, 8)  # the model sets both factors


def test_at_most_three_tickers_and_they_are_filtered_not_rejected():
    many = {**GOOD, "tickers": [
        {"symbol": s, "direction": "bullish"} for s in ("USO", "GLD", "LMT", "XLE", "FAKE")
    ]}
    out = _validate_generated(many, reach="global")
    assert [t["symbol"] for t in out["tickers"]] == ["USO", "GLD", "LMT"]


def test_picks_wider_than_the_events_reach_are_dropped():
    """A one-district event may not target a worldwide ETF — the rules' invariant."""
    picks = {**GOOD, "tickers": [
        {"symbol": "GLD", "direction": "bullish"},   # global
        {"symbol": "LMT", "direction": "bullish"},   # sector
        {"symbol": "USO", "direction": "bullish"},   # commodity
    ]}
    assert [t["symbol"] for t in _validate_generated(picks, reach="local")["tickers"]] == ["USO"]
    assert [t["symbol"] for t in _validate_generated(picks, reach="regional")["tickers"]] == ["LMT", "USO"]
    assert _validate_generated({**GOOD, "tickers": [{"symbol": "GLD", "direction": "bullish"}]}, "local") is None


def test_another_countrys_instrument_is_dropped_whatever_the_model_says():
    """Breadth alone let an Indonesian event pick Brazil's market: both are "national"."""
    from backend.services.geo.rules import allowed_symbols
    from backend.services.geo.sentinel import GeoEvent

    jakarta = GeoEvent(id="g", type="mass_protest", title="t", latitude=-6.2, longitude=106.8,
                       source="gdelt", timestamp=0, country="indonesia")
    picks = {**GOOD, "tickers": [
        {"symbol": "EWZ", "direction": "bearish"},   # Brazil
        {"symbol": "EIDO", "direction": "bearish"},  # Indonesia
    ]}
    allowed = allowed_symbols(jakarta)
    assert [t["symbol"] for t in _validate_generated(picks, "local", allowed)["tickers"]] == ["EIDO"]
    only_foreign = {**GOOD, "tickers": [{"symbol": "EWZ", "direction": "bearish"}]}
    assert _validate_generated(only_foreign, "local", allowed) is None


def test_analyze_unmatched_builds_a_rule_free_analysis(monkeypatch):
    monkeypatch.setattr(analyst, "_llm_generate", lambda event: _validate_generated(GOOD))
    ev = _event()
    res = analyze_unmatched(ev, regime="risk_off")
    assert res is not None and res.matched_rules == []
    assert [t.symbol for t in res.tickers] == ["USO"]
    assert res.confidence == 80.0 and res.risk_score == 7  # the LLM's risk, regime does not stack
    assert "→" in res.direction
    assert ev.raw_data["generated"] is True and ev.raw_data["llmConfidence"] == 80


def test_not_actionable_is_cached_and_costs_one_call(monkeypatch):
    calls: list[str] = []

    def fake_post(*a, **k):
        calls.append("post")

        class R:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": '{"actionable": false}'}}]}

        return R()

    monkeypatch.setattr(llm_envelope.httpx, "post", fake_post)
    ev = _event()
    assert analyze_unmatched(ev) is None
    assert analyze_unmatched(ev) is None
    assert calls == ["post"]
    assert "generated" not in ev.raw_data


# ── A 200 with no answer in it ────────────────────────────────────────
# What Cloud Run logged 2–7 times a day (this one 2026-10-04): the model spent
# the whole budget reasoning, so the 200 carries its reasoning and no answer.
REASONED_AWAY = {
    "choices": [{
        "message": {"role": "assistant", "content": None, "refusal": None,
                    "reasoning": "We need to decide whether this is tradable…",
                    "reasoning_details": []},
        "finish_reason": "length",
    }],
    "usage": {"prompt_tokens": 843, "completion_tokens": 2000,
              "completion_tokens_details": {"reasoning_tokens": 1967}},
}


def _answering(monkeypatch, body: dict) -> list[dict]:
    """OpenRouter answers 200 with ``body``; returns the request bodies it was sent."""
    sent: list[dict] = []

    class R:
        status_code = 200

        def json(self):
            return body

    def fake_post(*a, **k):
        sent.append(k["json"])
        return R()

    monkeypatch.setattr(llm_envelope.httpx, "post", fake_post)
    return sent


def test_an_answer_lost_to_reasoning_is_no_thesis_and_not_a_cached_no(monkeypatch):
    sent = _answering(monkeypatch, REASONED_AWAY)
    ev = _event()
    assert analyze_unmatched(ev) is None
    assert "generated" not in ev.raw_data
    # "Not actionable" is remembered for six hours. A call that produced nothing
    # is not that answer: caching it would silence the event on a failure.
    assert analyst.has_fresh_generative(ev.id) is False
    assert analyze_unmatched(ev) is None
    assert len(sent) == 2


def test_an_answer_cut_mid_json_is_no_thesis_either(monkeypatch):
    """The same cut, a little later (prod, 2026-10-02): reasoning left room for half the JSON."""
    cut = '{"actionable": true, "thesis": {"effect": "Libyan export terminals clo'
    _answering(monkeypatch, {"choices": [{"message": {"content": cut}, "finish_reason": "length"}]})
    ev = _event()
    assert analyze_unmatched(ev) is None
    assert "generated" not in ev.raw_data
    assert analyst.has_fresh_generative(ev.id) is False


def test_the_generative_call_turns_reasoning_off(monkeypatch):
    """max_tokens pays for the reasoning and the answer alike, and this model has
    no lower effort and no reasoning budget to ask for: off is the only bound."""
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    assert analyze_unmatched(_event()) is not None
    assert sent[0]["reasoning"] == {"effort": "none"}


def test_salience_gate():
    assert orchestrator._salient(_event(region="libya")) is True  # novel news
    assert orchestrator._salient(_event(region="libya", raw_data={"numMentions": 40})) is True
    assert orchestrator._salient(_event(region="libya", raw_data={"numMentions": 3, "novelty": {"novel": False}})) is False
    # Nearly every conflict bucket is "red" (CAMEO 19x is -10): severity must not
    # short-circuit the news test, and a story in no box is never salient.
    assert orchestrator._salient(_event(region="libya", severity="red", raw_data={"numMentions": 3})) is False
    assert orchestrator._salient(_event(region=None, severity="red", raw_data={"numMentions": 40})) is False
    assert orchestrator._salient(_event(source="usgs", type="earthquake", magnitude=7.4, raw_data={})) is True
    assert orchestrator._salient(_event(source="usgs", type="earthquake", magnitude=5.8, raw_data={})) is False
    assert orchestrator._salient(_event(source="EONET", type="volcano", severity="red", raw_data={})) is True
    assert orchestrator._salient(_event(source="EONET", type="volcano", raw_data={})) is False


def test_generative_pass_is_capped_per_request_and_replaces_in_place(monkeypatch):
    asked: list[str] = []

    def fake(event, regime=None):
        asked.append(event.id)
        return AnalystResult(event=event, matched_rules=[], tickers=[], confidence=80.0,
                             risk_score=7, direction="t") if event.id != "e2" else None

    monkeypatch.setattr(orchestrator, "analyze_unmatched", fake)
    analyses = [
        AnalystResult(event=_event(id=f"e{i}", region="libya"), matched_rules=[], tickers=[],
                      confidence=0.0, risk_score=5, direction="")
        for i in range(5)
    ]
    matched = AnalystResult(event=_event(id="m", region="libya"), matched_rules=[], tickers=[analyst.AnalystTicker("USO", "bullish", "r")],
                            confidence=80.0, risk_score=8, direction="rule")
    analyses.insert(0, matched)
    assert orchestrator._generative_pass(analyses, None) == 3
    assert asked == ["e0", "e1", "e2"]  # the matched one was skipped, the cap held
    assert analyses[1].confidence == 80.0 and analyses[3].confidence == 0.0  # e2 stayed unmatched


def test_a_cached_answer_is_free_and_a_capped_pass_still_refreshes_cached_events(monkeypatch):
    """Three live generated signals used to occupy the three slots for six hours."""
    asked: list[str] = []
    monkeypatch.setattr(analyst, "_GENERATIVE_CACHE", {f"e{i}": (time.time(), {"x": 1}) for i in range(3)})
    monkeypatch.setattr(orchestrator, "has_fresh_generative", analyst.has_fresh_generative)

    def fake(event, regime=None):
        asked.append(event.id)
        return AnalystResult(event=event, matched_rules=[], tickers=[], confidence=80.0,
                             risk_score=7, direction="t")

    monkeypatch.setattr(orchestrator, "analyze_unmatched", fake)
    analyses = [
        AnalystResult(event=_event(id=f"e{i}", region="libya"), matched_rules=[], tickers=[],
                      confidence=0.0, risk_score=5, direction="")
        for i in range(7)
    ]
    assert orchestrator._generative_pass(analyses, None) == 3  # e3, e4, e5 spent the cap
    assert asked == ["e0", "e1", "e2", "e3", "e4", "e5"]  # cached ones refreshed for free; e6 waited


def test_a_generated_signal_is_pinned_at_first_sighting(db):
    """A 6-hour re-call may name other instruments; the priced basket is day one's."""
    from backend.services.geo.advisor import generate_signal
    from backend.services.geo.analyst import AnalystTicker

    ev = _event(region="libya", raw_data={"generated": True, "llmConfidence": 80,
                                          "llmNarrative": "day one", "novelty": {"novel": True}})
    first = generate_signal(db, user_id=1, analysis=AnalystResult(
        event=ev, matched_rules=[], tickers=[AnalystTicker("USO", "bullish", "r")],
        confidence=80.0, risk_score=7, direction="t", llm_narrative="day one"), prices={"USO": 70.0})
    db.commit()
    ev2 = _event(region="libya", title="Something else", raw_data={"generated": True, "llmConfidence": 60,
                                                                  "llmNarrative": "day two", "novelty": {"novel": True}})
    res = generate_signal(db, user_id=1, analysis=AnalystResult(
        event=ev2, matched_rules=[], tickers=[AnalystTicker("TTF=F", "bullish", "r")],
        confidence=60.0, risk_score=4, direction="t2", llm_narrative="day two"), prices={})
    assert res.signal.id == first.signal.id
    assert res.signal.headline == "Coup in Tripoli" and "day one" in (res.signal.raw_json or "")
    assert float(res.signal.confidence) == 0.8 and int(res.signal.risk_score) == 7


def test_generated_theses_page_only_on_high_confidence():
    confident = _event(raw_data={"generated": True, "llmConfidence": 80, "novelty": {"novel": True}})
    timid = _event(raw_data={"generated": True, "llmConfidence": 60, "novelty": {"novel": True}})
    assert _pageable("gdelt", 70, confident) is True
    assert _pageable("gdelt", 70, timid) is False
    stale = _event(raw_data={"generated": True, "llmConfidence": 90, "novelty": {"novel": False}})
    assert _pageable("gdelt", 70, stale) is False  # every other gate still applies


def test_api_reads_the_generated_stamp():
    import json

    from backend.api.geo import _raw

    raw = json.dumps({"generated": True, "llmNarrative": "Ports shut."})
    assert _raw(raw)["generated"] is True and _raw(raw)["llmNarrative"] == "Ports shut."
    assert _raw("not json") == {} and _raw(None) == {}
