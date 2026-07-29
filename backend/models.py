"""SQLAlchemy models for FinView.

Core tables:
- Account: broker accounts (DEGIRO, IBKR, TR)
- Transaction: all buy/sell/dividend/interest/fee operations
- Dividend: dividend payments with withholding info
- TaxLot: FIFO lot tracking for cost basis
- Position: current holdings (derived)
- TaxResult: computed fiscal casillas per year
"""

from datetime import date, datetime, timezone
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

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


class FollowedInstrument(Base):
    """Canonical followed-instrument row — one per (user, ticker), with opt-in
    per-section "lenses". Replaces the separate options/zonas watchlist
    memberships (legacy tables migrated on first boot, see watchlist_service).

    Lens semantics:
    - options_enabled: shows in the options watchlist / agent scope.
    - options_paused:  stays in the options list but the agent skips it
      (maps the legacy WatchlistItem.enabled=False state).
    - zonas_enabled:   has a synced ZonasClaveWatchlistItem child row, which
      still parents ZonasClaveAnalysis via its own FK (kept internal on
      purpose — no FK surgery in prod).
    A row with no lens enabled is pruned.
    """

    __tablename__ = "followed_instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    options_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    options_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    zonas_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)


# NOTE: the legacy `watchlist_items` table (options membership pre-Fase B) has no
# model anymore — watchlist_service.migrate_legacy_watchlists() reads any remaining
# rows via raw SQL and drops the table (B3).


class OptionsSnapshot(Base):
    """Point-in-time options chain metrics for a ticker."""

    __tablename__ = "options_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
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
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.MEDIUM.value)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Macro-regime alignment tag (Phase 2b, informational): aligned/counter/neutral.
    # NULL on pre-2b rows and whenever FRED macro data is unavailable.
    regime_alignment: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (
        Index("ix_opt_alert_user", "user_id", "timestamp"),
    )


class UnusualActivity(Base):
    """Smart money / unusual volume detection."""

    __tablename__ = "unusual_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
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
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tickers_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    alerts_generated: Mapped[int] = mapped_column(Integer, default=0)
    unusual_activities: Mapped[int] = mapped_column(Integer, default=0)
    market_sentiment: Mapped[str | None] = mapped_column(String(20))
    claude_analysis: Mapped[str | None] = mapped_column(Text)
    execution_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class OptionsHiddenPortfolioTicker(Base):
    """Tickers the user has hidden from the Options Monitor portfolio tab."""

    __tablename__ = "options_hidden_portfolio_tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "ticker"),)


# ── Zonas Clave ──────────────────────────────────────────────────────


class ZonasClaveWatchlistItem(Base):
    """Tickers the user wants to analyze for key support/resistance zones."""

    __tablename__ = "zonas_clave_watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
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


class TechnicalSignal(Base):
    """A price approaching a support/resistance zone, scored for break probability.

    Owned by (user, ticker) rather than by a watchlist row: unlike
    ZonasClaveAnalysis, these outlive the watchlist membership that produced them
    (removing a ticker shouldn't erase the record of what it signalled), so
    there's deliberately no FK to zonas_clave_watchlist and no cascade.

    **Every scored candidate is stored, not just the alerting ones.** The
    ALERT_THRESHOLD is an uncalibrated guess — an LLM's "73%" is not a
    probability. Keeping the sub-threshold rows is the only way to ever check
    whether >70 actually breaks more often than <70 and move the cut on evidence.
    Same shape of reasoning as the Phase 2b regime instrumentation.
    """

    __tablename__ = "technical_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Zone context
    zone_level: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(20), default="")  # historical label
    zone_strength: Mapped[float | None] = mapped_column(Numeric(8, 4))
    zone_touches: Mapped[int | None] = mapped_column(Integer)
    price_at_signal: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    distance_pct: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)

    # from_below / from_above — which side price is approaching from. Derived from
    # price vs level, NOT from zone_type, which goes stale on flipped levels.
    approach: Mapped[str] = mapped_column(String(12), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # BULLISH|BEARISH

    # NULL when the LLM was unavailable/unparseable — never coerce to 0, that
    # would read as "certainly won't break" in any later calibration.
    break_probability: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(String(200))
    alerted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped["User"] = relationship()

    __table_args__ = (Index("ix_tech_signal_user_ticker", "user_id", "ticker"),)


# ── Backtesting ──────────────────────────────────────────────────────


class BacktestOutcome(PyEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    NEUTRAL = "NEUTRAL"  # price moved < 0.5 %


class BacktestSignal(Base):
    """Record of an alert signal with outcome tracking at +1D, +3D, +7D.

    Lifecycle:
        1. Created when an alert fires during a cycle (outcome fields = NULL).
        2. A background evaluator fills price_at_1d/3d/7d and outcome after
           the respective trading days have elapsed.
    """

    __tablename__ = "backtest_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Signal context
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. HIGH_IV, HIGH_PUT_CALL_RATIO, IV_SKEW, UNUSUAL_VOLUME
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # BULLISH or BEARISH — derived from alert type at record time
    price_at_signal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    alert_message: Mapped[str] = mapped_column(Text, default="")

    # Outcome prices (filled by evaluator)
    price_at_1d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    price_at_3d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    price_at_7d: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))

    # Accuracy at each horizon (NULL until evaluated)
    outcome_1d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    outcome_3d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    outcome_7d: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))

    # Macro-regime context frozen at record time (Phase 2b, instrumentation only).
    # regime: risk_on/neutral/risk_off; regime_alignment: aligned/counter/neutral.
    # NULL on pre-2b rows and whenever FRED macro data is unavailable.
    regime: Mapped[str | None] = mapped_column(String(12))
    regime_alignment: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (
        Index("ix_bt_user_ticker", "user_id", "ticker"),
        Index("ix_bt_recorded_at", "recorded_at"),
    )


# ── Geo-Intel (WorldHawk integration) ────────────────────────────────


class GeoDisplayCategory(PyEnum):
    """Coarse category surfaced to the frontend GeoSignal contract.

    The pipeline matches on a finer ``event_type`` (e.g. ``armed_conflict``);
    this collapses ~28 matcher categories into the 7 buckets the map UI uses.
    Values are lowercase to match the frontend type literal directly.
    """

    EARTHQUAKE = "earthquake"
    CYCLONE = "cyclone"
    FIRE = "fire"
    VOLCANO = "volcano"
    CONFLICT = "conflict"
    MARITIME = "maritime"
    WEATHER = "weather"


class GeoDirection(PyEnum):
    """Market thesis direction for a geo signal (frontend contract = lowercase)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class GeoSignalStatus(PyEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class GeoHorizon(PyEnum):
    """Checkpoint horizons for geo outcome tracking (union of all backtests)."""

    H1 = "1h"
    H6 = "6h"
    D1 = "1d"
    D3 = "3d"
    D7 = "7d"


def _geo_enum(enum_cls: type[PyEnum]) -> Enum:
    """Enum column that persists by VALUE, not member name.

    The geo enums use lowercase values (e.g. EARTHQUAKE="earthquake") to match the
    frontend GeoSignal contract, so name != value. SQLAlchemy defaults to storing
    the name; values_callable flips it to the value.
    """
    return Enum(enum_cls, values_callable=lambda obj: [e.value for e in obj])


class GeoSignal(Base):
    """A geopolitical / natural-event signal produced by the geo pipeline.

    Per-user (mirrors options / zonas-clave): the pipeline runs per user so each
    user's watchlist/notification scope is independent. ``event_type`` is the
    fine matcher category; ``display_category`` is the coarse UI bucket.
    """

    __tablename__ = "geo_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Classification
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # matcher category
    display_category: Mapped[str] = mapped_column(_geo_enum(GeoDisplayCategory), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # ingest feed key
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)  # source id (dedup)

    # Event content
    headline: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="")
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)

    # Scoring (frontend GeoSignal contract)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # 0-1
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 0-10
    direction: Mapped[str] = mapped_column(_geo_enum(GeoDirection), nullable=False)
    status: Mapped[str] = mapped_column(
        _geo_enum(GeoSignalStatus), default=GeoSignalStatus.ACTIVE.value
    )

    # Provenance
    matched_rule_ids: Mapped[str | None] = mapped_column(Text)  # JSON list of rule_id
    raw_json: Mapped[str | None] = mapped_column(Text)  # normalized source event

    tickers: Mapped[list["GeoSignalTicker"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )
    checkpoints: Mapped[list["GeoCheckpoint"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_geo_sig_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "source", "external_id", name="uq_geo_sig_dedup"),
    )


class GeoSignalTicker(Base):
    """A ticker affected by a geo signal, with its per-ticker thesis direction."""

    __tablename__ = "geo_signal_tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("geo_signals.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(_geo_enum(GeoDirection), nullable=False)
    # Price at signal time (per-ticker), used for basket outcome scoring.
    price_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    # False when prices.py cannot resolve the symbol (futures / foreign listings).
    resolved: Mapped[bool] = mapped_column(Boolean, default=True)

    signal: Mapped["GeoSignal"] = relationship(back_populates="tickers")


class GeoCheckpoint(Base):
    """Outcome-tracking checkpoint for a geo signal at one horizon.

    Parallel to BacktestSignal's per-horizon columns but row-per-horizon so it
    can carry the full union (+1h/+6h/+1d/+3d/+7d), which the options backtest
    columns cannot. Reuses BacktestOutcome for the verdict.
    """

    __tablename__ = "geo_checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("geo_signals.id"), nullable=False, index=True
    )
    horizon: Mapped[str] = mapped_column(_geo_enum(GeoHorizon), nullable=False)
    target_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Basket score 0-100 (% of non-neutral tickers that moved as predicted),
    # the BacktestOutcome verdict, and a human-readable per-ticker breakdown.
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    outcome: Mapped[str | None] = mapped_column(Enum(BacktestOutcome))
    detail: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)

    signal: Mapped["GeoSignal"] = relationship(back_populates="checkpoints")

    __table_args__ = (
        UniqueConstraint("signal_id", "horizon", name="uq_geo_checkpoint_horizon"),
        Index("ix_geo_chk_user_target", "user_id", "target_at"),
    )


class GeoRuleStat(Base):
    """Static rule definition + learned tuning for the 63 geo-economic rules.

    Global (no user_id): the rules are universal IP and tuning aggregates across
    all outcomes. Seeded idempotently from the rule table in P4. ``base_confidence``
    is static; ``confidence_mod`` is the auditor-learned adjustment applied at
    scoring time (effective = base_confidence + confidence_mod).
    """

    __tablename__ = "geo_rule_stats"

    rule_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    base_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    correct_signals: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence_mod: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


# ── Exchange Rates (ECB) ─────────────────────────────────────────────


class ExchangeRate(Base):
    """ECB daily reference rates. rate = units of `currency` per 1 EUR.

    Populated incrementally from the ECB eurofxref feed by
    services.exchange_rates. Used as an official-rate fallback for IRPF
    conversions when a broker file omits the rate or for manual entries.
    """

    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="ECB")

    __table_args__ = (
        UniqueConstraint("rate_date", "currency"),
        Index("ix_fx_ccy_date", "currency", "rate_date"),
    )


class FredRate(Base):
    """FRED (St. Louis Fed) risk-free rate series cache.

    rate = annualized risk-free rate as a decimal (0.053 = 5.3%). One row per
    (series_id, rate_date). Populated incrementally from the FRED API by
    services.fred_rates and used as the risk-free input for Black-Scholes
    Greeks, resolved per option currency. Empty/stale → Greeks fall back to
    per-currency constants (no-op when FINVIEW_FRED_API_KEY is unset).
    """

    __tablename__ = "fred_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    __table_args__ = (
        UniqueConstraint("series_id", "rate_date"),
        Index("ix_fred_series_date", "series_id", "rate_date"),
    )


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
