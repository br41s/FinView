"""`GET /geo/accuracy` and `POST /geo/rule-stats/reset` — seeing the loop.

The learning loop was unobservable and unresettable. In production
`geo_checkpoints` held 8500 rows (CORRECT 1571 / INCORRECT 5009 / NEUTRAL 1230 /
PENDING 690) of which 4374 evaluated rows scored exactly 0, because before
2026-09-06 the auditor compared a daily close against itself; `geo_rule_stats`
had 89 rows with two pinned at the -0.30 floor by that bogus history and no
endpoint to read or clear them. These tests pin the two properties that make the
numbers trustworthy: NEUTRAL never counts as a miss, and an unresolved
checkpoint is pending rather than neutral.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import accuracy, reset_rule_stats
from backend.app import app
from backend.models import Base, GeoCheckpoint, GeoRuleStat, GeoSignal

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=30)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class _User:
    def __init__(self, uid=1):
        self.id = uid


def _signal(db, user_id=1, external_id=None) -> GeoSignal:
    s = GeoSignal(
        user_id=user_id,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id=external_id or f"ev-{user_id}-{datetime.now().timestamp()}",
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
    db.add(s)
    db.flush()
    return s


def _checkpoint(db, signal, horizon, outcome, *, evaluated_days_ago=1, user_id=1):
    """Persist one checkpoint. `outcome=None` with a date = evaluated-but-null."""
    evaluated = (
        None
        if evaluated_days_ago is None
        else (NOW - timedelta(days=evaluated_days_ago)).replace(tzinfo=None)
    )
    db.add(
        GeoCheckpoint(
            user_id=user_id,
            signal_id=signal.id,
            horizon=horizon,
            target_at=(NOW - timedelta(days=2)).replace(tzinfo=None),
            score=None,
            outcome=outcome,
            evaluated_at=evaluated,
        )
    )
    db.flush()


def _rule(db, rule_id, *, total=0, correct=0, acc=None, mod=0.0, category="earthquake"):
    db.add(
        GeoRuleStat(
            rule_id=rule_id,
            category=category,
            base_confidence=0.8,
            total_signals=total,
            correct_signals=correct,
            accuracy=acc,
            confidence_mod=mod,
        )
    )
    db.flush()


# ── the horizon matrix ───────────────────────────────────────────────


def test_every_horizon_is_present_even_with_no_checkpoints(db):
    out = accuracy(db, _User(), SINCE)
    assert list(out.horizons) == ["1h", "6h", "1d", "3d", "7d"]
    assert all(h.accuracy is None for h in out.horizons.values())
    assert all(
        h.correct == h.incorrect == h.neutral == h.pending == 0
        for h in out.horizons.values()
    )


def test_counts_land_in_the_right_horizon_and_bucket(db):
    for horizon, outcomes in {
        "1h": ["CORRECT", "INCORRECT", "INCORRECT", "NEUTRAL"],
        "7d": ["CORRECT", "CORRECT", "CORRECT", "INCORRECT"],
    }.items():
        for i, outcome in enumerate(outcomes):
            _checkpoint(db, _signal(db, external_id=f"{horizon}-{i}"), horizon, outcome)

    horizons = accuracy(db, _User(), SINCE).horizons
    assert (horizons["1h"].correct, horizons["1h"].incorrect) == (1, 2)
    assert horizons["1h"].neutral == 1
    assert horizons["1h"].accuracy == pytest.approx(1 / 3)
    assert (horizons["7d"].correct, horizons["7d"].incorrect) == (3, 1)
    assert horizons["7d"].accuracy == pytest.approx(0.75)
    assert horizons["6h"].accuracy is None


def test_neutral_is_excluded_from_accuracy_not_counted_as_a_miss(db):
    """A checkpoint with nothing measurable is not a failed thesis."""
    _checkpoint(db, _signal(db, external_id="hit"), "1d", "CORRECT")
    for i in range(9):
        _checkpoint(db, _signal(db, external_id=f"n-{i}"), "1d", "NEUTRAL")

    bucket = accuracy(db, _User(), SINCE).horizons["1d"]
    assert bucket.neutral == 9
    assert bucket.accuracy == 1.0


def test_accuracy_is_null_when_nothing_measurable_happened(db):
    _checkpoint(db, _signal(db), "1h", "NEUTRAL")
    bucket = accuracy(db, _User(), SINCE).horizons["1h"]
    assert bucket.neutral == 1
    assert bucket.accuracy is None  # not 0.0 — no measurement is not a 0 % hit rate


# ── pending ──────────────────────────────────────────────────────────


def test_unevaluated_checkpoints_are_pending(db):
    _checkpoint(db, _signal(db), "3d", None, evaluated_days_ago=None)
    bucket = accuracy(db, _User(), SINCE).horizons["3d"]
    assert (bucket.pending, bucket.neutral) == (1, 0)


def test_evaluated_but_null_outcome_is_pending_not_neutral(db):
    """The latent lie the dots told: a stamped row with no verdict is not amber."""
    _checkpoint(db, _signal(db), "3d", None, evaluated_days_ago=1)
    bucket = accuracy(db, _User(), SINCE).horizons["3d"]
    assert (bucket.pending, bucket.neutral) == (1, 0)


def test_pending_is_counted_regardless_of_the_window(db):
    """An unresolved checkpoint has no date to filter on; it must not vanish."""
    _checkpoint(db, _signal(db), "7d", None, evaluated_days_ago=None)
    assert accuracy(db, _User(), NOW - timedelta(days=1)).horizons["7d"].pending == 1


# ── the since cutoff ─────────────────────────────────────────────────


def test_checkpoints_evaluated_before_since_are_excluded(db):
    """The pre-2026-09-06 rows were scored by a broken comparison — not evidence."""
    _checkpoint(db, _signal(db, external_id="old"), "1h", "INCORRECT", evaluated_days_ago=90)
    _checkpoint(db, _signal(db, external_id="new"), "1h", "CORRECT", evaluated_days_ago=3)

    bucket = accuracy(db, _User(), SINCE).horizons["1h"]
    assert (bucket.correct, bucket.incorrect) == (1, 0)
    assert bucket.accuracy == 1.0

    # Widen the window and the old failure comes back.
    wide = accuracy(db, _User(), NOW - timedelta(days=365)).horizons["1h"]
    assert (wide.correct, wide.incorrect) == (1, 1)


def test_since_defaults_to_thirty_days_ago(db):
    out = accuracy(db, _User(), None)
    assert abs((datetime.now(timezone.utc) - out.since).days - 30) <= 1
    assert out.since.tzinfo is not None  # timestamps leave this module UTC-stamped


def test_another_users_checkpoints_are_not_counted(db):
    _checkpoint(db, _signal(db, user_id=1), "1d", "CORRECT", user_id=1)
    _checkpoint(db, _signal(db, user_id=2), "1d", "INCORRECT", user_id=2)

    bucket = accuracy(db, _User(1), SINCE).horizons["1d"]
    assert (bucket.correct, bucket.incorrect) == (1, 0)


# ── the rule table ───────────────────────────────────────────────────


def test_rules_are_sorted_by_total_signals_desc(db):
    _rule(db, "quiet", total=0)
    _rule(db, "busy", total=102, correct=0, acc=0.0, mod=-0.30)
    _rule(db, "middling", total=12, correct=6, acc=0.5)

    rules = accuracy(db, _User(), SINCE).rules
    assert [r.ruleId for r in rules] == ["busy", "middling", "quiet"]
    assert rules[0].confidenceMod == pytest.approx(-0.30)  # the pinned floor, visible
    assert rules[2].accuracy is None


def test_rule_rows_carry_the_whole_learning_row(db):
    _rule(db, "fire-canada-lumber", total=102, correct=0, acc=0.0, mod=-0.30, category="fire")
    row = accuracy(db, _User(), SINCE).rules[0]
    assert (row.category, row.totalSignals, row.correctSignals) == ("fire", 102, 0)
    assert row.baseConfidence == pytest.approx(0.8)


# ── reset ────────────────────────────────────────────────────────────


def test_reset_zeroes_every_row_and_returns_the_count(db):
    _rule(db, "a", total=102, correct=3, acc=0.03, mod=-0.30)
    _rule(db, "b", total=8, correct=8, acc=1.0, mod=0.30)
    db.commit()

    assert reset_rule_stats(db, _User()).reset == 2

    for row in db.query(GeoRuleStat).all():
        assert float(row.confidence_mod) == 0.0
        assert (row.total_signals, row.correct_signals) == (0, 0)
        assert row.accuracy is None
        assert float(row.base_confidence) == 0.8  # static rule data, left alone


def test_reset_on_an_empty_table_is_a_no_op(db):
    assert reset_rule_stats(db, _User()).reset == 0


# ── auth ─────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    return TestClient(app)


def test_accuracy_requires_auth(client):
    assert client.get("/api/geo/accuracy").status_code == 401


def test_reset_requires_auth(client):
    """A global wipe of the learning table must not be reachable anonymously."""
    assert client.post("/api/geo/rule-stats/reset").status_code == 401
