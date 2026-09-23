"""Base types and the parsing helpers every importer shares."""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

# ── Shared parsing helpers ─────────────────────────────────────────────
# Each importer used to carry its own copy of these (seven file hashes, six
# European-decimal parsers, three DD/MM/YYYY parsers) and they had drifted.

ISIN_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}\d")


def file_sha256(paths: str | Path | Iterable[Path]) -> str:
    """SHA-256 used for import dedup. Several paths hash in sorted order."""
    if isinstance(paths, (str, Path)):
        paths = [Path(paths)]
    h = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
    return h.hexdigest()


def parse_eur_decimal(s: str) -> Decimal:
    """European format: '1.384,27€' → Decimal('1384.27')."""
    s = s.strip().rstrip("€").strip()
    return Decimal(s.replace(".", "").replace(",", "."))


def parse_dmy(s: str) -> date:
    """'DD/MM/YYYY' → date."""
    return datetime.strptime(s.strip(), "%d/%m/%Y").date()


# ── Shared country resolution ──────────────────────────────────────────

COUNTRY_NAMES: dict[str, str] = {
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Bélgica",
    "BR": "Brasil",
    "CA": "Canadá",
    "CH": "Suiza",
    "CN": "China",
    "DE": "Alemania",
    "DK": "Dinamarca",
    "ES": "España",
    "FI": "Finlandia",
    "FR": "Francia",
    "GB": "Reino Unido",
    "HK": "Hong Kong",
    "IE": "Irlanda",
    "IT": "Italia",
    "JP": "Japón",
    "LU": "Luxemburgo",
    "NL": "Países Bajos",
    "NO": "Noruega",
    "PT": "Portugal",
    "SE": "Suecia",
    "SG": "Singapur",
    "US": "Estados Unidos de América",
}


def country_from_isin(isin: str) -> str:
    """Derive Spanish country name from ISIN prefix."""
    code = isin[:2].upper() if isin and len(isin) >= 2 else ""
    return COUNTRY_NAMES.get(code, code)


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

    # Savings-income withholding. All amounts are positive magnitudes.
    # ``withholding_tax`` is the total cash withheld. The domestic/foreign
    # split is explicit because only Spanish payments on account and an
    # independently calculated foreign-tax credit reduce the IRPF result.
    withholding_tax: Decimal = Decimal("0")
    domestic_withholding_tax: Decimal | None = None
    foreign_withholding_tax: Decimal | None = None
    withholding_rate: Decimal | None = None
    double_taxation_amount: Decimal | None = None
    double_taxation_rate: Decimal | None = None

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
class ParsedGainLoss:
    """Realized gain/loss per product (from DEGIRO annual report)."""

    isin: str
    name: str
    realized_pl_eur: Decimal
    commission_eur: Decimal
    transaction_tax_eur: Decimal


@dataclass
class ParsedPortfolioHolding:
    """Holdings at year-end."""

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
    # Extra fields for DEGIRO
    price: Decimal = Decimal("0")
    exchange: str = ""


@dataclass
class OptionAssignment:
    """Detected option assignment from IBKR trade codes."""

    assignment_date: date
    underlying: str          # Stock symbol (e.g. "ADM")
    option_symbol: str       # Full option symbol (e.g. "ADM 20DEC24 52.5 P")
    option_type: str         # "P" (PUT) or "C" (CALL)
    strike: Decimal
    stock_quantity: Decimal   # Shares acquired/sold
    stock_isin: str
    premium_eur: Decimal      # Option premium in EUR (embedded in stock cost basis)


@dataclass
class IBKRAnnualReport:
    """Complete parsed IBKR Activity Statement CSV."""

    account_id: str
    account_name: str
    fiscal_year: int
    base_currency: str

    trades: list[ParsedTransaction] = field(default_factory=list)
    dividends: list[ParsedTransaction] = field(default_factory=list)
    interest: list[ParsedTransaction] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)
    realized_gains: list[ParsedGainLoss] = field(default_factory=list)
    assignments: list[OptionAssignment] = field(default_factory=list)
    symbol_isin_map: dict[str, str] = field(default_factory=dict)


@dataclass
class DGAnnualReport:
    """Complete parsed DEGIRO Annual Report."""

    fiscal_year: int
    dividends: list[ParsedTransaction] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)
    gains_summary: list[ParsedGainLoss] = field(default_factory=list)


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
    # Which TR report layout produced this. Distinguishes the up-to-three
    # documents that can exist for one fiscal year so they coexist instead of
    # replacing each other on import:
    #   "legacy"            — pre-2025 full-year Roman-numeral report
    #   "tr_de_premigration"— partial-year report before DE→ES IBAN migration
    #   "es_branch"         — 2025+ Sucursal España report
    source_variant: str = "legacy"


@dataclass
class INGAnnualReport:
    """Complete parsed ING Información Fiscal PDF."""

    fiscal_year: int
    interest: list[ParsedTransaction] = field(default_factory=list)
    dividends: list[ParsedTransaction] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)
    portfolio_snapshot_complete: bool = False


@dataclass
class BBVAAnnualReport:
    """Combined parsed BBVA annual PDFs (up to 3 documents)."""

    fiscal_year: int
    dividends: list[ParsedTransaction] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    holdings: list[ParsedPortfolioHolding] = field(default_factory=list)
    custody_fee: Decimal = Decimal("0")
    portfolio_snapshot_complete: bool = False


@dataclass
class EToroAnnualReport:
    """Parsed eToro annual account statement XLSX."""

    fiscal_year: int
    dividends: list[ParsedTransaction] = field(default_factory=list)
    transactions: list[ParsedTransaction] = field(default_factory=list)
    closed_positions: list[ParsedCapitalGain] = field(default_factory=list)
