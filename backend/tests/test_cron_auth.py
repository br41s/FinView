"""The shared-secret gate on the /cron endpoints.

Cloud Run scales to zero, so periodicity comes from an external scheduler
hitting these endpoints rather than from an in-process job. The secret is their
only protection, and the check used to be copy-pasted into all three — three
chances to get `hmac.compare_digest` or the empty-secret case subtly wrong, and
the zonas copy had no rejection tests at all.

These go through the real routes rather than calling the handlers. Asserting a
403 from a function body would only prove the body does something; it would not
prove the route is gated, which is the property that keeps the endpoint shut.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.auth import require_cron_key
from backend.app import app
from backend.config import settings

CRON_ROUTES = ["/api/geo/cron", "/api/options/agent/cron", "/api/zonas-clave/cron"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    return TestClient(app)


# ── every cron route is gated ────────────────────────────────────────


def test_every_cron_route_carries_the_gate():
    """Structural: a new cron endpoint must not ship without the secret check."""
    gated = {
        route.path
        for route in app.routes
        if any(
            getattr(d.dependency, "__name__", "") == "require_cron_key"
            for d in getattr(route, "dependencies", [])
        )
    }
    assert set(CRON_ROUTES) <= gated, f"ungated cron routes: {set(CRON_ROUTES) - gated}"


def test_no_other_route_is_gated_by_the_cron_secret():
    """A human-facing endpoint behind a machine secret would lock users out."""
    gated = {
        route.path
        for route in app.routes
        if any(
            getattr(d.dependency, "__name__", "") == "require_cron_key"
            for d in getattr(route, "dependencies", [])
        )
    }
    assert gated == set(CRON_ROUTES)


# ── rejection ────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_a_wrong_key_is_refused(client, path):
    assert client.post(path, headers={"X-Cron-Key": "wrong"}).status_code == 403


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_a_missing_header_is_refused(client, path):
    assert client.post(path).status_code == 403


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_an_empty_key_is_refused(client, path):
    assert client.post(path, headers={"X-Cron-Key": ""}).status_code == 403


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_an_unconfigured_secret_closes_the_endpoint(monkeypatch, path):
    """Unset must disable, not open — the opposite default would expose these
    to anyone the moment the secret went missing from the environment."""
    monkeypatch.setattr(settings, "cron_secret", "")
    unconfigured = TestClient(app)

    assert unconfigured.post(path, headers={"X-Cron-Key": ""}).status_code == 403
    assert unconfigured.post(path, headers={"X-Cron-Key": "anything"}).status_code == 403


def test_a_prefix_of_the_secret_is_not_enough(client):
    for guess in ("s", "s3cre", "s3cretx", "S3CRET"):
        assert client.post(CRON_ROUTES[0], headers={"X-Cron-Key": guess}).status_code == 403


# ── the dependency itself ────────────────────────────────────────────


def test_the_right_key_passes(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    require_cron_key(SimpleNamespace(headers={"x-cron-key": "s3cret"}))


def test_the_header_lookup_is_case_insensitive(monkeypatch):
    """Starlette lowercases header keys; a cron sending X-Cron-Key must work."""
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    client = TestClient(app)

    # A 403 here would mean the header never reached the check.
    assert client.post(CRON_ROUTES[0], headers={"x-CRON-key": "s3cret"}).status_code != 403
