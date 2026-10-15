"""Stripe billing service: checkout sessions, customer portal, webhook handling."""

import logging
from datetime import datetime, timezone

import stripe
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import SubscriptionStatus, SubscriptionTier, User

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key

# ---------- plan limits ----------

PLAN_LIMITS: dict[str, dict] = {
    SubscriptionTier.FREE.value: {
        "max_accounts": 2,
        "max_imports_per_month": 5,
        "label": "Free",
    },
    SubscriptionTier.PRO.value: {
        "max_accounts": 10,
        "max_imports_per_month": 50,
        "label": "Pro",
    },
    SubscriptionTier.UNLIMITED.value: {
        "max_accounts": 999,
        "max_imports_per_month": 999,
        "label": "Unlimited",
    },
}

# Map Stripe price IDs → tiers
PRICE_TO_TIER: dict[str, str] = {}


def _build_price_map() -> None:
    """Build price→tier map from config (called lazily)."""
    if PRICE_TO_TIER:
        return
    if settings.stripe_price_pro:
        PRICE_TO_TIER[settings.stripe_price_pro] = SubscriptionTier.PRO.value
    if settings.stripe_price_unlimited:
        PRICE_TO_TIER[settings.stripe_price_unlimited] = SubscriptionTier.UNLIMITED.value


def _tier_for_price(price_id: str | None) -> str | None:
    """Map a Stripe price ID to a tier, or None when it is not one of ours.

    Deliberately has no default. Defaulting an unrecognised price to PRO turned
    any price ID in the Stripe account — a test price, a retired price, a price
    belonging to another product — into a free Pro upgrade for whoever checked
    out with it. An unknown price means we do not know what was bought, so the
    caller must decline rather than guess.
    """
    _build_price_map()
    if not price_id:
        return None
    return PRICE_TO_TIER.get(price_id)


# ---------- Stripe customer ----------


def get_or_create_stripe_customer(db: Session, user: User) -> str:
    """Return existing Stripe customer ID or create one."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.name or user.email,
        metadata={"finview_user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# ---------- checkout ----------


def create_checkout_session(db: Session, user: User, price_id: str) -> str:
    """Create a Stripe Checkout Session and return the URL.

    ``price_id`` arrives straight from the client, so it is checked against the
    configured plans before it reaches Stripe. Without this, a caller could check
    out against any price in the account and be upgraded on the way back.
    """
    if _tier_for_price(price_id) is None:
        raise ValueError("Unknown plan")

    customer_id = get_or_create_stripe_customer(db, user)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing?success=true",
        cancel_url=f"{settings.frontend_url}/billing?canceled=true",
        metadata={"finview_user_id": str(user.id)},
    )
    return session.url


# ---------- customer portal ----------


def create_portal_session(db: Session, user: User) -> str:
    """Create a Stripe Customer Portal Session and return the URL."""
    customer_id = get_or_create_stripe_customer(db, user)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.frontend_url}/billing",
    )
    return session.url


def delete_stripe_customer(user: User) -> None:
    """Delete the user's Stripe customer ahead of account deletion.

    Deleting the customer cancels every active subscription in the same call, so
    a deleted account can never keep being charged. Stripe retains the invoices
    it is legally required to keep; FinView keeps nothing.

    Raises on any Stripe failure other than "already gone": the caller must not
    delete the account while a subscription may still be billing.
    """
    if not user.stripe_customer_id:
        return
    try:
        stripe.Customer.delete(user.stripe_customer_id)
    except stripe.InvalidRequestError as exc:
        if exc.code != "resource_missing":
            raise


# ---------- webhook processing ----------


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    """Verify and process a Stripe webhook event. Returns summary dict."""
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return _process_event(event)


def _process_event(event: stripe.Event) -> dict:
    """Route event to handler. Returns summary."""
    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data_object)
    elif event_type in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return _handle_subscription_change(data_object)
    elif event_type == "invoice.payment_failed":
        return _handle_payment_failed(data_object)

    return {"handled": False, "event_type": event_type}


def _handle_checkout_completed(session_obj: dict) -> dict:
    """Activate subscription after successful checkout."""
    from backend.database import SessionLocal

    subscription_id = session_obj.get("subscription")
    if not subscription_id:
        return {"handled": False, "reason": "no subscription in session"}

    subscription = stripe.Subscription.retrieve(subscription_id)
    customer_id = subscription.customer
    price_id = subscription["items"]["data"][0]["price"]["id"]
    tier = _tier_for_price(price_id)
    if tier is None:
        # Grant nothing we cannot price. Reaching here means checkout validation
        # was bypassed or the plan config changed after the session was created.
        logger.error("Checkout completed with unrecognised price %s — no tier granted", price_id)
        return {"handled": False, "reason": "unknown price"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if not user:
            return {"handled": False, "reason": "user not found"}

        user.subscription_tier = tier
        user.subscription_status = SubscriptionStatus.ACTIVE.value
        user.stripe_subscription_id = subscription.id
        user.subscription_current_period_end = datetime.fromtimestamp(
            subscription.current_period_end
        )
        db.commit()
        return {"handled": True, "event": "checkout_completed", "tier": tier}
    finally:
        db.close()


def _handle_subscription_change(sub_obj: dict) -> dict:
    """Handle subscription updates (upgrade/downgrade/cancel)."""
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.stripe_customer_id == sub_obj["customer"])
            .first()
        )
        if not user:
            return {"handled": False, "reason": "user not found"}

        stripe_status = sub_obj["status"]
        if stripe_status == "active":
            price_id = sub_obj["items"]["data"][0]["price"]["id"]
            tier = _tier_for_price(price_id)
            if tier is None:
                # The subscription is genuinely active, so status and period still
                # apply — but an unrecognised price must not move the tier.
                logger.error(
                    "Subscription active on unrecognised price %s — tier left unchanged",
                    price_id,
                )
            else:
                user.subscription_tier = tier
            user.subscription_status = SubscriptionStatus.ACTIVE.value
            user.subscription_current_period_end = datetime.fromtimestamp(
                sub_obj["current_period_end"]
            )
        elif stripe_status == "canceled":
            user.subscription_tier = SubscriptionTier.FREE.value
            user.subscription_status = SubscriptionStatus.CANCELED.value
            user.stripe_subscription_id = None
        elif stripe_status == "past_due":
            user.subscription_status = SubscriptionStatus.PAST_DUE.value
        else:
            user.subscription_status = SubscriptionStatus.INCOMPLETE.value

        db.commit()
        return {"handled": True, "event": "subscription_change", "status": stripe_status}
    finally:
        db.close()


def _handle_payment_failed(invoice_obj: dict) -> dict:
    """Mark subscription as past_due on payment failure."""
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.stripe_customer_id == invoice_obj["customer"])
            .first()
        )
        if not user:
            return {"handled": False, "reason": "user not found"}

        user.subscription_status = SubscriptionStatus.PAST_DUE.value
        db.commit()
        return {"handled": True, "event": "payment_failed"}
    finally:
        db.close()


# ---------- query helpers ----------


def get_user_subscription(user: User, db: Session | None = None) -> dict:
    """Return current subscription info for a user.

    `imports_this_month` is only filled when a session is passed — without it
    the caller gets None rather than a wrong zero.
    """
    tier = user.subscription_tier or SubscriptionTier.FREE.value
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS[SubscriptionTier.FREE.value])

    return {
        "tier": tier,
        "status": user.subscription_status,
        "label": limits["label"],
        "max_accounts": limits["max_accounts"],
        "max_imports_per_month": limits["max_imports_per_month"],
        "imports_this_month": count_imports_this_month(db, user) if db is not None else None,
        "current_period_end": (
            user.subscription_current_period_end.isoformat()
            if user.subscription_current_period_end
            else None
        ),
        "has_stripe_subscription": bool(user.stripe_subscription_id),
    }


def check_account_limit(db: Session, user: User) -> bool:
    """Return True if user can create more accounts within their plan."""
    from backend.models import Account

    tier = user.subscription_tier or SubscriptionTier.FREE.value
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS[SubscriptionTier.FREE.value])
    count = db.query(Account).filter(Account.user_id == user.id).count()
    return count < limits["max_accounts"]


def _limits_for(user: User) -> dict:
    tier = user.subscription_tier or SubscriptionTier.FREE.value
    return PLAN_LIMITS.get(tier, PLAN_LIMITS[SubscriptionTier.FREE.value])


def import_allowance(user: User) -> int:
    """Imports per month the user's plan permits. An unreadable tier gets Free."""
    return _limits_for(user)["max_imports_per_month"]


def count_imports_this_month(db: Session, user: User) -> int:
    """Imports the user has made since the start of the current UTC month.

    Counted from ImportRecord, which is the row an import actually creates, so
    a re-upload of a file already imported does not add to the total — the
    (file_hash, broker) unique constraint means it never produced a second row.
    Imports made by a broker sync (`origin` set) are not uploads and do not count.
    """
    from sqlalchemy import func

    from backend.models import Account, ImportRecord

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(func.count(ImportRecord.id))
        .join(Account, ImportRecord.account_id == Account.id)
        .filter(
            Account.user_id == user.id,
            ImportRecord.imported_at >= month_start,
            # A broker sync is not an upload: a full-history backfill alone
            # would spend a Free month's allowance several times over.
            ImportRecord.origin.is_(None),
        )
        .scalar()
        or 0
    )


def check_import_limit(db: Session, user: User) -> bool:
    """Return True if the user can import another file within their plan.

    The limit was advertised on the billing page and returned by the API but
    never enforced anywhere — every import endpoint accepted uploads without
    consulting it.
    """
    return count_imports_this_month(db, user) < import_allowance(user)
