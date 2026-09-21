"""The generative path: a salient event no rule covers gets one validated LLM thesis."""

import time

import pytest

from backend.services.geo import analyst, orchestrator
from backend.services.geo.advisor import _pageable
from backend.services.geo.analyst import AnalystResult, _validate_generated, analyze_unmatched
from backend.services.geo.sentinel import GeoEvent


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
    assert _validate_generated({**GOOD, "confidence": 140, "riskScore": 0})["confidence"] == 100


def test_at_most_three_tickers_and_they_are_filtered_not_rejected():
    many = {**GOOD, "tickers": [
        {"symbol": s, "direction": "bullish"} for s in ("USO", "GLD", "LMT", "XLE", "FAKE")
    ]}
    out = _validate_generated(many)
    assert [t["symbol"] for t in out["tickers"]] == ["USO", "GLD", "LMT"]


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

    monkeypatch.setattr(analyst.httpx, "post", fake_post)
    ev = _event()
    assert analyze_unmatched(ev) is None
    assert analyze_unmatched(ev) is None
    assert calls == ["post"]
    assert "generated" not in ev.raw_data


def test_salience_gate():
    assert orchestrator._salient(_event()) is True  # novel news
    assert orchestrator._salient(_event(raw_data={"numMentions": 40})) is True
    assert orchestrator._salient(_event(raw_data={"numMentions": 3, "novelty": {"novel": False}})) is False
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
        AnalystResult(event=_event(id=f"e{i}"), matched_rules=[], tickers=[], confidence=0.0,
                      risk_score=5, direction="")
        for i in range(5)
    ]
    matched = AnalystResult(event=_event(id="m"), matched_rules=[], tickers=[analyst.AnalystTicker("USO", "bullish", "r")],
                            confidence=80.0, risk_score=8, direction="rule")
    analyses.insert(0, matched)
    assert orchestrator._generative_pass(analyses, None) == 3
    assert asked == ["e0", "e1", "e2"]  # the matched one was skipped, the cap held
    assert analyses[1].confidence == 80.0 and analyses[3].confidence == 0.0  # e2 stayed unmatched


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
