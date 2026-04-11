"""Options data scraper — Yahoo Finance + MEFF (Spanish exchange).

Ported from OptionsAI/options_monitor_agent/tools/options_scraper.py
"""

import logging
import math
from datetime import datetime, timedelta

import numpy as np
import requests
import yfinance as yf
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_EXPIRATIONS = 3  # ~6 weeks of data
MEFF_URL = "https://www.meff.es/esp/Derivados/Ficha/"

_SQRT_2PI = math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def fetch_options(ticker: str) -> dict | None:
    """Fetch options chain for a ticker. Returns structured options data or None."""
    if ticker.endswith(".MC"):
        data = _fetch_meff(ticker)
        if data:
            return data
    return _fetch_yahoo(ticker)


def _fetch_yahoo(ticker: str) -> dict | None:
    """Fetch options data from Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="30d")

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None and not hist.empty:
            current_price = float(hist["Close"].iloc[-1])
        if not current_price:
            logger.warning("No price for %s", ticker)
            return None

        # Historical volatility (30d annualised)
        hv = None
        if len(hist) >= 5:
            returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
            hv_raw = float(returns.std() * np.sqrt(252) * 100)
            hv = hv_raw if not np.isnan(hv_raw) else None

        expirations = t.options[:MAX_EXPIRATIONS] if t.options else []
        calls, puts = [], []

        for exp in expirations:
            chain = t.option_chain(exp)
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
            days_to_exp = max((exp_date - datetime.now()).days, 1)

            for _, row in chain.calls.iterrows():
                calls.append(_yahoo_row_to_dict(row, days_to_exp, exp, "CALL"))
            for _, row in chain.puts.iterrows():
                puts.append(_yahoo_row_to_dict(row, days_to_exp, exp, "PUT"))

        total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
        total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        return {
            "ticker": ticker,
            "current_price": float(current_price),
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


def _safe_int(val, default: int = 0) -> int:
    """Convert to int, handling NaN and None."""
    import math
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
    """Convert to float, handling NaN and None."""
    import math
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


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


# ── MEFF (Spanish Exchange) ─────────────────────────────────────────


def _fetch_meff(ticker: str) -> dict | None:
    """Fallback scraper for .MC tickers via MEFF website."""
    try:
        meff_ticker = ticker.replace(".MC", "")
        url = f"https://api.allorigins.win/raw?url={MEFF_URL}{meff_ticker}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return None

        # Get underlying price from page
        price_el = soup.find("span", class_="last-price")
        current_price = float(price_el.text.replace(",", ".")) if price_el else None
        if not current_price:
            # Fallback to yfinance for price
            t = yf.Ticker(ticker)
            info = t.info or {}
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not current_price:
                return None

        calls, puts = [], []
        for table in tables:
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = [td.text.strip().replace(",", ".") for td in row.find_all("td")]
                if len(cols) < 6:
                    continue
                try:
                    opt = _parse_meff_row(cols, current_price)
                    if opt:
                        if opt["type"] == "CALL":
                            calls.append(opt)
                        else:
                            puts.append(opt)
                except (ValueError, IndexError):
                    continue

        if not calls and not puts:
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

    bid = float(cols[1]) if cols[1] else 0
    ask = float(cols[2]) if cols[2] else 0
    volume = int(float(cols[3])) if cols[3] else 0
    oi = int(float(cols[4])) if cols[4] else 0
    opt_type = cols[5].upper() if len(cols) > 5 else "CALL"

    mid = (bid + ask) / 2 if (bid and ask) else bid or ask
    days_to_exp = 30  # Default, MEFF doesn't always show expiration clearly

    # Newton-Raphson IV solver
    iv = _solve_iv(underlying_price, strike, days_to_exp / 365.0, mid, opt_type)

    return {
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "lastPrice": mid,
        "volume": volume,
        "openInterest": oi,
        "impliedVolatility": iv,
        "daysToExpiry": days_to_exp,
        "expiration": (datetime.now() + timedelta(days=days_to_exp)).strftime("%Y-%m-%d"),
        "type": opt_type,
    }


def _solve_iv(
    S: float, K: float, T: float, market_price: float, opt_type: str,
    r: float = 0.053, tol: float = 1e-6, max_iter: int = 100,
) -> float:
    """Newton-Raphson implied volatility solver."""
    if market_price <= 0 or T <= 0:
        return 0.0

    sigma = 0.3  # initial guess
    for _ in range(max_iter):
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if opt_type == "CALL":
            price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

        vega = S * _norm_pdf(d1) * math.sqrt(T)
        if vega < 1e-10:
            break

        sigma -= (price - market_price) / vega
        if abs(price - market_price) < tol:
            break
        if sigma <= 0:
            sigma = 0.01

    return round(max(sigma, 0), 4)
