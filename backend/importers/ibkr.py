"""IBKR Activity Statement CSV parser.

Parses the multi-section CSV exported from Interactive Brokers.
Each line: SectionName,Header|Data|SubTotal|Total,...fields

Key principle: IBKR data is the source of truth. We extract pre-calculated
realized P/L from the Realized & Unrealized Performance Summary rather
than computing it ourselves.
"""

import csv
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

from backend.importers.base import (
    IBKRAnnualReport,
    ParsedGainLoss,
    ParsedPortfolioHolding,
    ParsedTransaction,
    TxType,
)

# Country lookup from ISIN prefix
_COUNTRY_NAMES = {
    "DE": "Alemania",
    "BR": "Brasil",
    "ES": "España",
    "US": "Estados Unidos de América",
    "FR": "Francia",
    "PT": "Portugal",
    "GB": "Reino Unido",
    "CH": "Suiza",
    "NL": "Países Bajos",
    "IE": "Irlanda",
    "IT": "Italia",
}


def _dec(value: str) -> Decimal:
    """Parse a decimal value, handling commas in large numbers."""
    value = value.strip().replace(",", "")
    if not value or value == "--":
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(value: str) -> date:
    """Parse IBKR date format '2024-12-19, 16:20:00' or '2024-12-19'."""
    date_str = value.split(",")[0].strip()
    return date.fromisoformat(date_str)


def _country_from_isin(isin: str) -> str:
    """Derive country name from ISIN prefix."""
    code = isin[:2] if isin and len(isin) >= 2 else ""
    return _COUNTRY_NAMES.get(code, code)


def compute_file_hash(path: Path) -> str:
    """SHA-256 hash for deduplication."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _parse_sections(text: str) -> dict[str, list[list[str]]]:
    """Group CSV rows by section name. Returns {section: [rows]}."""
    sections: dict[str, list[list[str]]] = {}
    reader = csv.reader(StringIO(text))
    for row in reader:
        if len(row) < 2:
            continue
        section = row[0].strip()
        sections.setdefault(section, []).append(row)
    return sections


def _extract_account_info(rows: list[list[str]]) -> tuple[str, str, str]:
    """Extract account_id, name, base_currency from Account Information rows."""
    account_id = ""
    name = ""
    base_currency = "EUR"
    for row in rows:
        if len(row) < 4 or row[1].strip() != "Data":
            continue
        field = row[2].strip()
        value = row[3].strip()
        if field == "Account":
            account_id = value
        elif field == "Name":
            name = value
        elif field == "Base Currency":
            base_currency = value
    return account_id, name, base_currency


def _extract_fiscal_year(rows: list[list[str]]) -> int:
    """Extract fiscal year from Statement period."""
    for row in rows:
        if len(row) < 4 or row[1].strip() != "Data":
            continue
        if row[2].strip() == "Period":
            # "January 1, 2024 - December 31, 2024"
            m = re.search(r"(\d{4})\s*$", row[3].strip())
            if m:
                return int(m.group(1))
    return date.today().year


def _extract_instrument_info(rows: list[list[str]]) -> dict[str, str]:
    """Build symbol → ISIN mapping from Financial Instrument Information."""
    symbol_isin: dict[str, str] = {}
    for row in rows:
        if len(row) < 7 or row[1].strip() != "Data":
            continue
        category = row[2].strip()
        if category != "Stocks":
            continue
        symbol = row[3].strip()
        # Security ID (ISIN) is at index 6: Section,Data,Category,Symbol,Description,Conid,SecurityID,...
        isin = row[6].strip()
        if isin and len(isin) == 12:
            symbol_isin[symbol] = isin
    return symbol_isin


def _is_trade_order(row: list[str]) -> bool:
    """Check if row is a trade Order data row (not Header/SubTotal/Total/Forex)."""
    return (
        len(row) >= 6
        and row[1].strip() == "Data"
        and row[2].strip() == "Order"
        and row[3].strip() != "Forex"
    )


def _parse_single_trade(
    row: list[str], symbol_isin: dict[str, str]
) -> ParsedTransaction | None:
    """Parse a single trade Order row into a ParsedTransaction."""
    asset_category = row[3].strip()
    currency = row[4].strip() if len(row) > 4 else "EUR"
    symbol = row[5].strip() if len(row) > 5 else ""
    date_str = row[6].strip() if len(row) > 6 else ""
    quantity = _dec(row[7]) if len(row) > 7 else Decimal("0")
    t_price = _dec(row[8]) if len(row) > 8 else Decimal("0")
    proceeds = _dec(row[10]) if len(row) > 10 else Decimal("0")
    commission = _dec(row[11]) if len(row) > 11 else Decimal("0")
    realized_pl = _dec(row[13]) if len(row) > 13 else Decimal("0")

    if not date_str or not symbol:
        return None

    tx_type = TxType.BUY if quantity > 0 else TxType.SELL
    quantity = abs(quantity)

    underlying = symbol.split()[0] if " " in symbol else symbol
    isin = symbol_isin.get(underlying, symbol_isin.get(symbol, ""))
    name = f"[OPT] {symbol}" if asset_category == "Equity and Index Options" else symbol

    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=_parse_date(date_str),
        isin=isin,
        name=name,
        country=_country_from_isin(isin),
        quantity=quantity,
        price=abs(t_price),
        currency=currency,
        gross_amount=abs(proceeds),
        fees=abs(commission),
        net_amount_eur=abs(proceeds) - abs(commission),
        realized_pl_eur=realized_pl,
    )


def _extract_trades(
    rows: list[list[str]], symbol_isin: dict[str, str]
) -> list[ParsedTransaction]:
    """Parse individual trades (stocks and options) from Trades section."""
    trades: list[ParsedTransaction] = []
    for row in rows:
        if not _is_trade_order(row):
            continue
        tx = _parse_single_trade(row, symbol_isin)
        if tx:
            trades.append(tx)
    return trades


def _build_wht_lookup(wht_rows: list[list[str]]) -> dict[tuple[str, str, str], Decimal]:
    """Build withholding tax lookup: (currency, date, symbol) → amount."""
    wht_by_key: dict[tuple[str, str, str], Decimal] = {}
    skip_rows = ("Total", "Total in EUR", "Total Withholding Tax in EUR")
    for row in wht_rows:
        if len(row) < 6 or row[1].strip() != "Data":
            continue
        currency = row[2].strip()
        if currency in skip_rows:
            continue
        desc = row[4].strip()
        m = re.match(r"(\w+)\(", desc)
        symbol = m.group(1) if m else ""
        wht_by_key[(currency, row[3].strip(), symbol)] = _dec(row[5])
    return wht_by_key


def _parse_div_symbol_isin(
    desc: str, symbol_isin: dict[str, str]
) -> tuple[str, str]:
    """Extract symbol and ISIN from dividend description."""
    m = re.match(r"(\w+)\(([A-Z0-9]{12})\)", desc)
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(r"(\w+)", desc)
    symbol = m2.group(1) if m2 else ""
    return symbol, symbol_isin.get(symbol, "")


def _extract_dividends(
    rows: list[list[str]], symbol_isin: dict[str, str], wht_rows: list[list[str]]
) -> list[ParsedTransaction]:
    """Parse dividends and match with withholding tax."""
    wht_by_key = _build_wht_lookup(wht_rows)
    dividends: list[ParsedTransaction] = []

    for row in rows:
        if len(row) < 6 or row[1].strip() != "Data":
            continue
        currency = row[2].strip()
        if currency in ("Total", "Total in EUR"):
            continue
        date_str = row[3].strip()
        if not date_str:
            continue

        desc = row[4].strip()
        amount = _dec(row[5])
        symbol, isin = _parse_div_symbol_isin(desc, symbol_isin)

        wht = abs(wht_by_key.get((currency, date_str, symbol), Decimal("0")))
        wht_rate = (wht / amount * 100) if amount else None

        dividends.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=_parse_date(date_str),
            isin=isin,
            name=f"{symbol} - {desc}" if symbol else desc,
            country=_country_from_isin(isin),
            quantity=Decimal("1"),
            price=amount,
            currency=currency,
            gross_amount=amount,
            fees=Decimal("0"),
            net_amount_eur=amount - wht,
            withholding_tax=wht,
            withholding_rate=wht_rate,
        ))

    return dividends


def _extract_interest(rows: list[list[str]]) -> list[ParsedTransaction]:
    """Parse interest income from Interest section."""
    interest: list[ParsedTransaction] = []

    for row in rows:
        if len(row) < 6 or row[1].strip() != "Data":
            continue
        currency = row[2].strip()
        if currency in ("Total",):
            continue
        date_str = row[3].strip()
        desc = row[4].strip()
        amount = _dec(row[5])

        if not date_str:
            continue

        trade_date = _parse_date(date_str)

        tx = ParsedTransaction(
            tx_type=TxType.INTEREST,
            trade_date=trade_date,
            isin="",
            name=desc,
            country="",
            quantity=Decimal("1"),
            price=amount,
            currency=currency,
            gross_amount=amount,
            fees=Decimal("0"),
            net_amount_eur=amount,
        )
        interest.append(tx)

    return interest


def _extract_open_positions(
    rows: list[list[str]], symbol_isin: dict[str, str]
) -> list[ParsedPortfolioHolding]:
    """Parse open positions at year-end."""
    holdings: list[ParsedPortfolioHolding] = []

    for row in rows:
        if len(row) < 14 or row[1].strip() != "Data":
            continue
        disc = row[2].strip()
        if disc != "Summary":
            continue

        asset_category = row[3].strip()
        if asset_category not in ("Stocks",):
            continue  # Only stocks for Modelo 714

        currency = row[4].strip()
        symbol = row[5].strip()
        quantity = _dec(row[7])
        close_price = _dec(row[11])
        value = _dec(row[12])

        isin = symbol_isin.get(symbol, "")
        country = _country_from_isin(isin)

        holdings.append(
            ParsedPortfolioHolding(
                isin=isin,
                name=symbol,
                currency=currency,
                asset_type="Acciones",
                country=country,
                casilla_714=0,  # Assigned during import based on value threshold
                quantity=quantity,
                avg_q4_balance=quantity,  # Simplified
                value_dec31_eur=value,
                fiscal_valuation=value,
                price=close_price,
                exchange="IBKR",
            )
        )

    return holdings


def _resolve_perf_symbol(
    asset_category: str, symbol: str, symbol_isin: dict[str, str]
) -> tuple[str, str]:
    """Resolve (isin, display_name) for a performance summary row."""
    if asset_category == "Equity and Index Options":
        underlying = symbol.split()[0]
        return symbol_isin.get(underlying, ""), f"[OPT] {symbol}"
    if asset_category == "Forex":
        return "", f"[FX] {symbol}"
    return symbol_isin.get(symbol, ""), symbol


def _extract_realized_performance(
    rows: list[list[str]], symbol_isin: dict[str, str]
) -> list[ParsedGainLoss]:
    """Extract realized P/L per instrument from Realized & Unrealized Performance Summary.

    Values in this section are already in base currency (EUR).
    This is the source of truth for gains/losses.
    """
    skip = ("Total", "Total (All Assets)")
    gains: list[ParsedGainLoss] = []

    for row in rows:
        if len(row) < 10 or row[1].strip() != "Data":
            continue
        asset_category = row[2].strip()
        symbol = row[3].strip()
        if asset_category in skip or not symbol:
            continue

        realized_total = _dec(row[9])
        if realized_total == 0:
            continue

        isin, name = _resolve_perf_symbol(asset_category, symbol, symbol_isin)
        gains.append(ParsedGainLoss(
            isin=isin,
            name=name,
            realized_pl_eur=realized_total,
            commission_eur=Decimal("0"),
            transaction_tax_eur=Decimal("0"),
        ))

    return gains


def parse_ibkr_activity_statement(path: Path) -> IBKRAnnualReport:
    """Parse an IBKR Activity Statement CSV file."""
    text = path.read_text(encoding="utf-8-sig")
    sections = _parse_sections(text)

    # Account info
    account_id, name, base_currency = _extract_account_info(
        sections.get("Account Information", [])
    )

    # Fiscal year from statement period
    fiscal_year = _extract_fiscal_year(sections.get("Statement", []))

    # Symbol → ISIN mapping
    symbol_isin = _extract_instrument_info(
        sections.get("Financial Instrument Information", [])
    )

    # Individual trades
    trades = _extract_trades(sections.get("Trades", []), symbol_isin)

    # Dividends + withholding
    dividends = _extract_dividends(
        sections.get("Dividends", []),
        symbol_isin,
        sections.get("Withholding Tax", []),
    )

    # Interest
    interest = _extract_interest(sections.get("Interest", []))

    # Open positions (holdings)
    holdings = _extract_open_positions(
        sections.get("Open Positions", []), symbol_isin
    )

    # Realized P/L from performance summary (source of truth)
    realized_gains = _extract_realized_performance(
        sections.get("Realized & Unrealized Performance Summary", []),
        symbol_isin,
    )

    return IBKRAnnualReport(
        account_id=account_id,
        account_name=name,
        fiscal_year=fiscal_year,
        base_currency=base_currency,
        trades=trades,
        dividends=dividends,
        interest=interest,
        holdings=holdings,
        realized_gains=realized_gains,
        symbol_isin_map=symbol_isin,
    )
