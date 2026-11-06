"""The generative path: a salient event no rule covers gets one validated LLM thesis."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from backend.models import GeoGenerativeAnswer
from backend.services import llm_envelope
from backend.services.geo import analyst, orchestrator
from backend.services.geo.advisor import _pageable
from backend.services.geo.analyst import (
    AnalystResult,
    MalformedAnswer,
    _validate_generated,
    analyze_unmatched,
)
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
    base = {
        "id": "gdelt-armed_conflict-libya", "type": "armed_conflict", "title": "Coup in Tripoli",
        "latitude": 32.9, "longitude": 13.2, "source": "gdelt",
        "timestamp": int(time.time() * 1000),
        "raw_data": {"numMentions": 40, "novelty": {"novel": True}},
    }
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
    capped = _validate_generated({**GOOD, "confidence": 140, "riskScore": 10})
    assert (capped["confidence"], capped["riskScore"]) == (85, 8)  # the model sets both factors
    # A numeric string is still a number, as it has always been for the rules' risk.
    assert _validate_generated({**GOOD, "confidence": "80.5", "riskScore": "7"})["confidence"] == 80


def test_a_no_is_the_models_own_or_the_gates():
    """None is the outcome worth six hours: the model said no, or it answered
    in full and nothing it named is an instrument this event may reach."""
    assert _validate_generated({**GOOD, "actionable": False}) is None
    assert _validate_generated({"actionable": False}) is None
    assert _validate_generated({**GOOD, "tickers": [{"symbol": "NVDA", "direction": "bullish"}]}) is None
    # The gates decide before the rest is read: a complete version of this
    # answer would be the same "no".
    vetoed = {"actionable": True, "tickers": [{"symbol": "NVDA", "direction": "bearish"}]}
    assert _validate_generated(vetoed) is None


_NO_THESIS = {k: v for k, v in GOOD.items() if k != "thesis"}
_NO_PICKS = {k: v for k, v in GOOD.items() if k != "tickers"}


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("not a dict", "not an object"),
        ({}, "actionable"),
        ({"error": {"message": "upstream timeout"}}, "actionable"),
        ({**GOOD, "actionable": "true"}, "actionable"),
        ({**GOOD, "actionable": None}, "actionable"),
        (_NO_PICKS, "pick"),
        ({**GOOD, "tickers": []}, "pick"),
        ({**GOOD, "tickers": {"symbol": "USO", "direction": "bullish"}}, "pick"),
        ({**GOOD, "tickers": 5}, "pick"),
        ({**GOOD, "tickers": ["USO"]}, "pick"),
        ({**GOOD, "tickers": [{"symbol": ["USO"], "direction": "bullish"}]}, "pick"),
        ({**GOOD, "tickers": [{"symbol": "USO", "direction": "neutral"}]}, "pick"),
        ({**GOOD, "tickers": [{"symbol": "USO"}]}, "pick"),
        ({**GOOD, "confidence": "alto"}, "not a number"),
        ({**GOOD, "confidence": None}, "not a number"),
        ({**GOOD, "confidence": True}, "not a number"),
        ({**GOOD, "riskScore": float("inf")}, "not a number"),
        ({**GOOD, "riskScore": float("nan")}, "not a number"),
        ({**GOOD, "riskScore": {}}, "not a number"),
        (_NO_THESIS, "thesis"),
        ({**GOOD, "thesis": ""}, "thesis"),
        ({**GOOD, "thesis": ["Ports close", "Brent tightens"]}, "thesis"),
        ({**GOOD, "thesis": {"effect": "", "flow": None, "instrument": 3}}, "thesis"),
    ],
)
def test_an_object_that_does_not_answer_is_malformed_not_a_no(body, why):
    with pytest.raises(MalformedAnswer, match=why):
        _validate_generated(body)


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
# What Cloud Run logged 3–8 times a day (this one 2026-10-04): the model spent
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
    # Two attempts, each asking twice (the envelope's one retry): nothing was remembered.
    assert [r["reasoning"] for r in sent] == [llm_envelope.NO_REASONING, llm_envelope.REASONING_DISABLED] * 2


def test_an_answer_cut_mid_json_is_no_thesis_either(monkeypatch):
    """The same cut, a little later (prod, 2026-10-02): reasoning left room for half the JSON."""
    cut = '{"actionable": true, "thesis": {"effect": "Libyan export terminals clo'
    _answering(monkeypatch, {"choices": [{"message": {"content": cut}, "finish_reason": "length"}]})
    ev = _event()
    assert analyze_unmatched(ev) is None
    assert "generated" not in ev.raw_data
    assert analyst.has_fresh_generative(ev.id) is False


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == analyst.logger.name and r.levelno == logging.WARNING]


def test_an_answer_that_is_not_json_is_logged_with_what_it_was(monkeypatch, caplog):
    """Prod, 2026-09-27 and 2026-10-05: `Expecting value: line 1 column 1 (char 0)`
    under a traceback. The content had passed the non-empty check and nothing
    recorded it. This text is a stand-in — the real one has never been seen."""
    answer = "Here is the analysis:\n" + json.dumps(GOOD)
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": answer}}]})
    ev = _event()
    with caplog.at_level(logging.WARNING):
        assert analyze_unmatched(ev) is None
    [line] = _warnings(caplog)
    assert line.startswith(f"geo generative LLM: content is not JSON for {ev.id} ")
    # Where the parser stopped, beside how long the answer was: char 0 of 300 is
    # a wrapped answer, a position near the length is a cut one.
    assert "char 0" in line and f"{len(answer)} chars" in line
    # A repr, and a short one: the newline is escaped, so text the model echoed
    # from a headline cannot start a log line of its own, and the tail is left out.
    assert "'Here is the analysis:\\n{" in line and "\n" not in line
    assert repr(answer[:200]) in line and answer[200:] not in line
    # Nothing is repaired on a guess: the object after the prose is not used.
    assert "generated" not in ev.raw_data
    # And an answer nobody could read is not a "no" for six hours.
    assert analyst.has_fresh_generative(ev.id) is False
    assert analyze_unmatched(ev) is None and len(sent) == 2


@pytest.mark.parametrize(
    "answer",
    ["[]", f"[{json.dumps(GOOD)}]", '"not actionable"', "null", "42"],
    ids=["empty array", "thesis inside an array", "string", "null", "number"],
)
def test_json_that_is_not_an_object_is_no_thesis_and_not_a_cached_no(monkeypatch, caplog, answer):
    """It used to reach the validator, fail there without a word and be
    remembered for six hours as "not actionable"."""
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": answer}}]})
    ev = _event()
    with caplog.at_level(logging.WARNING):
        assert analyze_unmatched(ev) is None
    [line] = _warnings(caplog)
    assert line.startswith(f"geo generative LLM: JSON is not an object for {ev.id} ")
    assert repr(answer[:200]) in line
    assert "generated" not in ev.raw_data
    assert analyst.has_fresh_generative(ev.id) is False
    assert analyze_unmatched(ev) is None and len(sent) == 2


def test_an_answer_nobody_could_read_stores_nothing(db, monkeypatch):
    _answering(monkeypatch, {"choices": [{"message": {"content": "[]"}}]})
    started = datetime.now(timezone.utc)
    assert analyze_unmatched(_event()) is None
    assert orchestrator._persist_generative_cache(db, started) == 0
    assert db.query(GeoGenerativeAnswer).count() == 0


# ── A JSON object that is still not an answer ─────────────────────────
# Everything below parsed, was an object, and used to be remembered for six
# hours as "not actionable" — in the cache and in geo_generative_answers —
# without a line in the log. None of these shapes has been seen in prod: nothing
# recorded them. They are the ways the format can be missed, not a transcript.
MALFORMED = {
    "empty object": ("{}", "actionable is neither true nor false"),
    "error object": ('{"error": {"message": "upstream timeout", "code": 504}}',
                     "actionable is neither true nor false"),
    "yes as a string": (json.dumps({**GOOD, "actionable": "yes"}),
                        "actionable is neither true nor false"),
    "yes with no pick": (json.dumps({**GOOD, "tickers": []}),
                         "actionable with no well-formed pick"),
    "yes with a direction outside the format": (
        json.dumps({**GOOD, "tickers": [{"symbol": "USO", "direction": "neutral"}]}),
        "actionable with no well-formed pick"),
    "confidence in words": (json.dumps({**GOOD, "confidence": "alto"}),
                            "confidence or riskScore is not a number"),
    "risk beyond a float": (json.dumps(GOOD).replace('"riskScore": 7', '"riskScore": 1e999'),
                            "confidence or riskScore is not a number"),
    "no thesis": (json.dumps(_NO_THESIS), "no thesis"),
}


@pytest.mark.parametrize(("answer", "why"), MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_answer_is_logged_and_is_not_a_cached_no(db, monkeypatch, caplog, answer, why):
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": answer}}]})
    started = datetime.now(timezone.utc)
    ev = _event()
    with caplog.at_level(logging.WARNING):
        assert analyze_unmatched(ev) is None
    # One line, in the family of the two above it: which event, why, how long
    # the answer was, and its beginning as a repr.
    [line] = _warnings(caplog)
    assert line.startswith(f"geo generative LLM: answer is not usable for {ev.id} ({why}; ")
    assert f"{len(answer)} chars" in line and repr(answer[:200]) in line
    assert "generated" not in ev.raw_data
    # Not a "no": nothing in the cache, nothing in the table, asked again.
    assert analyst.has_fresh_generative(ev.id) is False
    assert orchestrator._persist_generative_cache(db, started) == 0
    assert db.query(GeoGenerativeAnswer).count() == 0
    assert analyze_unmatched(ev) is None and len(sent) == 2


VETOED = {
    "outside the universe": [{"symbol": "NVDA", "direction": "bullish"}],
    "another country's market": [{"symbol": "EWZ", "direction": "bearish"}],
    "wider than the event": [{"symbol": "GLD", "direction": "bullish"}],  # global, event local
}


@pytest.mark.parametrize("picks", VETOED.values(), ids=VETOED.keys())
def test_a_complete_answer_the_gates_reject_is_a_no_worth_remembering(db, monkeypatch, caplog, picks):
    """The model answered the question and named instruments this event may not
    reach. Asked again in an hour it is the same event against the same gates."""
    answer = json.dumps({**GOOD, "tickers": picks})
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": answer}}]})
    started = datetime.now(timezone.utc)
    ev = _event()
    with caplog.at_level(logging.INFO):
        assert analyze_unmatched(ev) is None
        assert analyze_unmatched(ev) is None
    assert len(sent) == 1 and analyst.has_fresh_generative(ev.id) is True
    assert "generated" not in ev.raw_data
    assert orchestrator._persist_generative_cache(db, started) == 1
    assert json.loads(db.query(GeoGenerativeAnswer).one().proposal_json) == {}
    # Not a warning, but not silent either: the call is accounted for once.
    assert _warnings(caplog) == []
    said = [r.getMessage() for r in caplog.records if r.name == analyst.logger.name]
    assert said.count(f"geo generative: {ev.id} → not actionable") == 1


def test_one_pick_that_survives_is_a_thesis_whatever_came_with_it(monkeypatch):
    mixed = {**GOOD, "tickers": [
        {"symbol": "NVDA", "direction": "bullish"},
        {"symbol": "USO", "direction": " Bullish "},
        {"symbol": "XLE", "direction": "neutral"},
        "junk",
    ]}
    _answering(monkeypatch, {"choices": [{"message": {"content": json.dumps(mixed)}}]})
    res = analyze_unmatched(_event())
    assert [(t.symbol, t.direction) for t in res.tickers] == [("USO", "bullish")]


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


# ── The answers outlive the instance ──────────────────────────────────
NOT_ACTIONABLE = {"choices": [{"message": {"content": '{"actionable": false}'}}]}


def _cold_start(monkeypatch) -> None:
    """Cloud Run reclaimed the instance: the next cycle starts in an empty process."""
    monkeypatch.setattr(analyst, "_GENERATIVE_CACHE", {})


def _cycle(db, monkeypatch, events: list[dict]) -> None:
    """One cron request through the real prepare_cycle, with the feeds stubbed."""
    async def no_sources():
        return None

    monkeypatch.setattr(orchestrator, "fetch_all_sources", no_sources)
    monkeypatch.setattr(orchestrator, "_collect_events", lambda bundle: [_event(**kw) for kw in events])
    monkeypatch.setattr(orchestrator, "_macro_regime", lambda: None)
    orchestrator.prepare_cycle(db)


def _asked(sent: list[dict]) -> list[str]:
    """The event title each request was about, in the order they were sent."""
    prompts = (s["messages"][0]["content"] for s in sent)
    return [next(ln[9:] for ln in p.splitlines() if ln.startswith("- Title: ")) for p in prompts]


def test_a_new_instance_remembers_the_answers_and_the_cap_moves_on(db, monkeypatch):
    """Through prepare_cycle, on purpose. Nearly every hourly cycle starts on a
    new instance, so the in-memory cache was empty: the first three salient
    events were asked again every hour and the ones behind the cap never were."""
    sent = _answering(monkeypatch, NOT_ACTIONABLE)
    events = [{"id": f"e{i}", "title": f"Coup {i}", "region": "libya"} for i in range(5)]

    _cycle(db, monkeypatch, events)
    assert _asked(sent) == ["Coup 0", "Coup 1", "Coup 2"]

    _cold_start(monkeypatch)
    _cycle(db, monkeypatch, events)
    assert _asked(sent)[3:] == ["Coup 3", "Coup 4"]  # not the first three again

    _cold_start(monkeypatch)
    _cycle(db, monkeypatch, events)
    assert len(sent) == 5  # every answer is on record: nothing left to ask


def test_a_thesis_comes_back_whole_after_a_cold_start(db, monkeypatch):
    sent = _answering(monkeypatch, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    started = datetime.now(timezone.utc)
    first = analyze_unmatched(_event())
    assert orchestrator._persist_generative_cache(db, started) == 1

    _cold_start(monkeypatch)
    assert orchestrator._hydrate_generative_cache(db) == 1
    again = analyze_unmatched(_event())
    assert len(sent) == 1  # the second analysis cost nothing
    assert [(t.symbol, t.direction) for t in again.tickers] == [("USO", "bullish")]
    assert (again.confidence, again.risk_score, again.direction, again.llm_narrative) == (
        first.confidence, first.risk_score, first.direction, first.llm_narrative,
    )
    # A restored answer is older than this request: it is not written twice.
    assert orchestrator._persist_generative_cache(db, datetime.now(timezone.utc)) == 0


def test_six_hours_later_the_answer_is_forgotten_and_the_event_asked_again(db, monkeypatch):
    now = datetime.now(timezone.utc)
    stale = _event()
    db.add(GeoGenerativeAnswer(event_id=stale.id, asked_at=now - timedelta(hours=7), proposal_json="{}"))
    db.add(GeoGenerativeAnswer(event_id="recent", asked_at=now - timedelta(hours=1), proposal_json="{}"))
    db.commit()

    assert orchestrator._hydrate_generative_cache(db) == 1
    assert analyst.has_fresh_generative("recent") and not analyst.has_fresh_generative(stale.id)

    sent = _answering(monkeypatch, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    assert analyze_unmatched(stale) is not None and len(sent) == 1
    assert orchestrator._persist_generative_cache(db, now) == 1
    # One row per event: the seven-hour-old "no" is gone, the new thesis is in its place.
    rows = {r.event_id: json.loads(r.proposal_json) for r in db.query(GeoGenerativeAnswer).all()}
    assert set(rows) == {stale.id, "recent"}
    assert rows[stale.id]["tickers"][0]["symbol"] == "USO" and rows["recent"] == {}


def test_a_call_with_no_answer_stores_nothing(db, monkeypatch):
    """A failure is not an answer: stored, it would be a "no" for six hours."""
    _answering(monkeypatch, REASONED_AWAY)
    started = datetime.now(timezone.utc)
    assert analyze_unmatched(_event()) is None
    assert orchestrator._persist_generative_cache(db, started) == 0
    assert db.query(GeoGenerativeAnswer).count() == 0


def test_a_row_that_cannot_be_read_is_not_a_no(db):
    now = datetime.now(timezone.utc)
    for i, body in enumerate(("not json", "[]", "null")):
        db.add(GeoGenerativeAnswer(event_id=f"bad{i}", asked_at=now, proposal_json=body))
    db.commit()
    assert orchestrator._hydrate_generative_cache(db) == 0
    assert not any(analyst.has_fresh_generative(f"bad{i}") for i in range(3))


def test_answers_that_cannot_be_stored_do_not_fail_the_cycle(db, monkeypatch):
    """The merge can fail before the commit does (a manual run and the cron
    writing the same event id). The price is a repeated call, not the cycle."""
    from sqlalchemy.exc import OperationalError

    def refuse(*a, **k):
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    started = datetime.now(timezone.utc)
    analyst._GENERATIVE_CACHE["e0"] = (time.time(), {})
    monkeypatch.setattr(db, "merge", refuse)
    assert orchestrator._persist_generative_cache(db, started) == 0


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
