"""Alternative investments and the CNMV catalog."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# ── Alternative Investments (private banking) ────────────────────────


class AltInvestmentType(PyEnum):
    PRIVATE_EQUITY = "PRIVATE_EQUITY"
    VENTURE_CAPITAL = "VENTURE_CAPITAL"
    REAL_ESTATE = "REAL_ESTATE"
    HEDGE_FUND = "HEDGE_FUND"
    STRUCTURED_PRODUCT = "STRUCTURED_PRODUCT"
    OTHER = "OTHER"


class AltInvestmentStatus(PyEnum):
    ACTIVE = "ACTIVE"
    REALIZED = "REALIZED"


class AltInvestment(Base):
    """A single alternative-investment position held in private banking.

    MVP: manually tracked. Cash flows are stored as running aggregates
    (committed / called / distributed) plus current NAV — enough to derive
    the standard PE/VC metrics (TVPI, DPI, RVPI, unfunded) without a
    movement-level sub-table.
    """

    __tablename__ = "alt_investments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(Enum(AltInvestmentType), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(AltInvestmentStatus), default=AltInvestmentStatus.ACTIVE.value
    )
    manager: Mapped[str] = mapped_column(String(200), default="")  # fund / private bank
    isin: Mapped[str | None] = mapped_column(String(12))  # set when added from the CNMV catalog
    vintage_year: Mapped[int | None] = mapped_column(Integer)
    geography: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    # Cash-flow aggregates (in the position's currency)
    committed_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    called_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    distributed_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    current_nav: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("ix_alt_user", "user_id"),)


class AltInvestmentCatalog(Base):
    """Searchable index of regulated Spanish vehicles (CNMV).

    Populated by services.cnmv_catalog from the free CNMV IIC registry
    (one row per share-class ISIN). Read-only reference data used to power
    the search bar on /alt-investments; selecting a result pre-fills the
    add form. Refreshed periodically in the background, never per request.
    """

    __tablename__ = "alt_investment_catalog"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. CNMV_IIC
    external_id: Mapped[str] = mapped_column(String(20), nullable=False)  # the ISIN

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Enum(AltInvestmentType), nullable=False)
    manager: Mapped[str] = mapped_column(String(255), default="")
    isin: Mapped[str | None] = mapped_column(String(12))
    vehicle_subtype: Mapped[str] = mapped_column(String(20), default="")  # raw CNMV Tipo

    # Enrichment from the CNMV FONDMENS monthly file (FI funds only)
    nav: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # latest per-unit NAV (EUR)
    fund_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # fund AUM (EUR)
    data_date: Mapped[date | None] = mapped_column(Date)  # FONDMENS period

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        Index("ix_alt_catalog_name", "name"),
    )
