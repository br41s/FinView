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
    "SG": "Singapur",
}

# Section name normalization: Spanish → English
_SECTION_EN: dict[str, str] = {
    "Información sobre la cuenta": "Account Information",
    "Valor liquidativo": "Net Asset Value",
    "Cambio en NAV": "Change in NAV",
    "Resumen Rendimiento Valoración al mercado": "Mark-to-Market Performance Summary",
    "Resumen del rendimiento realizado y no realizado": "Realized & Unrealized Performance Summary",
    "Informe de efectivo": "Cash Report",
    "Posiciones abiertas": "Open Positions",
    "Saldos en fórex": "Forex Balances",
    "Operaciones": "Trades",
    "Acciones corporativas": "Corporate Actions",
    "Actividad de la subvención": "Grant Activity",
    "Depósitos y retiradas": "Deposits & Withdrawals",
    "Dividendos": "Dividends",
    "Retención de impuestos": "Withholding Tax",
    "Interés": "Interest",
    "Devengo de intereses": "Interest Accruals",
    "Modificación en los dividendos devengados": "Change in Dividend Accruals",
    "Información de instrumento financiero": "Financial Instrument Information",
    "Código": "Codes",
    "Notas/Notas legales": "Notes/Legal Notes",
    "PyG totales del período del extracto": "Total P/L for Statement Period",
    "Tarifas": "Fees",
}

# Category normalization: Spanish → English
_CAT_EN: dict[str, str] = {
    "Acciones": "Stocks",
    "Fórex": "Forex",
    "Opciones sobre acciones e índices": "Equity and Index Options",
}


def _norm_cat(value: str) -> str:
    """Normalize asset-category / field value to English."""
    return _CAT_EN.get(value, value)


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
    """Group CSV rows by section name. Returns {section: [rows]}.

    Section names are normalized to English so the rest of the parser
    works identically for both EN and ES IBKR exports.
    """
    sections: dict[str, list[list[str]]] = {}
    reader = csv.reader(StringIO(text))
    for row in reader:
        if len(row) < 2:
            continue
        section = row[0].strip()
        section = _SECTION_EN.get(section, section)
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
        if field in ("Account", "Cuenta"):
            account_id = value
        elif field in ("Name", "Nombre"):
            name = value
        elif field in ("Base Currency", "Divisa base"):
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
        category = _norm_cat(row[2].strip())
        if category != "Stocks":
            continue
        symbol = row[3].strip()
        # Security ID (ISIN) is at index 6: Section,Data,Category,Symbol,Description,Conid,SecurityID,...
        isin = row[6].strip()
        if isin and len(isin) == 12:
            symbol_isin[symbol] = isin
    return symbol_isin


def _extract_forex_rates(rows: list[list[str]]) -> dict[str, list[tuple[date, Decimal]]]:
    """Parse Forex trades to build exchange rate lookup.

    Returns {currency: [(date, rate_per_eur)]} where 1 EUR = rate_per_eur foreign.
    To convert foreign→EUR: amount / rate_per_eur.
    """
    rates_by_date: dict[str, dict[date, Decimal]] = {}
    for row in rows:
        if len(row) < 9 or row[1].strip() != "Data" or row[2].strip() != "Order":
            continue
        if _norm_cat(row[3].strip()) != "Forex":
            continue
        currency = row[4].strip()
        rate = _dec(row[8])
        if rate <= 0:
            continue
        trade_date = _parse_date(row[6])
        # Keep last rate per date (rows are chronological)
        rates_by_date.setdefault(currency, {})[trade_date] = rate

    return {
        currency: sorted(date_rates.items())
        for currency, date_rates in rates_by_date.items()
    }


def _extract_yearend_fx_rates(rows: list[list[str]]) -> dict[str, Decimal]:
    """Extract year-end exchange rates from Mark-to-Market Performance Summary.

    Returns {currency: eur_per_foreign} where 1 foreign = eur_per_foreign EUR.
    """
    rates: dict[str, Decimal] = {}
    for row in rows:
        if len(row) < 8 or row[1].strip() != "Data":
            continue
        if _norm_cat(row[2].strip()) != "Forex":
            continue
        symbol = row[3].strip()
        if symbol == "EUR":
            continue
        current_price = _dec(row[7])
        if current_price > 0:
            rates[symbol] = current_price
    return rates


def _to_eur(
    amount: Decimal,
    currency: str,
    forex_rates: dict[str, list[tuple[date, Decimal]]],
    trade_date: date,
) -> tuple[Decimal, Decimal]:
    """Convert amount to EUR using closest available forex rate.

    Returns (amount_eur, eur_per_foreign) where eur_per_foreign is the rate used.
    """
    if currency == "EUR" or amount == 0:
        return amount, Decimal("1")

    rates = forex_rates.get(currency, [])
    if not rates:
        return amount, Decimal("1")

    # Find closest rate on or before trade_date
    best_rate = rates[0][1]
    for d, r in rates:
        if d <= trade_date:
            best_rate = r
        else:
            break

    # best_rate = 1 EUR = best_rate foreign → 1 foreign = (1/best_rate) EUR
    eur_per_foreign = Decimal("1") / best_rate
    return amount * eur_per_foreign, eur_per_foreign


def _is_trade_order(row: list[str]) -> bool:
    """Check if row is a trade Order data row (not Header/SubTotal/Total/Forex)."""
    return (
        len(row) >= 6
        and row[1].strip() == "Data"
        and row[2].strip() == "Order"
        and _norm_cat(row[3].strip()) != "Forex"
    )


def _parse_single_trade(
    row: list[str],
    symbol_isin: dict[str, str],
    forex_rates: dict[str, list[tuple[date, Decimal]]],
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
    trade_dt = _parse_date(date_str)

    underlying = symbol.split()[0] if " " in symbol else symbol
    isin = symbol_isin.get(underlying, symbol_isin.get(symbol, ""))
    name = f"[OPT] {symbol}" if _norm_cat(asset_category) == "Equity and Index Options" else symbol

    # Convert amounts to EUR
    proceeds_eur, fx_rate = _to_eur(abs(proceeds), currency, forex_rates, trade_dt)
    commission_eur, _ = _to_eur(abs(commission), currency, forex_rates, trade_dt)

    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=trade_dt,
        isin=isin,
        name=name,
        country=_country_from_isin(isin),
        quantity=quantity,
        price=abs(t_price),
        currency=currency,
        exchange_rate=fx_rate,
        gross_amount=proceeds_eur,
        fees=commission_eur,
        net_amount_eur=proceeds_eur - commission_eur,
        realized_pl_eur=realized_pl,
    )


def _extract_trades(
    rows: list[list[str]],
    symbol_isin: dict[str, str],
    forex_rates: dict[str, list[tuple[date, Decimal]]],
) -> list[ParsedTransaction]:
    """Parse individual trades (stocks and options) from Trades section."""
    trades: list[ParsedTransaction] = []
    for row in rows:
        if not _is_trade_order(row):
            continue
        tx = _parse_single_trade(row, symbol_isin, forex_rates)
        if tx:
            trades.append(tx)
    return trades


def _build_wht_lookup(wht_rows: list[list[str]]) -> dict[tuple[str, str, str], Decimal]:
    """Build withholding tax lookup: (currency, date, symbol) → amount."""
    wht_by_key: dict[tuple[str, str, str], Decimal] = {}
    for row in wht_rows:
        if len(row) < 6 or row[1].strip() != "Data":
            continue
        currency = row[2].strip()
        if currency.startswith("Total"):
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
    rows: list[list[str]],
    symbol_isin: dict[str, str],
    wht_rows: list[list[str]],
    forex_rates: dict[str, list[tuple[date, Decimal]]],
) -> list[ParsedTransaction]:
    """Parse dividends and match with withholding tax. Amounts converted to EUR."""
    wht_by_key = _build_wht_lookup(wht_rows)
    dividends: list[ParsedTransaction] = []

    for row in rows:
        if len(row) < 6 or row[1].strip() != "Data":
            continue
        currency = row[2].strip()
        if currency.startswith("Total"):
            continue
        date_str = row[3].strip()
        if not date_str:
            continue

        desc = row[4].strip()
        amount = _dec(row[5])
        symbol, isin = _parse_div_symbol_isin(desc, symbol_isin)

        wht = abs(wht_by_key.get((currency, date_str, symbol), Decimal("0")))
        # Withholding rate is based on original currency amounts
        wht_rate = (wht / amount * 100) if amount else None

        # Convert to EUR
        trade_dt = _parse_date(date_str)
        amount_eur, fx_rate = _to_eur(amount, currency, forex_rates, trade_dt)
        wht_eur, _ = _to_eur(wht, currency, forex_rates, trade_dt)

        dividends.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=trade_dt,
            isin=isin,
            name=f"{symbol} - {desc}" if symbol else desc,
            country=_country_from_isin(isin),
            quantity=Decimal("1"),
            price=amount,
            currency=currency,
            exchange_rate=fx_rate,
            gross_amount=amount_eur,
            fees=Decimal("0"),
            net_amount_eur=amount_eur - wht_eur,
            withholding_tax=wht_eur,
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


def _detect_open_col_offset(rows: list[list[str]]) -> int:
    """Detect whether the Open Positions section has an 'Open' column.

    The 2024 EN format has: ...Symbol,Open,Quantity,Mult,...  (offset=1)
    The 2025 ES format has: ...Símbolo,Cantidad,Mult.,...    (offset=0)
    """
    for row in rows:
        if len(row) > 6 and row[1].strip() == "Header":
            if row[6].strip().lower() == "open":
                return 1
            break
    return 0


def _extract_open_positions(
    rows: list[list[str]],
    symbol_isin: dict[str, str],
    yearend_rates: dict[str, Decimal],
) -> list[ParsedPortfolioHolding]:
    """Parse open positions at year-end. Values converted to EUR."""
    holdings: list[ParsedPortfolioHolding] = []
    offset = _detect_open_col_offset(rows)

    for row in rows:
        if len(row) < 13 + offset or row[1].strip() != "Data":
            continue
        disc = row[2].strip()
        if disc != "Summary":
            continue

        asset_category = _norm_cat(row[3].strip())
        if asset_category != "Stocks":
            continue  # Only stocks for Modelo 714

        currency = row[4].strip()
        symbol = row[5].strip()
        quantity = _dec(row[6 + offset])
        close_price = _dec(row[10 + offset])
        value = _dec(row[11 + offset])

        # Convert to EUR using year-end rate
        fx_rate = yearend_rates.get(currency, Decimal("1")) if currency != "EUR" else Decimal("1")
        value_eur = value * fx_rate

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
                value_dec31_eur=value_eur,
                fiscal_valuation=value_eur,
                price=close_price,
                exchange="IBKR",
            )
        )

    return holdings


def _resolve_perf_symbol(
    asset_category: str, symbol: str, symbol_isin: dict[str, str]
) -> tuple[str, str]:
    """Resolve (isin, display_name) for a performance summary row."""
    norm = _norm_cat(asset_category)
    if norm == "Equity and Index Options":
        underlying = symbol.split()[0]
        return symbol_isin.get(underlying, ""), f"[OPT] {symbol}"
    if norm == "Forex":
        return "", f"[FX] {symbol}"
    return symbol_isin.get(symbol, ""), symbol


def _extract_realized_performance(
    rows: list[list[str]], symbol_isin: dict[str, str]
) -> list[ParsedGainLoss]:
    """Extract realized P/L per instrument from Realized & Unrealized Performance Summary.

    Values in this section are already in base currency (EUR).
    This is the source of truth for gains/losses.
    """
    gains: list[ParsedGainLoss] = []

    for row in rows:
        if len(row) < 10 or row[1].strip() != "Data":
            continue
        asset_category = row[2].strip()
        symbol = row[3].strip()
        if asset_category.startswith("Total") or not symbol:
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

    # Exchange rates from Forex trades (source of truth for currency conversion)
    trades_rows = sections.get("Trades", [])
    forex_rates = _extract_forex_rates(trades_rows)

    # Year-end exchange rates from Mark-to-Market (for holdings valuation)
    yearend_rates = _extract_yearend_fx_rates(
        sections.get("Mark-to-Market Performance Summary", [])
    )

    # Individual trades (amounts converted to EUR)
    trades = _extract_trades(trades_rows, symbol_isin, forex_rates)

    # Dividends + withholding (amounts converted to EUR)
    dividends = _extract_dividends(
        sections.get("Dividends", []),
        symbol_isin,
        sections.get("Withholding Tax", []),
        forex_rates,
    )

    # Interest (already in EUR for this account)
    interest = _extract_interest(sections.get("Interest", []))

    # Open positions (values converted to EUR using year-end rates)
    holdings = _extract_open_positions(
        sections.get("Open Positions", []), symbol_isin, yearend_rates
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
