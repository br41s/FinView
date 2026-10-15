"""Direct broker connections. Today: IBKR through the Flex Web Service.

The token is write-only from the client's side: it is accepted on connect and
never returned (only its last four characters, so the user can tell which one
is stored).
"""

import re
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.services import broker_sync
from backend.services.credentials_crypto import CredentialsUnavailable, credentials_enabled

router = APIRouter(prefix="/brokers", tags=["brokers"])

UNAVAILABLE = "La conexión directa con brokers no está disponible en este momento."
NOT_CONNECTED = "No hay ninguna conexión con IBKR. Conéctala primero."
UNREADABLE = (
    "No se pudo leer el token guardado de IBKR. Vuelve a conectar la cuenta con tu token."
)


class IBKRConnectIn(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    query_id: str = Field(min_length=1, max_length=20)
    full_history: bool = True

    @field_validator("token", "query_id", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("token")
    @classmethod
    def _token_shape(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]+", value):
            raise ValueError("El token de IBKR solo contiene letras y números.")
        return value

    @field_validator("query_id")
    @classmethod
    def _query_shape(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("El ID de la Flex Query es un número.")
        return value


class BrokerConnectionOut(BaseModel):
    enabled: bool
    connected: bool
    query_id: str | None = None
    token_hint: str | None = None
    account_opened_on: date | None = None
    history_pending: bool = False
    last_synced_at: datetime | None = None
    last_error: str | None = None
    in_progress: bool = False
    gaps: dict[str, str] = Field(default_factory=dict)


class SyncProgressOut(BaseModel):
    state: str  # "running" | "done" | "error"
    done: int
    total: int
    year: int | None = None
    message: str | None = None
    gaps: dict[str, str] = Field(default_factory=dict)
    retry_after: int


def _require_enabled() -> None:
    if not credentials_enabled():
        raise HTTPException(status_code=503, detail=UNAVAILABLE)


@router.get("/ibkr", response_model=BrokerConnectionOut)
def get_ibkr(db: DbSession, user: CurrentUser):
    conn = broker_sync.get_connection(db, user)
    return broker_sync.connection_out(conn, enabled=credentials_enabled())


@router.put("/ibkr", response_model=BrokerConnectionOut)
def connect_ibkr(body: IBKRConnectIn, db: DbSession, user: CurrentUser):
    _require_enabled()
    conn = broker_sync.connect(
        db, user, token=body.token, query_id=body.query_id, full_history=body.full_history
    )
    return broker_sync.connection_out(conn, enabled=True)


@router.post("/ibkr/sync", response_model=SyncProgressOut)
def sync_ibkr(db: DbSession, user: CurrentUser):
    """Advance the sync by at most one year. Call again while `state` is "running"."""
    _require_enabled()
    try:
        return broker_sync.sync_step(db, user)
    except broker_sync.NotConnected:
        raise HTTPException(status_code=404, detail=NOT_CONNECTED) from None
    except CredentialsUnavailable:
        db.rollback()
        raise HTTPException(status_code=409, detail=UNREADABLE) from None


@router.delete("/ibkr", status_code=204)
def disconnect_ibkr(db: DbSession, user: CurrentUser):
    broker_sync.disconnect(db, user)
