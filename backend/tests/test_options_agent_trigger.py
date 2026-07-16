"""Tests for the options agent's cycle entry points.

Covers the manual background trigger (dedup, cleanup, return shape) and the
external-cron entry (/options/agent/cron: shared-secret auth, per-user cycles,
and the in-progress guard shared with the manual trigger).

trigger_cycle() and cron_run() only depend on `user.id` / a headers mapping, so
they're called directly here (bypassing the FastAPI/HTTP layer) with lightweight
fakes, matching this test suite's existing style of exercising functions directly
rather than spinning up a TestClient.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.api.options as options_api
from backend.config import settings
from backend.models import Base, User


def _user(uid: int) -> SimpleNamespace:
    return SimpleNamespace(id=uid)


def _wait_until_removed(user_id: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if user_id not in options_api._cycles_in_progress:
            return
        time.sleep(0.02)
    raise AssertionError(f"user {user_id} still marked in-progress after {timeout}s")


def test_trigger_cycle_returns_started_and_marks_in_progress():
    release = threading.Event()
    with patch.object(options_api, "run_cycle", side_effect=lambda uid: release.wait(2)):
        result = options_api.trigger_cycle(_user(101))
        assert result.status == "started"
        assert result.cycle is None
        # Added synchronously in the request thread, before the background
        # thread even starts — no race to poll for here.
        assert 101 in options_api._cycles_in_progress
        release.set()
    _wait_until_removed(101)


def test_trigger_cycle_dedupes_concurrent_calls_for_same_user():
    release = threading.Event()
    with patch.object(options_api, "run_cycle", side_effect=lambda uid: release.wait(2)) as mock_run:
        first = options_api.trigger_cycle(_user(202))
        second = options_api.trigger_cycle(_user(202))

        assert first.status == "started"
        assert second.status == "already_running"
        mock_run.assert_called_once_with(202)
        release.set()
    _wait_until_removed(202)


def test_trigger_cycle_allows_different_users_concurrently():
    release = threading.Event()
    with patch.object(options_api, "run_cycle", side_effect=lambda uid: release.wait(2)):
        first = options_api.trigger_cycle(_user(301))
        second = options_api.trigger_cycle(_user(302))

        assert first.status == "started"
        assert second.status == "started"
        release.set()
    _wait_until_removed(301)
    _wait_until_removed(302)


def test_trigger_cycle_cleans_up_after_run_cycle_raises():
    with patch.object(options_api, "run_cycle", side_effect=RuntimeError("boom")):
        result = options_api.trigger_cycle(_user(404))
        assert result.status == "started"
    # run_cycle itself always swallows exceptions in production code, but the
    # background wrapper's `finally` must still discard the flag even if a
    # mocked run_cycle raises past that — otherwise a real bug there would
    # permanently lock the user out of triggering another cycle.
    _wait_until_removed(404)


def test_trigger_cycle_second_call_after_completion_starts_a_new_cycle():
    release = threading.Event()
    with patch.object(options_api, "run_cycle", side_effect=lambda uid: release.wait(2)) as first_mock:
        first = options_api.trigger_cycle(_user(505))
        assert first.status == "started"
        release.set()
    _wait_until_removed(505)
    first_mock.assert_called_once_with(505)

    release2 = threading.Event()
    with patch.object(options_api, "run_cycle", side_effect=lambda uid: release2.wait(2)) as second_mock:
        second = options_api.trigger_cycle(_user(505))
        assert second.status == "started"
        release2.set()
    _wait_until_removed(505)
    second_mock.assert_called_once_with(505)


# ── /options/agent/cron shared-secret auth + in-progress guard ────────


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class _Req:
    def __init__(self, key: str | None):
        self.headers = {"x-cron-key": key} if key is not None else {}


def _users(db, *uids: int) -> None:
    for uid in uids:
        db.add(User(id=uid, email=f"u{uid}@x.com", password_hash="x"))
    db.commit()


def test_cron_rejected_without_secret_configured(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    with pytest.raises(HTTPException) as exc:
        options_api.cron_run(_Req("anything"), db)
    assert exc.value.status_code == 403


def test_cron_rejected_with_wrong_key(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "right")
    with pytest.raises(HTTPException) as exc:
        options_api.cron_run(_Req("wrong"), db)
    assert exc.value.status_code == 403


def test_cron_rejected_without_header(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "right")
    with pytest.raises(HTTPException) as exc:
        options_api.cron_run(_Req(None), db)
    assert exc.value.status_code == 403


def test_cron_runs_one_cycle_per_user(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "right")
    _users(db, 11, 12)
    with patch.object(options_api, "run_cycle", return_value={"status": "ok"}) as mock_run:
        result = options_api.cron_run(_Req("right"), db)
    assert result == {"status": "done", "users": 2, "cycles_ok": 2, "skipped": 0}
    assert sorted(c.args[0] for c in mock_run.call_args_list) == [11, 12]


def test_cron_counts_only_ok_cycles(db, monkeypatch):
    """run_cycle swallows its own errors and returns {"status": "error"} — it
    never raises — so cycles_ok must key off the status, not off absence of an
    exception (geo's `is not None` idiom would count failures as successes)."""
    monkeypatch.setattr(settings, "cron_secret", "right")
    _users(db, 21, 22)
    with patch.object(
        options_api, "run_cycle", side_effect=[{"status": "ok"}, {"status": "error"}]
    ):
        result = options_api.cron_run(_Req("right"), db)
    assert result == {"status": "done", "users": 2, "cycles_ok": 1, "skipped": 0}


def test_cron_skips_user_with_cycle_already_in_progress(db, monkeypatch):
    """A cron tick landing on top of a manual /agent/run must not double-fetch."""
    monkeypatch.setattr(settings, "cron_secret", "right")
    _users(db, 31, 32)
    options_api._cycles_in_progress.add(31)
    try:
        with patch.object(options_api, "run_cycle", return_value={"status": "ok"}) as mock_run:
            result = options_api.cron_run(_Req("right"), db)
        assert result == {"status": "done", "users": 2, "cycles_ok": 1, "skipped": 1}
        mock_run.assert_called_once_with(32)
    finally:
        options_api._cycles_in_progress.discard(31)


def test_cron_releases_guard_even_when_run_cycle_raises(db, monkeypatch):
    """run_cycle shouldn't raise, but if it ever does the user must not stay
    permanently locked out of future cycles."""
    monkeypatch.setattr(settings, "cron_secret", "right")
    _users(db, 41)
    with patch.object(options_api, "run_cycle", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            options_api.cron_run(_Req("right"), db)
    assert 41 not in options_api._cycles_in_progress
