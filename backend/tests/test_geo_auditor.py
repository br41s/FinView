"""Regression tests for the geo auditor's +7d resolution + rule-learning loop.

The bug (fixed): chk.horizon reads back from the DB as a GeoHorizon *member*
(Enum values_callable, no str mixin), so `chk.horizon == "7d"` was always False
and the +7d checkpoint never resolved the signal — every signal stayed ACTIVE
forever, and _update_rule_stats (same branch) never ran. The test MUST round-trip
the checkpoint through a DB read so horizon is a member; an in-session string
checkpoint would not reproduce the bug.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base,
    GeoCheckpoint,
    GeoHorizon,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
    GeoSignalTicker,
)
from backend.services.geo import auditor


def _status(signal) -> str:
    """signal.status reads back as a GeoSignalStatus member after a DB round-trip
    (same enum boundary as the bug under test) — normalize to its value."""
    return getattr(signal.status, "value", signal.status)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _mature_signal(db, monkeypatch, horizon: str, *, direction="bullish", price_now=110.0):
    """Create an active signal with one already-due checkpoint at `horizon`,
    round-tripped through the DB so checkpoint.horizon is an enum member.
    Stubs price fetch so the basket scores CORRECT (bull thesis, price up)."""
    past = datetime.now(timezone.utc) - timedelta(days=8)
    signal = GeoSignal(
        user_id=1,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id="ev-resolve",
        headline="M6.4 quake near Antofagasta",
        location="chile",
        lat=-23.0,
        lng=-70.0,
        importance=78,
        confidence=0.82,
        risk_score=7.6,
        direction="bearish",
        status=GeoSignalStatus.ACTIVE.value,
        created_at=past,
        matched_rule_ids=json.dumps(["eq-chile-copper"]),
    )
    db.add(signal)
    db.flush()
    signal.tickers.append(
        GeoSignalTicker(symbol="COPX", direction=direction, price_at_signal=100.0)
    )
    db.add(
        GeoCheckpoint(
            user_id=1,
            signal_id=signal.id,
            horizon=horizon,
            target_at=past + auditor._HORIZON_DELAYS[horizon],
        )
    )
    db.commit()
    # Force a fresh read so horizon comes back as GeoHorizon member (reproduces bug).
    db.expire_all()

    monkeypatch.setattr(
        auditor, "fetch_ticker_prices", lambda symbols: {"COPX": price_now}
    )
    return signal.id


def test_checkpoint_horizon_reads_back_as_enum_member(db, monkeypatch):
    """Guards the premise: a DB-read horizon is a GeoHorizon member, not a str,
    so the old `== "7d"` comparison is genuinely False."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value)
    chk = db.query(GeoCheckpoint).one()
    assert chk.horizon is GeoHorizon.D7
    assert chk.horizon != "7d"  # the exact trap the fix works around


def test_final_horizon_resolves_signal_and_updates_rule_stats(db, monkeypatch):
    db.add(
        GeoRuleStat(rule_id="eq-chile-copper", category="earthquake", base_confidence=0.82)
    )
    db.commit()
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D7.value)

    n = auditor.evaluate_pending(db, user_id=1)

    assert n == 1
    signal = db.get(GeoSignal, signal_id)
    assert _status(signal) == GeoSignalStatus.RESOLVED.value

    stat = db.get(GeoRuleStat, "eq-chile-copper")
    assert stat.total_signals == 1
    assert stat.correct_signals == 1  # bull thesis + price up = correct
    assert float(stat.confidence_mod) == pytest.approx(0.02)


def test_basket_scores_correct_on_db_read_direction(db, monkeypatch):
    """_score_basket compares t.direction, which reads back as a GeoDirection member;
    a bullish ticker whose price rose must score CORRECT (guards the same enum trap)."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value, direction="bullish", price_now=110.0)
    auditor.evaluate_pending(db, user_id=1)
    chk = db.query(GeoCheckpoint).one()
    assert float(chk.score) == 100.0  # 1/1 non-neutral tickers moved as predicted


def test_basket_scores_incorrect_when_price_moves_against_thesis(db, monkeypatch):
    """A bullish ticker whose price fell scores INCORRECT — proves direction is
    actually read, not that everything trivially passes."""
    _mature_signal(db, monkeypatch, GeoHorizon.D7.value, direction="bullish", price_now=90.0)
    auditor.evaluate_pending(db, user_id=1)
    chk = db.query(GeoCheckpoint).one()
    assert float(chk.score) == 0.0


def test_non_final_horizon_evaluates_but_leaves_signal_active(db, monkeypatch):
    """A matured +1d checkpoint scores an outcome but must NOT resolve the signal."""
    signal_id = _mature_signal(db, monkeypatch, GeoHorizon.D1.value)

    n = auditor.evaluate_pending(db, user_id=1)

    assert n == 1
    chk = db.query(GeoCheckpoint).one()
    assert chk.outcome is not None
    signal = db.get(GeoSignal, signal_id)
    assert _status(signal) == GeoSignalStatus.ACTIVE.value
