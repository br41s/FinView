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
    resolution_data: str | None = None

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
    domestic_withholding_tax: Decimal | None = None
    foreign_withholding_tax: Decimal | None = None
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
    validation_status: str | None = None


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
    calculation_version: str | None

    model_config = {"from_attributes": True}


class FIFOAdjustmentOut(BaseModel):
    id: int
    fiscal_year: int
    isin: str
    name: str
    broker_pl_eur: Decimal
    fifo_pl_eur: Decimal
    adjustment_eur: Decimal
    broker_gains_eur: Decimal | None
    broker_losses_eur: Decimal | None
    fifo_gains_eur: Decimal | None
    fifo_losses_eur: Decimal | None
    calculation_version: str | None
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
    status: str  # currently "no_independent_data"
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
    regime_alignment: str | None = None  # aligned/counter/neutral (Phase 2b)

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


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AskIn(BaseModel):
    question: str
    history: list[ChatMessage] = []


class AskOut(BaseModel):
    answer: str


class AgentCycleResult(BaseModel):
    status: str
    cycle: int | None = None
    tickers_analyzed: int | None = None
    snapshots_saved: int | None = None
    alerts: int | None = None
    unusual: int | None = None
    execution_time: float | None = None
    claude_analysis: str | None = None
    ai_error: str | None = None


class AgentStatusOut(BaseModel):
    running: bool
    external_scheduler: bool = False
    interval_minutes: int
    last_cycle: datetime | None = None
    total_cycles: int = 0


class LastAnalysisOut(BaseModel):
    timestamp: datetime | None = None
    cycle: int | None = None
    tickers_analyzed: int | None = None
    alerts: int | None = None
    unusual: int | None = None
    market_sentiment: str | None = None
    claude_analysis: str | None = None
    ai_configured: bool = False
    # Macro-regime annotation (FRED). None when no macro data is cached.
    macro: dict | None = None


class BacktestSignalOut(BaseModel):
    id: int
    recorded_at: datetime
    ticker: str
    signal_type: str
    direction: str
    price_at_signal: Decimal
    alert_message: str
    price_at_1d: Decimal | None
    price_at_3d: Decimal | None
    price_at_7d: Decimal | None
    outcome_1d: str | None
    outcome_3d: str | None
    outcome_7d: str | None

    model_config = {"from_attributes": True}


class BacktestHorizonStats(BaseModel):
    evaluated: int
    correct: int
    incorrect: int
    neutral: int
    accuracy_pct: float | None


class BacktestSignalTypeStats(BaseModel):
    correct: int
    total: int
    accuracy_pct: float | None


class BacktestStatsOut(BaseModel):
    total: int
    evaluated: int
    by_horizon: dict[str, BacktestHorizonStats]
    by_signal_type: dict[str, BacktestSignalTypeStats]
    # aligned/counter/neutral → accuracy at 7d (Phase 2b). Empty until signals
    # recorded with a regime have been evaluated.
    by_alignment: dict[str, BacktestSignalTypeStats] = {}


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


class TechnicalSignalOut(BaseModel):
    id: int
    created_at: datetime
    ticker: str
    zone_level: float
    zone_type: str
    zone_strength: float | None
    zone_touches: int | None
    price_at_signal: float
    distance_pct: float
    approach: str
    direction: str
    # None when the LLM was unavailable — not a low probability. Consumers must
    # render it as "sin puntuar", never as 0.
    break_probability: int | None
    rationale: str | None
    alerted: bool

    model_config = {"from_attributes": True}


class ZonasClaveSchedulerStatus(BaseModel):
    running: bool
    external_scheduler: bool = False
    last_run: datetime | None = None
    total_items: int = 0


# ── Geo-Intel ────────────────────────────────────────────────────────


class GeoSignalTickerOut(BaseModel):
    symbol: str
    direction: str  # bullish|bearish|neutral
    priceAtSignal: float | None = None
    # For a Spanish retail account: cash_eu | options_only (US ETF, IBKR options) |
    # not_tradable — with the nearest EU-listed alternative when one exists.
    tradability: str = "cash_eu"
    alternate: str | None = None


class GeoRuleOut(BaseModel):
    """Matched rule that explains why a signal fired (what/why)."""

    id: str
    description: str  # what happened, e.g. "Major Chilean earthquake disrupts copper supply"
    thesis: str  # rationale, e.g. "Copper supply disruption → COPX up, miners down"
    confidence: float  # rule's base confidence, 0-1
    category: str = ""  # event bucket the rule belongs to, e.g. "earthquake"
    trigger: str = ""  # the condition that fired, e.g. "mag>=6.5 near chile_mining"
    scope: str = ""  # site | local | regional | global — how wide the event is


class GeoCheckpointOut(BaseModel):
    horizon: str  # 1h|6h|1d|3d|7d
    targetAt: datetime
    score: float | None = None  # 0-100, % of tickers that moved as predicted
    outcome: str | None = None  # CORRECT|INCORRECT|NEUTRAL, None = not yet evaluated
    detail: str | None = None  # per-ticker % move breakdown
    evaluatedAt: datetime | None = None


class GeoSignalOut(BaseModel):
    """Matches the frontend GeoSignal contract (camelCase, lowercase enums)."""

    id: str
    headline: str
    category: str  # coarse display category (earthquake|cyclone|fire|…)
    eventType: str  # fine matcher category
    lat: float
    lng: float
    location: str
    importance: int  # 0-100
    confidence: float  # 0-1
    riskScore: float  # 0-10
    direction: str  # bullish|bearish|neutral
    tickers: list[GeoSignalTickerOut]
    rules: list[GeoRuleOut] = []
    checkpoints: list[GeoCheckpointOut] = []
    timestamp: datetime
    notifiedAt: datetime | None = None  # when a channel actually delivered it
    status: str  # active|resolved
    source: str = ""  # ingest feed key (usgs|EONET|gdelt|…)
    sourceUrl: str | None = None  # link to the underlying source event, when captured


class GeoCycleRunOut(BaseModel):
    """The last execution of the geo pipeline — its liveness, not its output.

    The date of the newest signal cannot distinguish a stopped pipeline from a
    quiet one, which is why Ideas could sit dead for weeks looking merely calm.
    """

    started_at: datetime
    finished_at: datetime
    ok: bool
    events: int = 0
    new_signals: int = 0
    notified: int = 0  # signals that reached at least one channel
    notify_failed: int = 0  # signals the gate selected that no channel delivered
    checkpoints_evaluated: int = 0
    persist_failures: int = 0
    sources: dict[str, int] = {}
    error: str | None = None


class GeoSchedulerStatus(BaseModel):
    running: bool
    external_scheduler: bool = False
    interval_minutes: int
    total_signals: int = 0
    active_signals: int = 0
    last_signal_at: datetime | None = None
    last_run: GeoCycleRunOut | None = None


class GeoRunResult(BaseModel):
    status: str
    events: int | None = None
    new_signals: int | None = None
    notified: int | None = None


class GeoHorizonAccuracy(BaseModel):
    """Outcome matrix for one checkpoint horizon over the requested window."""

    correct: int = 0
    incorrect: int = 0
    neutral: int = 0
    pending: int = 0
    # correct / (correct + incorrect). NEUTRAL is excluded on purpose: it means
    # "nothing measurable moved", not a thesis that failed, so counting it as a
    # miss would drag every hit rate toward zero the way the dots already do.
    # None when the denominator is 0 — no measurement is not 0 %.
    accuracy: float | None = None


class GeoRuleAccuracy(BaseModel):
    """One `geo_rule_stats` row: what the auditor has learned about a rule.

    Nothing exposed this table before, so the learning loop was unobservable:
    two rules sat pinned at the -0.30 `confidenceMod` floor with no way to see
    it, let alone why.
    """

    ruleId: str
    category: str
    baseConfidence: float
    confidenceMod: float  # auditor-learned adjustment, -0.30..+0.30
    totalSignals: int
    correctSignals: int
    accuracy: float | None = None  # as stored by the auditor; None = never scored


class GeoAccuracyOut(BaseModel):
    """Per-horizon hit rate plus the per-rule learning table."""

    since: datetime
    horizons: dict[str, GeoHorizonAccuracy]  # keyed 1h|6h|1d|3d|7d
    rules: list[GeoRuleAccuracy]  # sorted by totalSignals desc


class GeoRuleStatsReset(BaseModel):
    reset: int  # rows zeroed


# ── Fiscal onboarding (savings-base IRPF estimate, v1 individual) ────────────
class FiscalProfileIn(BaseModel):
    age: int | None = None
    disability: str | None = None  # None | "general" | "severe"
    descendants: int = 0
    general_base: Decimal = Decimal("0")
    prior_rcm_loss: Decimal = Decimal("0")  # pending prior-year RCM losses (art. 49)
    prior_gp_loss: Decimal = Decimal("0")   # pending prior-year G/P losses (art. 49)


class FiscalProfileOut(FiscalProfileIn):
    fiscal_year: int
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ManualSavingsIncomeIn(BaseModel):
    fiscal_year: int
    category: str  # RCM | GAIN | LOSS
    label: str = ""
    amount_eur: Decimal
    withholding_eur: Decimal = Decimal("0")


class ManualSavingsIncomeOut(ManualSavingsIncomeIn):
    id: int

    model_config = {"from_attributes": True}


class SavingsEstimateOut(BaseModel):
    fiscal_year: int
    rates_year_used: int
    rcm_net: Decimal
    gp_net: Decimal
    savings_base: Decimal
    rcm_carryforward: Decimal
    gp_carryforward: Decimal
    prior_rcm_loss_applied: Decimal
    prior_gp_loss_applied: Decimal
    personal_minimum: Decimal
    minimum_on_savings: Decimal
    gross_quota: Decimal
    quota: Decimal
    withholdings: Decimal
    cash_withholdings: Decimal = Decimal("0")
    domestic_withholdings: Decimal = Decimal("0")
    double_taxation_credit: Decimal = Decimal("0")
    double_taxation_credit_applied: Decimal = Decimal("0")
    withholding_breakdown_complete: bool = True
    incomplete_withholding_transactions: int = 0
    result: Decimal  # >0 a ingresar · <0 a devolver
    brackets: list[dict]
    casillas: dict[str, Decimal]  # source casilla totals (brokers + manual)


# ── Charts ───────────────────────────────────────────────────────────
#
# The chart endpoints fed the dashboard as bare dicts, with the matching shapes
# hand-declared in frontend/src/lib/types.ts and hand-cast at each call site.
# CLAUDE.md forbids breaking an API contract without updating those types, but
# nothing connected the two: renaming a label in a SQL aggregate rendered blank
# widgets with no type error, no failing test and a green build. These models
# make the backend the single source of truth and put the shapes in the OpenAPI
# schema.
#
# Money is emitted as a decimal string, not a float, so the exact value the
# fiscal engine computed survives the wire unrounded. The fields below are `str`
# because that is what the endpoints already send — do not "fix" them to float.


class DividendsByCountryOut(BaseModel):
    country: str
    gross: str
    withholding: str
    net: str
    count: int


class DividendsMonthlyOut(BaseModel):
    month: str
    gross: str
    withholding: str
    net: str
    count: int


class TopDividendPayerOut(BaseModel):
    isin: str | None
    name: str
    country: str | None
    gross: str
    withholding: str
    net: str
    count: int


class CapitalGainsBreakdownOut(BaseModel):
    isin: str | None
    name: str
    gains: str
    losses: str
    net: str
    trades: int


class PatrimonioCompositionOut(BaseModel):
    casilla: int
    description: str | None
    amount: str
    fiscal_year: int


class DividendYieldOut(BaseModel):
    isin: str
    name: str
    ticker: str | None
    country: str | None
    total_dividends: str
    total_invested: str
    qty_remaining: str
    latest_price: str
    current_value: str
    yield_on_cost: str
    yield_on_value: str
    payment_count: int
    currency: str
    # Present only for positions priced in a non-EUR currency.
    original_price: str | None = None
    fx_rate: str | None = None


class WithholdingsByCountryOut(BaseModel):
    country: str
    gross: str
    withholding: str
    net: str
    effective_rate: str


class CompanyDividendsYearlyOut(BaseModel):
    isin: str | None
    name: str
    ticker: str
    # year → gross dividends that year, as a decimal string.
    years: dict[str, str]
    total: str


class OhlcBarOut(BaseModel):
    date: str
    # Epoch seconds, sent only for intraday intervals where several bars share
    # one calendar day.
    time: int | None = None
    open: float
    high: float
    low: float
    close: float
    volume: int


class FundamentalsOut(BaseModel):
    """yfinance `.info` snapshot — every field optional.

    `.info` is scraped, has no stable contract, and returns a mostly-empty dict
    for plenty of valid tickers. An empty object means "nothing to show", not
    "bad ticker": the caller hides the section rather than rendering zeros.
    """

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    profit_margins: float | None = None
    debt_to_equity: float | None = None
    return_on_equity: float | None = None
    revenue_growth: float | None = None
    beta: float | None = None
