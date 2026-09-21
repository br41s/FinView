"""Tests for the macro-regime annotation layer (Phase 2a)."""

from datetime import date

import pytest

from backend.services import fred_rates, macro_context
from backend.services.macro_context import _classify, macro_context as get_macro, macro_prompt_block


@pytest.fixture(autouse=True)
def _fresh_snapshot(monkeypatch):
    """macro_context() caches 15 min in-process; every test starts cold."""
    monkeypatch.setattr(macro_context, "_snapshot", None)


# ── Regime classification ────────────────────────────────────────────────


def test_classify_risk_off():
    # High VIX, inverted curve, elevated stress, wide HY → clearly risk-off.
    assert _classify(vix=32, spread=-0.4, stress=0.8, hy=6.5) == "risk_off"


def test_classify_risk_on():
    # Calm VIX, positive curve, low stress, tight HY → risk-on.
    assert _classify(vix=12, spread=0.6, stress=-0.8, hy=2.5) == "risk_on"


def test_classify_neutral_midrange():
    assert _classify(vix=18, spread=0.2, stress=-0.2, hy=4.0) == "neutral"


def test_classify_missing_indicators_abstain():
    # All missing → score 0 → neutral (never crashes).
    assert _classify(None, None, None, None) == "neutral"


# ── macro_context() ──────────────────────────────────────────────────────


def test_macro_context_none_without_data(monkeypatch):
    monkeypatch.setattr(fred_rates, "latest_value", lambda *a, **k: None)
    assert get_macro() is None


def test_macro_context_builds_snapshot(monkeypatch):
    values = {
        "VIXCLS": 30.0,
        "T10Y2Y": -0.3,
        "STLFSI4": 0.5,
        "BAMLH0A0HYM2": 5.5,
    }
    monkeypatch.setattr(fred_rates, "latest_value", lambda sid, on=None: values.get(sid))
    monkeypatch.setattr(fred_rates, "_max_cached", lambda sid: date(2026, 6, 20))

    ctx = get_macro()
    assert ctx["regime"] == "risk_off"
    assert ctx["vix"] == pytest.approx(30.0)
    assert ctx["yield_spread"] == pytest.approx(-0.3)
    assert ctx["as_of"] == "2026-06-20"
    # Values are plain floats (JSON-serializable), not Decimal.
    assert isinstance(ctx["vix"], float)


# ── Prompt block ─────────────────────────────────────────────────────────


def test_prompt_block_no_data(monkeypatch):
    monkeypatch.setattr(macro_context, "macro_context", lambda: None)
    assert "No disponible" in macro_prompt_block()


def test_prompt_block_renders_regime(monkeypatch):
    monkeypatch.setattr(
        macro_context,
        "macro_context",
        lambda: {
            "regime": "neutral",
            "vix": 18.0,
            "yield_spread": 0.1,
            "financial_stress": -0.1,
            "hy_spread": 3.8,
            "as_of": "2026-06-20",
        },
    )
    block = macro_prompt_block()
    assert "Régimen: neutral" in block
    assert "VIX: 18.00" in block
