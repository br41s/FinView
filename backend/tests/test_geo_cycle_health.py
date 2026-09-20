"""Regression tests for the two ways the Ideas pipeline died quietly.

1. A resolved signal's event recurring hit `uq_geo_sig_dedup` and raised
   IntegrityError inside `generate_signal`'s flush. That killed the whole cycle
   *before* the auditor ran, so from that day on there were no new signals and no
   resolutions either — while `/geo/cron` kept answering 200. Feeds make this
   certain, not unlucky: an EONET event stays open for months and `wx-*`,
   `ais-*`, `fire-cluster-*` and `*-escalation-*` ids are region-keyed and never
   rotate, so every one of them recurs after the auditor resolves it at +7d.

2. Nothing recorded that a cycle had run, so "the pipeline is dead" and "nothing
   happened today" looked identical from the API and the UI.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.models import Base, GeoCycleRun, GeoSignal, GeoSignalStatus
from backend.services.geo import orchestrator
from backend.services.geo.advisor import generate_signal
from backend.services.geo.analyst import AnalystResult, AnalystTicker
from backend.services.geo.sentinel import GeoEvent


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _event(event_id: str = "evt-EONET_6789") -> GeoEvent:
    return GeoEvent(
        id=event_id,
        type="volcano",
        title="Volcano - Etna",
        latitude=37.7,
        longitude=15.0,
        source="eonet",
        timestamp=0,
        region="mediterranean",
        raw_data={},
    )


def _analysis(event: GeoEvent) -> AnalystResult:
    return AnalystResult(
        event=event,
        matched_rules=[],
        tickers=[AnalystTicker("XLE", "bullish", "energy supply")],
        confidence=55.0,
        risk_score=6,
        direction="bullish",
    )


def _status(signal: GeoSignal) -> str:
    return getattr(signal.status, "value", signal.status)


# ── Recurrence after resolution ───────────────────────────────────────


def test_resolved_event_can_be_tracked_again(db):
    """The +7d resolution must not poison the event id forever."""
    event = _event()
    generate_signal(db, user_id=1, analysis=_analysis(event), prices={"XLE": 90.0})
    db.commit()

    # +7d: the auditor resolves it while the event is still open in the feed.
    db.query(GeoSignal).one().status = GeoSignalStatus.RESOLVED.value
    db.commit()

    generate_signal(db, user_id=1, analysis=_analysis(event), prices={"XLE": 92.0})
    db.commit()  # used to raise IntegrityError and take the cycle down with it

    signals = db.query(GeoSignal).order_by(GeoSignal.id).all()
    assert [_status(s) for s in signals] == ["resolved", "active"]
    # The resolved sighting keeps its own entry price, so its outcome history
    # stays intact rather than being overwritten by the new one.
    assert float(signals[0].tickers[0].price_at_signal) == 90.0
    assert float(signals[1].tickers[0].price_at_signal) == 92.0


def test_two_active_signals_for_one_event_are_still_rejected(db):
    """Dedup is narrowed to ACTIVE rows, not dropped: overlapping cycles (the
    manual Run cycle landing on top of a cron tick) must not double-post."""
    event = _event()
    generate_signal(db, user_id=1, analysis=_analysis(event), prices={})
    db.commit()

    db.add(
        GeoSignal(
            user_id=1,
            event_type="volcano",
            display_category="volcano",
            source="eonet",
            external_id=event.id,
            headline="duplicate",
            location="mediterranean",
            lat=37.7,
            lng=15.0,
            importance=33,
            confidence=0.55,
            risk_score=6,
            direction="bullish",
            status=GeoSignalStatus.ACTIVE.value,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_same_event_stays_isolated_per_user(db):
    """The index is scoped by user: one global event feeds every user's board."""
    event = _event()
    generate_signal(db, user_id=1, analysis=_analysis(event), prices={})
    generate_signal(db, user_id=2, analysis=_analysis(event), prices={})
    db.commit()

    assert db.query(GeoSignal).count() == 2


# ── One bad event must not take the cycle down ────────────────────────


def _stub_cycle_inputs(monkeypatch, analyses):
    """Drive run_cycle from a fixed analysis list, with no network anywhere."""
    async def _no_network():
        return _Bundle()

    monkeypatch.setattr(orchestrator, "seed_rule_stats", lambda db: None)
    monkeypatch.setattr(orchestrator, "_load_stats", lambda db: {})
    monkeypatch.setattr(orchestrator, "fetch_all_sources", _no_network)
    monkeypatch.setattr(orchestrator, "_collect_events", lambda bundle: [a.event for a in analyses])
    monkeypatch.setattr(
        orchestrator, "analyze_event", lambda event, stats, use_llm=False: _by_event(analyses, event)
    )
    monkeypatch.setattr(orchestrator, "_compound_analyses", lambda a, stats=None: [])
    monkeypatch.setattr(
        "backend.services.prices.fetch_ticker_prices", lambda symbols, budget=None: {}
    )


class _Bundle:
    """Minimal SourceBundle stand-in: every source empty."""

    def __getattr__(self, name):  # pragma: no cover - trivial
        return []


def _by_event(analyses, event):
    return next(a for a in analyses if a.event.id == event.id)


def test_one_unwritable_signal_does_not_stop_the_cycle(db, monkeypatch):
    """A single failing write costs its own signal and nothing else.

    Before, the failure escaped generate_signal, aborted the whole cycle and — the
    part that made it permanent — skipped Phase F, so the auditor stopped
    resolving anything too.
    """
    good, bad = _analysis(_event("evt-ok")), _analysis(_event("evt-poison"))
    _stub_cycle_inputs(monkeypatch, [bad, good])

    real_generate = orchestrator.generate_signal

    def flaky(db_, *, user_id, analysis, prices):
        if analysis.event.id == "evt-poison":
            # Same shape as the real failure: raised by the flush inside the
            # advisor, with the session already dirty.
            db_.add(GeoSignal())  # missing NOT NULL columns
            db_.flush()
        return real_generate(db_, user_id=user_id, analysis=analysis, prices=prices)

    monkeypatch.setattr(orchestrator, "generate_signal", flaky)
    evaluated: list[int] = []
    monkeypatch.setattr(
        orchestrator, "evaluate_pending", lambda db_, uid, budget=None: evaluated.append(uid) or 0
    )

    result = orchestrator.run_cycle(db, user_id=1)

    assert result.persist_failures == 1
    assert result.new_signals == 1
    assert [s.external_id for s in db.query(GeoSignal).all()] == ["evt-ok"]
    assert evaluated == [1], "the auditor must run even when a write failed"


def test_cycle_reports_per_source_counts(db, monkeypatch):
    """All-zero source counts are the signature of an ingest outage."""
    analysis = _analysis(_event("evt-1"))
    _stub_cycle_inputs(monkeypatch, [analysis])
    monkeypatch.setattr(orchestrator, "evaluate_pending", lambda db_, uid, budget=None: 0)

    result = orchestrator.run_cycle(db, user_id=1)

    assert set(result.sources) == set(orchestrator._SOURCE_KEYS)
    assert all(count == 0 for count in result.sources.values())


# ── The heartbeat row ─────────────────────────────────────────────────


def test_record_run_stores_a_successful_cycle(db):
    started = datetime.now(timezone.utc)
    result = orchestrator.CycleResult(
        events=12,
        new_signals=3,
        notified=1,
        checkpoints_evaluated=5,
        sources={"earthquakes": 7, "events": 5},
        persist_failures=0,
    )

    orchestrator._record_run(db, 1, started, result, None)

    run = db.query(GeoCycleRun).one()
    assert run.ok is True
    assert run.events == 12 and run.new_signals == 3
    assert json.loads(run.sources) == {"earthquakes": 7, "events": 5}
    assert run.error is None


def test_record_run_stores_the_failure_of_a_dirty_session(db):
    """The cycle blew up mid-write, so the row has to survive a poisoned session."""
    db.add(GeoSignal())  # pending garbage, would fail on flush
    started = datetime.now(timezone.utc)

    orchestrator._record_run(db, 1, started, None, "IntegrityError: UNIQUE constraint failed")

    run = db.query(GeoCycleRun).one()
    assert run.ok is False
    assert run.events == 0
    assert "UNIQUE constraint failed" in run.error


def test_record_run_prunes_old_rows(db):
    old = datetime.now(timezone.utc) - timedelta(days=orchestrator._RUN_RETENTION_DAYS + 1)
    db.add(GeoCycleRun(user_id=1, started_at=old, finished_at=old, ok=True))
    db.add(GeoCycleRun(user_id=2, started_at=old, finished_at=old, ok=True))
    db.commit()

    orchestrator._record_run(
        db, 1, datetime.now(timezone.utc), orchestrator.CycleResult(0, 0, 0, 0), None
    )

    assert db.query(GeoCycleRun).filter(GeoCycleRun.user_id == 1).count() == 1
    assert db.query(GeoCycleRun).filter(GeoCycleRun.user_id == 2).count() == 1, (
        "pruning is per user"
    )
