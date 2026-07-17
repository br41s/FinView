"""Options chain analysis — IV, sentiment, alerts, unusual activity.

Ported from OptionsAI/options_monitor_agent/tools/analysis_tool.py
"""

import logging

logger = logging.getLogger(__name__)

# Thresholds
HIGH_IV_THRESHOLD = 50  # %
HIGH_PCR_THRESHOLD = 1.5
LOW_PCR_THRESHOLD = 0.5
IV_SKEW_THRESHOLD = 10  # percentage points
IV_PREMIUM_RATIO = 1.5  # IV / HV
UNUSUAL_VOLUME_RATIO = 3.0  # volume / open_interest

# Ceiling for a usable implied volatility, as the ratio the source reports
# (10.0 = 1000%). Anything above is not a fat tail, it's a solver blowing up on a
# dead contract: yfinance/MEFF happily return IVs like 1790.38 (179,038%) for
# near-expiry strikes with zero bid and zero open interest.
#
# This is load-bearing. Feeding those into the average produced avg_call_iv
# values in the tens of millions, which overflowed OptionsSnapshot's
# Numeric(10, 4) and made the WHOLE cycle's commit fail — no snapshots, no
# alerts, no cycle log, Monitor permanently empty with no error surfaced to the
# UI. Widening the column would only persist nonsense; the fix is to not average
# noise in the first place.
#
# Real IVs top out around 300% in a crisis; 1000% leaves room for genuinely
# extreme near-expiry pricing while cutting the garbage by orders of magnitude.
MAX_USABLE_IV = 10.0

# Minimum total day volume (calls + puts) before a P/C-ratio alert is trusted.
# The ratio is meaningless on thin options: 2 puts against 1 call is a ratio of
# 2.0, which without a floor fires a HIGH "bearish" alert off pure noise. MEFF
# and Eurex names are routinely this thin, so on a cold-start cycle ~100 tickers
# tripped HIGH_PUT_CALL_RATIO at once — a flood, not a signal. 500 cuts the
# illiquid noise while leaving liquid US names through; uncalibrated, revisit
# once there's data on how many HIGH it lets through per day.
MIN_PCR_ALERT_VOLUME = 500


def _usable_ivs(options: list[dict]) -> list[float]:
    """Implied volatilities in percent, with unusable readings dropped.

    Dropped rather than clamped: a bogus IV shouldn't drag the mean toward the
    cap, it should not vote at all.
    """
    out: list[float] = []
    for o in options:
        iv = o.get("impliedVolatility")
        if not isinstance(iv, (int, float)) or isinstance(iv, bool):
            continue
        if iv <= 0 or iv > MAX_USABLE_IV:
            continue
        out.append(iv * 100)
    return out


def analyze_ticker(options_data: dict) -> dict:
    """Produce analytics summary for one ticker's options data.

    Returns dict with: summary, alerts, unusual_activity, sentiment.
    """
    ticker = options_data.get("ticker", "?")
    calls = options_data.get("calls", [])
    puts = options_data.get("puts", [])
    hv = options_data.get("historical_volatility")

    # Aggregate volumes
    total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
    total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)
    total_call_oi = sum(c.get("openInterest", 0) or 0 for c in calls)
    total_put_oi = sum(p.get("openInterest", 0) or 0 for p in puts)

    # IV averages — garbage readings dropped, see MAX_USABLE_IV
    call_ivs = _usable_ivs(calls)
    put_ivs = _usable_ivs(puts)
    avg_call_iv = sum(call_ivs) / len(call_ivs) if call_ivs else 0
    avg_put_iv = sum(put_ivs) / len(put_ivs) if put_ivs else 0
    iv_skew = avg_put_iv - avg_call_iv

    # Ratios
    pcr_vol = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0
    pcr_oi = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

    # Sentiment
    if pcr_vol > HIGH_PCR_THRESHOLD:
        sentiment = "BEARISH 🐻"
    elif pcr_vol < LOW_PCR_THRESHOLD:
        sentiment = "BULLISH 🐂"
    else:
        sentiment = "NEUTRAL 😐"

    summary = {
        "ticker": ticker,
        "current_price": options_data.get("current_price"),
        "call_volume": total_call_vol,
        "put_volume": total_put_vol,
        "call_open_interest": total_call_oi,
        "put_open_interest": total_put_oi,
        "put_call_ratio_volume": pcr_vol,
        "put_call_ratio_oi": pcr_oi,
        "avg_call_iv": round(avg_call_iv, 2),
        "avg_put_iv": round(avg_put_iv, 2),
        "historical_volatility": round(hv, 2) if hv else None,
        "iv_skew": round(iv_skew, 2),
        "market_sentiment": sentiment,
    }

    # Generate alerts
    alerts = _generate_alerts(ticker, summary, hv)

    # Unusual activity (smart money)
    unusual = _detect_unusual_activity(ticker, calls + puts)

    return {
        "summary": summary,
        "alerts": alerts,
        "unusual_activity": unusual,
        "sentiment": sentiment,
    }


def _generate_alerts(ticker: str, summary: dict, hv: float | None) -> list[dict]:
    alerts = []
    avg_call_iv = summary["avg_call_iv"]
    avg_put_iv = summary["avg_put_iv"]
    pcr = summary["put_call_ratio_volume"]
    skew = summary["iv_skew"]
    avg_iv = (avg_call_iv + avg_put_iv) / 2 if (avg_call_iv and avg_put_iv) else 0

    if avg_call_iv > HIGH_IV_THRESHOLD or avg_put_iv > HIGH_IV_THRESHOLD:
        alerts.append({
            "type": "HIGH_IV",
            "ticker": ticker,
            "message": f"IV alta — Calls: {avg_call_iv:.1f}%, Puts: {avg_put_iv:.1f}%",
            "severity": "MEDIUM",
        })

    # P/C-ratio alerts only when there's enough volume for the ratio to mean
    # anything — see MIN_PCR_ALERT_VOLUME. The ratio and the sentiment label still
    # surface everywhere; this only gates the alert.
    pcr_volume = summary["call_volume"] + summary["put_volume"]
    if pcr_volume >= MIN_PCR_ALERT_VOLUME:
        if pcr > HIGH_PCR_THRESHOLD:
            alerts.append({
                "type": "HIGH_PUT_CALL_RATIO",
                "ticker": ticker,
                "message": f"P/C ratio alto: {pcr:.2f} — sentimiento bajista",
                "severity": "HIGH",
            })
        elif pcr < LOW_PCR_THRESHOLD and pcr > 0:
            alerts.append({
                "type": "LOW_PUT_CALL_RATIO",
                "ticker": ticker,
                "message": f"P/C ratio bajo: {pcr:.2f} — sentimiento alcista",
                "severity": "MEDIUM",
            })

    if abs(skew) > IV_SKEW_THRESHOLD:
        direction = "puts más caras" if skew > 0 else "calls más caras"
        alerts.append({
            "type": "IV_SKEW",
            "ticker": ticker,
            "message": f"IV Skew: {skew:.1f}% — {direction}",
            "severity": "MEDIUM",
        })

    if hv and avg_iv > 0 and hv > 0 and avg_iv / hv > IV_PREMIUM_RATIO:
        ratio = avg_iv / hv
        alerts.append({
            "type": "IV_PREMIUM",
            "ticker": ticker,
            "message": f"IV={avg_iv:.1f}% >> HV={hv:.1f}% (ratio: {ratio:.2f})",
            "severity": "MEDIUM",
        })

    return alerts


def _detect_unusual_activity(ticker: str, options: list[dict]) -> list[dict]:
    unusual = []
    for opt in options:
        vol = opt.get("volume", 0) or 0
        oi = opt.get("openInterest", 0) or 0
        if oi > 0 and vol / oi > UNUSUAL_VOLUME_RATIO:
            unusual.append({
                "ticker": ticker,
                "option_type": opt.get("type", "CALL"),
                "strike": opt.get("strike"),
                "expiration": opt.get("expiration"),
                "volume": vol,
                "open_interest": oi,
                "vol_oi_ratio": round(vol / oi, 2),
                "implied_volatility": opt.get("impliedVolatility"),
                "last_price": opt.get("lastPrice"),
            })
    return unusual
