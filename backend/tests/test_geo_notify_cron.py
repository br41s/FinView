"""Tests for geo notifications (channel fan-out, Telegram escaping) and /geo/cron."""

import logging
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.geo import cron_run
from backend.models import Base, GeoSignal, GeoSignalTicker, User
from backend.services.geo import notify
from backend.services.geo.advisor import SignalResult
from backend.services.geo.notify import _md_escape, notify_signal


@pytest.fixture(autouse=True)
def _fresh_delivery_ledger(monkeypatch):
    monkeypatch.setattr(notify, "_DELIVERED", {})


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
    monkeypatch.setattr(
        notify, "send_ntfy", lambda *a, **k: calls.setdefault("ntfy", a) or True
    )
    monkeypatch.setattr(
        notify, "send_telegram", lambda text: calls.setdefault("tg", text) or True
    )
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.setdefault("email", a) or True)

    delivered = notify_signal(_signal(), importance=72)

    assert {"ntfy", "tg", "email"} <= set(calls)
    assert delivered == {"ntfy": True, "telegram": True, "email": True}
    # Raw specials from the headline must arrive escaped in the Telegram text.
    assert "\\*Tokyo\\*" in calls["tg"]
    assert "\\[USGS\\_live]" in calls["tg"]


def test_notify_signal_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("channel down")

    monkeypatch.setattr(notify, "send_ntfy", boom)
    monkeypatch.setattr(notify, "send_telegram", boom)
    monkeypatch.setattr(notify, "send_email", boom)
    assert notify_signal(_signal(), importance=72) == {  # must not raise
        "ntfy": False,
        "telegram": False,
        "email": False,
    }


def test_notify_signal_reports_every_channel_unconfigured(monkeypatch, caplog):
    """Prod ran seven days with 0 notification log lines and no way to tell a
    delivered alert from a swallowed one: the three senders returned False with
    no log when unconfigured and notify_signal discarded the return values."""
    from backend.config import settings

    for attr in (
        "ntfy_topic", "telegram_bot_token", "telegram_chat_id",
        "notify_email_from", "notify_email_to", "notify_email_password",
    ):
        monkeypatch.setattr(settings, attr, "")

    signal = _signal()
    with caplog.at_level(logging.WARNING):
        delivered = notify_signal(signal, importance=72)

    assert delivered == {"ntfy": False, "telegram": False, "email": False}
    assert not any(delivered.values())
    assert signal.notified_at is None
    text = caplog.text
    assert "not configured" in text  # from the senders themselves
    for channel in ("ntfy", "telegram", "email"):
        assert f"channel {channel} did not deliver" in text


def test_notify_signal_isolates_a_failing_channel(monkeypatch):
    """One `try` used to wrap all three channels, so a Telegram exception
    silently dropped the email that came after it."""
    calls: list[str] = []

    def boom(*a, **k):
        calls.append("tg")
        raise RuntimeError("telegram down")

    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: calls.append("ntfy") or True)
    monkeypatch.setattr(notify, "send_telegram", boom)
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.append("email") or True)

    delivered = notify_signal(_signal(), importance=72)

    assert calls == ["ntfy", "tg", "email"]
    assert delivered == {"ntfy": True, "telegram": False, "email": True}


def _gated(signal: GeoSignal) -> SignalResult:
    return SignalResult(signal=signal, importance=72, is_new=True, should_notify=True)


def test_cycle_stamps_notified_at_when_one_channel_delivers(db, monkeypatch):
    """`notified_at` is the delivery record the pipeline never had.

    Email alone delivering is the point: two dead channels must not make this
    read as undelivered.
    """
    from backend.services.geo import orchestrator

    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: False)
    monkeypatch.setattr(notify, "send_telegram", lambda text: False)
    monkeypatch.setattr(notify, "send_email", lambda *a: True)

    signal = _signal()
    db.add(signal)
    db.commit()

    notified, failed = orchestrator._dispatch_notifications(db, 1, [_gated(signal)])

    assert (notified, failed) == (1, 0)
    db.refresh(signal)
    assert signal.notified_at is not None


def test_cycle_counts_an_undelivered_signal_instead_of_stamping_it(db, monkeypatch):
    """`GeoCycleRun.notified` counted attempts, so a cycle where nothing could
    possibly be delivered still reported notifications."""
    from backend.services.geo import orchestrator

    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: False)
    monkeypatch.setattr(notify, "send_telegram", lambda text: False)
    monkeypatch.setattr(notify, "send_email", lambda *a: False)

    signal = _signal()
    db.add(signal)
    db.commit()

    notified, failed = orchestrator._dispatch_notifications(db, 1, [_gated(signal)])

    assert (notified, failed) == (0, 1)
    db.refresh(signal)
    assert signal.notified_at is None


# ── notification_service: unconfigured + transport ────────────────────


def test_send_email_uses_a_bounded_smtp_timeout(monkeypatch):
    """smtplib has no default deadline, and the geo cron is synchronous inside
    the Cloud Run request — an unreachable Gmail could hold it to the 1800s
    deadline."""
    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "notify_email_from", "a@x.com")
    monkeypatch.setattr(settings, "notify_email_password", "pw")
    monkeypatch.setattr(settings, "notify_email_to", "b@x.com")

    captured: dict = {}

    class _SMTP:
        def __init__(self, host, port, timeout=None):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(notification_service.smtplib, "SMTP", _SMTP)
    assert notification_service.send_email("s", "<p>b</p>") is True
    assert captured["timeout"] == notification_service._SMTP_TIMEOUT


def test_send_ntfy_retries_once_on_a_5xx(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "ntfy_topic", "finview-test")
    monkeypatch.setattr(notification_service.time, "sleep", lambda s: None)

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    attempts = []

    def fake_urlopen(req, timeout=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert notification_service.send_ntfy("t", "m") is True
    assert len(attempts) == 2


def test_send_ntfy_does_not_retry_a_4xx(monkeypatch):
    import urllib.error
    import urllib.request

    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "ntfy_topic", "finview-test")
    attempts = []

    def fake_urlopen(req, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert notification_service.send_ntfy("t", "m") is False
    assert len(attempts) == 1


def test_send_telegram_retries_once_on_a_timeout(monkeypatch):
    import io
    import urllib.request

    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id", "-100123")
    monkeypatch.setattr(settings, "telegram_thread_id", "")
    monkeypatch.setattr(notification_service.time, "sleep", lambda s: None)

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    attempts = []

    def fake_urlopen(req, timeout=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("timed out")
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert notification_service.send_telegram("hola") is True
    assert len(attempts) == 2


def test_unconfigured_senders_log_a_warning(monkeypatch, caplog):
    from backend.config import settings
    from backend.services import notification_service

    monkeypatch.setattr(settings, "ntfy_topic", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "notify_email_from", "")

    with caplog.at_level(logging.WARNING):
        assert notification_service.send_ntfy("t", "m") is False
        assert notification_service.send_telegram("t") is False
        assert notification_service.send_email("s", "b") is False

    assert "ntfy not configured" in caplog.text
    assert "Telegram not configured" in caplog.text
    assert "email not configured" in caplog.text


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


def _llm_answering(monkeypatch, body: dict) -> list[dict]:
    """OpenRouter answers 200 with ``body``; returns the request bodies it was sent."""
    import httpx

    from backend.config import settings
    from backend.services.geo import analyst

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(analyst, "_LLM_CACHE", {})
    sent: list[dict] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return body

    monkeypatch.setattr(httpx, "post", lambda *a, **k: sent.append(k["json"]) or _Resp())
    return sent


def test_llm_analyze_survives_an_answer_lost_to_reasoning(monkeypatch):
    """The enrichment shares the generative call's model and budget, so it shares
    the failure: a 200 whose tokens all went to reasoning. The rule-based
    analysis must stand, and the failure must not be cached as an answer."""
    from backend.services.geo import analyst
    from backend.services.geo.sentinel import GeoEvent

    sent = _llm_answering(monkeypatch, {
        "choices": [{"message": {"content": None, "reasoning": "…"}, "finish_reason": "length"}],
        "usage": {"completion_tokens": 2000, "completion_tokens_details": {"reasoning_tokens": 2000}},
    })
    event = GeoEvent(
        id="ev-empty", type="earthquake", title="quake", latitude=0.0,
        longitude=0.0, source="usgs", timestamp=0,
    )
    assert analyst._llm_analyze(event, []) is None
    assert analyst._LLM_CACHE == {}
    result = analyst.analyze_event(event, {}, use_llm=True)
    assert result.llm_narrative is None and result.direction == "quake"
    assert len(sent) == 2  # asked again: nothing was remembered


def test_llm_analyze_turns_reasoning_off(monkeypatch):
    from backend.services.geo import analyst
    from backend.services.geo.sentinel import GeoEvent

    sent = _llm_answering(monkeypatch, {"choices": [{"message": {"content": '{"confidence": 80}'}}]})
    event = GeoEvent(
        id="ev-shape", type="earthquake", title="quake", latitude=0.0,
        longitude=0.0, source="usgs", timestamp=0,
    )
    assert analyst._llm_analyze(event, []) == {"confidence": 80}
    assert sent[0]["reasoning"] == {"effort": "none"}


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


def test_a_channel_that_fails_once_is_skipped_for_the_rest_of_the_cycle(db, monkeypatch):
    """Bound the loop, not the call: with three signals gated and Telegram
    stalling, Telegram is attempted once, not three times, inside the cron
    request. The signals it missed stay un-stamped and retry next cycle."""
    from backend.services.geo import orchestrator

    calls: list[str] = []
    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: calls.append("ntfy") or True)
    monkeypatch.setattr(notify, "send_telegram", lambda text: calls.append("tg") or False)
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.append("email") or True)

    signals = [_signal(), _signal(), _signal()]
    for i, s in enumerate(signals):
        s.external_id = f"evt-{i}"
        db.add(s)
    db.commit()

    notified, failed = orchestrator._dispatch_notifications(db, 1, [_gated(s) for s in signals])

    assert calls.count("tg") == 1
    assert calls.count("ntfy") == 3 and calls.count("email") == 3
    assert (notified, failed) == (3, 0)


def test_an_undelivered_signal_is_reselected_next_cycle(db):
    """`notified_at` is the retry ledger. An ACTIVE signal above the gate with
    no delivery on record is selected again even with zero confidence shift;
    once any channel delivered, only a ≥15-point shift re-notifies."""
    import time

    from backend.services.geo.advisor import generate_signal
    from backend.services.geo.analyst import AnalystResult, AnalystTicker
    from backend.services.geo.sentinel import GeoEvent

    existing = _signal()
    db.add(existing)
    db.commit()

    event = GeoEvent(
        id=existing.external_id, type="earthquake", title="t", latitude=35.0,
        longitude=139.0, source=existing.source, timestamp=int(time.time() * 1000),
    )
    analysis = AnalystResult(
        event=event, matched_rules=[], tickers=[AnalystTicker("GLD", "bullish", "x")],
        confidence=float(existing.confidence) * 100, risk_score=9, direction="bearish",
    )

    assert generate_signal(db, user_id=1, analysis=analysis, prices={}).should_notify is True

    existing.notified_at = datetime.now(timezone.utc)
    db.commit()
    assert generate_signal(db, user_id=1, analysis=analysis, prices={}).should_notify is False


def test_one_event_is_delivered_once_across_users(monkeypatch):
    """Three accounts, one phone: the second and third users' copies of the
    same event are not sent again, but still count as delivered for them."""
    calls: list[str] = []
    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: calls.append("ntfy") or True)
    monkeypatch.setattr(notify, "send_telegram", lambda text: calls.append("tg") or True)
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.append("email") or True)

    first = notify_signal(_signal(), importance=72)
    second_user = _signal()
    second_user.user_id = 2
    second = notify_signal(second_user, importance=72)

    assert first == second == {"ntfy": True, "telegram": True, "email": True}
    assert calls == ["ntfy", "tg", "email"]


def test_a_failed_delivery_is_not_remembered_as_done(monkeypatch):
    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: False)
    monkeypatch.setattr(notify, "send_telegram", lambda text: False)
    monkeypatch.setattr(notify, "send_email", lambda *a: False)
    calls: list[int] = []
    notify_signal(_signal(), importance=72)
    monkeypatch.setattr(notify, "send_email", lambda *a: calls.append(1) or True)
    assert notify_signal(_signal(), importance=72)["email"] is True
    assert calls == [1]


def test_static_alert_zones_never_page(db):
    """The hardcoded ALERT_ZONES polygons emit the same red event every cycle.
    They stay on the board; they do not reach a phone."""
    import time

    from backend.services.geo.advisor import generate_signal
    from backend.services.geo.analyst import AnalystResult, AnalystTicker
    from backend.services.geo.sentinel import GeoEvent

    event = GeoEvent(
        id="alert-gaza-israel", type="conflict", title="Geopolitical Alert: Gaza / Israel",
        latitude=31.45, longitude=34.35, source="alerts", timestamp=int(time.time() * 1000),
        severity="red",
    )
    analysis = AnalystResult(
        event=event, matched_rules=[], tickers=[AnalystTicker("USO", "bullish", "x")],
        confidence=92.0, risk_score=9, direction="bullish",
    )
    res = generate_signal(db, user_id=1, analysis=analysis, prices={})
    assert res.importance >= 60 and res.should_notify is False


def test_a_rule_only_refresh_keeps_the_llm_risk(db):
    """The LLM runs on first sighting only. Its risk must survive the next
    cycle's rule-only refresh, or the override flips back and pages."""
    import time

    from backend.services.geo.advisor import generate_signal
    from backend.services.geo.analyst import AnalystResult, AnalystTicker
    from backend.services.geo.sentinel import GeoEvent

    existing = _signal()
    existing.risk_score = 5  # the LLM's call on first sighting: 0.8 × 5 → 40, no page
    existing.importance = 40
    db.add(existing)
    db.commit()
    event = GeoEvent(
        id=existing.external_id, type="earthquake", title="t", latitude=35.0,
        longitude=139.0, source=existing.source, timestamp=int(time.time() * 1000),
    )
    rule_only = AnalystResult(
        event=event, matched_rules=[], tickers=[AnalystTicker("GLD", "bullish", "x")],
        confidence=80.0, risk_score=9, direction="bearish",  # the rules alone say 9
    )
    res = generate_signal(db, user_id=1, analysis=rule_only, prices={})
    assert (res.signal.risk_score, res.importance, res.should_notify) == (5, 40, False)

    with_llm = AnalystResult(
        event=event, matched_rules=[], tickers=[AnalystTicker("GLD", "bullish", "x")],
        confidence=80.0, risk_score=9, direction="bearish", llm_narrative="escalating",
    )
    res = generate_signal(db, user_id=1, analysis=with_llm, prices={})
    assert (res.signal.risk_score, res.importance, res.should_notify) == (9, 72, True)


def test_the_shared_half_and_the_cycle_run_once(db, monkeypatch):
    """Four accounts used to mean four ingests, four price fetches and four
    identical cycles over one bundle; now the owner's cycle is the only one."""
    from backend.config import settings
    from backend.services.geo import orchestrator
    from backend.services.geo.owner import geo_owner_id

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    prepared: list[int] = []
    monkeypatch.setattr(
        orchestrator, "prepare_cycle", lambda db: prepared.append(1) or "inputs"
    )
    seen: list[tuple[int, object]] = []
    monkeypatch.setattr(
        orchestrator, "run_cycle_for_user",
        lambda uid, inputs=None: seen.append((uid, inputs)) or object(),
    )
    for email in ("a@x.com", "b@x.com", "c@x.com"):
        db.add(User(email=email))
    db.commit()

    result = cron_run(db)
    assert result["cycles_ok"] == 1
    assert prepared == [1]
    assert seen == [(geo_owner_id(db), "inputs")]


def test_a_failed_shared_half_fails_the_job(db, monkeypatch):
    from backend.config import settings
    from backend.services.geo import orchestrator
    from backend.services.geo.owner import geo_owner_id

    monkeypatch.setattr(settings, "cron_secret", "s3cret")

    def boom(db):
        raise RuntimeError("ingest exploded")

    monkeypatch.setattr(orchestrator, "prepare_cycle", boom)
    recorded: list[tuple[int, str | None]] = []
    monkeypatch.setattr(
        orchestrator, "_record_run",
        lambda db, uid, started, result, error: recorded.append((uid, error)),
    )
    db.add(User(email="a@x.com"))
    db.commit()

    with pytest.raises(HTTPException):
        cron_run(db)
    assert [uid for uid, _ in recorded] == [geo_owner_id(db)]
    assert all("ingest exploded" in err for _, err in recorded)


def test_email_html_escapes_the_headline(monkeypatch):
    """Generated theses let region-less, externally authored headlines reach the notifier."""
    captured: list[str] = []
    monkeypatch.setattr(notify, "send_ntfy", lambda *a, **k: True)
    monkeypatch.setattr(notify, "send_telegram", lambda text: True)
    monkeypatch.setattr(notify, "send_email", lambda title, html: captured.append(html) or True)
    s = _signal()
    s.headline = "<script>alert(1)</script> & co"
    notify_signal(s, importance=72)
    assert "<script>" not in captured[0] and "&lt;script&gt;" in captured[0]
