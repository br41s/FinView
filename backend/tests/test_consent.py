"""Consent is recorded, and never assumed.

Two consents matter legally. Accepting the terms and the privacy policy at
sign-up must be an explicit act, stored with its version and time (GDPR art.
7.1: the controller must be able to demonstrate it). And the disability level in
the fiscal profile is health data (art. 9), so it is stored only alongside an
explicit consent that clearing the field withdraws.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.auth import router as auth_router
from backend.api.fiscal import router as fiscal_router
from backend.database import get_db
from backend.models import Base, FiscalProfile, User
from backend.services.auth_service import (
    TERMS_VERSION,
    create_access_token,
    create_user,
    has_accepted_current_terms,
)
from backend.services.rate_limit import limiter


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(auth_router, prefix="/api")
    app.include_router(fiscal_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    limiter.reset()
    return TestClient(app)


def _register(client, **overrides):
    body = {"email": "ana@example.com", "name": "Ana", "password": "long enough", **overrides}
    return client.post("/api/auth/register", json=body)


# ── terms at sign-up ─────────────────────────────────────────────────


def test_registration_without_accepting_the_terms_is_rejected(db, client):
    res = _register(client)

    assert res.status_code == 400
    assert "condiciones" in res.json()["detail"]
    assert db.query(User).count() == 0


def test_an_explicit_false_is_rejected_too(db, client):
    assert _register(client, accept_terms=False).status_code == 400
    assert db.query(User).count() == 0


def test_registration_records_the_accepted_version_and_time(db, client):
    res = _register(client, accept_terms=True)

    assert res.status_code == 200
    assert res.json()["user"]["terms_accepted"] is True
    user = db.query(User).one()
    assert user.terms_version == TERMS_VERSION
    assert user.terms_accepted_at is not None


def test_a_user_from_before_consent_was_recorded_is_asked_again(db, client):
    legacy = create_user(db, email="old@example.com", name="", password="long enough")
    token = create_access_token(legacy.id, legacy.email)

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.json()["terms_accepted"] is False


def test_a_new_terms_version_invalidates_the_old_acceptance(db):
    user = create_user(db, email="a@b.c", name="", password="long enough", accepted_terms=True)
    assert has_accepted_current_terms(user)

    user.terms_version = "2020-01-01"

    assert not has_accepted_current_terms(user)


# ── health data in the fiscal profile ────────────────────────────────


@pytest.fixture
def auth(db):
    user = create_user(db, email="ana@example.com", name="", password="long enough")
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


def test_disability_is_not_stored_without_explicit_consent(db, client, auth):
    res = client.put("/api/fiscal/profile/2025", json={"disability": "general"}, headers=auth)

    assert res.status_code == 422
    assert "consentimiento" in res.json()["detail"]
    assert db.query(FiscalProfile).count() == 0


def test_disability_with_consent_is_stored_with_its_timestamp(db, client, auth):
    res = client.put(
        "/api/fiscal/profile/2025",
        json={"disability": "general", "health_data_consent": True},
        headers=auth,
    )

    assert res.status_code == 200
    assert res.json()["health_data_consent"] is True
    profile = db.query(FiscalProfile).one()
    assert profile.disability == "general"
    assert profile.health_data_consent_at is not None


def test_clearing_disability_withdraws_the_consent(db, client, auth):
    client.put(
        "/api/fiscal/profile/2025",
        json={"disability": "severe", "health_data_consent": True},
        headers=auth,
    )

    res = client.put("/api/fiscal/profile/2025", json={"disability": None}, headers=auth)

    assert res.status_code == 200
    assert res.json()["health_data_consent"] is False
    profile = db.query(FiscalProfile).one()
    assert profile.disability is None
    assert profile.health_data_consent_at is None


def test_a_profile_without_disability_needs_no_consent(client, auth):
    res = client.put("/api/fiscal/profile/2025", json={"age": 40}, headers=auth)

    assert res.status_code == 200
    assert res.json()["health_data_consent"] is False
