"""eToro XLSX parser for annual account statements.

eToro provides a single XLSX file per fiscal year with sheets:
- Account Summary: fiscal year dates, totals
- Dividends: individual dividend payments with ISIN, EUR amounts
- Closed Positions: realized gains/losses with open/close info
- Account Activity: timeline of all events (opens, dividends, withdrawals)
- Financial Summary: aggregated P&L by category

Column layouts vary between years (e.g. 2024 has 10 dividend columns,
2023/2025 have 14). We detect columns by header name, not index.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

from backend.importers.base import (
    EToroAnnualReport,
    ParsedCapitalGain,
    ParsedTransaction,
    TxType,
    country_from_isin,
)

_D = Decimal

# eToro uses ticker symbols in Account Activity but full names in Dividends.
# Map well-known tickers to ISINs as fallback.
_KNOWN_TICKER_ISINS: dict[str, str] = {
    "MSFT": "US5949181045",
    "AAPL": "US0378331005",
    "GOOGL": "US02079K3059",
    "AMZN": "US0231351067",
    "TSLA": "US88160R1014",
    "NVDA": "US67066G1040",
    "META": "US30303M1027",
}


def _to_decimal(val) -> Decimal:
    """Convert cell value to Decimal, handling None/empty/string."""
    if val is None or val == "" or val == "-":
        return _D("0")
    if isinstance(val, (int, float)):
        return _D(str(val))
    return _D(str(val).strip())


def _to_date(val) -> date:
    """Convert cell value to date. Handles datetime objects and DD/MM/YYYY strings."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    # String format: DD/MM/YYYY or DD/MM/YYYY HH:MM:SS
    s = str(val).strip().split(" ")[0]
    parts = s.split("/")
    return date(int(parts[2]), int(parts[1]), int(parts[0]))


def _parse_withholding_rate(val) -> Decimal:
    """Parse withholding rate like '15 %' or '15%' or 0.15."""
    if val is None or val == "" or val == "-":
        return _D("0")
    s = str(val).strip().replace("%", "").strip()
    rate = _D(s)
    # If > 1, it's a percentage (e.g. 15), convert to decimal
    if rate > 1:
        rate = rate / 100
    return rate


def _col_index(headers: list[str], *names: str) -> int | None:
    """Find column index by matching any of the given names (case-insensitive)."""
    for i, h in enumerate(headers):
        if h:
            h_lower = h.strip().lower()
            for name in names:
                if name.lower() == h_lower:
                    return i
    return None


def _require_col(headers: list[str], *names: str) -> int:
    """Like _col_index but raises if not found."""
    idx = _col_index(headers, *names)
    if idx is None:
        raise ValueError(f"Column not found: {names} in {headers}")
    return idx


def _read_sheet(wb: openpyxl.Workbook, name: str) -> tuple[list[str], list[tuple]]:
    """Read sheet headers and data rows. Returns (headers, data_rows)."""
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return [], []
    headers = [str(h).strip() if h else "" for h in rows[0]]
    return headers, rows[1:]


_EQUITY_TYPES = {"stocks", "etf"}


def _skip_non_equity(row: tuple, type_col: int | None) -> bool:
    """Return True if this row's asset type is not stocks/ETF."""
    if type_col is None or not row[type_col]:
        return False
    return str(row[type_col]).strip().lower() not in _EQUITY_TYPES


def _parse_fiscal_year(wb: openpyxl.Workbook) -> int:
    """Extract fiscal year from Account Summary sheet."""
    ws = wb["Account Summary"]
    for row in ws.iter_rows(min_row=1, max_row=20, values_only=True):
        if row and row[0] and "start date" in str(row[0]).lower():
            # Value is in next column
            val = row[1] if len(row) > 1 else None
            if val:
                d = _to_date(val)
                return d.year
    # Fallback: look for year in any date-like cell
    raise ValueError("Could not determine fiscal year from Account Summary")


def _parse_dividends(wb: openpyxl.Workbook) -> list[ParsedTransaction]:
    """Parse Dividends sheet — handles both 10-col and 14-col formats."""
    headers, data_rows = _read_sheet(wb, "Dividends")
    if not data_rows:
        return []

    # Find columns by name
    i_date = _require_col(headers, "Date of Payment")
    i_name = _require_col(headers, "Instrument Name")
    i_net_eur = _require_col(headers, "Net Dividend Received (EUR)")
    i_wh_rate = _require_col(headers, "Withholding Tax Rate (%)")
    i_wh_eur = _require_col(headers, "Withholding Tax Amount (EUR)")
    i_isin = _require_col(headers, "ISIN")
    i_type = _col_index(headers, "Type")

    results = []
    for row in data_rows:
        if not row or not row[i_date]:
            continue
        if _skip_non_equity(row, i_type):
            continue

        isin = str(row[i_isin]).strip() if row[i_isin] else ""
        net_eur = _to_decimal(row[i_net_eur])
        wh_eur = _to_decimal(row[i_wh_eur])

        results.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=_to_date(row[i_date]),
            isin=isin,
            name=str(row[i_name]).strip() if row[i_name] else "",
            country=country_from_isin(isin),
            quantity=_D("0"),
            price=_D("0"),
            currency="EUR",
            gross_amount=net_eur + wh_eur,
            net_amount_eur=net_eur,
            withholding_tax=wh_eur,
            domestic_withholding_tax=(wh_eur if country_from_isin(isin) == "España" else _D("0")),
            foreign_withholding_tax=(_D("0") if country_from_isin(isin) == "España" else wh_eur),
            withholding_rate=_parse_withholding_rate(row[i_wh_rate]),
        ))

    return results


def _parse_closed_positions(wb: openpyxl.Workbook) -> list[ParsedCapitalGain]:
    """Parse Closed Positions sheet → matched buy/sell pairs with realized P&L.

    eToro reports Profit(EUR) directly. Cost/proceeds in EUR are derived from
    the USD amounts + the implied FX ratio (profit_eur / profit_usd) so that
    proceeds_eur − cost_basis_eur == profit_eur exactly.
    """
    headers, data_rows = _read_sheet(wb, "Closed Positions")
    if not data_rows:
        return []

    i_action = _require_col(headers, "Action")
    i_units = _require_col(headers, "Units / Contracts")
    i_open_date = _require_col(headers, "Open Date")
    i_close_date = _require_col(headers, "Close Date")
    i_profit_usd = _require_col(headers, "Profit(USD)")
    i_profit_eur = _require_col(headers, "Profit(EUR)")
    i_open_rate = _require_col(headers, "Open Rate")
    i_close_rate = _require_col(headers, "Close Rate")
    i_isin = _require_col(headers, "ISIN")
    i_type = _col_index(headers, "Type")

    results = []
    for row in data_rows:
        if not row or not row[i_open_date]:
            continue
        if _skip_non_equity(row, i_type):
            continue

        isin = str(row[i_isin]).strip() if row[i_isin] else ""
        action_str = str(row[i_action]).strip() if row[i_action] else ""
        name = action_str.replace("Buy ", "").replace("Sell ", "").split("/")[0].strip()

        units = _to_decimal(row[i_units])
        open_date = _to_date(row[i_open_date])
        close_date = _to_date(row[i_close_date])
        open_rate = _to_decimal(row[i_open_rate])
        close_rate = _to_decimal(row[i_close_rate])
        profit_usd = _to_decimal(row[i_profit_usd])
        profit_eur = _to_decimal(row[i_profit_eur])
        proceeds_usd = units * close_rate

        # Derive USD→EUR ratio from the two Profit columns so EUR totals match
        fx = profit_eur / profit_usd if profit_usd != 0 else _D("1")
        proceeds_eur = (proceeds_usd * fx).quantize(_D("0.01"))
        cost_basis_eur = (proceeds_eur - profit_eur).quantize(_D("0.01"))

        holding_days = (close_date - open_date).days
        holding_period = ">1y" if holding_days >= 365 else "<1y"
        casilla = 332 if profit_eur >= 0 else 337

        results.append(ParsedCapitalGain(
            isin=isin,
            name=name,
            country=country_from_isin(isin),
            buy_date=open_date,
            buy_quantity=units,
            buy_price=open_rate,
            buy_fees=_D("0"),
            buy_total_eur=cost_basis_eur,
            sell_date=close_date,
            sell_quantity=units,
            sell_price=close_rate,
            sell_fees=_D("0"),
            sell_total_eur=proceeds_eur,
            realized_pl_eur=profit_eur,
            holding_period=holding_period,
            casilla=casilla,
        ))

    return results


def _parse_open_positions(wb: openpyxl.Workbook) -> list[ParsedTransaction]:
    """Parse Account Activity 'Open Position' rows for buy transactions (still held)."""
    headers, data_rows = _read_sheet(wb, "Account Activity")
    if not data_rows:
        return []

    i_date = _require_col(headers, "Date")
    i_type = _require_col(headers, "Type")
    i_details = _require_col(headers, "Details")
    i_amount = _require_col(headers, "Amount")
    i_units = _require_col(headers, "Units / Contracts")
    i_asset = _col_index(headers, "Asset type")

    # Also collect position IDs of closed positions to avoid duplicates
    closed_pos_ids = _get_closed_position_ids(wb)

    # Get position ID column
    i_pos_id = _col_index(headers, "Position ID")

    results = []
    for row in data_rows:
        if not row or not row[i_type]:
            continue
        if str(row[i_type]).strip() != "Open Position":
            continue
        if _skip_non_equity(row, i_asset):
            continue

        # Skip positions that were later closed (we already have those from Closed Positions)
        if i_pos_id is not None and row[i_pos_id]:
            pos_id = str(row[i_pos_id]).strip()
            if pos_id in closed_pos_ids:
                continue

        details = str(row[i_details]).strip() if row[i_details] else ""
        # Details is like "MSFT/USD"
        name = details.split("/")[0].strip()

        trade_date = _to_date(row[i_date])
        amount = _to_decimal(row[i_amount])
        units = _to_decimal(row[i_units])

        # eToro open positions from Account Activity don't have ISIN
        # We'll need to match by name later. For now use empty ISIN.
        results.append(ParsedTransaction(
            tx_type=TxType.BUY,
            trade_date=trade_date,
            isin="",  # Will be enriched from dividends/closed positions
            name=name,
            country="",
            quantity=units,
            price=amount / units if units else _D("0"),
            currency="USD",
            gross_amount=amount,
            net_amount_eur=amount,
        ))

    return results


def _get_closed_position_ids(wb: openpyxl.Workbook) -> set[str]:
    """Get all Position IDs from Closed Positions sheet."""
    headers, data_rows = _read_sheet(wb, "Closed Positions")
    if not data_rows:
        return set()

    i_pos_id = _col_index(headers, "Position ID")
    if i_pos_id is None:
        return set()

    return {str(row[i_pos_id]).strip() for row in data_rows if row and row[i_pos_id]}


def _build_isin_map(
    dividends: list[ParsedTransaction],
    closed: list[ParsedCapitalGain],
) -> dict[str, str]:
    """Build name → ISIN map from parsed data. Keys include both full names and ticker symbols."""
    name_to_isin: dict[str, str] = {}
    entries: list[tuple[str, str]] = [(d.name, d.isin) for d in dividends]
    entries.extend((c.name, c.isin) for c in closed)
    for name, isin in entries:
        if not isin or not name:
            continue
        name_to_isin[name.upper()] = isin
        if "(" in name and ")" in name:
            ticker = name.split("(")[-1].rstrip(")").strip()
            if ticker:
                name_to_isin[ticker.upper()] = isin
    return name_to_isin


def _enrich_open_positions(
    open_positions: list[ParsedTransaction],
    isin_map: dict[str, str],
) -> list[ParsedTransaction]:
    """Fill in ISIN and country for open position buys using the name→ISIN map."""
    for tx in open_positions:
        if not tx.isin and tx.name:
            key = tx.name.upper()
            isin = isin_map.get(key, _KNOWN_TICKER_ISINS.get(key, ""))
            if isin:
                tx.isin = isin
                tx.country = country_from_isin(isin)
    return open_positions


def parse_etoro_statement(xlsx_path: Path) -> EToroAnnualReport:
    """Parse an eToro annual account statement XLSX."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

    try:
        fiscal_year = _parse_fiscal_year(wb)
        dividends = _parse_dividends(wb)
        closed_positions = _parse_closed_positions(wb)
        open_positions = _parse_open_positions(wb)

        isin_map = _build_isin_map(dividends, closed_positions)
        open_positions = _enrich_open_positions(open_positions, isin_map)

        return EToroAnnualReport(
            fiscal_year=fiscal_year,
            dividends=dividends,
            transactions=open_positions,
            closed_positions=closed_positions,
        )
    finally:
        wb.close()
