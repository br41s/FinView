"""Daily stock price fetching and caching via Yahoo Finance."""

import logging
from datetime import datetime, time, date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import PriceCache
from backend.services import exchange_rates, ticker_map, yahoo_budget
from backend.services.yahoo_budget import GEO_CYCLE_SECONDS, PORTFOLIO_SECONDS, Budget

logger = logging.getLogger(__name__)

# Exchange suffix → trading currency


def _resolve_ticker(isin: str, db: Session) -> str | None:
    """Resolve ISIN to Yahoo Finance ticker: curated map, learned map, then cache.

    The PriceCache fallback only ever held tickers that came from one of the
    first two, so on its own it could never widen coverage — an ISIN nothing
    resolved was never fetched, so it never got a cache row to be found in.
    It stays as a fallback for installations whose cache predates `ticker_map`.
    """
    resolved = ticker_map.resolve(db, isin)
    if resolved:
        return resolved

    cached = (
        db.query(PriceCache.yahoo_ticker)
        .filter(PriceCache.isin == isin, PriceCache.yahoo_ticker.isnot(None))
        .first()
    )
    return cached[0] if cached else None


def get_cached_prices(db: Session, isins: list[str]) -> dict[str, Decimal]:
    """Get today's cached prices. Returns dict[isin, price]."""
    today = date.today()
    rows = (
        db.query(PriceCache.isin, PriceCache.price)
        .filter(PriceCache.isin.in_(isins), PriceCache.fetched_date == today)
        .all()
    )
    return {r.isin: r.price for r in rows}


def fetch_and_cache_prices(
    db: Session, isins: list[str],
) -> dict[str, Decimal]:
    """Fetch current prices for ISINs, cache them, return dict[isin, price].

    Only fetches ISINs not already cached for today.
    """
    today = date.today()
    cached = get_cached_prices(db, isins)
    missing = [isin for isin in isins if isin not in cached]

    if not missing:
        return cached

    # Resolve tickers for missing ISINs
    ticker_to_isins: dict[str, list[str]] = {}
    for isin in missing:
        ticker = _resolve_ticker(isin, db)
        if ticker:
            ticker_to_isins.setdefault(ticker, []).append(isin)
        else:
            logger.warning("No Yahoo ticker for ISIN %s", isin)

    if not ticker_to_isins:
        return cached

    # Batch fetch via yfinance, bounded: a user is waiting, and a stalled batch is
    # superlinear in the number of symbols (see yahoo_budget). Whatever the budget
    # stops fetching stays absent, which portfolio totals already treat as "unknown
    # price" and fail closed on — never as a price of zero.
    prices = _fetch_yahoo_prices(
        list(ticker_to_isins.keys()),
        budget=Budget(PORTFOLIO_SECONDS, "portfolio valuation"),
    )

    # Determine which currencies need conversion
    non_eur_currencies: set[str] = set()
    ticker_currencies: dict[str, str] = {}
    for ticker in ticker_to_isins:
        ccy = ticker_map.currency_for_ticker(ticker)
        ticker_currencies[ticker] = ccy
        if ccy != "EUR":
            non_eur_currencies.add(ccy)

    # Fetch forex rates for non-EUR currencies via the ECB service (DB-cached,
    # ±7d fallback) rather than yfinance — a single failed/rate-limited yfinance
    # forex call used to silently drop every non-EUR position from valuation.
    fx_rates: dict[str, Decimal] = {}
    for ccy in non_eur_currencies:
        rate = exchange_rates.get_rate(ccy, today)
        if rate is not None:
            fx_rates[ccy] = rate
        else:
            logger.warning("No ECB rate for %s", ccy)

    for ticker, price_val in prices.items():
        ticker_isins = ticker_to_isins.get(ticker)
        if not ticker_isins:
            continue

        # London Stock Exchange quotes in GBX (pence) — convert to GBP
        if ticker.endswith(".L"):
            price_val = price_val / 100.0

        # Track original currency and price
        ccy = ticker_currencies.get(ticker, "EUR")
        orig_price = Decimal(str(round(price_val, 6)))
        rate = fx_rates.get(ccy)

        # Convert to EUR if needed
        if ccy != "EUR" and rate is not None:
            price_eur = price_val / float(rate)
        elif ccy != "EUR":
            logger.warning("No FX rate for %s, skipping %s", ccy, ticker)
            continue
        else:
            price_eur = price_val

        price_dec = Decimal(str(round(price_eur, 6)))

        # One Yahoo ticker can represent multiple ISINs across a corporate
        # action (for example AENA pre/post split). Cache every requested ISIN.
        for isin in ticker_isins:
            existing = (
                db.query(PriceCache)
                .filter(PriceCache.isin == isin, PriceCache.fetched_date == today)
                .first()
            )
            if existing:
                existing.price = price_dec
                existing.yahoo_ticker = ticker
                existing.original_currency = ccy
                existing.original_price = orig_price
                existing.fx_rate = rate
            else:
                db.add(PriceCache(
                    isin=isin,
                    yahoo_ticker=ticker,
                    price=price_dec,
                    currency="EUR",
                    original_currency=ccy,
                    original_price=orig_price,
                    fx_rate=rate,
                    fetched_date=today,
                ))
            cached[isin] = price_dec

    db.commit()
    return cached


# Geo scores moves over hours, so it prices on intraday bars; a daily close cannot
# resolve a +1h checkpoint (it compares that close against itself). 5-minute bars over
# the last 5 sessions cover weekends and holidays — the last bar is simply the most
# recent trade, which outside market hours is the close.
_INTRADAY_PERIOD = "5d"
_INTRADAY_INTERVAL = "5m"


def _last_closes(data, tickers: list[str]) -> dict[str, float]:
    """Last non-NaN close per ticker from a yfinance download frame.

    Shared by the daily and intraday fetches: the column shape is the fiddly part
    (a single ticker comes back as a Series, several as a MultiIndex DataFrame) and
    getting it wrong silently drops every price.
    """
    import pandas as pd

    result: dict[str, float] = {}
    if data is None or getattr(data, "empty", True):
        return result
    try:
        close_data = data["Close"]
    except (KeyError, TypeError, IndexError):
        return result

    if isinstance(close_data, pd.Series):
        vals = close_data.dropna()
        if not vals.empty and tickers:
            result[tickers[0]] = float(vals.iloc[-1])
        return result

    if isinstance(close_data, pd.DataFrame):
        if close_data.columns.nlevels > 1:
            close_data = close_data.droplevel(0, axis=1)
        for ticker in tickers:
            if ticker in close_data.columns:
                series = close_data[ticker].dropna()
                if not series.empty:
                    result[ticker] = float(series.iloc[-1])
            elif len(tickers) == 1 and len(close_data.columns) == 1:
                series = close_data.iloc[:, 0].dropna()
                if not series.empty:
                    result[tickers[0]] = float(series.iloc[-1])
    return result


# Daily bars come back as tz-naive *dates*. Stamping them at midnight puts day
# D's close 20 hours before it happened, so an as-of lookup at 15:00 on D read
# the future; 21:00 UTC is after the US close in both EDT and EST.
_DAILY_CLOSE_UTC = time(21, 0)


def _close_series(
    data, tickers: list[str], *, daily: bool = False
) -> dict[str, list[tuple[datetime, float]]]:
    """Full (timestamp, close) series per ticker from a yfinance download frame,
    timestamps normalised to aware UTC (daily bars at the session close). Same
    column-shape handling as ``_last_closes``; NaN bars are dropped."""
    import pandas as pd

    result: dict[str, list[tuple[datetime, float]]] = {}
    if data is None or getattr(data, "empty", True):
        return result
    try:
        close_data = data["Close"]
    except (KeyError, TypeError, IndexError):
        return result

    def _rows(series) -> list[tuple[datetime, float]]:
        series = series.dropna()
        out: list[tuple[datetime, float]] = []
        for ts, val in series.items():
            ts = pd.Timestamp(ts)
            if daily and ts.tzinfo is None:
                ts = pd.Timestamp(datetime.combine(ts.date(), _DAILY_CLOSE_UTC))
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            out.append((ts.to_pydatetime(), float(val)))
        return out

    if isinstance(close_data, pd.Series):
        if tickers:
            result[tickers[0]] = _rows(close_data)
        return result
    if isinstance(close_data, pd.DataFrame):
        if close_data.columns.nlevels > 1:
            close_data = close_data.droplevel(0, axis=1)
        for ticker in tickers:
            if ticker in close_data.columns:
                result[ticker] = _rows(close_data[ticker])
            elif len(tickers) == 1 and len(close_data.columns) == 1:
                result[ticker] = _rows(close_data.iloc[:, 0])
    return {k: v for k, v in result.items() if v}


# Symbols per round trip when a budget is watching. A stalled batch costs far more
# than one stalled request: measured against a socket that accepts and never answers,
# 1 symbol is 60s, 2 is 90s, and 6 is 300s — superlinear, so the 63 symbols the geo
# rules carry would be well over half an hour inside a single uninterruptible call.
# Three keeps one stalled chunk near the 120s cycle budget, so the worst case is the
# budget plus one chunk instead of the whole batch.
_STALL_CHUNK = 3


def _fetch_yahoo_prices(
    tickers: list[str],
    *,
    period: str = "5d",
    interval: str = "1d",
    budget: Budget | None = None,
) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance. Returns dict[ticker, price].

    Defaults to daily closes — that is what the portfolio cache stores, one row per
    ISIN per day, paired with an ECB rate for the same day. Do not switch that path
    to intraday.

    Without a *budget* this is one batched call, which is what the portfolio path
    wants: nobody can interrupt it, but a user is waiting and the happy path is a
    single round trip. With one, the work is split so the budget has somewhere to
    look — chunking without a budget would only add round trips and bound nothing.
    """

    groups = (
        [tickers[i : i + _STALL_CHUNK] for i in range(0, len(tickers), _STALL_CHUNK)]
        if budget is not None
        else [tickers]
    )

    out: dict[str, float] = {}
    for group in groups:
        if budget is not None and budget.spent():
            logger.warning(
                "Yahoo prices: budget spent, %d of %d symbols not fetched (%s/%s)",
                len(tickers) - len(out),
                len(tickers),
                period,
                interval,
            )
            break
        try:
            data = yahoo_budget.download(
                group,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            out.update(_last_closes(data, group))
        except Exception:
            # One bad chunk must not drop the symbols that did resolve. Missing
            # symbols are already treated as unresolvable, never as zero.
            logger.exception("Error fetching Yahoo Finance prices (%s/%s)", period, interval)
    return out


def fetch_price_series(
    tickers: list[str],
    *,
    period: str,
    interval: str,
    budget: Budget | None = None,
) -> dict[str, list[tuple[datetime, float]]]:
    """Close series per symbol — the auditor's as-of prices and noise estimate.

    A checkpoint is scored against the bar *at its target time*, not the last
    bar at evaluation time: the cron runs every 30 minutes, so "now" is a random
    60–90 minute window for a +1h horizon, and several horizons due in one cycle
    used to receive the identical price. Same chunking/budget rules as
    ``_fetch_yahoo_prices``; symbols without bars are absent, never empty.
    """
    unique = list(dict.fromkeys(tickers))
    groups = (
        [unique[i : i + _STALL_CHUNK] for i in range(0, len(unique), _STALL_CHUNK)]
        if budget is not None
        else [unique]
    )
    out: dict[str, list[tuple[datetime, float]]] = {}
    for group in groups:
        if budget is not None and budget.spent():
            logger.warning(
                "Yahoo series: budget spent, %d of %d symbols not fetched (%s/%s)",
                len(unique) - len(out), len(unique), period, interval,
            )
            break
        try:
            data = yahoo_budget.download(
                group, period=period, interval=interval, auto_adjust=True,
                progress=False, threads=True,
            )
            out.update(_close_series(data, group, daily=interval.endswith("d")))
        except Exception:
            logger.exception("Error fetching Yahoo Finance series (%s/%s)", period, interval)
    return out


def fetch_ticker_prices(
    tickers: list[str], budget: Budget | None = None
) -> dict[str, float]:
    """Latest traded price per symbol — geo-intel entry prices and outcome scoring.

    Intraday first. Both ends of a geo measurement come from here: the price stamped
    on a signal when it is created, and the price the auditor compares it against at
    +1h/+6h/+1d/+3d/+7d. On daily closes the two intraday horizons compared a close
    against itself and scored every basket 0.

    Falls back to the daily close per symbol, not per batch: a thin listing with no
    5-minute bars still gets a price instead of dropping out of the basket entirely.
    Symbols absent from the result are unresolvable (some futures / foreign listings)
    and should be flagged, not treated as zero.
    """
    if not tickers:
        return {}
    unique = list(dict.fromkeys(tickers))
    # One cycle, one allowance. The caller passes its own so that the two fetches a
    # cycle makes — enrichment and the auditor's scoring — share 120s rather than
    # taking 120s each.
    if budget is None:
        budget = Budget(GEO_CYCLE_SECONDS, "geo price enrichment")

    prices = _fetch_yahoo_prices(
        unique, period=_INTRADAY_PERIOD, interval=_INTRADAY_INTERVAL, budget=budget
    )
    missing = [t for t in unique if t not in prices]
    if missing:
        # The fallback is a second full round-trip to Yahoo. When the intraday
        # leg already burned the cycle's allowance — a stalled Yahoo costs ~30s
        # per symbol and no call-site timeout changes that (see yahoo_budget) —
        # skip it. Symbols stay absent, which the caller already treats as
        # unresolvable rather than as a price of zero.
        if budget.spent():
            logger.warning(
                "geo prices: skipping the daily-close fallback for %d symbols", len(missing)
            )
            return prices
        logger.info("geo prices: %d/%d symbols fell back to the daily close",
                    len(missing), len(unique))
        prices.update(_fetch_yahoo_prices(missing, budget=budget))
    return prices


def get_currency_info(db: Session, isins: list[str]) -> dict[str, dict]:
    """Get currency info for ISINs from today's cache.

    Returns dict[isin, {currency, original_price, fx_rate}].
    Falls back to the ticker map when cache has no original_currency.
    """
    today = date.today()
    rows = (
        db.query(
            PriceCache.isin,
            PriceCache.original_currency,
            PriceCache.original_price,
            PriceCache.fx_rate,
            PriceCache.yahoo_ticker,
        )
        .filter(PriceCache.isin.in_(isins), PriceCache.fetched_date == today)
        .all()
    )
    result: dict[str, dict] = {}
    for r in rows:
        ccy = r.original_currency
        if not ccy and r.yahoo_ticker:
            ccy = ticker_map.currency_for_ticker(r.yahoo_ticker)
        result[r.isin] = {
            "currency": ccy or "EUR",
            "original_price": str(r.original_price) if r.original_price else None,
            "fx_rate": str(r.fx_rate) if r.fx_rate else None,
        }

    # For ISINs not in today's cache, derive from ticker map
    known = ticker_map.effective_map(db) if len(result) < len(isins) else {}
    for isin in isins:
        if isin not in result:
            ticker = known.get(isin)
            ccy = ticker_map.currency_for_ticker(ticker) if ticker else "EUR"
            result[isin] = {"currency": ccy, "original_price": None, "fx_rate": None}

    return result
