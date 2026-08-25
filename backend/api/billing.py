"""Billing API: checkout, portal, subscription status, webhook."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.auth import CurrentUser
from backend.database import DbSession
from backend.services.billing_service import (
    create_checkout_session,
    create_portal_session,
    get_user_subscription,
    handle_webhook_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# --------------- schemas ---------------


class CheckoutRequest(BaseModel):
    price_id: str


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    tier: str
    status: str | None
    label: str
    max_accounts: int
    max_imports_per_month: int
    imports_this_month: int | None = None
    current_period_end: str | None
    has_stripe_subscription: bool


# --------------- routes ---------------


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(db: DbSession, user: CurrentUser):
    """Return the current user's subscription details, with usage against the plan."""
    return get_user_subscription(user, db)


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    responses={400: {"description": "Invalid price ID or Stripe error"}},
)
def checkout(body: CheckoutRequest, user: CurrentUser, db: DbSession):
    """Create a Stripe Checkout Session for subscription purchase."""
    try:
        url = create_checkout_session(db, user, body.price_id)
        return {"url": url}
    except Exception as e:
        logger.exception("Stripe checkout error")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/portal",
    response_model=PortalResponse,
    responses={400: {"description": "Stripe portal error"}},
)
def portal(user: CurrentUser, db: DbSession):
    """Create a Stripe Customer Portal Session for subscription management."""
    try:
        url = create_portal_session(db, user)
        return {"url": url}
    except Exception as e:
        logger.exception("Stripe portal error")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Handle incoming Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    try:
        result = handle_webhook_event(payload, sig_header)
        return result
    except ValueError:
        logger.warning("Stripe webhook signature validation failed")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as e:
        logger.exception("Webhook processing error")
        raise HTTPException(status_code=400, detail=str(e))
