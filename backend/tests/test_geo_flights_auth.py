"""OpenSky authentication: OAuth2 client credentials, with graceful degradation.

OpenSky's portal issues a client id + secret, not a password, so the old basic-auth
path could never lift the anonymous rate limit — and a rate-limited source reads as
"no flights today", which is indistinguishable from a quiet sky. These tests cover
the failure shapes, not just the happy one: a token endpoint that errors, one that
answers 200 with no token, and one that answers with a token that expires.
"""

import asyncio

import pytest

from backend.config import settings
from backend.services.geo.ingest import flights


@pytest.fixture(autouse=True)
def clean_auth_state(monkeypatch):
    """Credentials off and the token cache empty before every test."""
    for field in (
        "opensky_client_id",
        "opensky_client_secret",
        "opensky_username",
        "opensky_password",
    ):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(flights, "_token", None)
    monkeypatch.setattr(flights._cache, "_value", None)
    yield
    monkeypatch.setattr(flights, "_token", None)


def _creds(monkeypatch, client_id="cid", secret="sec"):
    monkeypatch.setattr(settings, "opensky_client_id", client_id)
    monkeypatch.setattr(settings, "opensky_client_secret", secret)


def _record_calls(monkeypatch, token_body):
    """Stub fetch_json: token exchanges answer `token_body`, box scans answer empty."""
    calls: list[dict] = []

    async def fake_fetch_json(url, **kw):
        calls.append({"url": url, **kw})
        if url == flights._TOKEN_URL:
            return token_body
        return {"states": []}

    monkeypatch.setattr(flights, "fetch_json", fake_fetch_json)
    return calls


def test_client_credentials_are_exchanged_for_a_bearer_token(monkeypatch):
    _creds(monkeypatch)
    calls = _record_calls(monkeypatch, {"access_token": "tok-123", "expires_in": 1800})

    asyncio.run(flights.fetch_flights())

    token_call = next(c for c in calls if c["url"] == flights._TOKEN_URL)
    assert token_call["method"] == "POST"
    # Form-encoded, not JSON: OAuth2 token endpoints reject a JSON body.
    assert token_call["data"]["grant_type"] == "client_credentials"
    assert token_call["data"]["client_id"] == "cid"

    scans = [c for c in calls if c["url"] != flights._TOKEN_URL]
    assert scans, "the region scans should still run"
    for call in scans:
        assert call["headers"] == {"Authorization": "Bearer tok-123"}
        assert call["auth"] is None


def test_the_token_is_reused_across_cycles(monkeypatch):
    """One token per ~30 minutes, not one per region box per cycle."""
    _creds(monkeypatch)
    calls = _record_calls(monkeypatch, {"access_token": "tok-123", "expires_in": 1800})

    asyncio.run(flights.fetch_flights())
    monkeypatch.setattr(flights._cache, "_value", None)  # force a second fetch
    asyncio.run(flights.fetch_flights())

    assert len([c for c in calls if c["url"] == flights._TOKEN_URL]) == 1


def test_an_expired_token_is_refreshed(monkeypatch):
    _creds(monkeypatch)
    calls = _record_calls(monkeypatch, {"access_token": "tok-123", "expires_in": 1800})

    asyncio.run(flights.fetch_flights())
    # Simulate the deadline passing.
    monkeypatch.setattr(flights, "_token", ("tok-123", 0.0))
    monkeypatch.setattr(flights._cache, "_value", None)
    asyncio.run(flights.fetch_flights())

    assert len([c for c in calls if c["url"] == flights._TOKEN_URL]) == 2


def test_a_200_with_no_access_token_degrades_to_anonymous(monkeypatch):
    """The envelope is validated before it is trusted."""
    _creds(monkeypatch)
    calls = _record_calls(monkeypatch, {"error": "invalid_client"})

    asyncio.run(flights.fetch_flights())  # must not raise

    for call in (c for c in calls if c["url"] != flights._TOKEN_URL):
        assert call["headers"] is None
        assert call["auth"] is None


def test_a_failed_token_exchange_degrades_to_anonymous(monkeypatch):
    _creds(monkeypatch)
    calls = _record_calls(monkeypatch, None)  # fetch_json returns None on any failure

    asyncio.run(flights.fetch_flights())

    assert [c for c in calls if c["url"] != flights._TOKEN_URL], "scans still ran"
    assert flights._token is None


def test_legacy_basic_auth_is_used_when_only_a_password_exists(monkeypatch):
    """Accounts that predate the OAuth portal keep working."""
    monkeypatch.setattr(settings, "opensky_username", "brais")
    monkeypatch.setattr(settings, "opensky_password", "pw")
    calls = _record_calls(monkeypatch, None)

    asyncio.run(flights.fetch_flights())

    assert not [c for c in calls if c["url"] == flights._TOKEN_URL]
    for call in calls:
        assert call["auth"] == ("brais", "pw")
        assert call["headers"] is None


def test_client_credentials_win_over_legacy_basic_auth(monkeypatch):
    _creds(monkeypatch)
    monkeypatch.setattr(settings, "opensky_username", "brais")
    monkeypatch.setattr(settings, "opensky_password", "pw")
    calls = _record_calls(monkeypatch, {"access_token": "tok-123"})

    asyncio.run(flights.fetch_flights())

    for call in (c for c in calls if c["url"] != flights._TOKEN_URL):
        assert call["headers"] == {"Authorization": "Bearer tok-123"}
        assert call["auth"] is None


def test_no_credentials_at_all_stays_anonymous(monkeypatch):
    calls = _record_calls(monkeypatch, None)

    asyncio.run(flights.fetch_flights())

    assert not [c for c in calls if c["url"] == flights._TOKEN_URL]
    for call in calls:
        assert call["auth"] is None and call["headers"] is None


def test_missing_expires_in_still_caches_the_token(monkeypatch):
    """OpenSky documents expires_in, but a missing or junk value must not crash."""
    _creds(monkeypatch)
    _record_calls(monkeypatch, {"access_token": "tok-123", "expires_in": "not-a-number"})

    asyncio.run(flights.fetch_flights())

    assert flights._token is not None
    assert flights._token[0] == "tok-123"
