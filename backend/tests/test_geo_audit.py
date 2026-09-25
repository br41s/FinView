"""The learning loop, closed: accuracy → confidence_mod → notify gate, plus the
live re-rating and the audit job that runs both on its own cadence.

Before this, confidence_mod was a ±0.02/−0.03 step counter that only the +7d
checkpoint touched. A rule at 24% accuracy (prod, 2026-09-20) kept most of its
base confidence; `accuracy` was computed and displayed but read by nothing.
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
from backend.services.geo import auditor, orchestrator
from backend.services.geo.advisor import IMPORTANCE_THRESHOLD, compute_importance
from backend.services.geo.rules import FAST_RULES, effective_confidence


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── learned_confidence_mod ────────────────────────────────────────────

@pytest.mark.parametrize(
    "correct,total,expected",
    [
        (0, 0, 0.0),        # nothing measured → no adjustment
        (1, 1, 0.03),       # one hit, a tenth of the evidence in
        (10, 10, 0.30),     # perfect record at full weight → the cap
        (0, 10, -0.30),     # always wrong at full weight → the floor
        (5, 10, 0.0),       # coin flip earns nothing either way
        (24, 100, -0.156),  # prod's 24%: (0.24 − 0.5) × 0.6
        (100, 100, 0.30),   # the cap holds however long the record
    ],
)
def test_learned_mod_is_accuracy_scaled_by_evidence(correct, total, expected):
    assert auditor.learned_confidence_mod(correct, total) == pytest.approx(expected)


def test_a_bad_record_drops_the_rule_below_the_notify_gate():
    """THE point of the loop: a rule that is usually wrong stops paging.

    eq-chile-copper base 0.82 with the fattest risk the rule can carry pages;
    the same rule at 20% accuracy over 10 outcomes must not.
    """
    rule = next(r for r in FAST_RULES if r.id == "eq-chile-copper")
    good = GeoRuleStat(rule_id=rule.id, category=rule.category, confidence_mod=0.0)
    bad = GeoRuleStat(rule_id=rule.id, category=rule.category, total_signals=10, correct_signals=2)
    auditor._apply_learned_mod(bad)
    assert float(bad.confidence_mod) == pytest.approx(-0.18)

    conf_good = round(effective_confidence(rule, good) * 100)
    conf_bad = round(effective_confidence(rule, bad) * 100)
    risk = 8
    assert compute_importance(conf_good, risk) >= IMPORTANCE_THRESHOLD
    assert compute_importance(conf_bad, risk) < IMPORTANCE_THRESHOLD


def test_recompute_rederives_every_rule_from_its_counters(db):
    """A row still carrying the old step-counter value converges on the next audit."""
    db.add(GeoRuleStat(rule_id="a", category="x", base_confidence=0.7, total_signals=10, correct_signals=9, confidence_mod=0.02))
    db.add(GeoRuleStat(rule_id="b", category="x", base_confidence=0.7, total_signals=0, correct_signals=0, confidence_mod=-0.09))
    db.add(GeoRuleStat(rule_id="c", category="x", base_confidence=0.7, total_signals=4, correct_signals=2, accuracy=0.5, confidence_mod=0.0))
    db.commit()

    changed = auditor.recompute_confidence_mods(db)
    db.commit()

    assert changed == 2  # "c" was already right
    assert float(db.get(GeoRuleStat, "a").confidence_mod) == pytest.approx(0.24)
    assert float(db.get(GeoRuleStat, "b").confidence_mod) == 0.0
    assert db.get(GeoRuleStat, "b").accuracy is None
    assert auditor.recompute_confidence_mods(db) == 0  # idempotent


# ── create_checkpoints / _reanchor ────────────────────────────────────

def _signal(db, *, created_at, symbol="COPX", direction="bullish"):
    signal = GeoSignal(
        user_id=1, event_type="earthquake", display_category="earthquake", source="usgs",
        external_id=f"ev-{created_at.timestamp()}", headline="quake", location="chile",
        lat=-23.0, lng=-70.0, importance=70, confidence=0.8, risk_score=7,
        direction=direction, status=GeoSignalStatus.ACTIVE.value, created_at=created_at,
        matched_rule_ids=json.dumps(["eq-chile-copper"]),
    )
    db.add(signal)
    db.flush()
    signal.tickers.append(GeoSignalTicker(symbol=symbol, direction=direction, price_at_signal=100.0))
    return signal


def test_create_checkpoints_keeps_already_scored_horizons(db):
    """_reanchor deletes the pending checkpoints and recreates from now; a scored
    +1h must survive, not collide with a duplicate (signal_id, horizon)."""
    signal = _signal(db, created_at=datetime.now(timezone.utc) - timedelta(days=2))
    auditor.create_checkpoints(db, signal)
    db.commit()
    scored = next(c for c in signal.checkpoints if getattr(c.horizon, "value", c.horizon) == "1h")
    scored.outcome = "CORRECT"
    scored.score = 100
    scored.evaluated_at = datetime.now(timezone.utc)
    for c in list(signal.checkpoints):
        if c.outcome is None:
            db.delete(c)
    signal.checkpoints = [c for c in signal.checkpoints if c.outcome is not None]
    db.flush()

    signal.created_at = datetime.now(timezone.utc)
    auditor.create_checkpoints(db, signal)
    db.commit()  # would raise IntegrityError on a duplicate 1h

    horizons = sorted(getattr(c.horizon, "value", c.horizon) for c in db.query(GeoCheckpoint).all())
    assert horizons == ["1d", "1h", "3d", "6h", "7d"]
    kept = next(c for c in db.query(GeoCheckpoint).all() if getattr(c.horizon, "value", c.horizon) == "1h")
    assert kept.outcome is not None and kept.score == 100


# ── rate_active ───────────────────────────────────────────────────────

def _bars(price, hours=9 * 24):
    start = datetime.now(timezone.utc) - timedelta(days=9)
    return [
        (start + timedelta(hours=i), price * (1 + (0.0001 if i % 2 else -0.0001)))
        for i in range(hours)
    ]


def test_rate_active_scores_every_open_signal_against_the_latest_price(db, monkeypatch):
    _signal(db, created_at=datetime.now(timezone.utc) - timedelta(hours=30), symbol="UP")
    _signal(db, created_at=datetime.now(timezone.utc) - timedelta(hours=2), symbol="DN")
    resolved = _signal(db, created_at=datetime.now(timezone.utc) - timedelta(days=9), symbol="OLD")
    resolved.status = GeoSignalStatus.RESOLVED.value
    db.commit()
    db.expire_all()
    monkeypatch.setattr(
        auditor, "fetch_price_series",
        lambda symbols, budget=None, **kw: {"UP": _bars(110.0), "DN": _bars(90.0), "OLD": _bars(200.0)},
    )

    assert auditor.rate_active(db, user_id=1) == 2

    by_symbol = {s.tickers[0].symbol: s for s in db.query(GeoSignal).all()}
    assert float(by_symbol["UP"].live_score) == 100.0 and by_symbol["UP"].live_outcome == "CORRECT"
    assert float(by_symbol["DN"].live_score) == 0.0 and by_symbol["DN"].live_outcome == "INCORRECT"
    assert by_symbol["UP"].live_rated_at is not None
    assert by_symbol["OLD"].live_rated_at is None, "resolved signals are the record, not re-rated"


def test_rate_active_keeps_the_last_rating_when_there_is_no_price(db, monkeypatch):
    signal = _signal(db, created_at=datetime.now(timezone.utc) - timedelta(hours=3))
    stamp = datetime.now(timezone.utc) - timedelta(hours=4)
    signal.live_score, signal.live_outcome, signal.live_rated_at = 100, "CORRECT", stamp
    db.commit()
    monkeypatch.setattr(auditor, "fetch_price_series", lambda symbols, budget=None, **kw: {})

    assert auditor.rate_active(db, user_id=1) == 0
    db.expire_all()
    fresh = db.query(GeoSignal).one()
    assert fresh.live_outcome == "CORRECT" and fresh.live_rated_at.replace(tzinfo=timezone.utc) == stamp


def test_elapsed_horizon_reads_against_the_noise_of_the_age_reached():
    now = datetime.now(timezone.utc)
    assert auditor._elapsed_horizon(now - timedelta(minutes=20), now) == GeoHorizon.H1.value
    assert auditor._elapsed_horizon(now - timedelta(hours=7), now) == GeoHorizon.H6.value
    assert auditor._elapsed_horizon(now - timedelta(days=4), now) == GeoHorizon.D3.value
    assert auditor._elapsed_horizon(now - timedelta(days=30), now) == GeoHorizon.D7.value


# ── run_audit / run_audits ────────────────────────────────────────────

def test_run_audit_recomputes_then_scores_then_rates(db, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(auditor, "recompute_confidence_mods", lambda db_: calls.append("recompute") or 3)
    monkeypatch.setattr(auditor, "evaluate_pending", lambda db_, uid, b=None, c=None: calls.append("score") or 2)
    monkeypatch.setattr(auditor, "rate_active", lambda db_, uid, b=None, c=None: calls.append("rate") or 5)

    result = auditor.run_audit(db, user_id=1)

    assert calls == ["recompute", "score", "rate"]
    assert (result.checkpoints_evaluated, result.signals_rated, result.rules_recomputed) == (2, 5, 3)


def test_the_cycle_no_longer_audits(db, monkeypatch):
    """Ingestion and learning run on different clocks: the 30-min cycle must not
    touch the auditor, or the 4-hour job would be a second scorer racing it."""
    import inspect
    src = inspect.getsource(orchestrator.run_cycle)
    assert "evaluate_pending" not in src and "rate_active" not in src and "run_audit(" not in src


def test_a_failed_user_audit_is_reported_as_none(monkeypatch):
    monkeypatch.setattr(orchestrator, "seed_rule_stats", lambda db: 0)

    def boom(db, uid, budget=None, series_cache=None):
        raise RuntimeError("yahoo on fire")

    monkeypatch.setattr(orchestrator, "run_audit", boom)
    assert orchestrator.run_audits([7]) == [None]
    assert orchestrator.run_audits([]) == []
