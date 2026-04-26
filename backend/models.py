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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Stripe / subscription
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    subscription_tier: Mapped[str] = mapped_column(
        Enum(SubscriptionTier), default=SubscriptionTier.FREE.value
    )
    subscription_status: Mapped[str | None] = mapped_column(Enum(SubscriptionStatus))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime)

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    broker: Mapped[str] = mapped_column(Enum(Broker), nullable=False)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User | None"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    imports: Mapped[list["ImportRecord"]] = relationship(back_populates="account")

    __table_args__ = (UniqueConstraint("broker", "account_id", "user_id"),)


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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, default=1)
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
        UniqueConstraint("user_id", "fiscal_year", "broker", "modelo", "casilla"),
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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, default=1)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")

    broker_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fifo_pl_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjustment_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
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
    original_currency: Mapped[str | None] = mapped_column(String(3))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fetched_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("isin", "fetched_date"),
    )


# ── Options Monitor Models ───────────────────────────────────────────


class AlertSeverity(PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class WatchlistItem(Base):
    """Tickers the user wants to monitor for options activity."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "ticker"),
    )


class OptionsSnapshot(Base):
    """Point-in-time options chain metrics for a ticker."""

    __tablename__ = "options_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    call_volume: Mapped[int] = mapped_column(Integer, default=0)
    put_volume: Mapped[int] = mapped_column(Integer, default=0)
    call_open_interest: Mapped[int] = mapped_column(Integer, default=0)
    put_open_interest: Mapped[int] = mapped_column(Integer, default=0)
    put_call_ratio_volume: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    put_call_ratio_oi: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    avg_call_iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    avg_put_iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    historical_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    iv_skew: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    market_sentiment: Mapped[str | None] = mapped_column(String(20))

    # Full chain data stored as JSON text for detail views
    chain_data: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_opt_snap_user_ticker", "user_id", "ticker"),
    )


class OptionsAlert(Base):
    """Generated alerts from options monitoring cycles."""

    __tablename__ = "options_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.MEDIUM.value)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_opt_alert_user", "user_id", "timestamp"),
    )


class UnusualActivity(Base):
    """Smart money / unusual volume detection."""

    __tablename__ = "unusual_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # CALL / PUT
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expiration: Mapped[str] = mapped_column(String(10), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False)
    vol_oi_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))


class OptionsAgentLog(Base):
    """Log of each agent cycle execution."""

    __tablename__ = "options_agent_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tickers_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    alerts_generated: Mapped[int] = mapped_column(Integer, default=0)
    unusual_activities: Mapped[int] = mapped_column(Integer, default=0)
    market_sentiment: Mapped[str | None] = mapped_column(String(20))
    claude_analysis: Mapped[str | None] = mapped_column(Text)
    execution_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


# ── Zonas Clave ──────────────────────────────────────────────────────


class ZonasClaveWatchlistItem(Base):
    """Tickers the user wants to analyze for key support/resistance zones."""

    __tablename__ = "zonas_clave_watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship()
    analyses: Mapped[list["ZonasClaveAnalysis"]] = relationship(
        back_populates="watchlist_item", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)


class ZonasClaveAnalysis(Base):
    """Computed support/resistance zones, indicators and price history for one ticker."""

    __tablename__ = "zonas_clave_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(
        ForeignKey("zonas_clave_watchlist.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    zones: Mapped[str | None] = mapped_column(Text)           # JSON list of zone dicts
    trend_bias_bullish_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    trend_bias_bearish_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    rsi: Mapped[float | None] = mapped_column(Numeric(8, 4))
    macd_signal: Mapped[str | None] = mapped_column(String(20))  # bullish|bearish|neutral
    macd_histogram: Mapped[float | None] = mapped_column(Numeric(10, 6))
    price_history: Mapped[str | None] = mapped_column(Text)   # JSON [{date,close,volume}]
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 6))

    watchlist_item: Mapped["ZonasClaveWatchlistItem"] = relationship(back_populates="analyses")

    __table_args__ = (Index("ix_zc_analysis_item_ts", "watchlist_item_id", "timestamp"),)
