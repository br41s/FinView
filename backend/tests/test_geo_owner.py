"""Ideas has one owner: the pipeline runs once and every account reads its rows.

Four accounts used to mean four copies of every signal and checkpoint and a
2 s cycle each; the rows are computed from the same public feeds and the
channels are global, so the copies carried no information. These tests pin
the owner's identity (a users row that cannot log in), the one-time adoption
of the first account's history, and that the API serves the owner's rows to
whoever is authenticated.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import cron_run, list_signals, scheduler_status
from backend.models import Base, GeoCheckpoint, GeoCycleRun, GeoSignal, User
from backend.services.geo.owner import GEO_OWNER_EMAIL, geo_owner_id


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _signal(user_id: int, external_id: str = "ev-1") -> GeoSignal:
    return GeoSignal(
        user_id=user_id,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id=external_id,
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


def test_owner_is_created_once_and_cannot_log_in(db):
    owner = geo_owner_id(db)
    assert geo_owner_id(db) == owner
    row = db.query(User).filter(User.email == GEO_OWNER_EMAIL).one()
    assert row.is_active is False
    assert row.password_hash is None
    assert db.query(User).count() == 1


def test_the_first_account_history_is_adopted_on_creation(db):
    """Without this the first shared cycle re-tracks every live event and pages
    it again; the first account was the pipeline's only real reader."""
    first, second = User(email="first@x.com"), User(email="second@x.com")
    db.add_all([first, second])
    db.commit()
    db.add(_signal(first.id))
    db.add(_signal(second.id))
    db.commit()
    sig = db.query(GeoSignal).filter(GeoSignal.user_id == first.id).one()
    now = datetime.now(timezone.utc)
    db.add(GeoCheckpoint(user_id=first.id, signal_id=sig.id, horizon="1d", target_at=now))
    db.add(GeoCycleRun(user_id=first.id, started_at=now, finished_at=now, ok=True))
    db.add(GeoCycleRun(user_id=second.id, started_at=now, finished_at=now, ok=True))
    db.commit()

    owner = geo_owner_id(db)

    assert db.query(GeoSignal).filter(GeoSignal.user_id == owner).count() == 1
    assert db.query(GeoSignal).filter(GeoSignal.user_id == first.id).count() == 0
    assert db.query(GeoCheckpoint).filter(GeoCheckpoint.user_id == owner).count() == 1
    assert db.query(GeoCycleRun).filter(GeoCycleRun.user_id == owner).count() == 1
    # The second account's copy is left alone: never read, never re-tracked.
    assert db.query(GeoSignal).filter(GeoSignal.user_id == second.id).count() == 1
    assert db.query(GeoCycleRun).filter(GeoCycleRun.user_id == second.id).count() == 1


def test_adoption_happens_only_when_the_owner_is_created(db):
    owner = geo_owner_id(db)
    late = User(email="late@x.com")
    db.add(late)
    db.commit()
    db.add(_signal(late.id))
    db.commit()

    assert geo_owner_id(db) == owner
    assert db.query(GeoSignal).filter(GeoSignal.user_id == late.id).count() == 1


def test_every_account_reads_the_owner_rows(db):
    owner = geo_owner_id(db)
    a, b = User(email="a@x.com"), User(email="b@x.com")
    db.add_all([a, b])
    db.commit()
    shared = _signal(owner, "shared")
    db.add(shared)
    db.add(_signal(a.id, "private-copy"))
    db.commit()

    for user in (a, b):
        rows = list_signals(db, user, status="active", limit=10)
        assert [r.headline for r in rows] == ["M6.4 quake near Antofagasta"]
        assert [r.id for r in rows] == [str(shared.id)]
        assert scheduler_status(db, user).active_signals == 1


def test_cron_runs_exactly_one_cycle_whatever_the_account_count(db, monkeypatch):
    from backend.services.geo import orchestrator

    ran: list[int] = []
    monkeypatch.setattr(orchestrator, "prepare_cycle", lambda db: "inputs")
    monkeypatch.setattr(
        orchestrator, "run_cycle_for_user",
        lambda uid, inputs=None: ran.append(uid) or object(),
    )
    for email in ("a@x.com", "b@x.com", "c@x.com"):
        db.add(User(email=email))
    db.commit()

    result = cron_run(db)

    assert result == {"status": "done", "cycles_ok": 1, "cycles_failed": 0}
    assert ran == [geo_owner_id(db)]


def test_cron_fails_the_job_when_the_cycle_fails(db, monkeypatch):
    from backend.services.geo import orchestrator

    monkeypatch.setattr(orchestrator, "prepare_cycle", lambda db: "inputs")
    monkeypatch.setattr(orchestrator, "run_cycle_for_user", lambda uid, inputs=None: None)

    with pytest.raises(HTTPException) as exc:
        cron_run(db)
    assert exc.value.status_code == 500


def test_the_other_crons_skip_the_owner(db, monkeypatch):
    """The owner has no portfolio and no watchlist; an options or zonas-clave
    cycle for it is a wasted loop at best, and the loops read every user."""
    from unittest.mock import patch

    from backend.api import options as options_api
    from backend.api import zonas_clave as zonas_api

    geo_owner_id(db)
    db.add(User(email="a@x.com"))
    db.commit()
    real = db.query(User).filter(User.email == "a@x.com").one().id

    seen: list[int] = []
    monkeypatch.setattr(options_api, "run_cycle", lambda uid: seen.append(uid) or {"status": "ok"})
    assert options_api.cron_run(db)["cycles_ok"] == 1
    assert seen == [real]

    with (
        patch("backend.services.reference_data_maintenance.run_reference_data_maintenance"),
        patch(
            "backend.services.zonas_clave_analyzer.run_analysis_for_user",
            return_value={"analyzed": 1, "signals": 0, "alerts": 0},
        ) as analyze,
    ):
        assert zonas_api.cron_run(db)["users"] == 1
    analyze.assert_called_once_with(real)


def test_signal_timestamps_still_leave_stamped(db):
    owner = geo_owner_id(db)
    signal = _signal(owner)
    signal.created_at = datetime(2026, 9, 4, 12, 0)
    db.add(signal)
    db.commit()
    status = scheduler_status(db, User(email="x@x.com"))
    assert status.last_signal_at.utcoffset() == timedelta(0)
