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


def _band(db, prob, correct, incorrect, neutral=0):
    for _ in range(correct):
        db.add(_row(prob, C))
    for _ in range(incorrect):
        db.add(_row(prob, INC))
    for _ in range(neutral):
        db.add(_row(prob, N))


def test_default_gate_while_the_evidence_is_thin(db):
    _band(db, 65, 10, 0)  # 100% but only 10 measured
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["suggested_threshold"] is None and cal["calibrated"] is False
    assert cal["effective_threshold"] == 70
    assert cal["by_bucket"]["60-69"] == {"n": 10, "measured": 10, "correct": 10, "accuracy_pct": 100.0}
    assert bs.alert_threshold_for(db, 1) == 70


def test_a_strong_high_tail_cannot_carry_a_weak_band_across_the_bar(db):
    """The auditor's case (PR #289): 200 rows at 85 with 85% hits plus 31 rows at
    50-59 with 10% hits. Cumulative ≥50 reads 74.9% on 231 measured, but the band
    being added is 10% accurate. The gate must not move to 50 — nor to 60, whose
    band is empty."""
    _band(db, 85, 170, 30)
    _band(db, 55, 3, 28)
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["cumulative_from"]["50"]["accuracy_pct"] == pytest.approx(74.9, abs=0.1)
    assert cal["by_bucket"]["50-59"]["accuracy_pct"] == pytest.approx(9.7, abs=0.1)
    assert cal["suggested_threshold"] is None and cal["effective_threshold"] == 70


def test_the_gate_loosens_one_band_at_a_time_on_that_bands_own_record(db):
    # 60-69 clears the bar on its own (70% of 30); 50-59 does not (20% of 20).
    _band(db, 65, 21, 9)
    _band(db, 55, 4, 16)
    _band(db, 85, 12, 0)
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["by_bucket"]["60-69"]["accuracy_pct"] == 70.0
    assert cal["suggested_threshold"] == 60 and cal["calibrated"] is True
    assert bs.alert_threshold_for(db, 1) == 60


def test_the_gate_reaches_50_only_when_both_lower_bands_clear(db):
    _band(db, 65, 16, 8)   # 66.7%
    _band(db, 55, 13, 9)   # 59.1%
    db.commit()
    assert bs.zone_calibration(db, 1)["suggested_threshold"] == 50


def test_a_thin_band_stops_the_walk_even_if_the_band_below_is_strong(db):
    _band(db, 65, 10, 0)   # too few to judge
    _band(db, 55, 30, 0)   # strong, but unreachable through an unjudged band
    db.commit()
    assert bs.zone_calibration(db, 1)["suggested_threshold"] is None


def test_the_gate_tightens_when_the_band_above_it_is_usually_wrong(db):
    _band(db, 75, 6, 20)   # 70-79 at 23%: alerting on it is the thing to stop
    _band(db, 85, 15, 5)   # 80-89 at 75%
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["suggested_threshold"] == 80
    assert bs.alert_threshold_for(db, 1) == 80


def test_tightening_walks_up_through_every_failing_band(db):
    _band(db, 75, 5, 20)
    _band(db, 85, 5, 20)
    db.commit()
    assert bs.zone_calibration(db, 1)["suggested_threshold"] == 90


def test_neutral_outcomes_are_evaluated_but_not_measured(db):
    _band(db, 65, 15, 0, neutral=10)  # 15 measured < 20: thin, even with 25 rows
    db.commit()
    cal = bs.zone_calibration(db, 1)
    assert cal["by_bucket"]["60-69"] == {"n": 25, "measured": 15, "correct": 15, "accuracy_pct": 100.0}
    assert cal["suggested_threshold"] is None


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


def test_alert_accuracy_views_ignore_the_non_alerting_rows(db):
    """Every scored candidate is recorded, but the alert stats must keep meaning
    "how did the alerts do", not "how did every candidate do"."""
    db.add(_row(85, C))
    db.add(_row(85, INC))
    db.add(_row(40, INC))  # scored, never alerted
    db.add(_row(35, INC))
    legacy = BacktestSignal(user_id=1, ticker="AAPL", signal_type="ZONE_BREAK", direction="BULLISH",
                            price_at_signal=100, alert_message="", outcome_7d=C,
                            recorded_at=datetime.now(timezone.utc) - timedelta(days=3))
    db.add(legacy)  # alerted=NULL: pre-calibration rows were all alerts
    db.commit()

    stats = bs.get_stats(db, 1)
    assert stats["total"] == 3 and stats["evaluated"] == 3
    assert stats["by_signal_type"]["ZONE_BREAK"] == {"correct": 2, "total": 3, "accuracy_pct": 66.7}
    cal = bs.get_calibration(db, 1)
    assert cal["total"] == 3 and cal["dedup_health"]["ZONE_BREAK"]["rows"] == 3


def test_a_calibration_failure_falls_back_to_the_default(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(bs, "zone_calibration", boom)
    assert bs.alert_threshold_for(db, 1) == 70
