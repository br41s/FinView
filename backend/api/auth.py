"""Auth API: register, login, current-user."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

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
from backend.services.rate_limit import client_ip, limiter
from backend.services.turnstile import verify_turnstile

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
    turnstile_token: str | None = None


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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No has iniciado sesión")
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no válida")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_cron_key(request: Request) -> None:
    """Gate an endpoint on the shared cron secret (`X-Cron-Key`).

    Cloud Run scales to zero, so periodicity comes from an external scheduler
    hitting the /cron endpoints rather than from an in-process job. Their only
    protection is this secret, and the check was copy-pasted into all three of
    them — one definition of a security rule is worth more than three chances
    to get `hmac.compare_digest` or the empty-secret case subtly wrong.

    An unset secret disables the endpoints entirely rather than opening them.
    Applied as a route dependency so a new cron endpoint cannot forget it in
    its body, and so a test can assert every cron route carries it.
    """
    secret = settings.cron_secret
    provided = request.headers.get("x-cron-key", "")
    if not secret or not hmac.compare_digest(provided, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


CronKey = Depends(require_cron_key)


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
        raise HTTPException(status_code=400, detail="Ese email ya está registrado")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    user = create_user(db, email=body.email, name=body.name, password=body.password)
    token = create_access_token(user.id, user.email)
    return {"user": _user_dict(user), "token": token}


@router.post("/login", response_model=AuthResponse, responses={401: {"description": "Invalid credentials"}, 403: {"description": "Account disabled"}, 429: {"description": "Too many requests"}})
@limiter.limit(settings.rate_limit_login)
def login(request: Request, body: LoginRequest, db: DbSession):
    if not verify_turnstile(body.turnstile_token, client_ip(request)):
        raise HTTPException(status_code=403, detail="No se pudo verificar el captcha")
    user = get_user_by_email(db, body.email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    token = create_access_token(user.id, user.email)
    return {"user": _user_dict(user), "token": token}


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return _user_dict(user)
