"""Tests for geo notifications (channel fan-out, Telegram escaping) and /geo/cron."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import cron_run
from backend.models import Base, GeoSignal, GeoSignalTicker, User
from backend.services.geo import notify
from backend.services.geo.notify import _md_escape, notify_signal


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _signal() -> GeoSignal:
    s = GeoSignal(
        user_id=1,
        event_type="earthquake",
        display_category="earthquake",
        source="usgs",
        external_id="ev-1",
        headline="M7.1 quake near *Tokyo* [USGS_live]",
        location="japan",
        lat=35.0,
        lng=139.0,
        importance=72,
        confidence=0.8,
        risk_score=9,
        direction="bearish",
        status="active",
    )
    s.tickers.append(GeoSignalTicker(symbol="EWJ", direction="bearish"))
    return s


# ── Telegram Markdown escaping ────────────────────────────────────────


def test_md_escape_escapes_all_specials():
    assert _md_escape("a*b_c`d[e") == "a\\*b\\_c\\`d\\[e"


def test_notify_signal_fans_out_to_all_channels(monkeypatch):
    calls = {}
    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: calls.setdefault("ntfy", a))
    monkeypatch.setattr(notify, "send_telegram", lambda text: calls.setdefault("tg", text))
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.setdefault("email", a))

    notify_signal(_signal(), importance=72)

    assert {"ntfy", "tg", "email"} <= set(calls)
    # Raw specials from the headline must arrive escaped in the Telegram text.
    assert "\\*Tokyo\\*" in calls["tg"]
    assert "\\[USGS\\_live]" in calls["tg"]


def test_notify_signal_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("channel down")

    monkeypatch.setattr(notify, "send_ntfy", boom)
    monkeypatch.setattr(notify, "send_telegram", boom)
    monkeypatch.setattr(notify, "send_email", boom)
    notify_signal(_signal(), importance=72)  # must not raise


# ── Telegram forum-topic routing ──────────────────────────────────────


def test_send_telegram_includes_thread_id_when_set(monkeypatch):
    import io
    import json
    import urllib.request

    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id", "-100123")
    monkeypatch.setattr(settings, "telegram_thread_id", "42")

    captured: dict = {}

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured.update(json.loads(req.data))
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert notification_service.send_telegram("hola") is True
    assert captured["message_thread_id"] == 42

    # Empty thread id → field omitted (message goes to General)
    monkeypatch.setattr(settings, "telegram_thread_id", "")
    captured.clear()
    notification_service.send_telegram("hola")
    assert "message_thread_id" not in captured


# ── LLM token gating ──────────────────────────────────────────────────


def test_llm_analyze_caches_per_event(monkeypatch):
    import httpx

    from backend.config import settings
    from backend.services.geo import analyst
    from backend.services.geo.sentinel import GeoEvent

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(analyst, "_LLM_CACHE", {})

    calls = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"confidence": 80}'}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(1) or _Resp())

    event = GeoEvent(
        id="ev-cache", type="earthquake", title="quake", latitude=0.0,
        longitude=0.0, source="usgs", timestamp=0,
    )
    # Second call for the same event id (another user's cycle) must hit the cache.
    assert analyst._llm_analyze(event, []) == {"confidence": 80}
    assert analyst._llm_analyze(event, []) == {"confidence": 80}
    assert len(calls) == 1


def test_has_active_signal_gates_known_events(db):
    from backend.services.geo.orchestrator import _has_active_signal
    from backend.services.geo.sentinel import GeoEvent

    db.add(_signal())
    db.commit()

    known = GeoEvent(
        id="ev-1", type="earthquake", title="quake", latitude=0.0,
        longitude=0.0, source="usgs", timestamp=0,
    )
    unknown = GeoEvent(
        id="ev-new", type="earthquake", title="quake", latitude=0.0,
        longitude=0.0, source="usgs", timestamp=0,
    )
    assert _has_active_signal(db, 1, known) is True
    assert _has_active_signal(db, 1, unknown) is False
    assert _has_active_signal(db, 2, known) is False  # other user, own scope


# ── /geo/cron shared-secret auth ──────────────────────────────────────


def test_cron_runs_cycle_per_user(db, monkeypatch):
    from backend.config import settings
    from backend.services.geo import orchestrator

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    ran: list[int] = []
    monkeypatch.setattr(
        orchestrator, "run_cycle_for_user", lambda uid: ran.append(uid) or object()
    )

    db.add(User(email="a@x.com"))
    db.add(User(email="b@x.com"))
    db.commit()

    result = cron_run(db)
    assert result["users"] == 2
    assert result["cycles_ok"] == 2
    assert sorted(ran) == [1, 2]


def test_cron_reports_failure_when_no_cycle_completes(db, monkeypatch):
    """Cloud Scheduler only sees the status code.

    `run_cycle_for_user` swallows its exception and returns None, so this
    endpoint answered 200 "done" over a pipeline that failed on every call —
    every scheduled run looked successful while Ideas produced nothing for weeks.
    """
    from fastapi import HTTPException

    from backend.services.geo import orchestrator

    monkeypatch.setattr(orchestrator, "run_cycle_for_user", lambda uid: None)
    db.add(User(email="a@x.com"))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        cron_run(db)
    assert exc.value.status_code == 500


def test_cron_succeeds_when_at_least_one_cycle_completes(db, monkeypatch):
    """One user's blow-up must not fail the whole job — the count carries it."""
    from backend.services.geo import orchestrator

    monkeypatch.setattr(
        orchestrator, "run_cycle_for_user", lambda uid: None if uid == 1 else object()
    )
    db.add(User(email="a@x.com"))
    db.add(User(email="b@x.com"))
    db.commit()

    result = cron_run(db)
    assert result["cycles_ok"] == 1
    assert result["cycles_failed"] == 1


def test_cron_with_no_users_is_not_a_failure(db, monkeypatch):
    from backend.services.geo import orchestrator

    monkeypatch.setattr(orchestrator, "run_cycle_for_user", lambda uid: None)
    assert cron_run(db)["users"] == 0


def test_scheduler_status_stamps_utc_on_the_last_signal(db, monkeypatch):
    """`last_signal_at` feeds the header stat and the staleness read; naive would
    shift both by the viewer's offset."""
    from backend.api.geo import scheduler_status
    from backend.config import settings

    monkeypatch.setattr(settings, "request_scoped_runtime", True)
    user = User(email="a@x.com")
    db.add(user)
    signal = _signal()
    signal.created_at = datetime(2026, 9, 4, 12, 0)  # naive, as read back from the DB
    db.add(signal)
    db.commit()

    status = scheduler_status(db, user)

    assert status.last_signal_at.utcoffset().total_seconds() == 0
