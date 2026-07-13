"""Tests for the options agent's background cycle trigger: dedup, cleanup, return shape.

trigger_cycle() only depends on `user.id`, so it's called directly here (bypassing
the FastAPI/HTTP layer) with a lightweight fake user, matching this test suite's
existing style of exercising functions directly rather than spinning up a TestClient.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import backend.api.options as options_api


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
