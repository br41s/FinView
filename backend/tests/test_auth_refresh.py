"""POST /auth/refresh keeps a live session alive without a password.

The token was only minted at login, so a session could outlive it: the NextAuth
cookie rolls forward on activity while the token kept its original 90-day
expiry, and on day 90 every request answered 401 (production, 2026-10-14).
Refresh extends a valid session and must never revive an expired one or one
whose user was deactivated.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.auth import router as auth_router
from backend.config import settings
from backend.database import get_db
from backend.models import Base
from backend.services.auth_service import create_access_token, create_user, decode_access_token
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
    app.dependency_overrides[get_db] = lambda: db
    limiter.reset()
    return TestClient(app)


def _user(db, email="ana@example.com"):
    return create_user(db, email=email, name="Ana", password="long enough", accepted_terms=True)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_live_token_is_exchanged_for_a_fresh_one(db, client):
    user = _user(db)
    old = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "exp": datetime.now(timezone.utc) + timedelta(days=3),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    r = client.post("/api/auth/refresh", headers=_bearer(old))

    assert r.status_code == 200, r.text
    new = r.json()["token"]
    payload = decode_access_token(new)
    assert payload["sub"] == str(user.id)
    assert payload["exp"] > decode_access_token(old)["exp"]
    assert client.get("/api/auth/me", headers=_bearer(new)).status_code == 200


def test_an_expired_token_cannot_be_refreshed(db, client):
    user = _user(db)
    dead = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "exp": datetime.now(timezone.utc) - timedelta(seconds=5),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    r = client.post("/api/auth/refresh", headers=_bearer(dead))

    assert r.status_code == 401
    assert r.json()["detail"] == "Sesión no válida"


def test_a_deactivated_user_cannot_refresh(db, client):
    user = _user(db)
    token = create_access_token(user.id, user.email)
    user.is_active = False
    db.commit()

    r = client.post("/api/auth/refresh", headers=_bearer(token))

    assert r.status_code == 401


def test_refresh_needs_a_token(client):
    assert client.post("/api/auth/refresh").status_code == 401
