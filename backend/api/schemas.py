"""Pydantic schemas for API responses."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DataIssueOut(BaseModel):
    id: int
    issue_type: str
    severity: str
    isin: str | None
    name: str
    description: str
    status: str
    auto_resolution: str | None

    model_config = {"from_attributes": True}


class ImportResult(BaseModel):
    status: str
    message: str | None = None
    import_id: int | None = None
    fiscal_year: int | None = None
    counts: dict[str, int] | None = None
    issues: list[DataIssueOut] = []


class TransactionOut(BaseModel):
    id: int
    type: str
    trade_date: date
    isin: str | None
    name: str
    country: str | None
    quantity: Decimal
    price: Decimal
    currency: str
    gross_amount: Decimal
    fees: Decimal
    withholding_tax: Decimal
    net_amount_eur: Decimal
    casilla: int | None
    holding_period: str | None

    model_config = {"from_attributes": True}


class DividendSummary(BaseModel):
    isin: str
    name: str
    country: str | None
    total_gross_eur: Decimal
    total_withholding_eur: Decimal
    total_net_eur: Decimal
    payment_count: int


class CapitalGainOut(BaseModel):
    id: int
    isin: str
    name: str
    buy_date: date
    sell_date: date
    quantity: Decimal
    cost_basis_eur: Decimal
    proceeds_eur: Decimal
    realized_pl_eur: Decimal
    holding_period: str | None

    model_config = {"from_attributes": True}


class CasillaOut(BaseModel):
    modelo: int
    casilla: int
    description: str
    amount_eur: Decimal
    broker: str | None

    model_config = {"from_attributes": True}


class BrokerAmount(BaseModel):
    broker: str
    amount_eur: Decimal


class AggregatedCasillaOut(BaseModel):
    modelo: int
    casilla: int
    description: str
    amount_eur: Decimal
    brokers: list[BrokerAmount]
    fifo_adjustment_eur: Decimal | None = None
    tr_reference_amount: Decimal | None = None
    validation_status: str | None = None  # "match" | "mismatch" | None


class CrossBrokerLotOut(BaseModel):
    id: int
    fiscal_year: int
    isin: str
    name: str
    buy_broker: str
    sell_broker: str
    quantity: Decimal
    cost_basis_eur: Decimal
    proceeds_eur: Decimal
    realized_pl_eur: Decimal
    holding_period: str | None
    casilla: int

    model_config = {"from_attributes": True}


class FIFOAdjustmentOut(BaseModel):
    id: int
    fiscal_year: int
    isin: str
    name: str
    broker_pl_eur: Decimal
    fifo_pl_eur: Decimal
    adjustment_eur: Decimal
    note: str

    model_config = {"from_attributes": True}


class FiscalSummary(BaseModel):
    fiscal_year: int
    total_dividends_gross: Decimal
    total_dividends_net: Decimal
    total_withholdings: Decimal
    total_gains: Decimal
    total_losses: Decimal
    net_capital_gains: Decimal
    casillas: list[AggregatedCasillaOut]


class AccountOut(BaseModel):
    id: int
    broker: str
    account_id: str
    name: str
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportRecordOut(BaseModel):
    id: int
    filename: str
    broker: str
    fiscal_year: int | None
    imported_at: datetime
    record_count: int

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    total_transactions: int
    total_dividends_eur: Decimal
    total_gains_eur: Decimal
    total_losses_eur: Decimal
    net_pl_eur: Decimal
    accounts: int
    imports: int
    fiscal_years: list[int]


class OptionAssignmentOut(BaseModel):
    id: int
    fiscal_year: int
    assignment_date: date
    underlying: str
    option_symbol: str
    option_type: str  # PUT / CALL
    strike: Decimal
    stock_quantity: Decimal
    stock_isin: str
    premium_eur: Decimal


class ResolveIssueRequest(BaseModel):
    action: str  # "dismiss", "resolve", "add_data"
    data: dict | None = None  # action-specific payload


# --- Cross-validation ---

class CrossValidationRow(BaseModel):
    modelo: int
    casilla: int
    description: str
    finview_amount: Decimal
    compare_amount: Decimal  # amount actually compared (TR-only for multi-broker casillas)
    tr_amount: Decimal | None
    difference: Decimal | None
    status: str  # "match" | "mismatch" | "no_tr_data"
    is_multi_broker: bool
    brokers: list[BrokerAmount]


class CrossValidationResult(BaseModel):
    fiscal_year: int
    rows: list[CrossValidationRow]
    total_match: int
    total_mismatch: int
    total_no_ref: int


# --- Multi-year comparison ---

class YearlyMetrics(BaseModel):
    fiscal_year: int
    dividends_gross: Decimal
    gains: Decimal
    losses: Decimal
    net_capital: Decimal
    withholdings: Decimal
    brokers: int
    positions: int


class YearlyComparisonResult(BaseModel):
    years: list[YearlyMetrics]


# ── Options Monitor Schemas ──────────────────────────────────────────


class WatchlistItemIn(BaseModel):
    ticker: str
    name: str = ""


class WatchlistItemOut(BaseModel):
    id: int
    ticker: str
    name: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OptionsSnapshotOut(BaseModel):
    id: int
    timestamp: datetime
    ticker: str
    current_price: Decimal
    call_volume: int
    put_volume: int
    call_open_interest: int
    put_open_interest: int
    put_call_ratio_volume: Decimal | None
    put_call_ratio_oi: Decimal | None
    avg_call_iv: Decimal | None
    avg_put_iv: Decimal | None
    historical_volatility: Decimal | None
    iv_skew: Decimal | None
    market_sentiment: str | None

    model_config = {"from_attributes": True}


class OptionsAlertOut(BaseModel):
    id: int
    timestamp: datetime
    ticker: str
    alert_type: str
    message: str
    severity: str
    acknowledged: bool

    model_config = {"from_attributes": True}


class UnusualActivityOut(BaseModel):
    id: int
    timestamp: datetime
    ticker: str
    option_type: str
    strike: Decimal
    expiration: str
    volume: int
    open_interest: int
    vol_oi_ratio: Decimal
    implied_volatility: Decimal | None
    last_price: Decimal | None

    model_config = {"from_attributes": True}


class AgentCycleResult(BaseModel):
    status: str
    cycle: int | None = None
    tickers_analyzed: int | None = None
    snapshots_saved: int | None = None
    alerts: int | None = None
    unusual: int | None = None
    execution_time: float | None = None
    claude_analysis: str | None = None


class AgentStatusOut(BaseModel):
    running: bool
    interval_minutes: int
    last_cycle: datetime | None = None
    total_cycles: int = 0


# ── Zonas Clave Schemas ──────────────────────────────────────────────


class ZonasClaveWatchlistItemIn(BaseModel):
    ticker: str
    name: str = ""


class ZcZoneOut(BaseModel):
    level: float
    zone_type: str       # "support" | "resistance"
    strength: float      # 0–1 normalized score
    touches: int
    volume_score: float


class ZonasClaveWatchlistItemOut(BaseModel):
    id: int
    ticker: str
    name: str
    added_at: datetime

    model_config = {"from_attributes": True}


class ZonasClaveAnalysisOut(BaseModel):
    id: int
    watchlist_item_id: int
    timestamp: datetime
    zones: list[ZcZoneOut]
    trend_bias_bullish_pct: float | None
    trend_bias_bearish_pct: float | None
    rsi: float | None
    macd_signal: str | None
    macd_histogram: float | None
    current_price: float | None
    price_history: list[dict]

    model_config = {"from_attributes": True}


class ZonasClaveSchedulerStatus(BaseModel):
    running: bool
    last_run: datetime | None = None
    total_items: int = 0
