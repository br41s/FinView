"""Auth API: register, login, current-user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import DbSession
from backend.models import User
from backend.services.auth_service import (
    create_access_token,
    create_user,
    decode_access_token,
    get_user_by_email,
    verify_password,
)
from backend.services.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)

# --------------- schemas ---------------


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = ""
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user: dict
    token: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    subscription_tier: str = "FREE"


# --------------- dependency ---------------


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """Extract and validate JWT from Authorization header."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User | None:
    """Like get_current_user but returns None if no token (for migration period)."""
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


# --------------- routes ---------------


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "subscription_tier": user.subscription_tier or "FREE",
    }


@router.post("/register", response_model=AuthResponse, responses={400: {"description": "Email already registered or weak password"}, 429: {"description": "Too many requests"}})
@limiter.limit(settings.rate_limit_register)
def register(request: Request, body: RegisterRequest, db: DbSession):
    if get_user_by_email(db, body.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = create_user(db, email=body.email, name=body.name, password=body.password)
    token = create_access_token(user.id, user.email)
    return {"user": _user_dict(user), "token": token}


@router.post("/login", response_model=AuthResponse, responses={401: {"description": "Invalid credentials"}, 403: {"description": "Account disabled"}, 429: {"description": "Too many requests"}})
@limiter.limit(settings.rate_limit_login)
def login(request: Request, body: LoginRequest, db: DbSession):
    user = get_user_by_email(db, body.email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token(user.id, user.email)
    return {"user": _user_dict(user), "token": token}


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return _user_dict(user)
