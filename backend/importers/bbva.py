"""BBVA (Spain) PDF parser for three document types.

BBVA provides 3 separate PDFs per fiscal year:
- acc-1: Operaciones (transactions — buys/sells)
- acc-2: Dividendos (dividend income)
- acc-3: Patrimonio (year-end holdings)

Each PDF is parsed independently and combined into a single BBVAAnnualReport.
"""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

from backend.importers.base import (
    BBVAAnnualReport,
    ParsedPortfolioHolding,
    ParsedTransaction,
    TxType,
    country_from_isin,
    parse_eur_decimal,
)

_D = Decimal

# ── BBVA value name → ISIN map (populated from patrimonio PDF) ─────────

_KNOWN_ISINS: dict[str, str] = {
    "A.BBVA": "ES0113211835",
    "A.TELEFONICA": "ES0178430E18",
}

# ── Country from ISIN ──────────────────────────────────────────────────


# ── Number helpers ─────────────────────────────────────────────────────


def _parse_date_short(s: str) -> date:
    """DD-MM-YY → date (assumes 2000s)."""
    d, m, y = s.split("-")
    year = int(y)
    if year < 100:
        year += 2000
    return date(year, int(m), int(d))


def _parse_date_long(s: str) -> date:
    """DD-MM-YYYY → date."""
    d, m, y = s.split("-")
    return date(int(y), int(m), int(d))


# ── Document type detection ────────────────────────────────────────────

YEAR_RE = re.compile(r"Ejercicio:\s*(\d{4})")

# Operation codes: 1=Buy, 2=Subscribe, 3=Bonus shares, 5=Sell, etc.
_BUY_CODES = {"1", "2", "3", "4", "11"}
_SELL_CODES = {"5", "6", "7", "12", "13", "14"}

# acc-1 Operaciones: DD-MM-YY [HH:MM] CODE[(D)] NAME QTY BRUTO [GASTOS] EFECTIVO
TX_RE = re.compile(
    r"(\d{2}-\d{2}-\d{2})\s+"           # Date DD-MM-YY
    r"(?:\d{2}:\d{2}\s+)?"              # Optional time HH:MM
    r"(\d{1,2})"                         # Operation code
    r"(?:\(D\))?\s+"                     # Optional (D) suffix
    r"([A-Z][A-Z0-9.]+(?:[ ]+[A-Z][A-Z0-9.]*)*)\s+"  # Stock name (no newline, words start with letter)
    r"([\d.,]+)\s+"                      # Num valores (qty)
    r"([\d.,]+)\s+"                      # Importe bruto
    r"(?:([\d.,]+)\s+)?"                 # Optional gastos
    r"([\d.,]+)"                         # Importe efectivo
)

# acc-2 Dividendos: NAME DD-MM-YYYY QTY INTEGROS RETENCIONES [IMPUESTO_EXT]
DIV_RE = re.compile(
    r"([A-Z][A-Z0-9.]+(?:[ ]+[A-Z][A-Z0-9.]*)*)\s+"  # Stock name (no newline, words start with letter)
    r"(\d{2}-\d{2}-\d{4})\s+"                     # Payment date
    r"([\d.,]+)\s+"                                # Num valores
    r"([\d.,]+)\s+"                                # Ingresos íntegros
    r"([\d.,]+)"                                   # Retenciones
    # Optional: impuesto extranjero — may not be present
)

# acc-3 Patrimonio: ISIN NAME QTY COTIZACION VALOR
HOLD_RE = re.compile(
    r"([A-Z]{2}[A-Z0-9]{10})\s+"   # ISIN
    r"([A-Z][A-Z0-9.]+(?:[ ]+[A-Z][A-Z0-9.]*)*)\s+"  # Stock name (no newline, words start with letter)
    r"([\d.,]+)\s+"                 # Num valores
    r"([\d.,]+)\s+"                 # Cotización
    r"([\d.,]+)"                    # Valor patrimonial
)

# Custodia fee: "GASTOS DE ADMON.Y DEPÓSITO: 24,15"
CUSTODY_FEE_RE = re.compile(r"GASTOS DE ADMON\.?Y DEP[ÓO]SITO:\s*([\d.,]+)")


def _detect_document_type(text: str) -> str:
    """Detect which of the 3 BBVA document types this is."""
    if "OPERACIONESDEVALORES" in text.replace(" ", ""):
        return "operaciones"
    if "DIVIDENDOSEINTERESES" in text.replace(" ", ""):
        return "dividendos"
    if "PATRIMONIOENVALORES" in text.replace(" ", ""):
        return "patrimonio"
    raise ValueError("No se pudo detectar el tipo de documento BBVA")


# ── PDF text extraction ────────────────────────────────────────────────

def _extract_all_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    return text


# ── Section parsers ────────────────────────────────────────────────────

def _parse_fiscal_year(text: str) -> int:
    m = YEAR_RE.search(text)
    if m:
        return int(m.group(1))
    raise ValueError("No se encontró el año fiscal en el PDF de BBVA")


def _parse_operaciones(text: str, fiscal_year: int, isin_map: dict[str, str]) -> list[ParsedTransaction]:
    """Parse acc-1 (operations/transactions)."""
    results = []
    for m in TX_RE.finditer(text):
        trade_date = _parse_date_short(m.group(1))
        op_code = m.group(2)
        name = m.group(3).strip()
        qty = parse_eur_decimal(m.group(4))
        bruto = parse_eur_decimal(m.group(5))
        gastos = parse_eur_decimal(m.group(6)) if m.group(6) else _D("0")
        efectivo = parse_eur_decimal(m.group(7))

        if op_code in _BUY_CODES:
            tx_type = TxType.BUY
        elif op_code in _SELL_CODES:
            tx_type = TxType.SELL
        else:
            continue  # Skip unrecognized codes

        isin = isin_map.get(name.upper(), _KNOWN_ISINS.get(name.upper(), ""))

        results.append(ParsedTransaction(
            tx_type=tx_type,
            trade_date=trade_date,
            isin=isin,
            name=name,
            country=country_from_isin(isin) if isin else "España",
            quantity=qty,
            price=bruto / qty if qty else _D("0"),
            currency="EUR",
            gross_amount=bruto,
            fees=gastos,
            net_amount_eur=efectivo,
        ))
    return results


def _parse_dividendos(text: str, fiscal_year: int, isin_map: dict[str, str]) -> tuple[list[ParsedTransaction], Decimal]:
    """Parse acc-2 (dividends). Returns (dividends, custody_fee)."""
    results = []
    for m in DIV_RE.finditer(text):
        name = m.group(1).strip()
        payment_date = _parse_date_long(m.group(2))
        gross = parse_eur_decimal(m.group(4))
        withholding = parse_eur_decimal(m.group(5))

        isin = isin_map.get(name.upper(), _KNOWN_ISINS.get(name.upper(), ""))

        results.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=payment_date,
            isin=isin,
            name=name,
            country=country_from_isin(isin) if isin else "España",
            quantity=_D("0"),
            price=_D("0"),
            currency="EUR",
            gross_amount=gross,
            withholding_tax=withholding,
            domestic_withholding_tax=withholding,
            foreign_withholding_tax=_D("0"),
            net_amount_eur=gross - withholding,
        ))

    # Parse custody fee
    custody_fee = _D("0")
    cfm = CUSTODY_FEE_RE.search(text)
    if cfm:
        custody_fee = parse_eur_decimal(cfm.group(1))

    return results, custody_fee


def _parse_patrimonio(text: str, fiscal_year: int) -> tuple[list[ParsedPortfolioHolding], dict[str, str]]:
    """Parse acc-3 (holdings). Returns (holdings, name→ISIN map)."""
    holdings = []
    isin_map: dict[str, str] = {}

    for m in HOLD_RE.finditer(text):
        isin = m.group(1)
        name = m.group(2).strip()
        qty = parse_eur_decimal(m.group(3))
        price = parse_eur_decimal(m.group(4))
        value = parse_eur_decimal(m.group(5))

        isin_map[name.upper()] = isin

        holdings.append(ParsedPortfolioHolding(
            isin=isin,
            name=name,
            currency="EUR",
            asset_type="Stock",
            country=country_from_isin(isin),
            casilla_714=0,
            quantity=qty,
            avg_q4_balance=_D("0"),
            value_dec31_eur=value,
            fiscal_valuation=value,
            price=price,
        ))

    return holdings, isin_map


# ── Public API ─────────────────────────────────────────────────────────

def parse_bbva_pdfs(pdf_paths: list[Path]) -> BBVAAnnualReport:
    """Parse 1-3 BBVA PDFs and combine into a single report.

    Accepts any combination of the 3 document types.
    The patrimonio (acc-3) is parsed first to build the ISIN map.
    """
    texts: dict[str, tuple[str, int]] = {}  # type → (text, fiscal_year)

    for path in pdf_paths:
        text = _extract_all_text(path)
        fiscal_year = _parse_fiscal_year(text)
        doc_type = _detect_document_type(text)
        texts[doc_type] = (text, fiscal_year)

    # Determine fiscal year (should be same across all PDFs)
    years = {fy for _, fy in texts.values()}
    if len(years) > 1:
        raise ValueError(f"Los PDFs de BBVA son de años diferentes: {years}")
    fiscal_year = years.pop()

    # Parse patrimonio first (provides ISIN map)
    holdings: list[ParsedPortfolioHolding] = []
    isin_map: dict[str, str] = {}
    if "patrimonio" in texts:
        holdings, isin_map = _parse_patrimonio(texts["patrimonio"][0], fiscal_year)

    # Parse operaciones
    transactions: list[ParsedTransaction] = []
    if "operaciones" in texts:
        transactions = _parse_operaciones(texts["operaciones"][0], fiscal_year, isin_map)

    # Parse dividendos
    dividends: list[ParsedTransaction] = []
    custody_fee = _D("0")
    if "dividendos" in texts:
        dividends, custody_fee = _parse_dividendos(texts["dividendos"][0], fiscal_year, isin_map)

    return BBVAAnnualReport(
        fiscal_year=fiscal_year,
        dividends=dividends,
        transactions=transactions,
        holdings=holdings,
        custody_fee=custody_fee,
        portfolio_snapshot_complete="patrimonio" in texts,
    )


