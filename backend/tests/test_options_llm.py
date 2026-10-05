"""The options monitor's three LLM calls: cycle report, per-ticker report, chat.

Regression origin: in the 10 days to 2026-10-05 a third of the cycles that
reached the model (48 of 144) came back 200 with no report. The shared model
reasons before it answers and max_tokens pays for both, so all 1500 tokens went
to reasoning — `finish_reason: "length"`, `content: null`, billed in full. The
three calls now send `reasoning: {"effort": "none"}`.

No OpenRouter key exists outside Cloud Run, so nothing here proves the provider
honours that parameter. These pin what FinView sends, and what it does with a
200 that carries no answer.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.api.options as options_api
from backend.api.schemas import AskIn
from backend.config import settings
from backend.models import Base
from backend.services import llm_envelope, options_agent

# What Cloud Run logged 48 times (this one 2026-10-02 19:33 UTC): the report's
# whole budget spent reasoning, so the 200 carries the reasoning and no answer.
REASONED_AWAY = {
    "choices": [{
        "message": {"role": "assistant", "content": None, "refusal": None,
                    "reasoning": "Let me go through the alerts one by one…",
                    "reasoning_details": []},
        "finish_reason": "length",
    }],
    "usage": {"prompt_tokens": 3686, "completion_tokens": 1500,
              "completion_tokens_details": {"reasoning_tokens": 1499}},
}

REPORT = "## 1. Resumen Ejecutivo\nSesgo mixto.\n\n## 7. Gestión de Riesgo\nVolatilidad alta."
ALERT = {"ticker": "AAPL", "type": "HIGH_PUT_CALL_RATIO", "message": "P/C 2.1", "severity": "HIGH"}
SUMMARY = {"current_price": 190.0, "market_sentiment": "BEARISH 🐻"}


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    # The prompts' macro block reads FRED rows from the app database.
    monkeypatch.setattr(options_agent, "macro_prompt_block", lambda: "No disponible.")


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _text(content: str) -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


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


# ── Cycle report ──────────────────────────────────────────────────────


def test_the_cycle_report_turns_reasoning_off(monkeypatch):
    """This model has no lower effort and no reasoning budget to ask for: off is
    the only bound, and it leaves the 1500 tokens to the report."""
    sent = _answering(monkeypatch, _text(REPORT))
    assert options_agent._run_claude_analysis(["AAPL"], [ALERT], []) == (REPORT, None)
    assert sent[0]["reasoning"] == {"effort": "none"}


def test_a_cycle_report_lost_to_reasoning_is_an_error_not_silence(monkeypatch):
    _answering(monkeypatch, REASONED_AWAY)
    text, error = options_agent._run_claude_analysis(["AAPL"], [ALERT], [])
    assert text is None
    # (None, None) reads to the UI as "AI not configured": the reason has to
    # reach the cycle's `ai_error`, and finish_reason is what explains it.
    assert "length" in error


# ── Per-ticker report (instrument drawer) ─────────────────────────────


def test_the_ticker_report_turns_reasoning_off(monkeypatch):
    sent = _answering(monkeypatch, _text(REPORT))
    out = options_agent._run_ticker_claude_analysis("AAPL", SUMMARY, [ALERT], [])
    assert out == (REPORT, None)
    assert sent[0]["reasoning"] == {"effort": "none"}


def test_a_ticker_report_lost_to_reasoning_is_an_error_not_silence(monkeypatch):
    _answering(monkeypatch, REASONED_AWAY)
    text, error = options_agent._run_ticker_claude_analysis("AAPL", SUMMARY, [ALERT], [])
    assert text is None
    assert "length" in error


# ── Chat (/options/ask) ───────────────────────────────────────────────


def test_the_chat_turns_reasoning_off(monkeypatch, db):
    sent = _answering(monkeypatch, _text("El ratio put/call de AAPL es 2,1."))
    out = options_api.ask_agent(AskIn(question="¿Cómo está AAPL?"), db, SimpleNamespace(id=1))
    assert out.answer == "El ratio put/call de AAPL es 2,1."
    assert sent[0]["reasoning"] == {"effort": "none"}


def test_a_chat_answer_lost_to_reasoning_is_a_502_not_an_empty_answer(monkeypatch, db):
    _answering(monkeypatch, REASONED_AWAY)
    with pytest.raises(HTTPException) as exc:
        options_api.ask_agent(AskIn(question="¿Cómo está AAPL?"), db, SimpleNamespace(id=1))
    assert exc.value.status_code == 502
    assert exc.value.detail == "El asistente no ha podido responder. Inténtalo de nuevo."
