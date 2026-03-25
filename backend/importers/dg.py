"""DEGIRO Annual Report (Informe Anual) PDF parser.

Extracts:
- Dividends (Dividendos, Cupones y otras remuneraciones)
- Gains/Losses per product (Relación de ganancias y pérdidas)
- Year-end holdings (Certificado de Beneficiario)
- Transaction history (Beneficios y pérdidas derivadas)
"""

import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

from backend.importers.base import (
    DGAnnualReport,
    ParsedGainLoss,
    ParsedPortfolioHolding,
    ParsedTransaction,
    TxType,
)

# ── Number / date helpers ──────────────────────────────────────────────

_D = Decimal


def _parse_decimal(s: str) -> Decimal:
    """European format: 1.300,00 → 1300.00"""
    return _D(s.replace(".", "").replace(",", "."))


def _parse_date(s: str) -> date:
    """DD/MM/YYYY → date."""
    d, m, y = s.split("/")
    return date(int(y), int(m), int(d))


def _country_from_isin(isin: str) -> str:
    """Derive 2-letter country code from ISIN prefix."""
    return isin[:2] if isin and len(isin) >= 2 else ""


# ISO 2-letter → Spanish full name (matching TR format)
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
    "AT": "Austria",
    "BE": "Bélgica",
    "LU": "Luxemburgo",
    "NO": "Noruega",
    "SE": "Suecia",
    "DK": "Dinamarca",
    "FI": "Finlandia",
    "JP": "Japón",
    "CA": "Canadá",
    "AU": "Australia",
}


def _resolve_country(code: str) -> str:
    """Convert 2-letter ISO code to full Spanish name."""
    return _COUNTRY_NAMES.get(code.upper(), code) if code else ""


# ── Regex patterns ─────────────────────────────────────────────────────

# Section headers
SEC_DIVIDENDS = "Dividendos, Cupones y otras remuneraciones"
SEC_GAINS = "Relación de ganancias y pérdidas por producto"
SEC_HOLDINGS = "Certificado de Beneficiario"
SEC_TRANSACTIONS = "Beneficios y pérdidas derivadas de la transmisión"

# Dividend line: CC Product 40,00 EUR -7,60 EUR 32,40 EUR
DIV_RE = re.compile(
    r"^([A-Z]{2})\s+"
    r"(.+?)\s+"
    r"([\d.,]+)\s+EUR\s+"
    r"(-?[\d.,]+)\s+EUR\s+"
    r"(-?[\d.,]+)\s+EUR\s*$"
)

# Gains per product: Product ISIN P&L EUR Commission EUR Tax EUR
GAINS_RE = re.compile(
    r"^(.+?)\s+"
    r"([A-Z]{2}[A-Z0-9]{10})\s+"
    r"(-?[\d.,]+)\s+EUR\s+"
    r"([\d.,]+)\s+EUR\s+"
    r"([\d.,]+)\s+EUR\s*$"
)

# Holdings: Product ISIN Type Exchange Qty Currency Price Value
HOLD_RE = re.compile(
    r"^(.+?)\s+"
    r"([A-Z]{2}[A-Z0-9]{10})\s+"
    r"(Stock|Option|ETF|Bond|Fund)\s+"
    r"([A-Z]{2,4})\s+"
    r"(-?\d+)\s+"
    r"([A-Z]{3})\s+"
    r"([\d.,]+)\s+"
    r"(-?[\d.,]+)\s*$"
)

# Transactions: Date Product ISIN C/V Qty Price LocalVal EURVal Commission FX [P&L]
TX_RE = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+"
    r"(.+?)\s+"
    r"([A-Z]{2}[A-Z0-9]{10})\s+"
    r"([CV])\s+"
    r"(\d+)\s+"
    r"([\d.,]+)\s+"
    r"(-?[\d.,]+)\s+"
    r"(-?[\d.,]+)\s+"
    r"([\d.,]+)\s+"
    r"([\d.,]+)"
    r"(?:\s+(-?[\d.,]+))?"
    r"\s*$"
)

YEAR_RE = re.compile(r"Informe\s+(?:Fiscal|Anual)\s+(?:para\s+el\s+año\s+)?(\d{4})")

TOTAL_LINE_RE = re.compile(r"^Total\s+", re.IGNORECASE)


# ── Section extraction ─────────────────────────────────────────────────

def _extract_text(pdf_path: Path) -> tuple[str, str]:
    """Extract text from PDF.

    Returns (full_text, data_text) where data_text skips page 1 (cover/TOC)
    to avoid duplicate section headers.
    """
    full_text = ""
    data_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            full_text += page_text + "\n"
            if i > 0:
                data_text += page_text + "\n"
    return full_text, data_text


def _get_section_text(full_text: str, start_marker: str, end_markers: list[str]) -> str:
    """Extract text between section markers."""
    idx = full_text.find(start_marker)
    if idx == -1:
        return ""
    text = full_text[idx + len(start_marker):]
    for end in end_markers:
        end_idx = text.find(end)
        if end_idx != -1:
            text = text[:end_idx]
            break
    return text


# ── Section parsers ────────────────────────────────────────────────────

def _parse_fiscal_year(text: str) -> int:
    """Extract fiscal year from PDF text."""
    m = YEAR_RE.search(text)
    if m:
        return int(m.group(1))
    raise ValueError("No se encontró el año fiscal en el PDF de DEGIRO")


def _parse_dividends(text: str, fiscal_year: int) -> list[ParsedTransaction]:
    """Parse dividend section."""
    section = _get_section_text(
        text,
        SEC_DIVIDENDS,
        [SEC_GAINS, SEC_HOLDINGS, SEC_TRANSACTIONS, "Distribuciones Fondos"],
    )
    dividends = []
    for line in section.splitlines():
        line = line.strip()
        m = DIV_RE.match(line)
        if not m:
            continue
        country = _resolve_country(m.group(1))
        name = m.group(2).strip()
        gross = _parse_decimal(m.group(3))
        withholding = _parse_decimal(m.group(4))
        net = _parse_decimal(m.group(5))

        dividends.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=date(fiscal_year, 12, 31),
            isin="",  # enriched later
            name=name,
            country=country,
            quantity=_D("0"),
            price=_D("0"),
            currency="EUR",
            gross_amount=gross,
            withholding_tax=withholding,
            net_amount_eur=net,
        ))
    return dividends


def _parse_gains_summary(text: str) -> list[ParsedGainLoss]:
    """Parse gains/losses per product section."""
    section = _get_section_text(
        text,
        SEC_GAINS,
        [SEC_HOLDINGS, SEC_TRANSACTIONS, "Certificado de Beneficiario"],
    )
    results = []
    for line in section.splitlines():
        line = line.strip()
        if TOTAL_LINE_RE.match(line):
            break
        m = GAINS_RE.match(line)
        if not m:
            continue
        results.append(ParsedGainLoss(
            isin=m.group(2),
            name=m.group(1).strip(),
            realized_pl_eur=_parse_decimal(m.group(3)),
            commission_eur=_parse_decimal(m.group(4)),
            transaction_tax_eur=_parse_decimal(m.group(5)),
        ))
    return results


def _parse_holdings(text: str, fiscal_year: int) -> list[ParsedPortfolioHolding]:
    """Parse year-end holdings section."""
    section = _get_section_text(
        text,
        SEC_HOLDINGS,
        [SEC_TRANSACTIONS, "Beneficios y pérdidas"],
    )
    holdings = []
    for line in section.splitlines():
        line = line.strip()
        m = HOLD_RE.match(line)
        if not m:
            continue
        isin = m.group(2)
        qty = _D(m.group(5))
        price = _parse_decimal(m.group(7))
        value = _parse_decimal(m.group(8))

        holdings.append(ParsedPortfolioHolding(
            isin=isin,
            name=m.group(1).strip(),
            currency=m.group(6),
            asset_type=m.group(3),
            country=_resolve_country(_country_from_isin(isin)),
            casilla_714=0,
            quantity=qty,
            avg_q4_balance=_D("0"),
            value_dec31_eur=value,
            fiscal_valuation=value,
            price=price,
            exchange=m.group(4),
        ))
    return holdings


def _parse_transactions(text: str) -> list[ParsedTransaction]:
    """Parse detailed transaction history."""
    section = _get_section_text(
        text,
        SEC_TRANSACTIONS,
        ["Informe anual de flatex", "Informe Anual"],
    )
    transactions = []
    for line in section.splitlines():
        line = line.strip()
        if TOTAL_LINE_RE.match(line):
            break
        m = TX_RE.match(line)
        if not m:
            continue

        trade_date = _parse_date(m.group(1))
        isin = m.group(3)
        trade_type = m.group(4)  # C=buy, V=sell
        qty = _D(m.group(5))
        price = _parse_decimal(m.group(6))
        eur_value = _parse_decimal(m.group(8))
        commission = _parse_decimal(m.group(9))
        fx_rate = _parse_decimal(m.group(10))
        pl_raw = m.group(11)
        realized_pl = _parse_decimal(pl_raw) if pl_raw else None

        tx_type = TxType.BUY if trade_type == "C" else TxType.SELL

        transactions.append(ParsedTransaction(
            tx_type=tx_type,
            trade_date=trade_date,
            isin=isin,
            name=m.group(2).strip(),
            country=_resolve_country(_country_from_isin(isin)),
            quantity=qty,
            price=price,
            currency="EUR",
            exchange_rate=fx_rate,
            gross_amount=eur_value,
            fees=commission,
            net_amount_eur=eur_value,
            realized_pl_eur=realized_pl,
        ))
    return transactions


# ── Enrichment ─────────────────────────────────────────────────────────

def _build_name_isin_map(
    holdings: list[ParsedPortfolioHolding],
    transactions: list[ParsedTransaction],
    gains: list[ParsedGainLoss],
) -> dict[str, str]:
    """Build product-name → ISIN map for enriching dividends."""
    name_map: dict[str, str] = {}

    # Holdings are most reliable (clean names)
    for h in holdings:
        if h.isin and h.asset_type == "Stock":
            name_map[h.name.lower()] = h.isin

    # Gains summary and transactions as fallback
    for g in gains:
        key = g.name.lower()
        if key not in name_map and g.isin:
            name_map[key] = g.isin
    for tx in transactions:
        key = tx.name.lower()
        if key not in name_map and tx.isin:
            name_map[key] = tx.isin

    return name_map


def _enrich_dividends(
    dividends: list[ParsedTransaction],
    name_map: dict[str, str],
) -> None:
    """Add ISINs and country to dividend entries using name→ISIN map."""
    for div in dividends:
        if div.isin:
            continue
        key = div.name.lower()
        isin = name_map.get(key, "")
        if isin:
            div.isin = isin
            if not div.country or len(div.country) != 2:
                div.country = _resolve_country(_country_from_isin(isin))


# ── Public API ─────────────────────────────────────────────────────────

def parse_dg_annual_report(pdf_path: Path) -> DGAnnualReport:
    """Parse a DEGIRO Annual Report PDF.

    Returns a DGAnnualReport with dividends, transactions, holdings,
    and gains summary.
    """
    full_text, data_text = _extract_text(pdf_path)

    fiscal_year = _parse_fiscal_year(full_text)
    dividends = _parse_dividends(data_text, fiscal_year)
    gains = _parse_gains_summary(data_text)
    holdings = _parse_holdings(data_text, fiscal_year)
    transactions = _parse_transactions(data_text)

    # Enrich dividends with ISINs
    name_map = _build_name_isin_map(holdings, transactions, gains)
    _enrich_dividends(dividends, name_map)

    return DGAnnualReport(
        fiscal_year=fiscal_year,
        dividends=dividends,
        transactions=transactions,
        holdings=holdings,
        gains_summary=gains,
    )


def compute_file_hash(pdf_path: Path) -> str:
    """Compute SHA-256 hash of a PDF file."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
