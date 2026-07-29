"""ING Bank (Spain) PDF parser.

Supports two document types:
- Información Fiscal (annual tax report): interest, dividends, buy/sell, holdings
- Certificado de Operaciones (operations certificate): buy/sell transactions only
"""

import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

from backend.importers.base import (
    INGAnnualReport,
    ParsedPortfolioHolding,
    ParsedTransaction,
    TxType,
    country_from_isin,
)

_D = Decimal
_ESPAÑA = "España"

# ── Number / date helpers ──────────────────────────────────────────────


def _parse_decimal(s: str) -> Decimal:
    """European format: 1.384,27 → 1384.27; also handles '1.384,27€'."""
    s = s.strip().rstrip("€").strip()
    return _D(s.replace(".", "").replace(",", "."))


def _parse_date(s: str) -> date:
    """DD/MM/YYYY → date."""
    d, m, y = s.split("/")
    return date(int(y), int(m), int(d))


# ── Well-known ISINs (Spanish stocks from ING holdings) ────────────────

_KNOWN_ISINS: dict[str, str] = {
    "AENA": "ES0105046009",
    "AMADEUS": "ES0109067019",
    "BA.SANTANDER": "ES0113900J37",
    "SANTANDER": "ES0113900J37",
    "ENDESA": "ES0130670112",
    "IBERDROLA": "ES0144580Y14",
    "IBE.D": "ES0144580Y14",
    "INDITEX": "ES0148396007",
    "PESCANOVA": "ES0169350016",
    "REPSOL": "ES0173516115",
    "INM.COLONIAL": "ES0139140174",
    "COLONIAL": "ES0139140174",
    "COLONIAL SFL": "ES0139140174",
    # International stocks that may appear in ING's older "without-ISIN" format
    "TWITTER INC": "US90184L1026",
    "TWITTER": "US90184L1026",
}


# ── Regex patterns ─────────────────────────────────────────────────────

YEAR_RE = re.compile(r"Información\s+Fiscal\s+(\d{4})")

# Certificado de Operaciones detection and year extraction
CERT_DOC_RE = re.compile(r"Certificado\s+de\s+Operaciones")
CERT_YEAR_RE = re.compile(r"Fecha\s+inicio:\s*\d{2}/\d{2}/(\d{4})")

# Certificado de Operaciones transaction line:
# "30/12/2020 IBIO INC -25 1,090 USD 5,700"
# "28/05/2020 AENA +10 135,400 EUR 1.364,110"
CERT_TX_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+"                    # Date
    r"([A-Z][A-Z0-9\s.]+?)\s+"                   # Name (lazy)
    r"([+-]\d+)\s+"                               # Signed qty (+BUY / -SELL)
    r"([\d.,]+)\s+"                              # Price
    r"(EUR|USD|GBP|CHF|SEK|NOK|DKK|CAD)\s+"     # Currency
    r"([\d.,]+)"                                 # Importe
)

# Interest line: "Cuenta NÓMINA  1714909886  1  200,00€  0,00 €  38,00€"
INTEREST_RE = re.compile(
    r"Cuenta\s+\S+\s+"           # Product name
    r"(\d+)\s+"                  # Account number
    r"\d+\s+"                    # Cod. Tit.
    r"([\d.,]+)\s*€\s+"         # Intereses
    r"[\d.,]+\s*€\s+"           # Intereses negativos (ignored)
    r"([\d.,]+)\s*€"            # Retenciones
)

# Dividend line WITH ISIN (2024+): "BA.SANTANDER (ES0113900J37)  Nacional  DIVIDENDO  480,90€  91,37 €"
DIV_RE = re.compile(
    r"([A-Z][A-Z0-9.]+(?:\s+[A-Z0-9.]+)*)\s+"  # Name (e.g. "BA.SANTANDER")
    r"\(([A-Z]{2}[A-Z0-9]{10})\)\s+"            # ISIN in parentheses
    r"Nacional\s+"                                # Market (Nacional)
    r"(?:DIVIDENDO|Dividendo)\s+"                 # Concept
    r"([\d.,]+)\s*€\s+"                          # Importe bruto
    r"([\d.,]+)\s*€"                             # Retenciones
)

# Dividend line WITHOUT ISIN (2021-2025): "ENDESA  Nacional  Dividendo  35,00€  6,65€"
DIV_NO_ISIN_RE = re.compile(
    r"([A-Z][A-Z0-9.]+(?:\s+[A-Z0-9.]+)*)\s+"  # Name
    r"Nacional\s+"                                # Market
    r"(?:DIVIDENDO|Dividendo)\s+"                 # Concept
    r"([\d.,]+)\s*€\s+"                          # Importe bruto
    r"([\d.,]+)\s*€"                             # Retenciones
)

# Transaction line: "COLONIAL  Nacional  20/06/2024  COMPRA  20  117,95 €"
# Also handles: Internacional market, BAJA POR CANJE type
TX_RE = re.compile(
    r"([A-Z][A-Z0-9.\s]+?)\s+"  # Name
    r"(?:Nacional|Internacional)\s+"  # Market
    r"(\d{2}/\d{2}/\d{4})\s+"  # Date
    r"(COMPRA|VENTA|SUSCRIPCION|BAJA POR CANJE)\s+"  # Type
    r"(\d+)\s+"                 # Nº de títulos
    r"([\d.,]+)\s*€"           # Importe total
)

# Holdings line WITH ISIN (2023+): "ES0113900J37 - Nacional 4809 4,51€ 21.688,59€"
# Name appears on the NEXT line (e.g. "BA.SANTANDER")
HOLD_RE = re.compile(
    r"([A-Z]{2}[A-Z0-9]{10})\s+-\s+"  # ISIN
    r"Nacional\s+"                      # Market
    r"(\d+)\s+"                         # Nº de títulos
    r"([\d.,]+)\s*€\s+"               # Cambio (price)
    r"([\d.,]+)\s*€"                  # Valoración
)

# Holdings line WITHOUT ISIN (2021-2022): "AENA  Nacional  10  139,86€  1.398,60€"
HOLD_NO_ISIN_RE = re.compile(
    r"([A-Z][A-Z0-9.]+(?:\s+[A-Z0-9.]+)*)\s+"  # Name
    r"(?:Nacional|Internacional)\s+"              # Market
    r"(\d+)\s+"                                  # Qty
    r"([\d.,]+)\s*€\s+"                         # Price
    r"([\d.,]+)\s*€"                            # Value
)

# Rights: "DERECHOS REPSOL, S.A.  07/01/2021  13  2,64€  0,50€"
RIGHTS_RE = re.compile(
    r"DERECHOS\s+(.+?)\s+"                # Name (e.g. "REPSOL, S.A.")
    r"(\d{2}/\d{2}/\d{4})\s+"           # Date
    r"(\d+)\s+"                          # Qty
    r"([\d.,]+)\s*€\s+"                 # Amount
    r"([\d.,]+)\s*€"                    # Retenciones
)

# ISIN in parentheses (next line after transaction): "(CA05156X8843)"
ISIN_PAREN_RE = re.compile(r"\(([A-Z]{2}[A-Z0-9]{10})\)")

# Fund holding: "Fondo Cartera NARANJA ... 954,71  12,28€  11.722,31€"
FUND_RE = re.compile(
    r"([\d.,]+)\s+"     # Participaciones
    r"([\d.,]+)\s*€\s+" # Valor liquidativo
    r"([\d.,]+)\s*€"    # Importe
)


# ── PDF text extraction ────────────────────────────────────────────────

def _extract_all_text(pdf_path: Path) -> str:
    """Extract all text from the PDF."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    return text


# ── Section parsers ────────────────────────────────────────────────────

def _parse_fiscal_year(text: str) -> int:
    m = YEAR_RE.search(text)
    if m:
        return int(m.group(1))
    raise ValueError("No se encontró el año fiscal en el PDF de ING")


def _parse_interest(text: str, fiscal_year: int) -> list[ParsedTransaction]:
    """Parse interest section (Intereses de cuentas)."""
    results = []
    for m in INTEREST_RE.finditer(text):
        gross = _parse_decimal(m.group(2))
        withholding = _parse_decimal(m.group(3))
        if gross <= 0:
            continue
        results.append(ParsedTransaction(
            tx_type=TxType.INTEREST,
            trade_date=date(fiscal_year, 12, 31),
            isin="",
            name=f"Intereses cuenta ING {m.group(1)}",
            country=_ESPAÑA,
            quantity=_D("0"),
            price=_D("0"),
            currency="EUR",
            gross_amount=gross,
            withholding_tax=withholding,
            domestic_withholding_tax=withholding,
            foreign_withholding_tax=_D("0"),
            net_amount_eur=gross - withholding,
        ))
    return results


def _resolve_isin(name: str, isin_map: dict[str, str]) -> str:
    """Resolve ISIN from name using isin_map, then _KNOWN_ISINS."""
    key = name.strip().upper()
    return isin_map.get(key, "") or _KNOWN_ISINS.get(key, "")


def _parse_dividends(text: str, fiscal_year: int) -> list[ParsedTransaction]:
    """Parse dividend section (both with-ISIN and without-ISIN formats)."""
    results = []

    # Try with-ISIN format first (2024+)
    for m in DIV_RE.finditer(text):
        name = m.group(1).strip()
        isin = m.group(2)
        gross = _parse_decimal(m.group(3))
        withholding = _parse_decimal(m.group(4))
        results.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=date(fiscal_year, 12, 31),
            isin=isin,
            name=name,
            country=country_from_isin(isin),
            quantity=_D("0"),
            price=_D("0"),
            currency="EUR",
            gross_amount=gross,
            withholding_tax=withholding,
            domestic_withholding_tax=withholding,
            foreign_withholding_tax=_D("0"),
            net_amount_eur=gross - withholding,
        ))

    # If no with-ISIN matches, try without-ISIN format (2021-2023)
    if not results:
        # Build ISIN map from holdings section
        isin_map: dict[str, str] = {}
        lines = text.split("\n")
        for i, line in enumerate(lines):
            hm = HOLD_RE.search(line)
            if hm and i + 1 < len(lines):
                isin = hm.group(1)
                next_line = lines[i + 1].strip()
                if next_line and not HOLD_RE.search(next_line) and "Total" not in next_line:
                    isin_map[next_line.upper()] = isin

        for m in DIV_NO_ISIN_RE.finditer(text):
            name = m.group(1).strip()
            gross = _parse_decimal(m.group(2))
            withholding = _parse_decimal(m.group(3))
            isin = _resolve_isin(name, isin_map)
            results.append(ParsedTransaction(
                tx_type=TxType.DIVIDEND,
                trade_date=date(fiscal_year, 12, 31),
                isin=isin,
                name=name,
                country=country_from_isin(isin) if isin else _ESPAÑA,
                quantity=_D("0"),
                price=_D("0"),
                currency="EUR",
                gross_amount=gross,
                withholding_tax=withholding,
                domestic_withholding_tax=withholding,
                foreign_withholding_tax=_D("0"),
                net_amount_eur=gross - withholding,
            ))

    return results


def _build_name_isin_map(text: str) -> dict[str, str]:
    """Build a name→ISIN map from all available sources in the text."""
    name_isin: dict[str, str] = {}

    # From dividend section (with ISIN)
    for m in DIV_RE.finditer(text):
        name_isin[m.group(1).strip().upper()] = m.group(2)

    # From holdings section (with ISIN) — name on next line
    lines = text.split("\n")
    for i, line in enumerate(lines):
        hm = HOLD_RE.search(line)
        if hm and i + 1 < len(lines):
            isin = hm.group(1)
            next_line = lines[i + 1].strip()
            if next_line and not HOLD_RE.search(next_line) and "Total" not in next_line:
                name_isin[next_line.upper()] = isin

    # From ISINs in parentheses anywhere in text (e.g. transaction lines)
    for line in lines:
        pm = ISIN_PAREN_RE.search(line)
        if pm:
            isin = pm.group(1)
            # Extract name before the ISIN — look at preceding text
            before = line[:pm.start()].strip()
            if before:
                # Clean up: name might be continuation of previous line
                name_isin.setdefault(before.upper(), isin)

    return name_isin


def _parse_transactions(text: str, fiscal_year: int) -> list[ParsedTransaction]:
    """Parse buy/sell transactions and rights sections."""
    name_isin = _build_name_isin_map(text)

    # Add _KNOWN_ISINS as fallback
    for k, v in _KNOWN_ISINS.items():
        name_isin.setdefault(k.upper(), v)

    lines = text.split("\n")
    results = []

    # Parse standard transactions (COMPRA, VENTA, SUSCRIPCION, BAJA POR CANJE)
    for i, line in enumerate(lines):
        m = TX_RE.search(line)
        if not m:
            continue

        name = m.group(1).strip()
        trade_date = _parse_date(m.group(2))
        op_type_str = m.group(3)
        qty = _D(m.group(4))
        amount = _parse_decimal(m.group(5))

        if op_type_str in ("VENTA", "BAJA POR CANJE"):
            tx_type = TxType.SELL
        else:
            tx_type = TxType.BUY

        # Resolve ISIN: first from name map, then check next line for (ISIN)
        isin = name_isin.get(name.upper(), "")
        if not isin and i + 1 < len(lines):
            pm = ISIN_PAREN_RE.search(lines[i + 1])
            if pm:
                isin = pm.group(1)

        # Handle Iberdrola scrip dividends (IBE.XX.XXXX → Iberdrola ISIN)
        if not isin and name.upper().startswith("IBE"):
            isin = name_isin.get("IBERDROLA", _KNOWN_ISINS.get("IBERDROLA", "ES0144580Y14"))

        # Handle Repsol scrip dividends (REP MM.YY → Repsol ISIN)
        if not isin and name.upper().startswith("REP"):
            isin = name_isin.get("REPSOL", _KNOWN_ISINS.get("REPSOL", "ES0173516115"))
            name = f"REPSOL scrip {name}"

        results.append(ParsedTransaction(
            tx_type=tx_type,
            trade_date=trade_date,
            isin=isin,
            name=name,
            country=country_from_isin(isin) if isin else _ESPAÑA,
            quantity=qty,
            price=amount / qty if qty else _D("0"),
            currency="EUR",
            gross_amount=amount,
            fees=_D("0"),
            net_amount_eur=amount,
        ))

    # Parse rights (Transmisión de derechos de suscripción)
    for m in RIGHTS_RE.finditer(text):
        raw_name = m.group(1).strip()
        trade_date = _parse_date(m.group(2))
        qty = _D(m.group(3))
        amount = _parse_decimal(m.group(4))
        withholding = _parse_decimal(m.group(5))

        # Extract stock name from "REPSOL, S.A." → "REPSOL"
        # Also strip trailing date codes: "IBERDROLA 07.2025" → "IBERDROLA"
        stock_name = raw_name.split(",")[0].strip()
        stock_name = re.sub(r"\s+\d{2}\.\d{4}$", "", stock_name)
        parent_isin = name_isin.get(stock_name.upper(), "")

        # Rights have their own ISIN separate from the parent stock; we don't
        # know it here, so leave ISIN empty to keep FIFO of the parent stock
        # intact. The venta de derechos is still a "ganancia patrimonial" and
        # the withholding is preserved.
        results.append(ParsedTransaction(
            tx_type=TxType.SELL,
            trade_date=trade_date,
            isin="",
            name=f"Derechos {stock_name}",
            country=country_from_isin(parent_isin) if parent_isin else _ESPAÑA,
            quantity=qty,
            price=amount / qty if qty else _D("0"),
            currency="EUR",
            gross_amount=amount,
            withholding_tax=withholding,
            domestic_withholding_tax=withholding,
            foreign_withholding_tax=_D("0"),
            net_amount_eur=amount - withholding,
        ))

    return results


def _parse_holdings(text: str, fiscal_year: int) -> list[ParsedPortfolioHolding]:
    """Parse year-end holdings section (both with-ISIN and without-ISIN)."""
    holdings = []

    # Build ISIN → name map from dividends
    isin_name: dict[str, str] = {}
    for m in DIV_RE.finditer(text):
        isin_name[m.group(2)] = m.group(1).strip()

    # Try with-ISIN format first (2023+)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        hm = HOLD_RE.search(line)
        if not hm:
            continue
        isin = hm.group(1)
        qty = _D(hm.group(2))
        price = _parse_decimal(hm.group(3))
        value = _parse_decimal(hm.group(4))

        # Name from next line or from dividend map
        name = isin_name.get(isin, "")
        if not name and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and not HOLD_RE.search(next_line) and "Total" not in next_line:
                name = next_line
                isin_name.setdefault(isin, name)
        if not name:
            name = isin

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

    # If no with-ISIN matches, try without-ISIN format (2021-2022)
    if not holdings:
        # Find the holdings section (after "Cuenta de valores")
        in_holdings = False
        for line in lines:
            if "Cuenta de valores" in line:
                in_holdings = True
                continue
            if not in_holdings:
                continue
            if "Total:" in line:
                break

            hm = HOLD_NO_ISIN_RE.search(line)
            if not hm:
                continue

            name = hm.group(1).strip()
            qty = _D(hm.group(2))
            price = _parse_decimal(hm.group(3))
            value = _parse_decimal(hm.group(4))
            isin = _KNOWN_ISINS.get(name.upper(), "")

            holdings.append(ParsedPortfolioHolding(
                isin=isin,
                name=name,
                currency="EUR",
                asset_type="Stock",
                country=country_from_isin(isin) if isin else _ESPAÑA,
                casilla_714=0,
                quantity=qty,
                avg_q4_balance=_D("0"),
                value_dec31_eur=value,
                fiscal_valuation=value,
                price=price,
            ))

    return holdings


# ── Certificado de Operaciones parser ─────────────────────────────────


def _parse_cert_transactions(text: str) -> list[ParsedTransaction]:
    """Parse buy/sell transactions from a 'Certificado de Operaciones' PDF."""
    name_isin: dict[str, str] = {k.upper(): v for k, v in _KNOWN_ISINS.items()}
    results = []
    for m in CERT_TX_RE.finditer(text):
        trade_date = _parse_date(m.group(1))
        name = m.group(2).strip()
        qty_signed = int(m.group(3))
        price = _parse_decimal(m.group(4))
        currency = m.group(5)
        amount = _parse_decimal(m.group(6))

        qty = _D(abs(qty_signed))
        tx_type = TxType.BUY if qty_signed > 0 else TxType.SELL
        isin = name_isin.get(name.upper(), "")

        results.append(ParsedTransaction(
            tx_type=tx_type,
            trade_date=trade_date,
            isin=isin,
            name=name,
            country=country_from_isin(isin) if isin else _ESPAÑA,
            quantity=qty,
            price=price,
            currency=currency,
            gross_amount=amount,
            fees=_D("0"),
            net_amount_eur=amount,
        ))
    return results


# ── Public API ─────────────────────────────────────────────────────────

def parse_ing_report(pdf_path: Path) -> INGAnnualReport:
    """Parse an ING PDF (Información Fiscal or Certificado de Operaciones)."""
    text = _extract_all_text(pdf_path)

    if CERT_DOC_RE.search(text):
        m = CERT_YEAR_RE.search(text)
        if not m:
            raise ValueError("No se encontró el año fiscal en el PDF de ING")
        fiscal_year = int(m.group(1))
        return INGAnnualReport(
            fiscal_year=fiscal_year,
            interest=[],
            dividends=[],
            transactions=_parse_cert_transactions(text),
            holdings=[],
            portfolio_snapshot_complete=False,
        )

    fiscal_year = _parse_fiscal_year(text)
    return INGAnnualReport(
        fiscal_year=fiscal_year,
        interest=_parse_interest(text, fiscal_year),
        dividends=_parse_dividends(text, fiscal_year),
        transactions=_parse_transactions(text, fiscal_year),
        holdings=_parse_holdings(text, fiscal_year),
        portfolio_snapshot_complete=True,
    )


def compute_file_hash(pdf_path: Path) -> str:
    """Compute SHA-256 hash of a PDF file."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
