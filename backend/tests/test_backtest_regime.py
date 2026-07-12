"""Tests for Phase 2b — macro-regime alignment on backtest signals."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, BacktestOutcome, BacktestSignal
from backend.services.backtest_service import (
    alignment_for,
    alignment_for_alert,
    get_stats,
    record_signal,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── alignment_for ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "direction,regime,expected",
    [
        ("BULLISH", "risk_on", "aligned"),
        ("BEARISH", "risk_on", "counter"),
        ("BEARISH", "risk_off", "aligned"),
        ("BULLISH", "risk_off", "counter"),
        ("BULLISH", "neutral", "neutral"),
        ("BEARISH", "neutral", "neutral"),
        ("BULLISH", None, None),      # no regime → no label
        ("BEARISH", "", None),        # empty regime → no label
    ],
)
def test_alignment_for(direction, regime, expected):
    assert alignment_for(direction, regime) == expected


def test_alignment_for_alert_derives_direction():
    # HIGH_PUT_CALL_RATIO → BEARISH; in risk_off that's aligned.
    assert alignment_for_alert("HIGH_PUT_CALL_RATIO", "puts heavy", "risk_off") == "aligned"
    # Same bearish signal in risk_on is counter.
    assert alignment_for_alert("HIGH_PUT_CALL_RATIO", "puts heavy", "risk_on") == "counter"


# ── record_signal persists regime + alignment ─────────────────────────────


def test_record_signal_persists_regime_and_alignment(db):
    sig = record_signal(
        db,
        user_id=1,
        ticker="AAPL",
        alert_type="HIGH_IV_CALLS",  # BULLISH
        message="calls hot",
        current_price=100.0,
        regime="risk_on",
    )
    db.commit()
    assert sig.regime == "risk_on"
    assert sig.direction == "BULLISH"
    assert sig.regime_alignment == "aligned"


def test_record_signal_no_regime_leaves_nulls(db):
    sig = record_signal(
        db, user_id=1, ticker="AAPL", alert_type="IV_SKEW", message="skew",
        current_price=100.0,
    )
    db.commit()
    assert sig.regime is None
    assert sig.regime_alignment is None


# ── get_stats by_alignment ────────────────────────────────────────────────


def _signal(**kw):
    base = dict(
        user_id=1, ticker="AAPL", signal_type="HIGH_IV", direction="BULLISH",
        price_at_signal=100,
    )
    base.update(kw)
    return BacktestSignal(**base)


def test_get_stats_by_alignment(db):
    # 2 aligned (1 correct, 1 incorrect) → 50%; 1 counter (incorrect) → 0%.
    db.add_all([
        _signal(regime_alignment="aligned", outcome_7d=BacktestOutcome.CORRECT.value),
        _signal(regime_alignment="aligned", outcome_7d=BacktestOutcome.INCORRECT.value),
        _signal(regime_alignment="counter", outcome_7d=BacktestOutcome.INCORRECT.value),
        # A None-alignment row must be excluded from by_alignment entirely.
        _signal(regime_alignment=None, outcome_7d=BacktestOutcome.CORRECT.value),
    ])
    db.commit()

    stats = get_stats(db, user_id=1)
    ba = stats["by_alignment"]
    assert ba["aligned"] == {"correct": 1, "total": 2, "accuracy_pct": 50.0}
    assert ba["counter"] == {"correct": 0, "total": 1, "accuracy_pct": 0.0}
    assert None not in ba and "None" not in ba  # unlabeled rows excluded


def test_get_stats_by_alignment_empty_when_no_regime(db):
    db.add(_signal(regime_alignment=None, outcome_7d=BacktestOutcome.CORRECT.value))
    db.commit()
    assert get_stats(db, user_id=1)["by_alignment"] == {}


def test_horizon_accuracy_counts_correct(db):
    # Regression guard: outcomes come back as enum members after a query, so the
    # accuracy comparison must normalize them (previously always yielded 0%).
    db.add_all([
        _signal(outcome_7d=BacktestOutcome.CORRECT.value),
        _signal(outcome_7d=BacktestOutcome.INCORRECT.value),
    ])
    db.commit()
    seven = get_stats(db, user_id=1)["by_horizon"]["7d"]
    assert seven["correct"] == 1
    assert seven["accuracy_pct"] == 50.0
