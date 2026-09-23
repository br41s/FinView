"""The transaction ledger and everything FIFO/fiscal derives from it."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, Broker, TransactionType

if TYPE_CHECKING:
    from .auth import Account

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("import_records.id"))

    type: Mapped[str] = mapped_column(Enum(TransactionType), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[date | None] = mapped_column(Date)

    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str | None] = mapped_column(String(50))

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1)

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    # Positive cash amount withheld. The split is nullable so rows imported
    # before withholding semantics v2 remain identifiable as incomplete.
    withholding_tax: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    domestic_withholding_tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    foreign_withholding_tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    net_amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # For dividends: withholding details
    withholding_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    double_taxation_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    double_taxation_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    # Fiscal classification from TR PDF
    casilla: Mapped[int | None] = mapped_column(Integer)
    holding_period: Mapped[str | None] = mapped_column(String(10))  # "<1y" or ">1y"

    account: Mapped["Account"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_tx_isin_date", "isin", "trade_date"),
        Index("ix_tx_type_date", "type", "trade_date"),
    )


class TaxLot(Base):
    """FIFO lot tracking — each buy creates a lot, sells consume lots FIFO."""

    __tablename__ = "tax_lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    buy_tx_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    sell_tx_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))

    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    quantity_bought: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cost_basis_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Filled when lot is (partially) closed
    quantity_sold: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    proceeds_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    realized_pl_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close_date: Mapped[date | None] = mapped_column(Date)
    holding_period: Mapped[str | None] = mapped_column(String(10))

    buy_tx: Mapped["Transaction"] = relationship(foreign_keys=[buy_tx_id])
    sell_tx: Mapped["Transaction"] = relationship(foreign_keys=[sell_tx_id])


class TaxResult(Base):
    """Computed fiscal results per year per casilla."""

    __tablename__ = "tax_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Owning import. Lets complementary same-year reports for one broker (e.g. a
    # TR DE→ES migration year's pre- and post-migration reports) each keep their
    # own casilla rows; the fiscal layer sums rows per casilla. NULL for rows
    # written before this column existed.
    import_id: Mapped[int | None] = mapped_column(ForeignKey("import_records.id"))
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    broker: Mapped[str | None] = mapped_column(Enum(Broker))
    modelo: Mapped[int] = mapped_column(Integer, nullable=False)  # 100 or 714
    casilla: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(200), default="")
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # TR pre-calculated value for validation
    tr_reference_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    validated: Mapped[bool] = mapped_column(Boolean, default=False)

    # No UNIQUE(user, year, broker, modelo, casilla): a broker can legitimately
    # have two reports for one year (migration). Dedup is procedural — an
    # import's casillas are deleted (by import_id) before it is re-imported.
    __table_args__ = (
        Index("ix_tax_year_modelo", "fiscal_year", "modelo"),
    )


class CrossBrokerLot(Base):
    """FIFO lot matched across all brokers for Spanish IRPF compliance."""

    __tablename__ = "cross_broker_lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")

    buy_tx_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    sell_tx_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    buy_broker: Mapped[str] = mapped_column(String(20), nullable=False)
    sell_broker: Mapped[str] = mapped_column(String(20), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    cost_basis_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    proceeds_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    realized_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    holding_period: Mapped[str | None] = mapped_column(String(10))
    casilla: Mapped[int] = mapped_column(Integer, nullable=False)  # 332 or 337
    calculation_version: Mapped[str | None] = mapped_column(String(10))

    buy_tx: Mapped["Transaction"] = relationship(foreign_keys=[buy_tx_id])
    sell_tx: Mapped["Transaction"] = relationship(foreign_keys=[sell_tx_id])

    __table_args__ = (
        Index("ix_cbl_year_isin", "fiscal_year", "isin"),
        UniqueConstraint("buy_tx_id", "sell_tx_id"),
    )


class FIFOAdjustment(Base):
    """Summary of FIFO difference per ISIN when cross-broker differs from broker."""

    __tablename__ = "fifo_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")

    broker_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fifo_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjustment_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    broker_gains_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    broker_losses_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fifo_gains_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fifo_losses_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    calculation_version: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("user_id", "fiscal_year", "isin"),
    )


class ImportRecord(Base):
    """Track what files have been imported to prevent duplicates."""

    __tablename__ = "import_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    broker: Mapped[str] = mapped_column(Enum(Broker), nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    # Distinguishes co-existing reports for the same broker + fiscal year (e.g.
    # a TR DE→ES migration year has a pre-migration and a post-migration report).
    # Used as part of the year-replacement key. NULL for legacy/other imports.
    source_variant: Mapped[str | None] = mapped_column(String(20))
    # True when this import is an authoritative year-end portfolio snapshot,
    # including the valid case where the snapshot contains zero holdings.
    portfolio_snapshot_complete: Mapped[bool | None] = mapped_column(Boolean)

    account: Mapped["Account"] = relationship(back_populates="imports")

    __table_args__ = (UniqueConstraint("file_hash", "broker"),)


class OptionAssignmentRecord(Base):
    """Detected option assignments from IBKR trade codes.

    Tracks PUT/CALL assignments where the option premium is embedded
    in the resulting stock's cost basis per Spanish IRPF rules.
    IBKR's Realized P/L already accounts for this — this table is
    for audit/display purposes.
    """

    __tablename__ = "option_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_records.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_date: Mapped[date] = mapped_column(Date, nullable=False)
    underlying: Mapped[str] = mapped_column(String(50), nullable=False)
    option_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # PUT / CALL
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stock_isin: Mapped[str] = mapped_column(String(20), default="")
    premium_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    __table_args__ = (
        Index("ix_option_assignments_year", "fiscal_year"),
    )


class PortfolioHolding(Base):
    """Year-end portfolio holdings from broker reports."""

    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_records.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    broker: Mapped[str] = mapped_column(Enum(Broker), nullable=False)

    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    value_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    __table_args__ = (
        Index("ix_holdings_year_isin", "fiscal_year", "isin"),
    )


class DataIssue(Base):
    """Issues detected by the data supervisor during import."""

    __tablename__ = "data_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Direct owner is required for full-audit issues, which are not tied to one
    # import.  Nullable only for rows created before tenant ownership existed.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("import_records.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # info, warning, error
    isin: Mapped[str | None] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | auto_resolved | needs_input | resolved | dismissed
    auto_resolution: Mapped[str | None] = mapped_column(Text)
    resolution_data: Mapped[str | None] = mapped_column(Text)  # JSON with action details

    __table_args__ = (
        Index("ix_data_issues_import", "import_id"),
        Index("ix_data_issues_status", "status"),
    )
