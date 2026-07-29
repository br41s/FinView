"""Trade Republic Tax Report PDF parser.

Extracts structured data from the annual Tax Report PDF that Trade Republic
generates for Spanish tax residents. Uses pdfplumber for text extraction
and regex patterns for parsing.

Sections parsed:
- I:    Dividends (rendimientos del capital mobiliario)
- III:  Capital gains/losses (ganancias y pérdidas patrimoniales)
- V:    Withholding tax details
- VI:   All transactions
- VII:  Portfolio holdings at year-end
- VIII: Pre-calculated Modelo 100 casillas
- IX:   Pre-calculated Modelo 714 casillas
"""

import hashlib
import re
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from backend.importers.base import (
    ParsedCapitalGain,
    ParsedCasilla,
    ParsedPortfolioHolding,
    ParsedTransaction,
    ParsedWithholding,
    TRTaxReport,
    TxType,
)

# -- Number parsing (European format: 1.234,56) --

_EUR_NUM = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d+")


def parse_eur_number(s: str) -> Decimal:
    """Parse European-format number string: '1.234,56' -> Decimal('1234.56')."""
    s = s.strip()
    s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _try_parse_num(s: str) -> Decimal | None:
    try:
        return parse_eur_number(s)
    except (InvalidOperation, ValueError):
        return None


# -- Date parsing --

_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")


def parse_date(s: str) -> date:
    """Parse 'DD.MM.YYYY' -> date."""
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


# -- ISIN pattern --

ISIN_RE = re.compile(r"([A-Z]{2}[A-Z0-9]{9,10})\s*-\s*(.+)")

# Known country names that appear as section sub-headers
COUNTRY_NAMES = {
    "Alemania", "Brasil", "España", "Estados Unidos de América",
    "Francia", "Países Bajos", "Portugal", "Reino Unido", "Suiza",
}

# Map Spanish transaction type labels to TxType enum
_TX_TYPE_MAP = {
    "Compra": TxType.BUY,
    "Venta": TxType.SELL,
    "Spin-Off": TxType.SPINOFF,
    "Dividendo": TxType.DIVIDEND,
}


# -- Section identification --

SECTION_HEADERS = {
    "I": "I. Rendimientos del capital mobiliario",
    "II": "II. Rendimientos del capital mobiliario (resumen)",
    "III": "III. Ganancias y pérdidas patrimoniales",
    "IV": "IV. Ganancias y pérdidas patrimoniales (resumen)",
    "V": "V. Sección detallada de retención de impuestos",
    "VI": "VI. Información sobre transacciones y operaciones corporativas",
    "VII": "VII. Datos relativos al impuesto sobre el patrimonio",
    "VIII": "VIII. Modelo 100",
    "IX": "IX. Modelo 714",
    "X": "X. Descargo de responsabilidad",
    "XI": "XI. Notas explicativas",
}


def _identify_section(text: str) -> str | None:
    """Identify which section a page belongs to."""
    for key, header in SECTION_HEADERS.items():
        if header in text:
            return key
    return None


def _extract_pages_text(pdf: pdfplumber.PDF) -> list[str]:
    """Extract text from all pages (lazy, skip cover/disclaimer pages)."""
    results = []
    for i, page in enumerate(pdf.pages):
        # Skip page 0 (cover) and last 3 pages (disclaimer/notes)
        if i == 0:
            results.append("")
            continue
        text = page.extract_text() or ""
        results.append(text)
    return results


def _pages_for_section(pages_text: list[str], section: str) -> list[str]:
    """Get all page texts belonging to a given section."""
    result = []
    for text in pages_text:
        if _identify_section(text) == section:
            result.append(text)
    return result


# -- Header extraction --

_CLIENT_RE = re.compile(r"Clientela:\s*(\d+)")
_PERIOD_RE = re.compile(r"Período:\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")


def _extract_header(pages_text: list[str]) -> tuple[str, date, date]:
    """Extract client ID and period from first pages."""
    for text in pages_text[:5]:
        cm = _CLIENT_RE.search(text)
        pm = _PERIOD_RE.search(text)
        if cm and pm:
            return cm.group(1), parse_date(pm.group(1)), parse_date(pm.group(2))
    raise ValueError("Could not find client ID and period in PDF")


# -- Shared helpers for section parsers --

def _build_vi_transaction(tx_match, current_isin, current_name):
    """Build a ParsedTransaction from a Section VI regex match."""
    tx_type_str = tx_match.group(1)
    trade_date = parse_date(tx_match.group(2))
    currency = tx_match.group(3)
    exchange_rate = parse_eur_number(tx_match.group(4))
    quantity = parse_eur_number(tx_match.group(5))
    amount = parse_eur_number(tx_match.group(6))
    tx_type = _TX_TYPE_MAP.get(tx_type_str, TxType.DIVIDEND)
    price = abs(amount / quantity) if quantity != 0 else Decimal("0")

    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=trade_date,
        isin=current_isin,
        name=current_name,
        country="",
        quantity=quantity,
        price=price,
        currency=currency,
        exchange_rate=exchange_rate,
        gross_amount=amount,
        net_amount_eur=amount if exchange_rate == Decimal("1") else amount / exchange_rate,
    )


def _build_capital_gain(pending_buys, pending_sells, pl_match, current_isin, current_name, current_country):
    """Build a ParsedCapitalGain from accumulated buys/sells and a P&L match."""
    period_text = pl_match.group(1)
    pl_amount = parse_eur_number(pl_match.group(2))
    casilla = int(pl_match.group(3))
    holding = "<1y" if period_text == "menos" else ">1y"

    buy_total = sum(b["total_eur"] for b in pending_buys)
    buy_fees = sum(b["fees_eur"] for b in pending_buys)
    buy_qty = sum(b["quantity"] for b in pending_buys)
    buy_price = pending_buys[0]["price"] if pending_buys else Decimal("0")
    buy_date = pending_buys[0]["date"] if pending_buys else None

    sell_total = sum(s["total_eur"] for s in pending_sells)
    sell_fees = sum(s["fees_eur"] for s in pending_sells)
    sell_qty = sum(s["quantity"] for s in pending_sells)
    sell_price = pending_sells[0]["price"] if pending_sells else Decimal("0")
    sell_date = pending_sells[0]["date"] if pending_sells else None

    if not buy_date or not sell_date:
        return None

    return ParsedCapitalGain(
        isin=current_isin,
        name=current_name,
        country=current_country or "",
        buy_date=buy_date,
        buy_quantity=buy_qty,
        buy_price=buy_price,
        buy_fees=buy_fees,
        buy_total_eur=buy_total,
        sell_date=sell_date,
        sell_quantity=sell_qty,
        sell_price=sell_price,
        sell_fees=sell_fees,
        sell_total_eur=sell_total,
        realized_pl_eur=pl_amount,
        holding_period=holding,
        casilla=casilla,
    )


def _parse_withholding_data(line, current_isin, current_name, current_country, current_date):
    """Parse EUR data line in Section V. Returns ParsedWithholding or None."""
    nums = _EUR_NUM.findall(line)
    if len(nums) < 4:
        return None
    income = parse_eur_number(nums[0])
    withholding = parse_eur_number(nums[1])
    rate_str = re.search(r"(\d+,\d+)%", line)
    rate = parse_eur_number(rate_str.group(1)) if rate_str else Decimal("0")
    double_tax = parse_eur_number(nums[-1])

    return ParsedWithholding(
        country=current_country or "",
        isin=current_isin,
        name=current_name,
        tx_type="Dividendo",
        payment_date=current_date,
        currency="EUR",
        income_eur=income,
        withholding_eur=withholding,
        withholding_rate=rate,
        double_taxation_eur=double_tax,
    )


# =============================================================================
# Section VI: All transactions (simplest structure)
# =============================================================================

# Pattern: "Compra DD.MM.YYYY EUR 1,0000 QTY AMOUNT" or "Venta ..."
_TX_LINE_RE = re.compile(
    r"(Compra|Venta|Spin-Off|Dividendo)\s+"
    r"(\d{2}\.\d{2}\.\d{4})\s+"
    r"([A-Z]{3})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"   # exchange rate or qty
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"   # qty or amount
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)"      # amount
)


def _parse_section_vi(pages_text: list[str]) -> list[ParsedTransaction]:
    """Parse Section VI: all transactions."""
    pages = _pages_for_section(pages_text, "VI")
    transactions = []
    current_isin = None
    current_name = None

    for text in pages:
        lines = text.split("\n")
        for line in lines:
            # Check for ISIN line
            isin_match = ISIN_RE.search(line)
            if isin_match:
                current_isin = isin_match.group(1)
                current_name = isin_match.group(2).strip()
                continue

            if not current_isin:
                continue

            # Check for transaction line
            tx_match = _TX_LINE_RE.search(line)
            if tx_match:
                transactions.append(_build_vi_transaction(tx_match, current_isin, current_name))

    return transactions


# =============================================================================
# Section I: Dividends
# =============================================================================

# Dividend line pattern from the dense text:
# "Dividendo DD.MM.YYYY EUR QTY PRICE FEES INTEREST TOTAL WITHHOLDING EXCHANGE TOTAL_EUR FEES_EUR CASILLA"
_DIV_RE = re.compile(
    r"Dividendo\s+(\d{2}\.\d{2}\.\d{4})\s+"
    r"([A-Z]{3})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # quantity
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # unit price
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # fees
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # interest accrued
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total in currency
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # withholding
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # exchange rate
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total in EUR
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # fees EUR
    r"(\d+)"                               # casilla
)

# Interest line (same structure). "Saveback" is a cash-account reward that TR
# reports as casilla 27 income (note 3.6 of the report), with the same columns.
_INT_RE = re.compile(
    r"(?:Pago de intereses|Saveback)\s+(\d{2}\.\d{2}\.\d{4})\s+"
    r"([A-Z]{3})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # quantity
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # unit price
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # fees
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # interest accrued
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total in currency
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # withholding
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # exchange rate
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total in EUR
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # fees EUR
    r"(\d+)"                               # casilla
)


def _build_dividend_tx(m, tx_type, isin, name, country):
    """Build a ParsedTransaction from a dividend/interest regex match."""
    withholding = abs(parse_eur_number(m.group(8)))
    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=parse_date(m.group(1)),
        isin=isin,
        name=name,
        country=country or "",
        quantity=parse_eur_number(m.group(3)),
        price=parse_eur_number(m.group(4)),
        currency=m.group(2),
        fees=parse_eur_number(m.group(5)),
        gross_amount=parse_eur_number(m.group(7)),
        withholding_tax=withholding,
        domestic_withholding_tax=Decimal("0"),
        foreign_withholding_tax=withholding,
        exchange_rate=parse_eur_number(m.group(9)),
        net_amount_eur=parse_eur_number(m.group(10)) - withholding,
        casilla=int(m.group(12)),
    )


_DIV_PATTERNS = [(_DIV_RE, TxType.DIVIDEND), (_INT_RE, TxType.INTEREST)]


def _match_div_line(line, isin, name, country):
    """Try to match a line against dividend/interest patterns. Returns ParsedTransaction or None."""
    for pattern, tx_type in _DIV_PATTERNS:
        m = pattern.search(line)
        if m:
            return _build_dividend_tx(m, tx_type, isin, name, country)
    return None


def _parse_section_i(pages_text: list[str]) -> list[ParsedTransaction]:
    """Parse Section I: dividends & interest payments."""
    pages = _pages_for_section(pages_text, "I")
    results = []
    current_isin = None
    current_name = None
    current_country = None

    for text in pages:
        for line in text.split("\n"):
            stripped = line.strip()

            if stripped in COUNTRY_NAMES:
                current_country = stripped
                continue

            # Cash-account interest/Saveback rows carry no ISIN; without this
            # they would inherit the previous security's name. Use an empty
            # ISIN and a generic name instead.
            if stripped == "Cuenta de efectivo":
                current_isin = ""
                current_name = "Cuenta de efectivo"
                continue

            isin_match = ISIN_RE.search(line)
            if isin_match:
                current_isin = isin_match.group(1)
                current_name = isin_match.group(2).strip()
                continue

            if current_isin is None:
                continue

            tx = _match_div_line(line, current_isin, current_name, current_country)
            if tx:
                results.append(tx)

    return results


# =============================================================================
# Section III: Capital gains/losses (FIFO-matched pairs)
# =============================================================================

# The text pattern for section III is complex — buy/sell lines followed by P&L summary
_BUY_SELL_RE = re.compile(
    r"(Compra|Venta)\s+(\d{2}\.\d{2}\.\d{4})\s+"
    r"([A-Z]{3})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # quantity
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # unit price
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # fees
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # interest accrued
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total in currency
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # withholding
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # exchange rate
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # total EUR
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)"        # fees EUR
)

_PL_RE = re.compile(
    r"Ganancias y pérdidas (menos|más) 1 año\s+(-?\d{1,3}(?:\.\d{3})*,\d+)\s+(\d+)"
)


def _parse_bs_entry(bs_match):
    """Parse a buy/sell regex match into a dict entry."""
    return {
        "type": bs_match.group(1),
        "date": parse_date(bs_match.group(2)),
        "currency": bs_match.group(3),
        "quantity": parse_eur_number(bs_match.group(4)),
        "price": parse_eur_number(bs_match.group(5)),
        "fees": parse_eur_number(bs_match.group(6)),
        "total_eur": parse_eur_number(bs_match.group(11)),
        "fees_eur": parse_eur_number(bs_match.group(12)),
    }


def _process_iii_line(line, stripped, state, results):
    """Process a single line in Section III. Mutates state and results."""
    if stripped in COUNTRY_NAMES:
        state["country"] = stripped
        return

    isin_match = ISIN_RE.search(line)
    if isin_match and "Compra" not in line and "Venta" not in line:
        state["isin"] = isin_match.group(1)
        state["name"] = isin_match.group(2).strip()
        state["buys"] = []
        state["sells"] = []
        return

    if not state["isin"]:
        return

    bs_match = _BUY_SELL_RE.search(line)
    if bs_match:
        entry = _parse_bs_entry(bs_match)
        (state["buys"] if entry["type"] == "Compra" else state["sells"]).append(entry)
        return

    pl_match = _PL_RE.search(line)
    if pl_match and (state["buys"] or state["sells"]):
        gain = _build_capital_gain(
            state["buys"], state["sells"], pl_match,
            state["isin"], state["name"], state["country"],
        )
        if gain:
            results.append(gain)
        state["buys"] = []
        state["sells"] = []


def _parse_section_iii(pages_text: list[str]) -> list[ParsedCapitalGain]:
    """Parse Section III: capital gains/losses."""
    pages = _pages_for_section(pages_text, "III")
    results = []
    state = {"isin": None, "name": None, "country": None, "buys": [], "sells": []}

    for text in pages:
        for line in text.split("\n"):
            _process_iii_line(line, line.strip(), state, results)

    return results


# =============================================================================
# Section VIII: Modelo 100
# =============================================================================

_MODELO100_RE = re.compile(
    r"(.+?)\s+(\d{1,3})\s+(?:Validación\s+)?(-?\d{1,3}(?:\.\d{3})*,\d+)"
)


# The Modelo 100 section is "VIII" in the full-year report but "VII" in the
# pre-migration partial report (the patrimonio section that normally precedes
# it is absent), so match on the title rather than a fixed Roman numeral.
_MODELO100_TITLE_RE = re.compile(r"\b(?:VII|VIII)\.\s+Modelo 100\b")


def _parse_section_viii(pages_text: list[str]) -> list[ParsedCasilla]:
    """Parse the Modelo 100 casillas section (numbered VII or VIII)."""
    pages = [t for t in pages_text if _MODELO100_TITLE_RE.search(t)]
    results = []

    # Known casillas and their descriptions for matching
    casilla_map = {
        27: "Intereses de cuentas, depósitos y activos financieros en general",
        29: "Dividendos y demás rendimientos",
        332: "Ganancias patrimoniales",
        337: "Pérdidas patrimoniales",
    }

    for text in pages:
        for casilla_num, desc_prefix in casilla_map.items():
            # Look for the casilla number followed by an amount
            pattern = re.compile(
                rf"{casilla_num}\s+(?:Validación\s+)?(-?\d{{1,3}}(?:\.\d{{3}})*,\d+)"
            )
            m = pattern.search(text)
            if m:
                results.append(ParsedCasilla(
                    modelo=100,
                    casilla=casilla_num,
                    description=desc_prefix,
                    amount_eur=parse_eur_number(m.group(1)),
                ))

    return results


# =============================================================================
# Section IX: Modelo 714
# =============================================================================

def _parse_section_ix(pages_text: list[str]) -> list[ParsedCasilla]:
    """Parse Section IX: Modelo 714 casillas."""
    pages = _pages_for_section(pages_text, "IX")
    results = []

    casilla_map = {
        5: "Depósitos en cuenta corriente o de ahorro",
        6: "Deuda pública, obligaciones, bonos",
        8: "Acciones IIC negociadas en mercados organizados",
        9: "Acciones y participaciones negociadas en mercados organizados",
    }

    for text in pages:
        for casilla_num, desc_prefix in casilla_map.items():
            pattern = re.compile(
                rf"\b0{casilla_num}\b\s+(-?\d{{1,3}}(?:\.\d{{3}})*,\d+)"
            )
            m = pattern.search(text)
            if m:
                results.append(ParsedCasilla(
                    modelo=714,
                    casilla=casilla_num,
                    description=desc_prefix,
                    amount_eur=parse_eur_number(m.group(1)),
                ))

    return results


# =============================================================================
# Section VII: Portfolio holdings at year-end
# =============================================================================

_HOLDING_RE = re.compile(
    r"([A-Z]{2}[A-Z0-9]{9,10})\s*-\s*(.+?)\s+"
    r"([A-Z]{3})\s+"
    r"(Acciones|Renta fija|Cuenta de efectivo|ETF)\s+"
    r"(.+?)\s+"
    r"(\d{2})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # quantity
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # avg Q4 balance
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)\s+"     # value 31/12
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)"        # fiscal valuation
)


def _parse_section_vii(pages_text: list[str]) -> list[ParsedPortfolioHolding]:
    """Parse Section VII: portfolio holdings."""
    pages = _pages_for_section(pages_text, "VII")
    results = []

    for text in pages:
        for m in _HOLDING_RE.finditer(text):
            results.append(ParsedPortfolioHolding(
                isin=m.group(1),
                name=m.group(2).strip(),
                currency=m.group(3),
                asset_type=m.group(4),
                country=m.group(5).strip(),
                casilla_714=int(m.group(6)),
                quantity=parse_eur_number(m.group(7)),
                avg_q4_balance=parse_eur_number(m.group(8)),
                value_dec31_eur=parse_eur_number(m.group(9)),
                fiscal_valuation=parse_eur_number(m.group(10)),
            ))

    return results


# =============================================================================
# Section V: Withholding details
# =============================================================================

_ISIN_DIV_RE = re.compile(
    r"([A-Z]{2}[A-Z0-9]{9,10})\s*-\s*(.+?)\s+Dividendo\s+(\d{2}\.\d{2}\.\d{4})"
)


def _process_v_line(line, stripped, state, results):
    """Process a single line in Section V. Mutates state and results."""
    if stripped in COUNTRY_NAMES:
        state["country"] = stripped
        return

    isin_div = _ISIN_DIV_RE.search(line)
    if isin_div:
        state["isin"] = isin_div.group(1)
        state["name"] = isin_div.group(2).strip()
        state["date"] = parse_date(isin_div.group(3))
        return

    if state["isin"] and state["date"] and stripped.startswith("EUR"):
        entry = _parse_withholding_data(
            line, state["isin"], state["name"], state["country"], state["date"],
        )
        if entry:
            results.append(entry)
            state["isin"] = None
            state["date"] = None


def _parse_section_v(pages_text: list[str]) -> list[ParsedWithholding]:
    """Parse Section V: withholding tax details."""
    pages = _pages_for_section(pages_text, "V")
    results = []
    state = {"country": None, "isin": None, "name": None, "date": None}

    for text in pages:
        state["isin"] = None
        state["name"] = None
        state["date"] = None
        for line in text.split("\n"):
            _process_v_line(line, line.strip(), state, results)

    return results


def _apply_withholding_details(
    transactions: list[ParsedTransaction],
    details: list[ParsedWithholding],
) -> None:
    """Attach the explicit foreign-tax credit from legacy TR section V.

    Legacy Trade Republic reports were issued by the German entity, so their
    withholding is foreign rather than a Spanish payment on account. Matching
    by ISIN and payment date avoids inferring treaty limits from country names.
    """
    by_key: dict[tuple[str, date], deque[ParsedWithholding]] = defaultdict(deque)
    for detail in details:
        by_key[(detail.isin, detail.payment_date)].append(detail)
    for tx in transactions:
        matches = by_key.get((tx.isin, tx.trade_date))
        if not matches:
            continue
        detail = matches.popleft()
        tx.withholding_tax = abs(detail.withholding_eur)
        tx.domestic_withholding_tax = Decimal("0")
        tx.foreign_withholding_tax = abs(detail.withholding_eur)
        tx.withholding_rate = detail.withholding_rate
        tx.double_taxation_amount = abs(detail.double_taxation_eur)
        tx.double_taxation_rate = detail.double_taxation_rate


# =============================================================================
# Main parser
# =============================================================================

def parse_tr_tax_report(pdf_path: str | Path) -> TRTaxReport:
    """Parse a Trade Republic Tax Report PDF into structured data.

    Dispatches to the 2025+ Spanish-branch parser when the PDF was
    generated by ``Trade Republic Bank GmbH, Sucursal en España``
    (new flat layout with ``Retenciones en destino``). Legacy
    Roman-numeral reports (pre-2025) keep using the parser below.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        TRTaxReport with all sections parsed.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from backend.importers.tr_v2 import (
        is_spanish_branch_format,
        parse_tr_tax_report_v2,
    )
    if is_spanish_branch_format(pdf_path):
        return parse_tr_tax_report_v2(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        pages_text = _extract_pages_text(pdf)
        cover = pdf.pages[0].extract_text() or "" if pdf.pages else ""

    client_id, period_start, period_end = _extract_header(pages_text)

    # The pre-migration report (issued when the account moved DE→ES IBAN) is the
    # legacy layout but covers only part of the year and ends with a custody
    # transfer of every position to the new ES account. Its Section VI is only
    # historical context for FIFO, and the transferred-out positions are owned
    # by the post-migration ES report — so we keep its fiscal figures only and
    # drop Section VI to avoid phantom open lots.
    pre_migration = (
        "migró a un IBAN español" in cover or "Pre-migración" in cover
    )
    source_variant = "tr_de_premigration" if pre_migration else "legacy"
    transactions = [] if pre_migration else _parse_section_vi(pages_text)

    dividends = _parse_section_i(pages_text)
    withholdings = _parse_section_v(pages_text)
    _apply_withholding_details(dividends, withholdings)

    return TRTaxReport(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        currency="EUR",
        fiscal_year=period_end.year,
        dividends=dividends,
        capital_gains=_parse_section_iii(pages_text),
        transactions=transactions,
        withholdings=withholdings,
        holdings=_parse_section_vii(pages_text),
        casillas_modelo_100=_parse_section_viii(pages_text),
        casillas_modelo_714=_parse_section_ix(pages_text),
        source_variant=source_variant,
    )


def compute_file_hash(path: str | Path) -> str:
    """Compute SHA-256 hash of a file for dedup."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
