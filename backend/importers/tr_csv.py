"""Trade Republic transaction-export CSV parser.

Parses the "Transaction export" CSV that TR lets users download from the app.
Unlike the annual Tax Report PDF, the CSV is a running activity ledger across
all years — richer for raw transactions, but lacks pre-computed fiscal data
(capital_gains FIFO matches, holdings snapshot, Modelo 100/714 casillas).

Scope (per user decision):
- Transactions only. Holdings, capital_gains, withholdings and casillas are
  left empty on the returned TRTaxReport; the PDF stays authoritative for
  those year-end fiscal figures.
- Cash interest rows are emitted as INTEREST transactions flagged with
  casilla=27 (rendimientos del capital mobiliario).
- Non-investment rows (card, transfers, saveback, tax-optimisation, migration
  rebookings, cancelled spin-offs, liquidation pairs) are skipped entirely.
"""

import csv
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

_ISIN_IN_DESC = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")

from backend.importers.base import (
    ParsedTransaction,
    TRTaxReport,
    TxType,
    country_from_isin,
)

# Category/type combos we import.
_KEEP: set[tuple[str, str]] = {
    ("TRADING", "BUY"),
    ("TRADING", "SELL"),
    ("CASH", "DIVIDEND"),
    ("CASH", "INTEREST_PAYMENT"),
    ("CORPORATE_ACTION", "SPIN_OFF"),
    ("CORPORATE_ACTION", "INTERMEDIATE_SECURITIES_DISTRIBUTION"),
    ("CORPORATE_ACTION", "DIVIDEND_REINVESTMENT"),
}


def _dec(s: str | None) -> Decimal:
    if not s:
        return Decimal("0")
    try:
        return Decimal(s.strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_date(row: dict) -> date:
    s = (row.get("date") or "").strip()
    if s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    # fallback: take YYYY-MM-DD prefix from datetime
    dt = (row.get("datetime") or "").strip()
    return datetime.strptime(dt[:10], "%Y-%m-%d").date()


def _build_trading(row: dict, is_buy: bool) -> ParsedTransaction | None:
    isin = (row.get("symbol") or "").strip()
    if not isin:
        return None
    qty = abs(_dec(row.get("shares")))
    if qty == 0:
        return None
    price = _dec(row.get("price"))
    amount = _dec(row.get("amount"))
    fee = abs(_dec(row.get("fee")))
    tax = abs(_dec(row.get("tax")))
    fees = fee + tax
    if is_buy:
        net = abs(amount)          # cash out
        gross = net - fees          # price × qty, roughly
    else:
        net = amount                # cash in
        gross = net + fees          # before costs
    return ParsedTransaction(
        tx_type=TxType.BUY if is_buy else TxType.SELL,
        trade_date=_parse_date(row),
        isin=isin,
        name=(row.get("name") or "").strip(),
        country=country_from_isin(isin),
        quantity=qty,
        price=price,
        currency=(row.get("currency") or "EUR").strip() or "EUR",
        exchange_rate=Decimal("1"),
        gross_amount=gross,
        fees=fees,
        net_amount_eur=net,
    )


def _build_dividend(row: dict) -> ParsedTransaction | None:
    isin = (row.get("symbol") or "").strip()
    if not isin:
        m = _ISIN_IN_DESC.search(row.get("description") or "")
        if not m:
            return None
        isin = m.group(1)
    net = _dec(row.get("amount"))
    wht = abs(_dec(row.get("tax")))
    gross = net + wht
    return ParsedTransaction(
        tx_type=TxType.DIVIDEND,
        trade_date=_parse_date(row),
        isin=isin,
        name=(row.get("name") or "").strip(),
        country=country_from_isin(isin),
        quantity=Decimal("0"),
        price=Decimal("0"),
        currency=(row.get("currency") or "EUR").strip() or "EUR",
        exchange_rate=Decimal("1"),
        gross_amount=gross,
        fees=Decimal("0"),
        withholding_tax=wht,
        net_amount_eur=net,
        casilla=29,
    )


def _build_interest(row: dict) -> ParsedTransaction | None:
    amount = _dec(row.get("amount"))
    if amount == 0:
        return None
    return ParsedTransaction(
        tx_type=TxType.INTEREST,
        trade_date=_parse_date(row),
        isin="",
        name=(row.get("description") or "Interés Trade Republic").strip(),
        country="Alemania",
        quantity=Decimal("0"),
        price=Decimal("0"),
        currency=(row.get("currency") or "EUR").strip() or "EUR",
        exchange_rate=Decimal("1"),
        gross_amount=amount,
        fees=Decimal("0"),
        net_amount_eur=amount,
        casilla=27,
    )


def _build_spinoff(row: dict) -> ParsedTransaction | None:
    """Corporate action that adds shares at zero tracked cost.

    Covers SPIN_OFF, INTERMEDIATE_SECURITIES_DISTRIBUTION (rights allocation)
    and DIVIDEND_REINVESTMENT (DRIP). For DRIP the true cost is the matching
    CASH/DIVIDEND earlier in the file, but TR doesn't link them in the CSV
    and we keep PDF as source of truth for tax figures — so zero-cost is
    the safe default; the supervisor will surface it.
    """
    isin = (row.get("symbol") or "").strip()
    if not isin:
        return None
    qty = _dec(row.get("shares"))
    if qty <= 0:
        return None
    return ParsedTransaction(
        tx_type=TxType.SPINOFF,
        trade_date=_parse_date(row),
        isin=isin,
        name=(row.get("name") or "").strip(),
        country=country_from_isin(isin),
        quantity=qty,
        price=Decimal("0"),
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=Decimal("0"),
        fees=Decimal("0"),
        net_amount_eur=Decimal("0"),
    )


_BUILDERS = {
    ("TRADING", "BUY"): lambda r: _build_trading(r, is_buy=True),
    ("TRADING", "SELL"): lambda r: _build_trading(r, is_buy=False),
    ("CASH", "DIVIDEND"): _build_dividend,
    ("CASH", "INTEREST_PAYMENT"): _build_interest,
    ("CORPORATE_ACTION", "SPIN_OFF"): _build_spinoff,
    ("CORPORATE_ACTION", "INTERMEDIATE_SECURITIES_DISTRIBUTION"): _build_spinoff,
    ("CORPORATE_ACTION", "DIVIDEND_REINVESTMENT"): _build_spinoff,
}


def _iter_rows(path: Path) -> list[ParsedTransaction]:
    out: list[ParsedTransaction] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = ((row.get("category") or "").strip(), (row.get("type") or "").strip())
            builder = _BUILDERS.get(key)
            if builder is None:
                continue
            tx = builder(row)
            if tx is not None:
                out.append(tx)
    return out


def parse_tr_csv(path: str | Path) -> TRTaxReport:
    """Parse a TR Transaction export CSV into a TRTaxReport.

    Only `transactions` and `dividends` (and interest inside `transactions`)
    are populated. The caller decides how to merge with an existing account.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    parsed = _iter_rows(path)
    if not parsed:
        raise ValueError("CSV contained no importable rows (all categories skipped)")

    dividends = [t for t in parsed if t.tx_type is TxType.DIVIDEND]
    other_tx = [t for t in parsed if t.tx_type is not TxType.DIVIDEND]
    dates = [t.trade_date for t in parsed]
    min_date, max_date = min(dates), max(dates)

    return TRTaxReport(
        client_id="TR",
        period_start=min_date,
        period_end=max_date,
        currency="EUR",
        fiscal_year=max_date.year,
        dividends=dividends,
        capital_gains=[],
        transactions=other_tx,
        withholdings=[],
        holdings=[],
        casillas_modelo_100=[],
        casillas_modelo_714=[],
    )


def compute_file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
