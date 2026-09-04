"""Tests for geo-intel API serialization: matched rules and null-safe checkpoints/tickers."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import (
    _as_utc,
    _balance_ids_by_category,
    _load_rule_stats,
    _matched_rules,
    _serialize,
    _serialize_run,
)
from backend.models import (
    Base,
    GeoCheckpoint,
    GeoCycleRun,
    GeoRuleStat,
    GeoSignal,
    GeoSignalTicker,
)


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


# ── _balance_ids_by_category: category-balanced windowing ─────────────


def _rows(counts: dict[str, int]) -> list[tuple[int, str]]:
    """Build (id, category) rows already ordered by descending priority.

    Categories are interleaved by priority the way the SQL importance sort would
    hand them over, so the round-robin sees a realistic mixed stream rather than
    one category fully ahead of another.
    """
    remaining = dict(counts)
    rows: list[tuple[int, str]] = []
    next_id = 1
    while any(remaining.values()):
        for cat in list(remaining):
            if remaining[cat] > 0:
                rows.append((next_id, cat))
                next_id += 1
                remaining[cat] -= 1
    return rows


def test_balance_empty_input():
    assert _balance_ids_by_category([], 100) == []


def test_balance_returns_at_most_limit():
    rows = _rows({"fire": 464, "conflict": 180})
    assert len(_balance_ids_by_category(rows, 100)) == 100


def test_balance_returns_all_when_under_limit():
    rows = _rows({"fire": 10, "volcano": 5})
    assert len(_balance_ids_by_category(rows, 100)) == 15


def test_balance_surfaces_every_live_category_under_prod_distribution():
    # Measured prod active counts: fires and conflict dominate; volcano, weather
    # and cyclone are live but sparse and fell outside the old recency window.
    rows = _rows(
        {"fire": 464, "conflict": 180, "volcano": 30, "weather": 18, "cyclone": 15}
    )
    chosen = set(_balance_ids_by_category(rows, 100))
    by_cat: dict[str, int] = {}
    for sig_id, cat in rows:
        if sig_id in chosen:
            by_cat[cat] = by_cat.get(cat, 0) + 1
    # The sparse categories that used to vanish now all appear.
    for cat in ("volcano", "weather", "cyclone"):
        assert by_cat.get(cat, 0) > 0, f"{cat} was starved out of the window"
    # And no single high-churn category consumes the whole window.
    assert by_cat["fire"] < 100


def test_balance_caps_each_category_fairly():
    # 7 equal-priority categories share a 70-slot window → 10 each, none starved.
    rows = _rows({c: 50 for c in "abcdefg"})
    chosen = set(_balance_ids_by_category(rows, 70))
    by_cat = {c: 0 for c in "abcdefg"}
    for sig_id, cat in rows:
        if sig_id in chosen:
            by_cat[cat] += 1
    assert all(count == 10 for count in by_cat.values())


def test_balance_preserves_priority_order_within_category():
    # Ids ascend with priority within a category; the pick keeps the top ones.
    rows = [(i, "fire") for i in range(1, 21)]  # single category, ids 1..20
    assert _balance_ids_by_category(rows, 5) == [1, 2, 3, 4, 5]


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


# ── _serialize_run (pipeline heartbeat) ─────────────────────────────


def test_serialize_run_is_none_without_a_recorded_cycle():
    """A user who has never run a cycle reads as unknown, not as healthy."""
    assert _serialize_run(None) is None


def test_serialize_run_exposes_source_counts(db):
    run = GeoCycleRun(
        user_id=1,
        started_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 4, 10, 1, tzinfo=timezone.utc),
        ok=True,
        events=31,
        new_signals=4,
        sources=json.dumps({"earthquakes": 9, "events": 22}),
    )
    out = _serialize_run(run)
    assert out.ok is True
    assert out.events == 31 and out.new_signals == 4
    assert out.sources == {"earthquakes": 9, "events": 22}


def test_serialize_run_survives_malformed_source_json(db):
    """The counts are diagnostics; a broken payload must not 500 the status call."""
    run = GeoCycleRun(
        user_id=1,
        started_at=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 4, 10, 1, tzinfo=timezone.utc),
        ok=False,
        sources="not-json",
        error="IntegrityError: UNIQUE constraint failed",
    )
    out = _serialize_run(run)
    assert out.sources == {}
    assert out.ok is False
    assert "IntegrityError" in out.error


def test_serialize_run_marks_naive_timestamps_as_utc(db):
    """The DB columns are naive; the browser must not read them as local time.

    `new Date("2026-09-04T10:00:00")` is local in every browser, so an unstamped
    timestamp would shift the age of the last cycle by the viewer's offset — the
    exact number the health line is there to report.
    """
    run = GeoCycleRun(
        user_id=1,
        started_at=datetime(2026, 9, 4, 10, 0),  # naive, as read back from the DB
        finished_at=datetime(2026, 9, 4, 10, 1),
        ok=True,
    )
    out = _serialize_run(run)
    assert out.started_at.tzinfo is not None
    assert out.started_at.utcoffset().total_seconds() == 0
    assert out.model_dump_json().startswith('{"started_at":"2026-09-04T10:00:00Z"')


# ── UTC on every timestamp the API emits ────────────────────────────


def test_serialize_stamps_utc_on_signal_and_checkpoint_times(db):
    """Naive timestamps make the browser compute every age wrong.

    `new Date("2026-09-04T12:00:00")` is local in every browser, so from Madrid
    a signal two hours old rendered as four in the feed, and the checkpoint clock
    drifted by the same offset. Only `last_run` was stamped when it was added;
    the fields that predate it were not.
    """
    signal = _signal()
    signal.created_at = datetime(2026, 9, 4, 12, 0)  # naive, as read back
    signal.checkpoints.append(
        GeoCheckpoint(
            signal_id=1,
            user_id=1,
            horizon="1h",
            target_at=datetime(2026, 9, 4, 13, 0),
            evaluated_at=datetime(2026, 9, 4, 13, 5),
        )
    )
    db.add(signal)
    db.commit()

    out = _serialize(signal, {})

    assert out.timestamp.utcoffset().total_seconds() == 0
    assert out.checkpoints[0].targetAt.utcoffset().total_seconds() == 0
    assert out.checkpoints[0].evaluatedAt.utcoffset().total_seconds() == 0
    assert '"timestamp":"2026-09-04T12:00:00Z"' in out.model_dump_json()


def test_serialize_keeps_a_pending_checkpoint_unevaluated(db):
    """The UTC stamp must not turn "not evaluated yet" into a date."""
    signal = _signal()
    signal.created_at = datetime(2026, 9, 4, 12, 0)
    signal.checkpoints.append(
        GeoCheckpoint(
            signal_id=1, user_id=1, horizon="7d", target_at=datetime(2026, 9, 11, 12, 0)
        )
    )
    db.add(signal)
    db.commit()

    assert _serialize(signal, {}).checkpoints[0].evaluatedAt is None


def test_as_utc_does_not_shift_an_already_aware_timestamp():
    """Idempotent: a value that already carries an offset keeps its instant."""
    madrid = timezone(timedelta(hours=2))
    aware = datetime(2026, 9, 4, 14, 0, tzinfo=madrid)
    assert _as_utc(aware) == datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    assert _as_utc(None) is None
