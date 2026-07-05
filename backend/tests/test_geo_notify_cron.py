"""Tests for geo notifications (channel fan-out, Telegram escaping) and /geo/cron."""

import pytest
from fastapi import HTTPException
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


# ── /geo/cron shared-secret auth ──────────────────────────────────────


class _Req:
    def __init__(self, key: str | None):
        self.headers = {"x-cron-key": key} if key is not None else {}


def test_cron_rejected_without_secret_configured(db, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "cron_secret", "")
    with pytest.raises(HTTPException) as exc:
        cron_run(_Req("anything"), db)
    assert exc.value.status_code == 403


def test_cron_rejected_with_wrong_key(db, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    with pytest.raises(HTTPException) as exc:
        cron_run(_Req("wrong"), db)
    assert exc.value.status_code == 403


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

    result = cron_run(_Req("s3cret"), db)
    assert result["users"] == 2
    assert result["cycles_ok"] == 2
    assert sorted(ran) == [1, 2]
