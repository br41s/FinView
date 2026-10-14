"""The signed-in user's own account: accept terms, export data, delete account.

Lives under /users rather than /auth because the frontend forwards only
/api/auth/(login|register|me) to this backend; every other /api/auth/* path
belongs to NextAuth.
"""

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.auth import CurrentUser, UserResponse, _user_dict
from backend.config import settings
from backend.database import DbSession
from backend.services.auth_service import accept_terms, verify_password
from backend.services.billing_service import delete_stripe_customer
from backend.services.rate_limit import limiter
from backend.services.user_data import delete_user, iter_user_export

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class DeleteAccountRequest(BaseModel):
    password: str


@router.post("/me/accept-terms", response_model=UserResponse)
def accept_current_terms(user: CurrentUser, db: DbSession):
    """Record that the user accepts the current terms and privacy policy."""
    return _user_dict(accept_terms(db, user))


@router.get("/me/export")
def export_my_data(user: CurrentUser, db: DbSession):
    """Everything FinView stores about the user, as one JSON file (GDPR arts. 15, 20)."""

    def body() -> Iterator[str]:
        yield "{"
        for i, (table, rows) in enumerate(iter_user_export(db, user)):
            yield ("," if i else "") + json.dumps(table) + ":["
            for j, row in enumerate(rows):
                yield ("," if j else "") + json.dumps(jsonable_encoder(row), ensure_ascii=False)
            yield "]"
        yield "}"

    return StreamingResponse(
        body(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finview_mis_datos.json"'},
    )


@router.post(
    "/me/delete",
    status_code=204,
    responses={403: {"description": "Wrong password"}, 502: {"description": "Stripe unreachable"}},
)
@limiter.limit(settings.rate_limit_login)
def delete_my_account(request: Request, body: DeleteAccountRequest, user: CurrentUser, db: DbSession):
    """Erase the account and all its data, irreversibly (GDPR art. 17).

    The password is asked again because the session lasts 90 days: a borrowed
    laptop must not be enough to destroy an account. Billing is closed first and
    the deletion aborts if that fails — an erased account that keeps being
    charged is worse than a deletion the user has to retry.
    """
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")
    try:
        delete_stripe_customer(user)
    except Exception:
        logger.exception("Stripe customer deletion failed for user %s", user.id)
        raise HTTPException(
            status_code=502,
            detail="No se pudo cancelar tu suscripción. Tu cuenta no se ha eliminado; inténtalo de nuevo en unos minutos.",
        ) from None
    user_id = user.id
    delete_user(db, user)
    db.commit()
    logger.info("User %s deleted their account", user_id)
