"""ZONE_BREAK calibration: the 70 becomes a measured decision.

Only alerting candidates used to get an outcome row, so ">70 vs <70" had no data
on the <70 side and the gate could never move. Now every scored candidate is
recorded with its probability, the curve is readable, and the gate follows the
evidence once there is enough of it.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import BacktestOutcome, BacktestSignal, Base, User
from backend.services import backtest_service as bs


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, email="u@x.com", password_hash="x"))
    session.commit()
    yield session
    session.close()


def _row(prob, outcome, *, days_ago=3, signal_type="ZONE_BREAK", user_id=1):
    return BacktestSignal(
        user_id=user_id, ticker="AAPL", signal_type=signal_type, direction="BULLISH",
        price_at_signal=100, alert_message="", break_probability=prob, alerted=prob > 70,
        alert_threshold=70, outcome_7d=outcome,
        recorded_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


C, INC, N = BacktestOutcome.CORRECT.value, BacktestOutcome.INCORRECT.value, BacktestOutcome.NEUTRAL.value


def test_default_gate_while_the_evidence_is_thin(db):
    for _ in range(10):
        db.add(_row(85, C))
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["suggested_threshold"] is None and cal["calibrated"] is False
    assert cal["effective_threshold"] == 70
    assert cal["by_bucket"]["80-89"] == {"n": 10, "measured": 10, "correct": 10, "accuracy_pct": 100.0}
    assert bs.alert_threshold_for(db, 1) == 70


def test_the_lowest_floor_that_clears_the_bar_becomes_the_gate(db):
    # 60-69 breaks 70% of the time, 50-59 only 20%: the gate should drop to 60, not 50.
    for _ in range(20):
        db.add(_row(65, C))
    for _ in range(10):
        db.add(_row(65, INC))
    for _ in range(4):
        db.add(_row(55, C))
    for _ in range(16):
        db.add(_row(55, INC))
    for _ in range(12):
        db.add(_row(85, C))
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["cumulative_from"]["50"]["accuracy_pct"] == pytest.approx(58.1, abs=0.1)  # 36/62 — clears 55 too
    assert cal["cumulative_from"]["60"]["accuracy_pct"] == pytest.approx(76.2, abs=0.1)  # 32/42
    # ≥50 clears the bar with 62 measured, so the lowest qualifying floor is 50
    assert cal["suggested_threshold"] == 50
    assert bs.alert_threshold_for(db, 1) == 50


def test_a_floor_needs_thirty_measured_outcomes_not_thirty_rows(db):
    for _ in range(25):
        db.add(_row(75, C))
    for _ in range(10):
        db.add(_row(75, N))  # neutral: recorded and evaluated, but not measured
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["cumulative_from"]["70"] == {"n": 35, "measured": 25, "correct": 25, "accuracy_pct": 100.0}
    assert cal["suggested_threshold"] is None  # 25 < 30


def test_when_no_floor_clears_the_bar_the_default_stands(db):
    for _ in range(40):
        db.add(_row(90, INC))
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["cumulative_from"]["90"]["accuracy_pct"] == 0.0
    assert cal["suggested_threshold"] is None and cal["effective_threshold"] == 70


def test_only_this_users_zone_break_rows_count(db):
    db.add(User(id=2, email="v@x.com", password_hash="x"))
    for _ in range(40):
        db.add(_row(80, C, user_id=2))
    for _ in range(40):
        db.add(_row(80, C, signal_type="IV_SPIKE"))
    db.add(BacktestSignal(user_id=1, ticker="AAPL", signal_type="ZONE_BREAK", direction="BULLISH",
                          price_at_signal=100, alert_message="", outcome_7d=C))  # legacy, no probability
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["scored"] == 0 and cal["evaluated"] == 0 and cal["effective_threshold"] == 70


def test_unevaluated_rows_are_scored_but_not_measured(db):
    db.add(_row(80, None, days_ago=0))
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["scored"] == 1 and cal["evaluated"] == 0
    assert cal["by_bucket"]["80-89"]["n"] == 0


def test_a_calibration_failure_falls_back_to_the_default(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(bs, "zone_calibration", boom)
    assert bs.alert_threshold_for(db, 1) == 70
