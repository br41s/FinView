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
                tx_type_str = tx_match.group(1)
                trade_date = parse_date(tx_match.group(2))
                currency = tx_match.group(3)
                exchange_rate = parse_eur_number(tx_match.group(4))
                quantity = parse_eur_number(tx_match.group(5))
                amount = parse_eur_number(tx_match.group(6))

                if tx_type_str == "Compra":
                    tx_type = TxType.BUY
                elif tx_type_str == "Venta":
                    tx_type = TxType.SELL
                elif tx_type_str == "Spin-Off":
                    tx_type = TxType.SPINOFF
                else:
                    tx_type = TxType.DIVIDEND

                # Price per unit
                price = abs(amount / quantity) if quantity != 0 else Decimal("0")

                transactions.append(ParsedTransaction(
                    tx_type=tx_type,
                    trade_date=trade_date,
                    isin=current_isin,
                    name=current_name,
                    country="",  # Section VI doesn't have country
                    quantity=quantity,
                    price=price,
                    currency=currency,
                    exchange_rate=exchange_rate,
                    gross_amount=amount,
                    net_amount_eur=amount if exchange_rate == Decimal("1") else amount / exchange_rate,
                ))

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

# Interest line (same structure)
_INT_RE = re.compile(
    r"Pago de intereses\s+(\d{2}\.\d{2}\.\d{4})\s+"
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


def _parse_section_i(pages_text: list[str]) -> list[ParsedTransaction]:
    """Parse Section I: dividends & interest payments."""
    pages = _pages_for_section(pages_text, "I")
    results = []
    current_isin = None
    current_name = None
    current_country = None

    # Track country from section headers
    country_names = {
        "Alemania", "Brasil", "España", "Estados Unidos de América",
        "Francia", "Países Bajos", "Portugal", "Reino Unido", "Suiza",
    }

    for text in pages:
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()

            # Country detection
            if stripped in country_names:
                current_country = stripped
                continue

            # ISIN detection
            isin_match = ISIN_RE.search(line)
            if isin_match:
                current_isin = isin_match.group(1)
                current_name = isin_match.group(2).strip()
                continue

            if not current_isin:
                continue

            # Try dividend pattern
            for pattern, tx_type in [(_DIV_RE, TxType.DIVIDEND), (_INT_RE, TxType.INTEREST)]:
                m = pattern.search(line)
                if m:
                    results.append(ParsedTransaction(
                        tx_type=tx_type,
                        trade_date=parse_date(m.group(1)),
                        isin=current_isin,
                        name=current_name,
                        country=current_country or "",
                        quantity=parse_eur_number(m.group(3)),
                        price=parse_eur_number(m.group(4)),
                        currency=m.group(2),
                        fees=parse_eur_number(m.group(5)),
                        gross_amount=parse_eur_number(m.group(7)),
                        withholding_tax=parse_eur_number(m.group(8)),
                        exchange_rate=parse_eur_number(m.group(9)),
                        net_amount_eur=parse_eur_number(m.group(10)),
                        casilla=int(m.group(12)),
                    ))
                    break

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

_BUY_SELL_PAIR = re.compile(
    r"(Compra|Venta)"
)


def _parse_section_iii(pages_text: list[str]) -> list[ParsedCapitalGain]:
    """Parse Section III: capital gains/losses."""
    pages = _pages_for_section(pages_text, "III")
    results = []
    current_isin = None
    current_name = None
    current_country = None

    country_names = {
        "Alemania", "Brasil", "España", "Estados Unidos de América",
        "Francia", "Países Bajos", "Portugal", "Reino Unido", "Suiza",
    }

    # Collect buy/sell entries for current ISIN block
    pending_buys = []
    pending_sells = []

    def _flush_pair():
        """Emit a capital gain record from accumulated buys/sells."""
        nonlocal pending_buys, pending_sells
        # We don't emit here — we wait for the P&L line
        pass

    for text in pages:
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()

            if stripped in country_names:
                current_country = stripped
                continue

            isin_match = ISIN_RE.search(line)
            if isin_match and "Compra" not in line and "Venta" not in line:
                current_isin = isin_match.group(1)
                current_name = isin_match.group(2).strip()
                pending_buys = []
                pending_sells = []
                continue

            if not current_isin:
                continue

            # Buy/sell line
            bs_match = _BUY_SELL_RE.search(line)
            if bs_match:
                entry = {
                    "type": bs_match.group(1),
                    "date": parse_date(bs_match.group(2)),
                    "currency": bs_match.group(3),
                    "quantity": parse_eur_number(bs_match.group(4)),
                    "price": parse_eur_number(bs_match.group(5)),
                    "fees": parse_eur_number(bs_match.group(6)),
                    "total_eur": parse_eur_number(bs_match.group(11)),
                    "fees_eur": parse_eur_number(bs_match.group(12)),
                }
                if entry["type"] == "Compra":
                    pending_buys.append(entry)
                else:
                    pending_sells.append(entry)
                continue

            # P&L summary line
            pl_match = _PL_RE.search(line)
            if pl_match and (pending_buys or pending_sells):
                period_text = pl_match.group(1)
                pl_amount = parse_eur_number(pl_match.group(2))
                casilla = int(pl_match.group(3))
                holding = "<1y" if period_text == "menos" else ">1y"

                # Sum up buys and sells
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

                if buy_date and sell_date:
                    results.append(ParsedCapitalGain(
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
                    ))

                pending_buys = []
                pending_sells = []

    return results


# =============================================================================
# Section VIII: Modelo 100
# =============================================================================

_MODELO100_RE = re.compile(
    r"(.+?)\s+(\d{1,3})\s+(?:Validación\s+)?(-?\d{1,3}(?:\.\d{3})*,\d+)"
)


def _parse_section_viii(pages_text: list[str]) -> list[ParsedCasilla]:
    """Parse Section VIII: Modelo 100 casillas."""
    pages = _pages_for_section(pages_text, "VIII")
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

_WITH_ENTRY_RE = re.compile(
    r"([A-Z]{2}[A-Z0-9]{9,10})\s*-\s*(.+?)\s+"
    r"(Dividendo)\s+(\d{2}\.\d{2}\.\d{4})\s+"
    r"(-?\d{1,3}(?:\.\d{3})*,\d+)"        # exchange rate
)


def _parse_section_v(pages_text: list[str]) -> list[ParsedWithholding]:
    """Parse Section V: withholding tax details.

    This section is complex with multi-line entries per dividend.
    We use a simpler approach: pair ISINs with the data tables on each page.
    """
    pages = _pages_for_section(pages_text, "V")
    results = []
    current_country = None

    country_names = {
        "Alemania", "Brasil", "España", "Estados Unidos de América",
        "Francia", "Países Bajos", "Portugal", "Reino Unido", "Suiza",
    }

    for text in pages:
        lines = text.split("\n")
        current_isin = None
        current_name = None
        current_date = None

        for line in lines:
            stripped = line.strip()

            # Country
            if stripped in country_names:
                current_country = stripped
                continue

            # ISIN + Dividend + Date on same line
            isin_div = re.search(
                r"([A-Z]{2}[A-Z0-9]{9,10})\s*-\s*(.+?)\s+Dividendo\s+(\d{2}\.\d{2}\.\d{4})",
                line
            )
            if isin_div:
                current_isin = isin_div.group(1)
                current_name = isin_div.group(2).strip()
                current_date = parse_date(isin_div.group(3))
                continue

            # Data line with EUR amounts (the second line with EUR prefix)
            if current_isin and current_date and line.strip().startswith("EUR"):
                nums = _EUR_NUM.findall(line)
                if len(nums) >= 4:
                    income = parse_eur_number(nums[0])
                    withholding = parse_eur_number(nums[1])
                    # nums[2] is rate as percentage if present
                    rate_str = re.search(r"(\d+,\d+)%", line)
                    rate = parse_eur_number(rate_str.group(1)) if rate_str else Decimal("0")
                    double_tax = parse_eur_number(nums[-1])

                    results.append(ParsedWithholding(
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
                    ))
                    current_isin = None
                    current_date = None

    return results


# =============================================================================
# Main parser
# =============================================================================

def parse_tr_tax_report(pdf_path: str | Path) -> TRTaxReport:
    """Parse a Trade Republic Tax Report PDF into structured data.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        TRTaxReport with all sections parsed.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        pages_text = _extract_pages_text(pdf)

    client_id, period_start, period_end = _extract_header(pages_text)

    return TRTaxReport(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        currency="EUR",
        fiscal_year=period_end.year,
        dividends=_parse_section_i(pages_text),
        capital_gains=_parse_section_iii(pages_text),
        transactions=_parse_section_vi(pages_text),
        withholdings=_parse_section_v(pages_text),
        holdings=_parse_section_vii(pages_text),
        casillas_modelo_100=_parse_section_viii(pages_text),
        casillas_modelo_714=_parse_section_ix(pages_text),
    )


def compute_file_hash(path: str | Path) -> str:
    """Compute SHA-256 hash of a file for dedup."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
