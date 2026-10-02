"""Authentication helpers: password hashing and JWT tokens."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import User


# Version of the terms + privacy policy published under /legal. Bump it when a
# document changes in a way users must re-accept: everyone whose stored version
# differs is asked again. The date matches "Última actualización" on the pages
# (LEGAL_UPDATED in frontend/src/lib/legal.ts).
TERMS_VERSION = "2026-10-02"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns payload dict or None."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except PyJWTError:
        return None


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(
    db: Session, email: str, name: str, password: str, accepted_terms: bool = False
) -> User:
    user = User(email=email, name=name, password_hash=hash_password(password))
    if accepted_terms:
        _stamp_terms(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _stamp_terms(user: User) -> None:
    user.terms_version = TERMS_VERSION
    user.terms_accepted_at = datetime.now(timezone.utc)


def has_accepted_current_terms(user: User) -> bool:
    return user.terms_version == TERMS_VERSION


def accept_terms(db: Session, user: User) -> User:
    """Record acceptance of the current terms. Idempotent: the first timestamp stands."""
    if not has_accepted_current_terms(user):
        _stamp_terms(user)
        db.commit()
        db.refresh(user)
    return user
