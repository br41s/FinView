"""SQLAlchemy models for FinView.

Core tables:
- Account: broker accounts (DEGIRO, IBKR, TR)
- Transaction: all buy/sell/dividend/interest/fee operations
- Dividend: dividend payments with withholding info
- TaxLot: FIFO lot tracking for cost basis
- Position: current holdings (derived)
- TaxResult: computed fiscal casillas per year
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Broker(PyEnum):
    BBVA = "BBVA"
    DEGIRO = "DEGIRO"
    ETORO = "ETORO"
    IBKR = "IBKR"
    ING = "ING"
    TR = "TR"


class TransactionType(PyEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    SPINOFF = "SPINOFF"
    CORPORATE_ACTION = "CORPORATE_ACTION"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(Enum(Broker), nullable=False)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    imports: Mapped[list["ImportRecord"]] = relationship(back_populates="account")

    __table_args__ = (UniqueConstraint("broker", "account_id"),)


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
    withholding_tax: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
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
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    broker: Mapped[str | None] = mapped_column(Enum(Broker))
    modelo: Mapped[int] = mapped_column(Integer, nullable=False)  # 100 or 714
    casilla: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(200), default="")
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # TR pre-calculated value for validation
    tr_reference_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    validated: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_tax_year_modelo", "fiscal_year", "modelo"),
        UniqueConstraint("fiscal_year", "broker", "modelo", "casilla"),
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
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")

    broker_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fifo_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjustment_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("fiscal_year", "isin"),
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
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

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
    import_id: Mapped[int | None] = mapped_column(ForeignKey("import_records.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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


class PriceCache(Base):
    """Cache for Yahoo Finance daily prices."""

    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    yahoo_ticker: Mapped[str | None] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    fetched_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("isin", "fetched_date"),
    )
