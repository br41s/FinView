"""Tests for technical signal emission: what gets stored, what alerts, what doesn't."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, BacktestSignal, TechnicalSignal, User
from backend.services import technical_signals
from backend.services.technical_signals import emit_for_analysis


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(User(id=1, email="u@x.com", password_hash="x"))
    session.commit()
    yield session
    session.close()


def analysis(price=100.0, zones=None, ticker="AAPL"):
    return {
        "ticker": ticker,
        "current_price": price,
        "zones": zones if zones is not None else [{"level": 101.0, "zone_type": "resistance", "strength": 0.9, "touches": 5}],
        "rsi": 61.2,
        "macd_signal": "bullish",
        "macd_histogram": 0.4,
        "trend_bias_bullish_pct": 62.0,
    }


def _score(prob, rationale="porque sí"):
    return {"break_probability": prob, "rationale": rationale}


def test_no_nearby_zone_emits_nothing_and_never_calls_the_llm():
    """The gate is what bounds token spend — a far zone must not reach the scorer."""
    with patch.object(technical_signals, "score_break_probability") as scorer:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        out = emit_for_analysis(
            session, user_id=1, analysis=analysis(zones=[{"level": 130.0, "zone_type": "resistance"}])
        )
    assert out == []
    scorer.assert_not_called()


def test_high_score_stores_the_signal_and_marks_it_alerted(db):
    with patch.object(technical_signals, "score_break_probability", return_value=_score(85)):
        out = emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    assert len(out) == 1
    row = db.query(TechnicalSignal).one()
    assert row.break_probability == 85
    assert row.alerted is True
    assert row.direction == "BULLISH"


def test_low_score_is_still_stored_but_does_not_alert(db):
    """Sub-threshold rows are the whole point: without them the 70 cut can never
    be checked against outcomes."""
    with patch.object(technical_signals, "score_break_probability", return_value=_score(35)):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    row = db.query(TechnicalSignal).one()
    assert row.break_probability == 35
    assert row.alerted is False
    # …and it gets an outcome row too, or the cut could never be calibrated.
    bt = db.query(BacktestSignal).one()
    assert (bt.break_probability, bt.alerted, bt.alert_threshold) == (35, False, 70)


def test_the_gate_is_the_calibrated_threshold_not_the_constant(db):
    """With enough evidence the emitter alerts at the calibrated floor."""
    with patch.object(technical_signals, "alert_threshold_for", return_value=60), \
         patch.object(technical_signals, "score_break_probability", return_value=_score(65)):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    assert db.query(TechnicalSignal).one().alerted is True
    assert db.query(BacktestSignal).one().alert_threshold == 60


def test_threshold_is_exclusive_at_70(db):
    with patch.object(technical_signals, "score_break_probability", return_value=_score(70)):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    assert db.query(TechnicalSignal).one().alerted is False


def test_71_alerts(db):
    with patch.object(technical_signals, "score_break_probability", return_value=_score(71)):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    assert db.query(TechnicalSignal).one().alerted is True


def test_unscored_candidate_is_stored_with_null_probability_and_no_alert(db):
    """No LLM (no key / HTTP failure) must not read as 'certainly won't break'.
    Storing 0 would poison any later calibration."""
    with patch.object(technical_signals, "score_break_probability", return_value=None):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
    row = db.query(TechnicalSignal).one()
    assert row.break_probability is None
    assert row.alerted is False
    assert db.query(BacktestSignal).count() == 0


def test_alerting_signal_records_a_backtest_signal_with_the_exact_direction(db):
    """Direction comes from which side of the level price sits on — not from
    keyword-matching a message, which has no ZONE_BREAK case."""
    with patch.object(technical_signals, "score_break_probability", return_value=_score(90)):
        emit_for_analysis(
            db,
            user_id=1,
            analysis=analysis(zones=[{"level": 99.0, "zone_type": "support", "strength": 0.7, "touches": 3}]),
            regime="risk_off",
        )
        db.commit()
    bt = db.query(BacktestSignal).one()
    assert bt.signal_type == "ZONE_BREAK"
    assert bt.direction == "BEARISH"
    assert bt.regime == "risk_off"
    # risk_off + BEARISH is an aligned signal (Phase 2b semantics).
    assert bt.regime_alignment == "aligned"


def test_a_second_cycle_the_same_day_does_not_duplicate_the_row(db):
    """Proximity lasts days. Without dedup, a week near one level is a week of
    duplicate rows."""
    with patch.object(technical_signals, "score_break_probability", return_value=_score(80)) as scorer:
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
        emit_for_analysis(db, user_id=1, analysis=analysis())
        db.commit()
        assert scorer.call_count == 1
    assert db.query(TechnicalSignal).count() == 1


def test_two_users_near_the_same_zone_each_get_their_own_row(db):
    db.add(User(id=2, email="u2@x.com", password_hash="x"))
    db.commit()
    with patch.object(technical_signals, "score_break_probability", return_value=_score(80)):
        emit_for_analysis(db, user_id=1, analysis=analysis())
        emit_for_analysis(db, user_id=2, analysis=analysis())
        db.commit()
    assert db.query(TechnicalSignal).count() == 2


def test_several_nearby_zones_each_emit(db):
    with patch.object(technical_signals, "score_break_probability", return_value=_score(50)):
        out = emit_for_analysis(
            db,
            user_id=1,
            analysis=analysis(
                zones=[
                    {"level": 100.5, "zone_type": "resistance", "strength": 0.9, "touches": 4},
                    {"level": 99.2, "zone_type": "support", "strength": 0.6, "touches": 7},
                ]
            ),
        )
        db.commit()
    assert len(out) == 2
    assert {r.direction for r in db.query(TechnicalSignal).all()} == {"BULLISH", "BEARISH"}


def test_a_scorer_blowup_does_not_take_down_the_cycle(db):
    """The zones are the product; signalling is a bonus on top. A scorer raising
    must not lose the analysis."""
    with patch.object(technical_signals, "score_break_probability", side_effect=RuntimeError("boom")):
        out = emit_for_analysis(db, user_id=1, analysis=analysis())
    assert out == []


def test_malformed_analysis_returns_empty_instead_of_raising(db):
    assert emit_for_analysis(db, user_id=1, analysis={}) == []
    assert emit_for_analysis(db, user_id=1, analysis={"ticker": "X"}) == []
