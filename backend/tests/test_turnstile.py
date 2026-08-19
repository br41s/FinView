"""Tests for the Turnstile check that gates login against credential stuffing.

Two behaviours matter and neither was covered. It must be a **no-op** when no
secret is configured, or local dev and unconfigured deploys cannot log in at
all. And when it is configured it must **fail closed** — a missing token, a
Cloudflare outage or an unparseable answer all reject the login rather than
waving it through, which is the trade-off `turnstile.py` documents.
"""

import httpx
import pytest

from backend.services import turnstile
from backend.services.turnstile import turnstile_enabled, verify_turnstile


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(turnstile.settings, "turnstile_secret", "sk_test", raising=False)


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(turnstile.settings, "turnstile_secret", "", raising=False)


def _respond(monkeypatch, payload: dict, status: int = 200):
    """Stand in for the Cloudflare siteverify call."""
    def _post(url, **kwargs):
        return httpx.Response(status, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(turnstile.httpx, "post", _post)


def _raise(monkeypatch, exc: Exception):
    def _post(url, **kwargs):
        raise exc

    monkeypatch.setattr(turnstile.httpx, "post", _post)


# ── Unconfigured: verification is skipped entirely ───────────────────


def test_disabled_without_a_secret(unconfigured):
    assert turnstile_enabled() is False


def test_without_a_secret_any_token_passes(unconfigured, monkeypatch):
    """Local dev has no widget, so there is no token to send."""
    _raise(monkeypatch, AssertionError("Cloudflare must not be called when unconfigured"))

    assert verify_turnstile(None) is True
    assert verify_turnstile("") is True
    assert verify_turnstile("anything") is True


# ── Configured: fail closed ──────────────────────────────────────────


def test_enabled_with_a_secret(configured):
    assert turnstile_enabled() is True


def test_a_passing_challenge_is_accepted(configured, monkeypatch):
    _respond(monkeypatch, {"success": True})

    assert verify_turnstile("token") is True


def test_a_failing_challenge_is_rejected(configured, monkeypatch):
    _respond(monkeypatch, {"success": False, "error-codes": ["invalid-input-response"]})

    assert verify_turnstile("token") is False


@pytest.mark.parametrize("token", [None, ""])
def test_a_missing_token_never_reaches_cloudflare(configured, monkeypatch, token):
    """Rejected locally: no token means the widget was bypassed."""
    _raise(monkeypatch, AssertionError("Cloudflare must not be called without a token"))

    assert verify_turnstile(token) is False


def test_a_cloudflare_outage_blocks_the_login(configured, monkeypatch):
    """Fail closed, deliberately: availability loses to credential stuffing."""
    _raise(monkeypatch, httpx.ConnectError("cloudflare unreachable"))

    assert verify_turnstile("token") is False


def test_an_http_error_blocks_the_login(configured, monkeypatch):
    _respond(monkeypatch, {"success": True}, status=500)

    assert verify_turnstile("token") is False


def test_an_unparseable_body_blocks_the_login(configured, monkeypatch):
    """A 200 is not proof of a verdict — the body still has to make sense."""
    def _post(url, **kwargs):
        return httpx.Response(
            200, content=b"<html>not json</html>", request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(turnstile.httpx, "post", _post)

    assert verify_turnstile("token") is False


def test_a_response_without_success_blocks_the_login(configured, monkeypatch):
    _respond(monkeypatch, {"error-codes": ["internal-error"]})

    assert verify_turnstile("token") is False


def test_the_client_ip_is_forwarded_when_known(configured, monkeypatch):
    """remoteip lets Cloudflare score the challenge against the real caller."""
    sent = {}

    def _post(url, **kwargs):
        sent.update(kwargs.get("data") or {})
        return httpx.Response(200, json={"success": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(turnstile.httpx, "post", _post)
    verify_turnstile("token", "198.51.100.23")

    assert sent["remoteip"] == "198.51.100.23"
    assert sent["response"] == "token"
    assert sent["secret"] == "sk_test"


def test_no_remoteip_key_when_the_ip_is_unknown(configured, monkeypatch):
    sent = {}

    def _post(url, **kwargs):
        sent.update(kwargs.get("data") or {})
        return httpx.Response(200, json={"success": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(turnstile.httpx, "post", _post)
    verify_turnstile("token", None)

    assert "remoteip" not in sent
