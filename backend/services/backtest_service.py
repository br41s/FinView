"""Backtest service — records option alert signals and evaluates outcomes.

Lifecycle:
    1. record_signal() is called during each agent cycle for every HIGH/MEDIUM alert.
    2. evaluate_pending() is called periodically (or at cycle start) to fill in
       price_at_1d, price_at_3d, price_at_7d and derive outcomes.

Direction derivation:
    - HIGH_PUT_CALL_RATIO, HIGH_IV on puts, IV_SKEW  → BEARISH
    - HIGH_IV on calls, BULLISH sentiment             → BULLISH
    - UNUSUAL_VOLUME                                  → derived from option_type in message
    - Default fallback                                → BEARISH (conservative)

Outcome rule (per horizon):
    - BULLISH signal: CORRECT if price rose ≥ 0.5 %, INCORRECT if fell ≥ 0.5 %
    - BEARISH signal: CORRECT if price fell ≥ 0.5 %, INCORRECT if rose ≥ 0.5 %
    - Either case within ±0.5 %: NEUTRAL
"""

import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf
from sqlalchemy.orm import Session

from backend.models import BacktestOutcome, BacktestSignal

logger = logging.getLogger(__name__)

# Minimum price move to count as directional (0.5 %)
_MIN_MOVE_PCT = 0.005

# Horizons: label → calendar days to wait (not trading days — simpler)
_HORIZONS: list[tuple[str, int]] = [
    ("1d", 1),
    ("3d", 3),
    ("7d", 7),
]

# Signal types that imply BEARISH direction
_BEARISH_TYPES = {
    "HIGH_PUT_CALL_RATIO",
    "IV_SKEW",
    "HIGH_IV_PUTS",
}

# Signal types that imply BULLISH direction
_BULLISH_TYPES = {
    "HIGH_IV_CALLS",
    "BULLISH_SENTIMENT",
}


def _derive_direction(signal_type: str, message: str) -> str:
    """Return 'BULLISH' or 'BEARISH' from signal metadata."""
    st = signal_type.upper()
    if st in _BEARISH_TYPES:
        return "BEARISH"
    if st in _BULLISH_TYPES:
        return "BULLISH"
    if st == "UNUSUAL_VOLUME":
        msg = message.upper()
        if "PUT" in msg:
            return "BEARISH"
        if "CALL" in msg:
            return "BULLISH"
    # HIGH_IV generic: look at message
    if st == "HIGH_IV":
        if "PUT" in message.upper():
            return "BEARISH"
        if "CALL" in message.upper():
            return "BULLISH"
    return "BEARISH"  # conservative default


def _outcome(signal_direction: str, price_at_signal: float, price_later: float) -> str:
    """Evaluate a single horizon outcome."""
    if price_at_signal <= 0:
        return BacktestOutcome.NEUTRAL.value
    change_pct = (price_later - price_at_signal) / price_at_signal
    if abs(change_pct) < _MIN_MOVE_PCT:
        return BacktestOutcome.NEUTRAL.value
    if signal_direction == "BULLISH":
        return BacktestOutcome.CORRECT.value if change_pct > 0 else BacktestOutcome.INCORRECT.value
    # BEARISH
    return BacktestOutcome.CORRECT.value if change_pct < 0 else BacktestOutcome.INCORRECT.value


def record_signal(
    db: Session,
    *,
    user_id: int,
    ticker: str,
    alert_type: str,
    message: str,
    current_price: float,
) -> BacktestSignal | None:
    """Record one alert as a backtest signal. Returns the persisted object or None on error.

    Callers should NOT commit — they can batch-commit alongside other inserts.
    """
    try:
        direction = _derive_direction(alert_type, message)
        signal = BacktestSignal(
            user_id=user_id,
            ticker=ticker,
            signal_type=alert_type,
            direction=direction,
            price_at_signal=current_price,
            alert_message=message[:500],
        )
        db.add(signal)
        return signal
    except Exception:
        logger.exception("Failed to record backtest signal for %s / %s", ticker, alert_type)
        return None


def evaluate_pending(db: Session, user_id: int) -> int:
    """Evaluate all pending signals whose horizon days have elapsed.

    Fetches live prices from yfinance for each pending ticker.
    Returns the number of signals updated.
    """
    now = datetime.now(timezone.utc)
    # Signals that are at least 1 day old and have not been fully evaluated
    cutoff = now - timedelta(days=1)
    pending: list[BacktestSignal] = (
        db.query(BacktestSignal)
        .filter(
            BacktestSignal.user_id == user_id,
            BacktestSignal.recorded_at <= cutoff,
            BacktestSignal.outcome_7d.is_(None),  # not fully evaluated yet
        )
        .all()
    )

    if not pending:
        return 0

    # Batch tickers to minimise yfinance round trips
    tickers_needed: set[str] = {s.ticker for s in pending}
    price_cache: dict[str, float] = {}

    for ticker in tickers_needed:
        try:
            hist = yf.Ticker(ticker).history(period="10d")
            if not hist.empty:
                # Build date → close map (UTC-aware dates)
                for ts, row in hist.iterrows():
                    d = ts.date()
                    price_cache[f"{ticker}_{d.isoformat()}"] = float(row["Close"])
        except Exception:
            logger.warning("Could not fetch price history for %s", ticker)

    updated = 0
    for signal in pending:
        base_date = signal.recorded_at.date()
        changed = False

        for label, days in _HORIZONS:
            target_date = base_date + timedelta(days=days)
            if target_date > now.date():
                continue  # horizon not reached yet

            price_key = f"{signal.ticker}_{target_date.isoformat()}"
            # Try target date, then next 2 calendar days (weekend/holiday fallback)
            price_later: float | None = None
            for offset in range(3):
                d = target_date + timedelta(days=offset)
                p = price_cache.get(f"{signal.ticker}_{d.isoformat()}")
                if p is not None:
                    price_later = p
                    break

            if price_later is None:
                continue

            outcome = _outcome(signal.direction, float(signal.price_at_signal), price_later)
            if label == "1d":
                signal.price_at_1d = price_later
                signal.outcome_1d = outcome
            elif label == "3d":
                signal.price_at_3d = price_later
                signal.outcome_3d = outcome
            elif label == "7d":
                signal.price_at_7d = price_later
                signal.outcome_7d = outcome
            changed = True

        if changed:
            updated += 1

    if updated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit backtest evaluations")
            updated = 0

    return updated


def get_stats(db: Session, user_id: int, ticker: str | None = None) -> dict:
    """Return accuracy statistics for completed signals.

    Returns:
        {
            total: int,
            evaluated: int,       # have at least outcome_7d
            by_horizon: {
                "1d": {correct, incorrect, neutral, accuracy_pct},
                "3d": { ... },
                "7d": { ... },
            },
            by_signal_type: {<type>: {correct, total, accuracy_pct}},
        }
    """
    q = db.query(BacktestSignal).filter(BacktestSignal.user_id == user_id)
    if ticker:
        q = q.filter(BacktestSignal.ticker == ticker.upper())

    signals: list[BacktestSignal] = q.order_by(BacktestSignal.recorded_at.desc()).all()
    total = len(signals)
    evaluated = [s for s in signals if s.outcome_7d is not None]

    def _horizon_stats(outcome_attr: str) -> dict:
        rows = [s for s in signals if getattr(s, outcome_attr) is not None]
        correct = sum(1 for s in rows if getattr(s, outcome_attr) == BacktestOutcome.CORRECT.value)
        incorrect = sum(1 for s in rows if getattr(s, outcome_attr) == BacktestOutcome.INCORRECT.value)
        neutral = sum(1 for s in rows if getattr(s, outcome_attr) == BacktestOutcome.NEUTRAL.value)
        acc = round(correct / len(rows) * 100, 1) if rows else None
        return {"evaluated": len(rows), "correct": correct, "incorrect": incorrect, "neutral": neutral, "accuracy_pct": acc}

    by_signal: dict[str, dict] = {}
    for s in evaluated:
        st = s.signal_type
        if st not in by_signal:
            by_signal[st] = {"correct": 0, "total": 0}
        by_signal[st]["total"] += 1
        if s.outcome_7d == BacktestOutcome.CORRECT.value:
            by_signal[st]["correct"] += 1
    for st, v in by_signal.items():
        v["accuracy_pct"] = round(v["correct"] / v["total"] * 100, 1) if v["total"] else None

    return {
        "total": total,
        "evaluated": len(evaluated),
        "by_horizon": {
            "1d": _horizon_stats("outcome_1d"),
            "3d": _horizon_stats("outcome_3d"),
            "7d": _horizon_stats("outcome_7d"),
        },
        "by_signal_type": by_signal,
    }
