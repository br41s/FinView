"""ACLED: OAuth password grant (there is no API key), plus loud page truncation.

The API has no documented ordering, and a full page silently narrows the 30-day
window to whatever 500 rows came back.
"""

import asyncio

import pytest

from backend.config import settings
from backend.services.geo.ingest import acled


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(settings, "acled_email", "a@b.c")
    monkeypatch.setattr(settings, "acled_password", "pw")
    monkeypatch.setattr(acled, "_token", None)
    monkeypatch.setattr(acled._cache, "_value", None)
    yield
    monkeypatch.setattr(acled, "_token", None)


def _rows(n: int) -> list[dict]:
    return [
        {
            "event_id_cnty": f"E{i}", "event_date": f"2026-09-{1 + i % 19:02d}",
            "event_type": "Protests", "sub_event_type": "Peaceful protest",
            "country": "Kenya", "latitude": "-1.3", "longitude": "36.8",
            "fatalities": "0", "notes": "", "actor1": "", "actor2": "",
        }
        for i in range(n)
    ]


_TOKEN = {"access_token": "tok-1", "expires_in": 86400, "refresh_token": "ref-1"}


def _stub(monkeypatch, rows, token_body=_TOKEN):
    calls: list[dict] = []

    async def fake(url, **kw):
        calls.append({"url": url, **kw})
        if url == acled._TOKEN_URL:
            return token_body
        return {"success": True, "data": rows}

    monkeypatch.setattr(acled, "fetch_json", fake)
    return calls


def test_password_grant_then_bearer_read(monkeypatch):
    calls = _stub(monkeypatch, _rows(3))
    events = asyncio.run(acled.fetch_acled())

    token_call, read_call = calls
    assert token_call["url"] == acled._TOKEN_URL and token_call["method"] == "POST"
    assert token_call["data"] == {
        "grant_type": "password", "username": "a@b.c", "password": "pw", "client_id": "acled",
    }
    assert read_call["url"] == acled._ACLED_URL
    assert read_call["headers"] == {"Authorization": "Bearer tok-1"}
    assert "key" not in read_call["params"] and "email" not in read_call["params"]
    assert len(events) == 3


def test_token_is_reused_across_cycles(monkeypatch):
    calls = _stub(monkeypatch, _rows(1))
    asyncio.run(acled.fetch_acled())
    monkeypatch.setattr(acled._cache, "_value", None)
    asyncio.run(acled.fetch_acled())
    assert len([c for c in calls if c["url"] == acled._TOKEN_URL]) == 1


def test_expired_token_uses_the_refresh_grant(monkeypatch):
    calls = _stub(monkeypatch, _rows(1))
    asyncio.run(acled.fetch_acled())
    monkeypatch.setattr(acled, "_token", ("tok-1", 0.0, "ref-1"))
    monkeypatch.setattr(acled._cache, "_value", None)
    asyncio.run(acled.fetch_acled())
    grants = [c["data"]["grant_type"] for c in calls if c["url"] == acled._TOKEN_URL]
    assert grants == ["password", "refresh_token"]


def test_failed_token_exchange_degrades_to_stale_cache(monkeypatch, caplog):
    _stub(monkeypatch, _rows(1), token_body={"error": "invalid_grant"})
    assert asyncio.run(acled.fetch_acled()) == []
    assert "no access_token" in caplog.text
    assert acled._token is None


def test_unconfigured_credentials_skip_the_source(monkeypatch):
    monkeypatch.setattr(settings, "acled_password", "")
    calls = _stub(monkeypatch, _rows(1))
    assert asyncio.run(acled.fetch_acled()) == []
    assert calls == []


def test_a_full_page_warns_with_the_window_it_kept(monkeypatch, caplog):
    _stub(monkeypatch, _rows(acled._LIMIT))
    asyncio.run(acled.fetch_acled())
    assert "full page" in caplog.text
    assert "oldest kept event_date=2026-09-01" in caplog.text
    assert "newest=2026-09-19" in caplog.text


def test_a_short_page_is_quiet(monkeypatch, caplog):
    _stub(monkeypatch, _rows(acled._LIMIT - 1))
    asyncio.run(acled.fetch_acled())
    assert "full page" not in caplog.text
