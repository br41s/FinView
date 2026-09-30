"""Users, billing tier and broker accounts."""

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Broker

if TYPE_CHECKING:
    from .ledger import ImportRecord, Transaction

class SubscriptionTier(PyEnum):
    FREE = "FREE"
    PRO = "PRO"
    UNLIMITED = "UNLIMITED"


class SubscriptionStatus(PyEnum):
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    INCOMPLETE = "INCOMPLETE"


class User(Base):
    """Application user (multi-tenant owner of accounts)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Stripe / subscription
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    subscription_tier: Mapped[str] = mapped_column(
        Enum(SubscriptionTier), default=SubscriptionTier.FREE.value
    )
    subscription_status: Mapped[str | None] = mapped_column(Enum(SubscriptionStatus))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime)

    # Proof of consent (GDPR art. 7.1): which version of the terms and privacy
    # policy the user accepted, and when. NULL = registered before acceptance was
    # recorded; the app asks those users to accept on their next visit.
    terms_version: Mapped[str | None] = mapped_column(String(20))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime)

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    broker: Mapped[str] = mapped_column(Enum(Broker), nullable=False)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User | None"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    imports: Mapped[list["ImportRecord"]] = relationship(back_populates="account")

    __table_args__ = (UniqueConstraint("broker", "account_id", "user_id"),)
