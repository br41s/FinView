"""Tests for the zone-break LLM scorer.

Regression origin: the first prod cycle emitted 13 signals, all unscored. A 200
came back with `content: null` and `json.loads(None)` raised inside the scorer —
once per ticker, every cycle. It failed safe (break_probability stayed NULL, so
nothing alerted and no fake 0% poisoned the calibration data), but it failed
silently apart from a warning nobody was reading.

Every "the model answered weirdly" branch is covered here, because a 200 from an
LLM guarantees nothing about the body.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.config import settings
from backend.services import zone_scorer
from backend.services.zone_scorer import ALERT_THRESHOLD, score_break_probability


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    zone_scorer._SCORE_CACHE.clear()
    yield
    zone_scorer._SCORE_CACHE.clear()


def candidate(level=101.0):
    return {
        "level": level,
        "zone_type": "resistance",
        "distance_pct": 0.01,
        "approach": "from_below",
        "direction": "BULLISH",
        "strength": 0.9,
        "touches": 5,
    }


def indicators():
    return {
        "current_price": 100.0,
        "rsi": 61.0,
        "macd_signal": "bullish",
        "macd_histogram": 0.4,
        "trend_bias_bullish_pct": 62.0,
    }


def _resp(body: dict, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    return r


def _ok_body(content: str):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


def test_scores_a_well_formed_answer():
    body = _ok_body(json.dumps({"break_probability": 78, "rationale": "zona débil"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        out = score_break_probability("AAPL", candidate(), indicators())
    assert out == {"break_probability": 78, "rationale": "zona débil"}


def test_content_null_returns_no_score_instead_of_raising():
    """THE prod bug: 200 OK, content: null, json.loads(None) → TypeError."""
    body = {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_empty_string_content_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(_ok_body("   "))):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_missing_choices_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", return_value=_resp({"usage": {}})):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_content_that_is_not_json_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(_ok_body("lo siento, no puedo"))):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_json_that_is_not_an_object_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(_ok_body("[78]"))):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_non_numeric_probability_returns_no_score():
    body = _ok_body(json.dumps({"break_probability": "muy alta", "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_probability_out_of_range_is_clamped_not_discarded():
    body = _ok_body(json.dumps({"break_probability": 140, "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators())["break_probability"] == 100
    zone_scorer._SCORE_CACHE.clear()
    body = _ok_body(json.dumps({"break_probability": -20, "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators())["break_probability"] == 0


def test_float_probability_is_rounded():
    body = _ok_body(json.dumps({"break_probability": 72.6, "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators())["break_probability"] == 73


def test_http_error_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", return_value=_resp({}, status=429)):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_network_blowup_returns_no_score():
    with patch.object(zone_scorer.httpx, "post", side_effect=RuntimeError("boom")):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_no_api_key_skips_the_call_entirely(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    with patch.object(zone_scorer.httpx, "post") as post:
        assert score_break_probability("AAPL", candidate(), indicators()) is None
    post.assert_not_called()


def test_a_success_is_cached_so_the_same_zone_costs_one_call():
    """Proximity lasts days; without the cache every cycle re-pays the same call."""
    body = _ok_body(json.dumps({"break_probability": 55, "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)) as post:
        score_break_probability("AAPL", candidate(), indicators())
        score_break_probability("AAPL", candidate(), indicators())
        assert post.call_count == 1


def test_failures_are_not_cached_so_a_transient_error_retries():
    with patch.object(zone_scorer.httpx, "post", side_effect=RuntimeError("boom")) as post:
        score_break_probability("AAPL", candidate(), indicators())
        score_break_probability("AAPL", candidate(), indicators())
        assert post.call_count == 2


def test_max_tokens_leaves_room_for_reasoning_plus_the_answer():
    """The default model reasons before answering, and max_tokens covers both.

    Prod at 200: content null. Prod at 500: content null again, with
    finish_reason='length' and reasoning_tokens=500 — the whole budget went to
    thinking. The answer is an int and a sentence; the budget is sized for what
    happens before it.
    """
    body = _ok_body(json.dumps({"break_probability": 50, "rationale": "x"}))
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)) as post:
        score_break_probability("AAPL", candidate(), indicators())
    assert post.call_args.kwargs["json"]["max_tokens"] >= 1500


def test_reasoning_model_burning_the_budget_returns_no_score():
    """The exact prod response: reasoning ate every token, finish_reason=length,
    content empty. Must be a clean 'no score', never a crash and never a 0."""
    body = {
        "choices": [
            {
                "message": {"content": "", "reasoning": "...", "role": "assistant"},
                "finish_reason": "length",
            }
        ],
        "usage": {"completion_tokens": 501, "completion_tokens_details": {"reasoning_tokens": 500}},
    }
    with patch.object(zone_scorer.httpx, "post", return_value=_resp(body)):
        assert score_break_probability("AAPL", candidate(), indicators()) is None


def test_alert_threshold_stays_uncalibrated_at_70():
    # Guards the documented contract: everything scored is stored, only >70 alerts.
    assert ALERT_THRESHOLD == 70
