"""Tests for Phase 2b — macro-regime alignment on backtest signals."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, BacktestOutcome, BacktestSignal
from backend.services.backtest_service import (
    _DEDUP_WINDOW_HOURS,
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
    base = {
        "user_id": 1, "ticker": "AAPL", "signal_type": "HIGH_IV", "direction": "BULLISH",
        "price_at_signal": 100,
    }
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


# ── evaluate_pending window fix ────────────────────────────────────────────

import backend.services.backtest_service as backtest_service  # noqa: E402
from backend.services.backtest_service import evaluate_pending  # noqa: E402


def _fake_yf(close: float):
    """Minimal yfinance stand-in: a wide daily Close history at a fixed price."""
    import pandas as pd
    from datetime import date, timedelta

    end = date.today()
    idx = pd.date_range(start=end - timedelta(days=60), end=end, freq="D")
    df = pd.DataFrame({"Close": [close] * len(idx)}, index=idx)

    class _Ticker:
        def __init__(self, *_a, **_k):
            pass

        def history(self, **_k):
            return df

    class _Module:
        Ticker = _Ticker

    return _Module


def _pending_signal(days_old: int):
    from datetime import datetime, timedelta, timezone
    return BacktestSignal(
        user_id=1, ticker="AAPL", signal_type="ZONE_BREAK", direction="BULLISH",
        price_at_signal=100, recorded_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )


def test_evaluate_pending_fills_matured_signal_beyond_old_window(db, monkeypatch):
    # 20 days old: the old fixed "10d" fetch could never reach its T+7 price.
    sig = _pending_signal(days_old=20)
    db.add(sig)
    db.commit()
    monkeypatch.setattr(backtest_service, "yf", _fake_yf(close=105.0))  # +5% → CORRECT

    updated = evaluate_pending(db, user_id=1)
    db.refresh(sig)
    assert updated == 1
    assert sig.outcome_1d is not None
    # Post-refresh the column returns the enum member; +5% on a BULLISH signal → CORRECT.
    assert sig.outcome_7d == BacktestOutcome.CORRECT  # 7d now actually fills


def test_evaluate_pending_same_prices_report_nothing_updated(db, monkeypatch):
    # 4 days old → 1d/3d fill, 7d not reached yet, so the row stays in the pending
    # scan. A second run over the same prices must report 0, not one "update" per
    # signal scanned (prod logged pending=353 updated=353 every cycle).
    sig = _pending_signal(days_old=4)
    db.add(sig)
    db.commit()
    monkeypatch.setattr(backtest_service, "yf", _fake_yf(close=105.0))

    assert evaluate_pending(db, user_id=1) == 1
    db.refresh(sig)
    first = (sig.price_at_1d, sig.outcome_1d, sig.price_at_3d, sig.outcome_3d,
             sig.price_at_7d, sig.outcome_7d)
    assert first[0] == 105.0

    assert evaluate_pending(db, user_id=1) == 0
    db.refresh(sig)
    after = (sig.price_at_1d, sig.outcome_1d, sig.price_at_3d, sig.outcome_3d,
             sig.price_at_7d, sig.outcome_7d)
    assert after == first


def test_evaluate_pending_changed_price_overwrites_stored_values(db, monkeypatch):
    sig = _pending_signal(days_old=20)
    db.add(sig)
    db.commit()
    monkeypatch.setattr(backtest_service, "yf", _fake_yf(close=105.0))  # BULLISH +5%
    assert evaluate_pending(db, user_id=1) == 1
    db.refresh(sig)
    assert sig.price_at_7d == 105.0
    assert sig.outcome_7d == BacktestOutcome.CORRECT

    # The pending scan only selects rows whose 7d outcome is still NULL; clear it
    # to model a row a later run re-evaluates, keeping the stored 105 price.
    sig.outcome_7d = None
    db.commit()
    monkeypatch.setattr(backtest_service, "yf", _fake_yf(close=95.0))  # BULLISH −5%

    assert evaluate_pending(db, user_id=1) == 1
    db.refresh(sig)
    assert sig.price_at_7d == 95.0
    assert sig.outcome_7d == BacktestOutcome.INCORRECT


def test_evaluate_pending_skips_signals_past_max_age(db, monkeypatch):
    # Older than _MAX_EVAL_AGE_DAYS → terminally unevaluable, left out of the scan.
    sig = _pending_signal(days_old=backtest_service._MAX_EVAL_AGE_DAYS + 5)
    db.add(sig)
    db.commit()
    monkeypatch.setattr(backtest_service, "yf", _fake_yf(close=105.0))

    evaluate_pending(db, user_id=1)
    db.refresh(sig)
    assert sig.outcome_7d is None


# ── options-path cross-cycle dedup ─────────────────────────────────────────


def test_record_signal_dedups_same_condition_within_window(db):
    s1 = record_signal(db, user_id=1, ticker="AAPL", alert_type="HIGH_IV_CALLS",
                       message="calls hot", current_price=100)
    db.commit()
    s2 = record_signal(db, user_id=1, ticker="AAPL", alert_type="HIGH_IV_CALLS",
                       message="calls hot", current_price=101)
    assert s1 is not None
    assert s2 is None                                   # same open condition → skipped
    assert db.query(BacktestSignal).count() == 1


def test_record_signal_distinct_type_not_deduped(db):
    record_signal(db, user_id=1, ticker="AAPL", alert_type="HIGH_IV_CALLS",   # BULLISH
                  message="c", current_price=100)
    record_signal(db, user_id=1, ticker="AAPL", alert_type="HIGH_PUT_CALL_RATIO",  # BEARISH
                  message="p", current_price=100)
    db.commit()
    assert db.query(BacktestSignal).count() == 2        # different type/direction → distinct


def test_record_signal_allowed_after_window(db):
    from datetime import datetime, timedelta, timezone
    db.add(BacktestSignal(
        user_id=1, ticker="AAPL", signal_type="HIGH_IV_CALLS", direction="BULLISH",
        price_at_signal=100,
        recorded_at=datetime.now(timezone.utc) - timedelta(hours=_DEDUP_WINDOW_HOURS + 1),
    ))
    db.commit()
    s = record_signal(db, user_id=1, ticker="AAPL", alert_type="HIGH_IV_CALLS",
                      message="c", current_price=100)
    db.commit()
    assert s is not None                                # prior record is outside the window
    assert db.query(BacktestSignal).count() == 2


# ── calibration digest ─────────────────────────────────────────────────────

from backend.services.backtest_service import get_calibration  # noqa: E402


def _win_signal(days_old: int, **kw):
    from datetime import datetime, timedelta, timezone
    base = {"user_id": 1, "ticker": "AAA", "signal_type": "IV_SKEW", "direction": "BEARISH",
            "price_at_signal": 100}
    base.update(kw)
    return BacktestSignal(recorded_at=datetime.now(timezone.utc) - timedelta(days=days_old), **base)


def test_get_calibration_windows_and_alignment(db):
    db.add_all([
        _win_signal(2, ticker="AAA", regime_alignment="aligned", outcome_7d=BacktestOutcome.CORRECT.value),
        _win_signal(2, ticker="BBB", regime_alignment="aligned", outcome_7d=BacktestOutcome.INCORRECT.value),
        _win_signal(2, ticker="CCC", regime_alignment="counter", outcome_7d=BacktestOutcome.INCORRECT.value),
        _win_signal(40, ticker="DDD", regime_alignment="aligned", outcome_7d=BacktestOutcome.CORRECT.value),  # out of window
    ])
    db.commit()
    cal = get_calibration(db, user_id=1, days=30)
    assert cal["total"] == 3  # 40-day-old excluded
    assert cal["by_type_alignment"]["IV_SKEW"]["aligned"] == {"correct": 1, "total": 2, "accuracy_pct": 50.0}
    assert cal["by_type_alignment"]["IV_SKEW"]["counter"]["accuracy_pct"] == 0.0


def test_get_calibration_dedup_health(db):
    # 4 rows, same ticker + same day → 4.0 rows/ticker-day (unhealthy).
    for _ in range(4):
        db.add(_win_signal(1, ticker="AAA"))
    db.commit()
    assert get_calibration(db, user_id=1, days=30)["dedup_health"]["IV_SKEW"]["rows_per_ticker_day"] == 4.0
