"""Options data scraper — Yahoo Finance + MEFF (Spanish exchange)."""

import logging
import math
import re
from datetime import datetime, timedelta

import numpy as np
import requests
import yfinance as yf
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_EXPIRATIONS = 3  # ~6 weeks of data
MEFF_URL = "https://www.meff.es/esp/Derivados/Ficha/"
MEFF_PROXY = "https://api.allorigins.win/raw?url="
MEFF_DEFAULT_DAYS = 30

_SQRT_2PI = math.sqrt(2 * math.pi)

_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')
_ISIN_CACHE: dict[str, str] = {}  # ISIN → resolved ticker symbol


# ── Math helpers ─────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _safe_int(val, default: int = 0) -> int:
    """Convert to int, handling NaN, Inf, and None."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    """Convert to float, handling NaN, Inf, and None."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


# ── ISIN resolution ──────────────────────────────────────────────────


def _resolve_isin(isin: str) -> str | None:
    """Resolve an ISIN to a ticker symbol via Yahoo Finance search. Result is cached."""
    if isin in _ISIN_CACHE:
        return _ISIN_CACHE[isin]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}&quotesCount=1&newsCount=0"
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", [])
            if quotes:
                symbol = quotes[0].get("symbol")
                if symbol:
                    _ISIN_CACHE[isin] = symbol
                    logger.info("ISIN %s resolved to ticker %s", isin, symbol)
                    return symbol
    except Exception:
        logger.warning("ISIN resolution failed for %s", isin)
    return None


# ── Public API ───────────────────────────────────────────────────────


def fetch_options(ticker: str) -> dict | None:
    """Fetch options chain for a ticker. Returns structured options data or None.

    If *ticker* looks like an ISIN (e.g. ES0178430E18), it is first resolved
    to the proper exchange symbol (e.g. TEF.MC) via Yahoo Finance search.
    """
    if _ISIN_RE.match(ticker):
        resolved = _resolve_isin(ticker)
        if resolved:
            ticker = resolved
    if ticker.endswith(".MC"):
        data = _fetch_meff(ticker)
        if data:
            return data
    return _fetch_yahoo(ticker)


# ── Yahoo Finance ────────────────────────────────────────────────────


def _compute_hv(history) -> float | None:
    """30-day annualised historical volatility from price history."""
    if len(history) < 5:
        return None
    returns = np.log(history["Close"] / history["Close"].shift(1)).dropna()
    hv = float(returns.std() * np.sqrt(252) * 100)
    return hv if not np.isnan(hv) else None


def _get_current_price(info: dict, history) -> float | None:
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None and not history.empty:
        price = float(history["Close"].iloc[-1])
    return float(price) if price else None


def _build_yahoo_chain(ticker_obj, expirations: list[str]) -> tuple[list[dict], list[dict]]:
    """Fetch and flatten calls/puts for all expirations."""
    calls, puts = [], []
    for exp in expirations:
        chain = ticker_obj.option_chain(exp)
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        days_to_exp = max((exp_date - datetime.now()).days, 1)
        for _, row in chain.calls.iterrows():
            calls.append(_yahoo_row_to_dict(row, days_to_exp, exp, "CALL"))
        for _, row in chain.puts.iterrows():
            puts.append(_yahoo_row_to_dict(row, days_to_exp, exp, "PUT"))
    return calls, puts


def _fetch_yahoo(ticker: str) -> dict | None:
    """Fetch options data from Yahoo Finance."""
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        history = yf_ticker.history(period="30d")

        current_price = _get_current_price(info, history)
        if not current_price:
            logger.warning("No price for %s", ticker)
            return None

        hv = _compute_hv(history)
        expirations = yf_ticker.options[:MAX_EXPIRATIONS] if yf_ticker.options else []
        calls, puts = _build_yahoo_chain(yf_ticker, expirations)

        total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
        total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        return {
            "ticker": ticker,
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            "stock_data": {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
            },
            "historical_volatility": hv,
            "expirations_analyzed": expirations,
            "calls": calls,
            "puts": puts,
            "calls_count": len(calls),
            "puts_count": len(puts),
            "put_call_ratio": pcr,
            "status": "success",
            "source": "yahoo",
        }
    except Exception:
        logger.exception("Yahoo fetch failed for %s", ticker)
        return None


def _yahoo_row_to_dict(row, days_to_exp: int, expiration: str, opt_type: str) -> dict:
    return {
        "strike": _safe_float(row.get("strike", 0)),
        "bid": _safe_float(row.get("bid", 0)),
        "ask": _safe_float(row.get("ask", 0)),
        "lastPrice": _safe_float(row.get("lastPrice", 0)),
        "volume": _safe_int(row.get("volume", 0)),
        "openInterest": _safe_int(row.get("openInterest", 0)),
        "impliedVolatility": _safe_float(row.get("impliedVolatility", 0)),
        "daysToExpiry": days_to_exp,
        "expiration": expiration,
        "type": opt_type,
    }


# ── MEFF (Spanish Exchange) ──────────────────────────────────────────


def _get_meff_price(soup, ticker: str) -> float | None:
    """Extract underlying price from MEFF page, falling back to yfinance."""
    price_el = soup.find("span", class_="last-price")
    if price_el:
        try:
            return float(price_el.text.replace(",", "."))
        except ValueError:
            pass
    info = (yf.Ticker(ticker).info or {})
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    return float(price) if price else None


def _parse_meff_tables(tables, current_price: float) -> tuple[list[dict], list[dict]]:
    """Parse all MEFF option tables into calls and puts lists."""
    calls: list[dict] = []
    puts: list[dict] = []
    for table in tables:
        for row in table.find_all("tr")[1:]:
            cols = [td.text.strip().replace(",", ".") for td in row.find_all("td")]
            if len(cols) < 6:
                continue
            try:
                opt = _parse_meff_row(cols, current_price)
                if opt:
                    (calls if opt["type"] == "CALL" else puts).append(opt)
            except (ValueError, IndexError):
                continue
    return calls, puts


def _fetch_meff_soup(ticker: str) -> tuple | None:
    """Fetch and parse MEFF HTML. Returns (soup, tables) or None."""
    meff_ticker = ticker.replace(".MC", "")
    url = f"{MEFF_PROXY}{MEFF_URL}{meff_ticker}"
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    return (soup, tables) if tables else None


def _fetch_meff(ticker: str) -> dict | None:
    """Scrape options data for .MC tickers via MEFF website."""
    try:
        raw = _fetch_meff_soup(ticker)
        if not raw:
            return None
        soup, tables = raw

        current_price = _get_meff_price(soup, ticker)
        if not current_price:
            return None

        calls, puts = _parse_meff_tables(tables, current_price)
        all_options = calls + puts
        if not all_options:
            return None

        total_call_vol = sum(c.get("volume", 0) for c in calls)
        total_put_vol = sum(p.get("volume", 0) for p in puts)
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        return {
            "ticker": ticker,
            "current_price": float(current_price),
            "timestamp": datetime.now().isoformat(),
            "stock_data": {},
            "historical_volatility": None,
            "expirations_analyzed": [],
            "calls": calls,
            "puts": puts,
            "calls_count": len(calls),
            "puts_count": len(puts),
            "put_call_ratio": pcr,
            "status": "success",
            "source": "meff",
        }
    except Exception:
        logger.exception("MEFF fetch failed for %s", ticker)
        return None


def _parse_meff_row(cols: list[str], underlying_price: float) -> dict | None:
    """Parse a MEFF table row into an option dict."""
    strike = float(cols[0]) if cols[0] else None
    if not strike:
        return None

    bid = float(cols[1]) if cols[1] else 0.0
    ask = float(cols[2]) if cols[2] else 0.0
    volume = int(float(cols[3])) if cols[3] else 0
    oi = int(float(cols[4])) if cols[4] else 0
    opt_type = cols[5].upper() if len(cols) > 5 else "CALL"

    mid = (bid + ask) / 2 if (bid and ask) else bid or ask
    iv = _solve_iv(underlying_price, strike, MEFF_DEFAULT_DAYS / 365.0, mid, opt_type)
    expiration = (datetime.now() + timedelta(days=MEFF_DEFAULT_DAYS)).strftime("%Y-%m-%d")

    return {
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "lastPrice": mid,
        "volume": volume,
        "openInterest": oi,
        "impliedVolatility": iv,
        "daysToExpiry": MEFF_DEFAULT_DAYS,
        "expiration": expiration,
        "type": opt_type,
    }


def _solve_iv(
    spot: float,
    strike_price: float,
    time_to_exp: float,
    market_price: float,
    opt_type: str,
    risk_free: float = 0.053,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson implied volatility solver."""
    if market_price <= 0 or time_to_exp <= 0:
        return 0.0

    sigma = 0.3
    for _ in range(max_iter):
        d1 = (
            math.log(spot / strike_price) + (risk_free + 0.5 * sigma**2) * time_to_exp
        ) / (sigma * math.sqrt(time_to_exp))
        d2 = d1 - sigma * math.sqrt(time_to_exp)

        if opt_type == "CALL":
            price = spot * _norm_cdf(d1) - strike_price * math.exp(-risk_free * time_to_exp) * _norm_cdf(d2)
        else:
            price = strike_price * math.exp(-risk_free * time_to_exp) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

        vega = spot * _norm_pdf(d1) * math.sqrt(time_to_exp)
        if vega < 1e-10:
            break

        sigma -= (price - market_price) / vega
        if abs(price - market_price) < tol:
            break
        if sigma <= 0:
            sigma = 0.01

    return round(max(sigma, 0), 4)
