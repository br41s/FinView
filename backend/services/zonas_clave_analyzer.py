"""Zonas Clave algorithmic analyzer — pure technical analysis, no AI calls.

Pipeline per ticker:
  fetch_history → detect_pivots → cluster_pivots → compute_zone_strength
  → compute_rsi → compute_macd → compute_moving_averages → compute_trend_bias
  → store ZonasClaveAnalysis in DB
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yf.download() has internal shared state that isn't thread-safe: calling it
# concurrently for two different tickers (e.g. add_ticker spawns one
# background thread per watchlist add) can return one ticker's data for the
# other, silently persisting the wrong price/zones. Serializing the download
# itself is cheap (yfinance's own HTTP call already dominates latency) and
# closes the race without touching the calling threads' architecture.
_YF_DOWNLOAD_LOCK = threading.Lock()

# "max" was tried and reverted: for long-listed tickers it pulls in decades-old,
# split-adjusted penny-level prices that dominate zone detection with irrelevant
# S/R levels (e.g. $0.30 "resistance" zones next to a $300 current price). 20y
# still gives pivot detection much more history than before without that noise.
_HISTORY_PERIOD = "20y"
_HISTORY_INTERVAL = "1d"
_PIVOT_WINDOW = 10          # bars each side for pivot detection
_CLUSTER_THRESHOLD = 0.015  # 1.5% — pivots within this range merge into one zone
_MAX_ZONES = 8              # top N zones to return


# ── Data fetching ────────────────────────────────────────────────────

# Minimum bars needed for detect_pivots to find at least one pivot (a bar
# needs `_PIVOT_WINDOW` neighbors on each side). Below this there's truly
# nothing to detect; above it we analyze with whatever history exists
# instead of demanding a fixed lookback that recently-listed tickers can't
# have (e.g. a stock that IPO'd a few months ago).
_MIN_BARS = 2 * _PIVOT_WINDOW + 1


def fetch_history(ticker: str) -> pd.DataFrame | None:
    """Download up to 20 years of daily OHLCV. Returns DataFrame with Close/High/Low/Volume or None."""
    try:
        with _YF_DOWNLOAD_LOCK:
            df = yf.download(
                ticker,
                period=_HISTORY_PERIOD,
                interval=_HISTORY_INTERVAL,
                auto_adjust=True,
                progress=False,
            )
        if df is None or df.empty:
            return None
        # Flatten MultiIndex columns (yfinance sometimes returns them for single tickers)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        return df if len(df) >= _MIN_BARS else None
    except Exception:
        logger.exception("fetch_history failed for %s", ticker)
        return None


def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Extract a column defensively, flattening MultiIndex if present."""
    s = df[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    return s.astype(float)


# ── Ticker search ────────────────────────────────────────────────────

_SEARCHABLE_QUOTE_TYPES = {"EQUITY", "ETF", "INDEX"}


def search_tickers(query: str, max_results: int = 8) -> list[dict]:
    """Live global ticker search via Yahoo Finance (no local catalog to maintain).

    Returns [{ticker, name, exchange}], filtered to equities/ETFs/indices only.
    Best-effort: any failure (timeout, malformed response) returns [].
    """
    query = query.strip()
    if len(query) < 2:
        return []
    try:
        results = yf.Search(query, max_results=max_results, news_count=0, timeout=5).quotes
    except Exception:
        logger.warning("search_tickers failed for %r", query, exc_info=True)
        return []
    out = []
    for r in results:
        symbol = r.get("symbol")
        if not symbol or r.get("quoteType") not in _SEARCHABLE_QUOTE_TYPES:
            continue
        out.append({
            "ticker": symbol,
            "name": r.get("longname") or r.get("shortname") or symbol,
            "exchange": r.get("exchDisp") or "",
        })
    return out


# ── Pivot detection ──────────────────────────────────────────────────


def detect_pivots(
    df: pd.DataFrame, window: int = _PIVOT_WINDOW
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Detect pivot highs and lows using rolling window comparison.

    Returns:
      pivot_high_prices, pivot_high_volumes, pivot_low_prices, pivot_low_volumes
    Each array contains the price/volume at confirmed pivot bars.
    """
    high = _safe_series(df, "High").values
    low = _safe_series(df, "Low").values
    vol = _safe_series(df, "Volume").values
    n = len(high)

    pivot_high_prices, pivot_high_vols = [], []
    pivot_low_prices, pivot_low_vols = [], []

    for i in range(window, n - window):
        lo, hi = i - window, i + window + 1
        if high[i] == np.max(high[lo:hi]):
            pivot_high_prices.append(high[i])
            pivot_high_vols.append(vol[i])
        if low[i] == np.min(low[lo:hi]):
            pivot_low_prices.append(low[i])
            pivot_low_vols.append(vol[i])

    return (
        np.array(pivot_high_prices),
        np.array(pivot_high_vols),
        np.array(pivot_low_prices),
        np.array(pivot_low_vols),
    )


# ── Zone clustering ──────────────────────────────────────────────────


def cluster_pivots(
    prices: np.ndarray,
    volumes: np.ndarray,
    zone_type: str,
    threshold: float = _CLUSTER_THRESHOLD,
) -> list[dict]:
    """
    Cluster nearby pivot prices into zones.
    Pivots within threshold% of the cluster centroid are merged.
    Returns list of {level, zone_type, touches, avg_volume}.
    """
    if len(prices) == 0:
        return []

    # Remove NaN/inf
    mask = np.isfinite(prices) & np.isfinite(volumes)
    prices = prices[mask]
    volumes = volumes[mask]
    if len(prices) == 0:
        return []

    order = np.argsort(prices)
    prices = prices[order]
    volumes = volumes[order]

    zones: list[dict] = []
    cluster_prices = [prices[0]]
    cluster_vols = [volumes[0]]

    for p, v in zip(prices[1:], volumes[1:]):
        centroid = float(np.mean(cluster_prices))
        if abs(p - centroid) / centroid <= threshold:
            cluster_prices.append(p)
            cluster_vols.append(v)
        else:
            zones.append({
                "level": float(np.mean(cluster_prices)),
                "zone_type": zone_type,
                "touches": len(cluster_prices),
                "avg_volume": float(np.mean(cluster_vols)),
            })
            cluster_prices = [p]
            cluster_vols = [v]

    # Flush last cluster
    zones.append({
        "level": float(np.mean(cluster_prices)),
        "zone_type": zone_type,
        "touches": len(cluster_prices),
        "avg_volume": float(np.mean(cluster_vols)),
    })

    return zones


_PROXIMITY_HALF_LIFE = 0.10  # score halves every 10% of relative distance from current price


def compute_zone_strength(
    zones: list[dict], median_volume: float, current_price: float
) -> list[dict]:
    """
    Score zones by touches × volume_score × proximity_weight, normalize to
    [0, 1], keep top N.
    volume_score = avg_volume / median_volume (clamped to [0, 3]).
    proximity_weight decays zones the further their level sits from the
    current price — a level a stock hasn't traded near in years can still
    have the most historical touches (more calendar time to accumulate
    them), which without this would out-rank levels near the current price
    that are actually actionable. See _PROXIMITY_HALF_LIFE.
    """
    if not zones:
        return []

    for z in zones:
        vol_score = min(z["avg_volume"] / median_volume, 3.0) if median_volume > 0 else 1.0
        rel_distance = abs(z["level"] - current_price) / current_price if current_price > 0 else 0.0
        proximity_weight = 0.5 ** (rel_distance / _PROXIMITY_HALF_LIFE)
        z["raw_score"] = z["touches"] * vol_score * proximity_weight
        z["volume_score"] = round(vol_score, 4)

    max_score = max(z["raw_score"] for z in zones) or 1.0
    for z in zones:
        z["strength"] = round(z["raw_score"] / max_score, 4)
        del z["raw_score"]
        del z["avg_volume"]

    zones.sort(key=lambda z: z["strength"], reverse=True)
    return zones[:_MAX_ZONES]


# ── Technical indicators ─────────────────────────────────────────────


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI. Returns current RSI value (last bar)."""
    try:
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
        rs = gain / loss
        rsi = 100 - 100 / (1 + rs)
        val = float(rsi.iloc[-1])
        return val if np.isfinite(val) else None
    except Exception:
        return None


def compute_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict:
    """
    Standard MACD (12, 26, 9).
    Returns {macd_line, signal_line, histogram, signal: bullish|bearish|neutral}.
    """
    try:
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        h_last = float(histogram.iloc[-1])
        h_prev = float(histogram.iloc[-2]) if len(histogram) > 1 else 0.0

        if h_last > 0 and h_last > h_prev:
            sig = "bullish"
        elif h_last < 0 and h_last < h_prev:
            sig = "bearish"
        else:
            sig = "neutral"

        return {
            "macd_line": float(macd_line.iloc[-1]),
            "signal_line": float(signal_line.iloc[-1]),
            "histogram": h_last if np.isfinite(h_last) else 0.0,
            "signal": sig,
        }
    except Exception:
        return {"macd_line": 0.0, "signal_line": 0.0, "histogram": 0.0, "signal": "neutral"}


def compute_moving_averages(close: pd.Series) -> dict:
    """Returns price deviation vs MA50 and MA200 as fractions (positive = above MA)."""
    current = float(close.iloc[-1])
    result = {"price_vs_ma50": 0.0, "price_vs_ma200": 0.0}
    try:
        if len(close) >= 50:
            ma50 = float(close.iloc[-50:].mean())
            result["price_vs_ma50"] = (current - ma50) / ma50 if ma50 else 0.0
        if len(close) >= 200:
            ma200 = float(close.iloc[-200:].mean())
            result["price_vs_ma200"] = (current - ma200) / ma200 if ma200 else 0.0
    except Exception:
        pass
    return result


def compute_trend_bias(rsi: float | None, macd_result: dict, ma_result: dict) -> dict:
    """
    Weighted trend bias:
      RSI  (30%): (rsi - 50) / 50  → [-1, +1]
      MACD (30%): +1 bullish / -1 bearish / 0 neutral
      MA   (40%): avg of MA50 and MA200 deviations, clamped to [-1, +1]

    Returns {bullish_pct, bearish_pct} in [0, 100].
    """
    rsi_score = ((rsi - 50) / 50) if rsi is not None else 0.0
    rsi_score = max(-1.0, min(1.0, rsi_score))

    macd_sig = macd_result.get("signal", "neutral")
    macd_score = 1.0 if macd_sig == "bullish" else (-1.0 if macd_sig == "bearish" else 0.0)

    ma50_score = max(-1.0, min(1.0, ma_result.get("price_vs_ma50", 0.0) * 10))
    ma200_score = max(-1.0, min(1.0, ma_result.get("price_vs_ma200", 0.0) * 10))
    ma_score = 0.5 * ma50_score + 0.5 * ma200_score

    composite = 0.30 * rsi_score + 0.30 * macd_score + 0.40 * ma_score
    bullish_pct = round((composite + 1) / 2 * 100, 2)
    bearish_pct = round(100 - bullish_pct, 2)

    return {"bullish_pct": bullish_pct, "bearish_pct": bearish_pct}


# ── Main analysis pipeline ───────────────────────────────────────────


def analyze_ticker(ticker: str) -> dict | None:
    """
    Full TA pipeline for one ticker.
    Returns analysis dict or None on failure.
    """
    try:
        df = fetch_history(ticker)
        if df is None:
            logger.warning("No history for %s", ticker)
            return None

        close = _safe_series(df, "Close")
        current_price = float(close.iloc[-1])
        median_volume = float(_safe_series(df, "Volume").median())

        # Pivot detection
        ph_prices, ph_vols, pl_prices, pl_vols = detect_pivots(df)

        # Cluster into zones
        resistance_zones = cluster_pivots(ph_prices, ph_vols, "resistance")
        support_zones = cluster_pivots(pl_prices, pl_vols, "support")

        # Score and select top zones
        all_zones = compute_zone_strength(
            resistance_zones + support_zones, median_volume, current_price
        )

        # Technical indicators
        rsi = compute_rsi(close)
        macd = compute_macd(close)
        ma = compute_moving_averages(close)
        bias = compute_trend_bias(rsi, macd, ma)

        # Price history for chart — send all available bars so frontend can slice by scope.
        # OHLC is included so the frontend can render candlesticks; close/volume kept for
        # back-compat with any consumer that only reads the line value.
        chart_df = df
        price_history = [
            {
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx)[:10],
                "open": round(float(open_val), 4),
                "high": round(float(high_val), 4),
                "low": round(float(low_val), 4),
                "close": round(float(close_val), 4),
                "volume": int(vol_val),
            }
            for idx, open_val, high_val, low_val, close_val, vol_val in zip(
                chart_df.index,
                _safe_series(chart_df, "Open"),
                _safe_series(chart_df, "High"),
                _safe_series(chart_df, "Low"),
                _safe_series(chart_df, "Close"),
                _safe_series(chart_df, "Volume"),
            )
        ]

        return {
            "ticker": ticker,
            "current_price": current_price,
            "zones": all_zones,
            "trend_bias_bullish_pct": bias["bullish_pct"],
            "trend_bias_bearish_pct": bias["bearish_pct"],
            "rsi": rsi,
            "macd_signal": macd["signal"],
            "macd_histogram": macd["histogram"],
            "price_history": price_history,
        }
    except Exception:
        logger.exception("analyze_ticker failed for %s", ticker)
        return None


# ── Scheduler entry point ────────────────────────────────────────────


def run_analysis_for_user(user_id: int) -> dict:
    """
    Fetch all watchlist items for user, analyze each ticker, persist results.
    Called by APScheduler every 24h and on manual trigger.
    """
    from backend.database import SessionLocal
    from backend.models import ZonasClaveAnalysis, ZonasClaveWatchlistItem

    analyzed = 0
    failed = 0
    tickers: list[str] = []

    with SessionLocal() as db:
        items = (
            db.query(ZonasClaveWatchlistItem)
            .filter(ZonasClaveWatchlistItem.user_id == user_id)
            .all()
        )

    for item in items:
        tickers.append(item.ticker)
        result = analyze_ticker(item.ticker)
        if result is None:
            failed += 1
            continue

        row = ZonasClaveAnalysis(
            watchlist_item_id=item.id,
            timestamp=datetime.now(timezone.utc),
            zones=json.dumps(result["zones"]),
            trend_bias_bullish_pct=result["trend_bias_bullish_pct"],
            trend_bias_bearish_pct=result["trend_bias_bearish_pct"],
            rsi=result["rsi"],
            macd_signal=result["macd_signal"],
            macd_histogram=result["macd_histogram"],
            price_history=json.dumps(result["price_history"]),
            current_price=result["current_price"],
        )
        with SessionLocal() as db:
            db.add(row)
            db.commit()

        analyzed += 1
        # Avoid yfinance rate-limit between tickers
        time.sleep(1)

    logger.info(
        "Zonas Clave analysis for user %d: %d analyzed, %d failed",
        user_id, analyzed, failed,
    )
    return {"analyzed": analyzed, "failed": failed, "tickers": tickers}
