"""Tests for geo-intel API serialization: matched rules and null-safe checkpoints/tickers."""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import _load_rule_stats, _matched_rules, _serialize
from backend.models import Base, GeoCheckpoint, GeoRuleStat, GeoSignal, GeoSignalTicker


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _signal(**overrides) -> GeoSignal:
    defaults = dict(
        user_id=1,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id="ev-1",
        headline="M6.4 quake near Antofagasta",
        location="chile",
        lat=-23.0,
        lng=-70.0,
        importance=78,
        confidence=0.82,
        risk_score=7.6,
        direction="bearish",
        status="active",
    )
    defaults.update(overrides)
    return GeoSignal(**defaults)


# ── _matched_rules ──────────────────────────────────────────────────


def test_matched_rules_empty_when_no_rule_ids(db):
    assert _matched_rules(_signal(matched_rule_ids=None), {}) == []


def test_matched_rules_empty_for_empty_json_array(db):
    assert _matched_rules(_signal(matched_rule_ids="[]"), {}) == []


def test_matched_rules_empty_for_malformed_json(db):
    assert _matched_rules(_signal(matched_rule_ids="not-json"), {}) == []


def test_matched_rules_skips_unknown_rule_ids(db):
    s = _signal(matched_rule_ids=json.dumps(["eq-chile-copper", "does-not-exist"]))
    rules = _matched_rules(s, {})
    assert [r.id for r in rules] == ["eq-chile-copper"]


def test_matched_rules_uses_base_confidence_without_learned_stat(db):
    s = _signal(matched_rule_ids=json.dumps(["eq-chile-copper"]))
    rules = _matched_rules(s, {})
    assert rules[0].confidence == pytest.approx(0.82)  # base_confidence, no GeoRuleStat row yet


def test_matched_rules_uses_effective_confidence_with_learned_stat(db):
    db.add(
        GeoRuleStat(
            rule_id="eq-chile-copper",
            category="earthquake",
            base_confidence=0.82,
            confidence_mod=0.05,
        )
    )
    db.commit()
    s = _signal(matched_rule_ids=json.dumps(["eq-chile-copper"]))
    stats = _load_rule_stats(db, [s])
    rules = _matched_rules(s, stats)
    assert rules[0].confidence == pytest.approx(0.87)


# ── _load_rule_stats ──────────────────────────────────────────────────


def test_load_rule_stats_batches_across_signals(db):
    db.add(GeoRuleStat(rule_id="eq-chile-copper", category="earthquake", base_confidence=0.82))
    db.add(GeoRuleStat(rule_id="cyc-gulf-oil", category="cyclone", base_confidence=0.85))
    db.commit()

    signals = [
        _signal(matched_rule_ids=json.dumps(["eq-chile-copper"])),
        _signal(matched_rule_ids=json.dumps(["cyc-gulf-oil", "unknown-rule"])),
        _signal(matched_rule_ids=None),
    ]
    stats = _load_rule_stats(db, signals)
    assert set(stats) == {"eq-chile-copper", "cyc-gulf-oil"}


def test_load_rule_stats_empty_when_no_signals_have_rules(db):
    assert _load_rule_stats(db, [_signal(matched_rule_ids=None)]) == {}


# ── _serialize: null-field handling ──────────────────────────────────


def test_serialize_handles_null_ticker_price(db):
    s = _signal()
    db.add(s)
    db.flush()
    s.tickers.append(
        GeoSignalTicker(symbol="COPX", direction="bullish", price_at_signal=None, resolved=False)
    )
    db.commit()

    out = _serialize(s, {})
    assert out.tickers[0].priceAtSignal is None


def test_serialize_handles_pending_checkpoint(db):
    s = _signal()
    db.add(s)
    db.flush()
    db.add(
        GeoCheckpoint(
            user_id=1,
            signal_id=s.id,
            horizon="1h",
            target_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    out = _serialize(s, {})
    cp = out.checkpoints[0]
    assert cp.score is None
    assert cp.outcome is None
    assert cp.evaluatedAt is None


def test_serialize_orders_checkpoints_by_target_at(db):
    s = _signal()
    db.add(s)
    db.flush()
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    db.add(GeoCheckpoint(user_id=1, signal_id=s.id, horizon="1d", target_at=now + timedelta(days=1)))
    db.add(GeoCheckpoint(user_id=1, signal_id=s.id, horizon="1h", target_at=now + timedelta(hours=1)))
    db.commit()

    out = _serialize(s, {})
    assert [c.horizon for c in out.checkpoints] == ["1h", "1d"]
