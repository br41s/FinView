"""Chart and analytics API endpoints."""

import logging
import re
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.api.auth import CurrentUser
from backend.api.schemas import (
    CapitalGainsBreakdownOut,
    CompanyDividendsYearlyOut,
    DividendsByCountryOut,
    DividendsMonthlyOut,
    DividendYieldOut,
    FundamentalsOut,
    OhlcBarOut,
    PatrimonioCompositionOut,
    TopDividendPayerOut,
    WithholdingsByCountryOut,
)
from backend.database import DbSession
from backend.models import Account, PortfolioHolding, TaxLot, Transaction, TransactionType
from backend.services import yahoo_budget
from backend.services.portfolio_service import Position, get_open_positions
from backend.services.sql_compat import year_month_str, year_range, year_str

router = APIRouter(prefix="/charts", tags=["charts"])

logger = logging.getLogger(__name__)


@router.get("/dividends-by-country", response_model=list[DividendsByCountryOut])
def dividends_by_country(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
):
    """Dividends aggregated by country for donut chart."""
    q = db.query(
        func.coalesce(Transaction.country, "Desconocido").label("country"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(func.abs(Transaction.withholding_tax)).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).join(Account).filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))

    rows = q.group_by("country").order_by(func.sum(Transaction.gross_amount).desc()).all()

    return [
        {
            "country": r.country,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/dividends-monthly", response_model=list[DividendsMonthlyOut])
def dividends_monthly(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
):
    """Monthly dividend income for bar chart."""
    q = db.query(
        year_month_str(Transaction.trade_date).label("month"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(func.abs(Transaction.withholding_tax)).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).join(Account).filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))

    rows = q.group_by("month").order_by("month").all()

    return [
        {
            "month": r.month,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/top-dividend-payers", response_model=list[TopDividendPayerOut])
def top_dividend_payers(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
    limit: Annotated[int, Query(le=50)] = 10,
):
    """Top N dividend-paying companies."""
    q = db.query(
        Transaction.isin,
        func.min(Transaction.name).label("name"),
        func.max(Transaction.country).label("country"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(func.abs(Transaction.withholding_tax)).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).join(Account).filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))

    rows = (
        q.group_by(Transaction.isin)
        .order_by(func.sum(Transaction.gross_amount).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "isin": r.isin,
            "name": r.name,
            "country": r.country,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/capital-gains-breakdown", response_model=list[CapitalGainsBreakdownOut])
def capital_gains_breakdown(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
):
    """Capital gains/losses per ISIN for bar chart."""
    q = db.query(
        TaxLot.isin,
        func.sum(
            case((TaxLot.realized_pl_eur > 0, TaxLot.realized_pl_eur), else_=Decimal("0"))
        ).label("gains"),
        func.sum(
            case((TaxLot.realized_pl_eur < 0, TaxLot.realized_pl_eur), else_=Decimal("0"))
        ).label("losses"),
        func.sum(TaxLot.realized_pl_eur).label("net"),
        func.count().label("trades"),
    ).join(Transaction, TaxLot.buy_tx_id == Transaction.id).join(Account).filter(
        Account.user_id == user.id, TaxLot.sell_tx_id.isnot(None)
    )

    if fiscal_year:
        q = q.filter(year_range(TaxLot.close_date, fiscal_year))

    rows = q.group_by(TaxLot.isin).order_by(func.sum(TaxLot.realized_pl_eur)).all()

    # Build ISIN → name map from transactions
    isins = [r.isin for r in rows]
    name_rows = (
        db.query(Transaction.isin, Transaction.name)
        .filter(Transaction.isin.in_(isins))
        .distinct()
        .all()
    )
    name_map = {r.isin: r.name for r in name_rows}

    return [
        {
            "isin": r.isin,
            "name": name_map.get(r.isin, r.isin),
            "gains": str(r.gains or 0),
            "losses": str(r.losses or 0),
            "net": str(r.net or 0),
            "trades": r.trades,
        }
        for r in rows
    ]


@router.get("/patrimonio-composition", response_model=list[PatrimonioCompositionOut])
def patrimonio_composition(db: DbSession, user: CurrentUser, fiscal_year: int | None = None):
    """Portfolio composition from Modelo 714 casillas."""
    from backend.models import TaxResult

    q = db.query(TaxResult).filter(TaxResult.user_id == user.id, TaxResult.modelo == 714)
    if fiscal_year:
        q = q.filter(TaxResult.fiscal_year == fiscal_year)
    rows = q.order_by(TaxResult.fiscal_year.desc(), TaxResult.casilla).all()

    return [
        {
            "casilla": r.casilla,
            "description": r.description,
            "amount": str(r.amount_eur),
            "fiscal_year": r.fiscal_year,
        }
        for r in rows
    ]


def _compute_isin_yield(
    d, positions: dict[str, Position],
    price_map: dict,
    holdings_map: dict,
) -> dict:
    """Compute yield metrics for a single ISIN.

    Quantity and cost basis are the portfolio page's: the open-lot queue of
    ``portfolio_service`` (FIFO per account, reconciled against snapshots,
    unknown basis propagated). A second FIFO here used to disagree with it
    after splits, ISIN changes, spinoffs and cross-account sales.

    A closed position has cost ``0`` and yield ``"0"``. An open one whose basis
    is unknown has ``None`` for both, never a partial number.
    """
    isin = d.isin or ""
    total_div = Decimal(str(d.total_dividends or 0))

    pos = positions.get(isin)
    qty_remaining = pos.quantity if pos else Decimal("0")
    cost_basis = pos.total_cost_eur if pos else Decimal("0")

    latest_price = price_map.get(isin, Decimal("0"))
    # Snapshot-only holdings may have no trade or cached price: value them at
    # the snapshot's own EUR price. Only for a position that is still open, so
    # an old snapshot never resurrects shares the ledger has closed.
    holding = holdings_map.get(isin)
    if qty_remaining > 0 and latest_price == 0 and holding and holding.quantity:
        latest_price = abs(holding.value_eur / holding.quantity)
    current_value = abs(qty_remaining * latest_price)

    if cost_basis is None:
        yield_on_cost = None
    else:
        yield_on_cost = (total_div / cost_basis * 100) if cost_basis > 0 else Decimal("0")
    yield_on_value = (total_div / current_value * 100) if current_value > 0 else Decimal("0")

    return {
        "isin": isin,
        "name": d.name,
        "country": d.country,
        "ticker": d.ticker,
        "total_dividends": str(total_div),
        "total_invested": None if cost_basis is None else str(round(cost_basis, 2)),
        "qty_remaining": str(qty_remaining),
        "latest_price": str(latest_price),
        "current_value": str(round(current_value, 2)),
        "yield_on_cost": None if yield_on_cost is None else str(round(yield_on_cost, 2)),
        "yield_on_value": str(round(yield_on_value, 2)),
        "payment_count": d.payment_count,
        "currency": "EUR",
        "original_price": None,
        "fx_rate": None,
    }


def _first_per_key(rows, key_attr: str, val_attr: str) -> dict:
    """Build a dict mapping key → value, keeping only the first occurrence."""
    result: dict = {}
    for r in rows:
        k = getattr(r, key_attr)
        if k not in result:
            result[k] = Decimal(str(getattr(r, val_attr)))
    return result


def _merge_same_ticker_rows(rows: list[dict], db: Session) -> list[dict]:
    """Merge rows that share the same Yahoo Finance ticker.

    After a stock split with an ISIN change, old and new ISINs appear as
    separate rows. If both map to the same ticker, collapse them into one row
    by summing additive fields and recalculating derived ratios. An unknown
    cost on any row makes the merged cost unknown: a known subtotal must not
    be published as the cost of the whole position.
    """
    try:
        from backend.services import ticker_map

        known = ticker_map.effective_map(db)
    except Exception:
        return rows

    # Accumulators per canonical ticker key
    # div, cost (None = unknown), qty, value
    totals: dict[str, tuple[Decimal, Decimal | None, Decimal, Decimal]] = {}
    canonical: dict[str, dict] = {}  # representative row per key

    for row in rows:
        isin = row["isin"]
        key = known.get(isin, isin)
        div = Decimal(row["total_dividends"])
        cost = None if row["total_invested"] is None else Decimal(row["total_invested"])
        qty = Decimal(row["qty_remaining"])
        value = Decimal(row["current_value"])
        price = Decimal(row["latest_price"])

        if key not in canonical:
            canonical[key] = dict(row)
            canonical[key]["_price"] = price
            totals[key] = (div, cost, qty, value)
        else:
            prev_div, prev_cost, prev_qty, prev_value = totals[key]
            merged_cost = None if prev_cost is None or cost is None else prev_cost + cost
            totals[key] = (prev_div + div, merged_cost, prev_qty + qty, prev_value + value)
            canonical[key]["payment_count"] += row["payment_count"]
            # Prefer the newer (post-split) ISIN — it carries the live price
            if price > canonical[key]["_price"]:
                canonical[key].update(
                    isin=isin,
                    ticker=row["ticker"],
                    latest_price=row["latest_price"],
                    currency=row["currency"],
                    original_price=row["original_price"],
                    fx_rate=row["fx_rate"],
                    _price=price,
                )

    out = []
    for key, row in canonical.items():
        total_div, cost, qty, value = totals[key]
        row.pop("_price")
        row["total_dividends"] = str(total_div)
        row["total_invested"] = None if cost is None else str(round(cost, 2))
        row["qty_remaining"] = str(qty)
        row["current_value"] = str(round(value, 2))
        row["yield_on_cost"] = (
            None
            if cost is None
            else str(round(total_div / cost * 100 if cost > 0 else Decimal("0"), 2))
        )
        row["yield_on_value"] = str(round(total_div / value * 100 if value > 0 else Decimal("0"), 2))
        out.append(row)
    return out


@router.get("/dividend-yield", response_model=list[DividendYieldOut])
def dividend_yield(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
):
    """Dividend yield per ISIN: dividends vs the cost of what is still held.

    For each ISIN that paid dividends:
    - total_invested: cost basis of the open position, as the portfolio page
      computes it; None when that basis is unknown
    - qty_remaining: open quantity, as the portfolio page computes it
    - current_value: qty_remaining * latest price
    - yield_on_cost: dividends / total_invested * 100; None when unknown
    - yield_on_value: dividends / current_holding_value * 100
    """
    # Get dividend totals by ISIN (group only by ISIN to merge broker name variants)
    div_q = db.query(
        Transaction.isin,
        func.max(Transaction.name).label("name"),
        func.max(Transaction.country).label("country"),
        func.max(Transaction.ticker).label("ticker"),
        func.sum(Transaction.gross_amount).label("total_dividends"),
        func.count().label("payment_count"),
    ).join(Account).filter(Account.user_id == user.id, Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        div_q = div_q.filter(year_range(Transaction.trade_date, fiscal_year))

    div_rows = div_q.group_by(Transaction.isin).all()

    # Collect ISINs with dividends
    div_isins = [d.isin for d in div_rows if d.isin]

    if not div_isins:
        return []

    # Open quantity and cost basis come from the portfolio page's lot queue.
    # skip_prices: no live yfinance fetch in this request path (see below).
    positions = {
        p.isin: p
        for p in get_open_positions(db, user.id, skip_prices=True, isins=div_isins)
    }

    # Latest price per ISIN (exclude synthetic transactions)
    all_synthetic_ids = db.query(TaxLot.buy_tx_id).union(
        db.query(TaxLot.sell_tx_id).filter(TaxLot.sell_tx_id.isnot(None))
    ).scalar_subquery()
    latest_prices_q = (
        db.query(Transaction.isin, func.abs(Transaction.price).label("price"))
        .join(Account)
        .filter(Account.user_id == user.id)
        .filter(Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]))
        .filter(Transaction.isin.in_(div_isins))
        .filter(Transaction.id.notin_(all_synthetic_ids))
        .order_by(Transaction.isin, Transaction.trade_date.desc())
        .all()
    )
    price_map = _first_per_key(latest_prices_q, "isin", "price")

    # Overlay with cached Yahoo Finance prices when available. Read-only: the
    # synchronous yfinance fetch must not run in the request path (it blocked
    # the dashboard for seconds). The price cache is populated out-of-band by
    # POST /portfolio/warm-prices and the options agent; ISINs still held are
    # exactly the open positions that warming covers, and fully-sold ISINs have
    # current_value 0 regardless of price. Uncached ISINs fall back to the
    # historical transaction price already in price_map.
    try:
        from backend.services.prices import get_cached_prices, get_currency_info

        cached_prices = get_cached_prices(db, div_isins)
        price_map.update(cached_prices)
        currency_info = get_currency_info(db, div_isins)
    except Exception:
        logger.debug("Cached prices unavailable, using historical prices")
        currency_info = {}

    # Fetch portfolio holdings to supplement ISINs without buy/sell history
    holdings_q = db.query(PortfolioHolding).join(Account).filter(
        Account.user_id == user.id,
        PortfolioHolding.isin.in_(div_isins),
    )
    if fiscal_year:
        holdings_q = holdings_q.filter(PortfolioHolding.fiscal_year == fiscal_year)
    holdings_map: dict[str, PortfolioHolding] = {}
    for h in holdings_q.order_by(PortfolioHolding.fiscal_year.desc()).all():
        holdings_map.setdefault(h.isin, h)

    results = []
    for d in div_rows:
        row = _compute_isin_yield(d, positions, price_map, holdings_map)
        isin = d.isin or ""
        ci = currency_info.get(isin, {})
        row["currency"] = ci.get("currency", "EUR")
        row["original_price"] = ci.get("original_price")
        row["fx_rate"] = ci.get("fx_rate")
        results.append(row)

    results = _merge_same_ticker_rows(results, db)
    # Unknown yield-on-cost sorts last, not as if it were zero.
    results.sort(
        key=lambda x: float(x["yield_on_cost"]) if x["yield_on_cost"] is not None else float("-inf"),
        reverse=True,
    )
    return results


@router.get("/withholdings-by-country", response_model=list[WithholdingsByCountryOut])
def withholdings_by_country(
    db: DbSession,
    user: CurrentUser,
    fiscal_year: int | None = None,
):
    """Withholding tax breakdown by country for double taxation analysis."""
    q = db.query(
        func.coalesce(Transaction.country, "Desconocido").label("country"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(func.abs(Transaction.withholding_tax)).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
    ).join(Account).filter(
        Account.user_id == user.id,
        Transaction.type == TransactionType.DIVIDEND.value,
        Transaction.withholding_tax != 0,
    )

    if fiscal_year:
        q = q.filter(year_range(Transaction.trade_date, fiscal_year))

    rows = q.group_by("country").order_by(
        func.sum(func.abs(Transaction.withholding_tax)).desc()
    ).all()

    out = []
    for r in rows:
        # SUM(ABS(x)) and SUM(x) do not come back as the same Python type on
        # every backend: SQLite hands back a float for the ABS aggregate and a
        # Decimal for the plain one, so dividing them raised TypeError and 500'd
        # this endpoint on local dev. Normalise both before any arithmetic.
        gross = Decimal(str(r.gross)) if r.gross else Decimal("0")
        withholding = abs(Decimal(str(r.withholding))) if r.withholding else Decimal("0")
        net = Decimal(str(r.net)) if r.net else Decimal("0")
        effective_rate = (
            round(withholding / gross * 100, 2) if gross > 0 else Decimal("0")
        )
        out.append(
            {
                "country": r.country,
                "gross": str(gross),
                "withholding": str(withholding),
                "net": str(net),
                "effective_rate": str(effective_rate),
            }
        )
    return out


_IBKR_TICKER_RE = re.compile(r"^([A-Z0-9]{1,6})\(")


def _derive_ticker(names: list[str]) -> str:
    """Find a short display label from company name variants."""
    for name in names:
        m = _IBKR_TICKER_RE.match(name)
        if m:
            return m.group(1)
    shortest = min(names, key=len) if names else "?"
    first_word = shortest.split()[0].rstrip(",.:;") if shortest.split() else shortest
    if len(first_word) <= 10:
        return first_word
    return first_word[:8] + "…"


def _best_display_name(names: list[str]) -> str:
    """Pick the most readable company name from variants."""
    clean = [n for n in names if "Cash Dividend" not in n and "Payment in Lieu" not in n]
    if clean:
        return min(clean, key=len)
    return min(names, key=len) if names else ""


@router.get("/dividends-by-company-yearly", response_model=list[CompanyDividendsYearlyOut])
def dividends_by_company_yearly(db: DbSession, user: CurrentUser):
    """Dividends per company per year for multi-year timeline chart."""
    rows = (
        db.query(
            Transaction.isin,
            year_str(Transaction.trade_date).label("year"),
            func.sum(Transaction.gross_amount).label("gross"),
        )
        .join(Account)
        .filter(
            Account.user_id == user.id,
            Transaction.type == TransactionType.DIVIDEND.value,
            Transaction.isin.isnot(None),
        )
        .group_by(Transaction.isin, year_str(Transaction.trade_date))
        .all()
    )

    name_rows = (
        db.query(Transaction.isin, Transaction.name)
        .join(Account)
        .filter(
            Account.user_id == user.id,
            Transaction.type == TransactionType.DIVIDEND.value,
            Transaction.isin.isnot(None),
        )
        .distinct()
        .all()
    )
    names_by_isin: dict[str, list[str]] = {}
    for r in name_rows:
        names_by_isin.setdefault(r.isin, []).append(r.name)

    by_isin: dict[str, dict] = {}
    for r in rows:
        if r.isin not in by_isin:
            by_isin[r.isin] = {"years": {}, "total": Decimal("0")}
        by_isin[r.isin]["years"][r.year] = str(r.gross or 0)
        by_isin[r.isin]["total"] += r.gross or Decimal("0")

    result = []
    for isin, data in by_isin.items():
        names = names_by_isin.get(isin, [])
        result.append({
            "isin": isin,
            "name": _best_display_name(names),
            "ticker": _derive_ticker(names),
            "years": data["years"],
            "total": str(data["total"]),
        })

    result.sort(key=lambda x: float(x["total"]), reverse=True)
    return result


# OHLC history cache: key "TICKER:period:interval" → (rows, fetched_at). Daily
# bars only change once per session close, so a short TTL kills repeat yfinance
# downloads (every drawer/chart open re-fetched up to 10y of bars) without
# staleness risk. Intraday bars go stale faster but 15min is an acceptable
# trade-off against re-hitting yfinance on every scope click.
_PRICE_HISTORY_CACHE: dict[str, tuple[list, float]] = {}
_PRICE_HISTORY_TTL = 900.0  # seconds

# yfinance caps how far back each interval can be requested. Only pairs the
# frontend actually asks for (chartMarkers.ts SCOPE_PARAMS) are allowed —
# anything else silently falls back to a safe daily default rather than
# risking an oversized or empty intraday request.
_VALID_PERIODS_BY_INTERVAL: dict[str, set[str]] = {
    "1d": {"1d", "5d", "1mo", "6mo", "1y", "2y", "5y", "10y", "max"},
    "1h": {"1mo", "3mo", "6mo"},
    "15m": {"5d", "1mo"},
    "5m": {"1d", "5d"},
}


@router.get("/price-history", response_model=list[OhlcBarOut])
def price_history(
    ticker: str,
    user: CurrentUser,
    period: str = Query("2y"),
    interval: str = Query("1d"),
):
    """OHLC history for a ticker (yfinance), for position price charts.

    Read-only and best-effort: any failure or unknown ticker returns []
    so the frontend simply hides the chart. period/interval are whitelisted
    together since yfinance caps how far back intraday intervals can go.
    Intraday rows also carry a "time" (epoch seconds) field for the chart's
    x-axis; daily rows rely on "date" alone (lightweight-charts business-day
    format, which handles weekend gaps natively).
    """
    import time

    import pandas as pd

    if interval not in _VALID_PERIODS_BY_INTERVAL:
        interval = "1d"
    if period not in _VALID_PERIODS_BY_INTERVAL[interval]:
        period = "2y" if interval == "1d" else min(_VALID_PERIODS_BY_INTERVAL[interval])
    t = ticker.strip().upper()
    if not t:
        return []
    cache_key = f"{t}:{period}:{interval}"
    cached = _PRICE_HISTORY_CACHE.get(cache_key)
    if cached and time.time() - cached[1] < _PRICE_HISTORY_TTL:
        return cached[0]
    try:
        df = yahoo_budget.download(t, period=period, interval=interval, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return []
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        rows = [
            {
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx)[:10],
                **({"time": int(idx.timestamp())} if interval != "1d" else {}),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            }
            for idx, row in df.iterrows()
        ]
        # Only cache successful non-empty fetches — an empty [] is usually a
        # transient Yahoo failure, and caching it would hide the chart for 15 min.
        _PRICE_HISTORY_CACHE[cache_key] = (rows, time.time())
        return rows
    except Exception:
        logger.exception("price_history failed for %s (period=%s interval=%s)", t, period, interval)
        return []


# ── Fundamentals ─────────────────────────────────────────────────────

# Fundamentals move on earnings, not intraday, so a long TTL costs nothing and
# keeps a signal panel with several tickers from hammering yfinance.
_FUNDAMENTALS_CACHE: dict[str, tuple[dict, float]] = {}
_FUNDAMENTALS_TTL = 6 * 3600.0  # seconds

# yfinance `.info` keys → our field names. Deliberately a small set: these are
# context for a thesis, not a screener. Anything missing simply isn't rendered.
_FUNDAMENTAL_FIELDS: list[tuple[str, str]] = [
    ("sector", "sector"),
    ("industry", "industry"),
    ("marketCap", "market_cap"),
    ("trailingPE", "trailing_pe"),
    ("forwardPE", "forward_pe"),
    ("priceToBook", "price_to_book"),
    ("dividendYield", "dividend_yield"),
    ("profitMargins", "profit_margins"),
    ("debtToEquity", "debt_to_equity"),
    ("returnOnEquity", "return_on_equity"),
    ("revenueGrowth", "revenue_growth"),
    ("beta", "beta"),
    ("currency", "currency"),
    ("longName", "name"),
]


@router.get("/fundamentals", response_model=FundamentalsOut)
def fundamentals(ticker: str, user: CurrentUser):
    """Fundamental snapshot for a ticker (yfinance `.info`), for the Ideas desk.

    Read-only and best-effort: any failure, unknown ticker, or field yfinance
    doesn't carry returns `{}` / omits the key, and the caller hides the section.

    `.info` has no stable contract — it's scraped, its keys come and go, and it
    can return a mostly-empty dict for perfectly valid tickers (non-US listings
    especially). Every field is therefore optional and nothing here is load-
    bearing: this is colour for a thesis a human is reading, never an input to a
    signal, a score, or a gate.
    """
    import time

    import yfinance as yf

    t = ticker.strip().upper()
    if not t:
        return {}

    cached = _FUNDAMENTALS_CACHE.get(t)
    if cached and time.time() - cached[1] < _FUNDAMENTALS_TTL:
        return cached[0]

    try:
        info = yf.Ticker(t).info or {}
        if not isinstance(info, dict):
            return {}
        out: dict = {}
        for src, dest in _FUNDAMENTAL_FIELDS:
            value = info.get(src)
            if value is None or value == "":
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[dest] = float(value)
            elif isinstance(value, str):
                out[dest] = value
        # An info dict with nothing usable in it is a miss, not a result — don't
        # cache it as if the ticker had no fundamentals.
        if not out:
            return {}
        _FUNDAMENTALS_CACHE[t] = (out, time.time())
        return out
    except Exception:
        logger.exception("fundamentals failed for %s", t)
        return {}
