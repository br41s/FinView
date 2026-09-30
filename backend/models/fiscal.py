"""Fiscal profile and manual savings income."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class FiscalProfile(Base):
    """Per-user, per-year taxpayer answers feeding the IRPF savings estimate.

    v1 covers the individual return only. Marital status / joint-vs-separate and
    autonomic-community data are deferred with the general base (Fase 2).
    """

    __tablename__ = "fiscal_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    age: Mapped[int | None] = mapped_column(Integer)
    disability: Mapped[str | None] = mapped_column(String(10))  # None | general | severe
    # Disability is health data (GDPR art. 9): it is stored only with explicit
    # consent, and this is the record of when that consent was given.
    health_data_consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    descendants: Mapped[int] = mapped_column(Integer, default=0)
    # Net general-base income (employment, etc.). Absorbs the personal minimum
    # first; only the remainder lands on the savings base. 0 → full minimum on savings.
    general_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    # Pending savings-base losses carried from prior years (art. 49, 4-year window).
    # Positive magnitudes; compensate current same-type positive balances.
    prior_rcm_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    prior_gp_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (UniqueConstraint("user_id", "fiscal_year"),)


class ManualSavingsIncome(Base):
    """Savings income/withholdings entered by hand (outside broker imports).

    A dedicated table — NOT a `MANUAL` value on the Broker enum — because Broker
    is a native Postgres ENUM and the create_all/ensure_columns migration path
    cannot ADD VALUE to it. `amount_eur` is always a positive magnitude; the
    sign is implied by `category` (LOSS subtracts).
    """

    __tablename__ = "manual_savings_income"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # INTEREST→c27 · DIVIDEND→c29 · GAIN→c332 · LOSS→c337. Legacy "RCM" rows
    # (pre-split) fall back to c29. See _MANUAL_CATEGORY_CASILLA in api/fiscal.py.
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="")
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    withholding_eur: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_manual_savings_user_year", "user_id", "fiscal_year"),)
