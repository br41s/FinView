"""Tests for authentication: password hashing, JWTs, and the current-user gate.

Nothing covered auth before this file. That is the code deciding who gets to see
a user's brokerage history, so the cases below are the ones that matter when
they go wrong: a wrong password accepted, an expired or forged token honoured, a
deactivated account still able to read.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.auth import get_current_user
from backend.config import settings
from backend.models import Base
from backend.services.auth_service import (
    create_access_token,
    create_user,
    decode_access_token,
    get_user_by_email,
    hash_password,
    verify_password,
)

PASSWORD = "correct horse battery staple"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ── Password hashing ─────────────────────────────────────────────────


def test_a_correct_password_verifies():
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_a_wrong_password_does_not_verify():
    assert not verify_password("wrong", hash_password(PASSWORD))


def test_the_hash_does_not_contain_the_password():
    """A stolen database must not hand over the plaintext."""
    digest = hash_password(PASSWORD)

    assert PASSWORD not in digest
    assert digest.startswith("$2")  # bcrypt


def test_the_same_password_hashes_differently_each_time():
    """Per-hash salt: identical passwords must not produce identical rows."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verification_is_case_and_whitespace_sensitive():
    digest = hash_password(PASSWORD)

    assert not verify_password(PASSWORD.upper(), digest)
    assert not verify_password(PASSWORD + " ", digest)


# ── JWTs ─────────────────────────────────────────────────────────────


def test_a_freshly_issued_token_decodes_to_its_subject():
    payload = decode_access_token(create_access_token(42, "brais@example.com"))

    assert payload is not None
    # `sub` is a string per the JWT spec, and get_current_user int()s it.
    assert payload["sub"] == "42"
    assert payload["email"] == "brais@example.com"


def test_an_expired_token_is_rejected():
    expired = jwt.encode(
        {
            "sub": "42",
            "email": "brais@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(expired) is None


def test_a_token_signed_with_another_key_is_rejected():
    """The forgery case: a valid-looking token minted with the wrong secret."""
    forged = jwt.encode(
        {"sub": "1", "email": "attacker@example.com", "exp": datetime.now(timezone.utc)
         + timedelta(hours=1)},
        "not-the-real-secret",
        algorithm="HS256",
    )

    assert decode_access_token(forged) is None


def test_a_tampered_token_is_rejected():
    token = create_access_token(42, "brais@example.com")
    header, payload, signature = token.split(".")

    assert decode_access_token(f"{header}.{payload}x.{signature}") is None


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c", "Bearer x.y.z"])
def test_garbage_never_raises_only_returns_none(token):
    """Callers branch on None; an exception here would 500 instead of 401."""
    assert decode_access_token(token) is None


def test_an_unsigned_token_is_rejected():
    """alg=none is the classic JWT bypass; PyJWT must not accept it."""
    unsigned = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        key="",
        algorithm="none",
    )

    assert decode_access_token(unsigned) is None


# ── User lookup and creation ─────────────────────────────────────────


def test_create_user_stores_a_hash_not_the_password(db):
    user = create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)

    assert user.password_hash != PASSWORD
    assert verify_password(PASSWORD, user.password_hash)


def test_a_new_user_is_active_and_on_the_free_tier(db):
    user = create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)

    assert user.is_active is True
    # After refresh the Enum column hands back the member, not the raw string —
    # the same reason code elsewhere reaches for `.value`.
    tier = user.subscription_tier
    assert getattr(tier, "value", tier) == "FREE"


def test_lookup_by_email_finds_the_user_and_misses_others(db):
    create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)

    assert get_user_by_email(db, "brais@example.com") is not None
    assert get_user_by_email(db, "someone@else.com") is None


# ── get_current_user: the gate every protected route depends on ──────


def test_a_valid_token_resolves_to_its_user(db):
    user = create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)
    token = create_access_token(user.id, user.email)

    assert get_current_user(db=db, credentials=_credentials(token)).id == user.id


def test_no_credentials_is_401(db):
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=db, credentials=None)

    assert exc.value.status_code == 401


def test_an_invalid_token_is_401(db):
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=db, credentials=_credentials("garbage"))

    assert exc.value.status_code == 401


def test_a_token_for_a_deleted_user_is_401(db):
    """A token outlives the account it names; the row is the authority."""
    token = create_access_token(9999, "ghost@example.com")

    with pytest.raises(HTTPException) as exc:
        get_current_user(db=db, credentials=_credentials(token))

    assert exc.value.status_code == 401


def test_a_deactivated_user_is_locked_out_even_with_a_live_token(db):
    """Deactivation must take effect immediately, not at token expiry.

    Tokens last 90 days, so honouring an old one would leave a disabled account
    readable for a quarter.
    """
    user = create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)
    token = create_access_token(user.id, user.email)

    user.is_active = False
    db.commit()

    with pytest.raises(HTTPException) as exc:
        get_current_user(db=db, credentials=_credentials(token))

    assert exc.value.status_code == 401


def test_one_users_token_never_resolves_to_another(db):
    """Tenant isolation starts here: the subject claim picks the row."""
    brais = create_user(db, email="brais@example.com", name="Brais", password=PASSWORD)
    other = create_user(db, email="other@example.com", name="Other", password=PASSWORD)

    resolved = get_current_user(db=db, credentials=_credentials(create_access_token(
        brais.id, brais.email
    )))

    assert resolved.id == brais.id
    assert resolved.id != other.id
