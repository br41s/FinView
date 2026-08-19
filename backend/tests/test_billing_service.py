"""Tests for Stripe plan resolution.

The tier a user ends up on is decided in exactly three places: checkout
validation, the checkout-completed webhook and the subscription-change webhook.
All three previously defaulted an unrecognised price to PRO, which turned any
price ID in the Stripe account into a free upgrade. These pin the no-default
behaviour so it cannot regress quietly.
"""

import pytest

from backend.models import SubscriptionTier
from backend.services import billing_service


@pytest.fixture(autouse=True)
def _configured_prices(monkeypatch):
    """Configure two known prices and reset the lazily-built map for each test."""
    monkeypatch.setattr(billing_service.settings, "stripe_price_pro", "price_pro_1", raising=False)
    monkeypatch.setattr(
        billing_service.settings, "stripe_price_unlimited", "price_unl_1", raising=False
    )
    billing_service.PRICE_TO_TIER.clear()
    yield
    billing_service.PRICE_TO_TIER.clear()


# ── price → tier resolution ──────────────────────────────────────────


def test_configured_prices_map_to_their_tiers():
    assert billing_service._tier_for_price("price_pro_1") == SubscriptionTier.PRO.value
    assert billing_service._tier_for_price("price_unl_1") == SubscriptionTier.UNLIMITED.value


@pytest.mark.parametrize("price_id", ["price_someone_elses", "price_test_050", "", None])
def test_unknown_price_resolves_to_none_never_pro(price_id):
    """The regression: an unrecognised price must not fall back to a paid tier."""
    assert billing_service._tier_for_price(price_id) is None


class _FakeUser:
    def __init__(self, tier):
        self.id = 1
        self.subscription_tier = tier
        self.subscription_status = None
        self.subscription_current_period_end = None
        self.stripe_subscription_id = "sub_1"


# ── checkout validation ──────────────────────────────────────────────


def test_checkout_rejects_a_price_that_is_not_ours(monkeypatch):
    """A client-supplied price must never reach Stripe unchecked."""
    def _fail(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("Stripe was called with an unvalidated price")

    monkeypatch.setattr(billing_service.stripe.checkout.Session, "create", _fail)
    monkeypatch.setattr(billing_service, "get_or_create_stripe_customer", _fail)

    with pytest.raises(ValueError, match="Unknown plan"):
        billing_service.create_checkout_session(
            None, _FakeUser(SubscriptionTier.FREE.value), "price_someone_elses"
        )


def test_checkout_accepts_a_configured_price(monkeypatch):
    monkeypatch.setattr(billing_service, "get_or_create_stripe_customer", lambda db, u: "cus_1")
    monkeypatch.setattr(
        billing_service.stripe.checkout.Session,
        "create",
        classmethod(lambda cls, **kw: type("S", (), {"url": "https://stripe.test/checkout"})()),
    )

    url = billing_service.create_checkout_session(None, _FakeUser(SubscriptionTier.FREE.value), "price_pro_1")

    assert url == "https://stripe.test/checkout"


# ── checkout-completed webhook ───────────────────────────────────────


def _subscription(price_id: str):
    return type(
        "Sub",
        (),
        {
            "customer": "cus_1",
            "id": "sub_1",
            "current_period_end": 1_800_000_000,
            "__getitem__": lambda self, k: {
                "items": {"data": [{"price": {"id": price_id}}]}
            }[k],
        },
    )()


def test_checkout_completed_grants_nothing_for_an_unknown_price(monkeypatch):
    monkeypatch.setattr(
        billing_service.stripe.Subscription,
        "retrieve",
        classmethod(lambda cls, sid: _subscription("price_someone_elses")),
    )

    def _no_session():  # pragma: no cover - must not be reached
        raise AssertionError("opened a DB session for an unpriceable subscription")

    monkeypatch.setattr("backend.database.SessionLocal", _no_session)

    result = billing_service._handle_checkout_completed({"subscription": "sub_1"})

    assert result == {"handled": False, "reason": "unknown price"}


def test_checkout_completed_without_a_subscription_is_ignored():
    assert billing_service._handle_checkout_completed({}) == {
        "handled": False,
        "reason": "no subscription in session",
    }


# ── subscription-change webhook ──────────────────────────────────────


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy session returning one user."""

    def __init__(self, user):
        self._user = user
        self.committed = False

    def query(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self._user

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _run_subscription_change(monkeypatch, user, price_id, status="active"):
    monkeypatch.setattr("backend.database.SessionLocal", lambda: _FakeSession(user))
    return billing_service._handle_subscription_change(
        {
            "customer": "cus_1",
            "status": status,
            "current_period_end": 1_800_000_000,
            "items": {"data": [{"price": {"id": price_id}}]},
        }
    )


def test_subscription_change_leaves_tier_untouched_on_unknown_price(monkeypatch):
    """An active subscription on a price we cannot map must not promote anyone."""
    user = _FakeUser(SubscriptionTier.FREE.value)

    _run_subscription_change(monkeypatch, user, "price_someone_elses")

    assert user.subscription_tier == SubscriptionTier.FREE.value


def test_subscription_change_applies_a_configured_price(monkeypatch):
    user = _FakeUser(SubscriptionTier.FREE.value)

    _run_subscription_change(monkeypatch, user, "price_unl_1")

    assert user.subscription_tier == SubscriptionTier.UNLIMITED.value


def test_cancellation_drops_to_free(monkeypatch):
    user = _FakeUser(SubscriptionTier.UNLIMITED.value)

    _run_subscription_change(monkeypatch, user, "price_unl_1", status="canceled")

    assert user.subscription_tier == SubscriptionTier.FREE.value
    assert user.stripe_subscription_id is None
