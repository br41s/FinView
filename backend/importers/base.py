"""Base types for all importers."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class TxType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    SPINOFF = "SPINOFF"


@dataclass
class ParsedTransaction:
    """Normalized transaction from any broker."""

    tx_type: TxType
    trade_date: date
    isin: str
    name: str
    country: str
    quantity: Decimal
    price: Decimal
    currency: str = "EUR"
    exchange_rate: Decimal = Decimal("1")
    gross_amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    net_amount_eur: Decimal = Decimal("0")

    # Dividend-specific
    withholding_tax: Decimal = Decimal("0")
    withholding_rate: Decimal | None = None
    double_taxation_amount: Decimal | None = None

    # Fiscal pre-calculation from TR
    casilla: int | None = None
    holding_period: str | None = None  # "<1y" or ">1y"
    realized_pl_eur: Decimal | None = None


@dataclass
class ParsedCapitalGain:
    """A matched buy/sell pair with realized P&L (from TR Section III)."""

    isin: str
    name: str
    country: str

    buy_date: date
    buy_quantity: Decimal
    buy_price: Decimal
    buy_fees: Decimal
    buy_total_eur: Decimal

    sell_date: date
    sell_quantity: Decimal
    sell_price: Decimal
    sell_fees: Decimal
    sell_total_eur: Decimal

    realized_pl_eur: Decimal
    holding_period: str  # "<1y" or ">1y"
    casilla: int  # 332 (ganancia) or 337 (pérdida)


@dataclass
class ParsedWithholding:
    """Withholding tax detail from TR Section V."""

    country: str
    isin: str
    name: str
    tx_type: str  # "Dividendo"
    payment_date: date
    currency: str
    income_eur: Decimal
    withholding_eur: Decimal
    withholding_rate: Decimal
    double_taxation_eur: Decimal
    double_taxation_rate: Decimal | None = None


@dataclass
class ParsedCasilla:
    """Pre-calculated tax casilla from TR."""

    modelo: int  # 100 or 714
    casilla: int
    description: str
    amount_eur: Decimal


@dataclass
class ParsedPortfolioHolding:
    """Holdings at year-end from TR Section VII."""

    isin: str
    name: str
    currency: str
    asset_type: str
    country: str
    casilla_714: int
    quantity: Decimal
    avg_q4_balance: Decimal
    value_dec31_eur: Decimal
    fiscal_valuation: Decimal


@dataclass
class TRTaxReport:
    """Complete parsed Trade Republic Tax Report."""

    client_id: str
    period_start: date
    period_end: date
    currency: str
    fiscal_year: int

    dividends: list[ParsedTransaction] = field(default_factory=list)
    capital_gains: list[ParsedCapitalGain] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    withholdings: list[ParsedWithholding] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)
    casillas_modelo_100: list[ParsedCasilla] = field(default_factory=list)
    casillas_modelo_714: list[ParsedCasilla] = field(default_factory=list)
