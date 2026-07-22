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

# Widest age (calendar days) at which a signal is still evaluated. Bounds the
# per-run pending scan as volume grows AND drops signals whose 7d horizon can no
# longer be fetched. The 7-day horizon plus generous slack for cron outages.
_MAX_EVAL_AGE_DAYS = 45

# Cross-cycle dedup window for options signals. A persistent condition (IV stays
# elevated, P/C ratio stays extreme) fires the same alert every 15-min cycle;
# without this, one lingering setup records ~96 near-identical rows/day and
# swamps the backtest. Mirrors technical_signals._already_open (ZONE_BREAK dedup).
_DEDUP_WINDOW_HOURS = 20

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


def alignment_for(direction: str, regime: str | None) -> str | None:
    """Directional alignment of a signal with the macro regime (Phase 2b).

        aligned  — signal direction agrees with the regime's risk tilt
                   (risk_on + BULLISH, or risk_off + BEARISH)
        counter  — signal direction opposes it
        neutral  — regime has no tilt
        None     — no regime available (FRED unconfigured / no data)

    Instrumentation only: this label is recorded and surfaced, never used to
    gate or reweight what fires.
    """
    if not regime:
        return None
    if regime == "neutral":
        return "neutral"
    bullish = direction.upper() == "BULLISH"
    if regime == "risk_on":
        return "aligned" if bullish else "counter"
    if regime == "risk_off":
        return "counter" if bullish else "aligned"
    return None


def alignment_for_alert(alert_type: str, message: str, regime: str | None) -> str | None:
    """Alignment for a raw alert — derives direction first, then aligns.

    Lets the OptionsAlert insert tag alignment identically to how record_signal
    stores it (both go through _derive_direction), without duplicating logic.
    """
    return alignment_for(_derive_direction(alert_type, message), regime)


def _recently_recorded(
    db: Session, user_id: int, ticker: str, signal_type: str, direction: str
) -> bool:
    """True if the same (ticker, type, direction) was already recorded recently.

    Cross-cycle dedup for the options path: a condition that stays true across
    cycles is one signal, not one per cycle. Keyed on direction too, so a
    HIGH_IV on calls and on puts stay distinct.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=_DEDUP_WINDOW_HOURS)
    return (
        db.query(BacktestSignal.id)
        .filter(
            BacktestSignal.user_id == user_id,
            BacktestSignal.ticker == ticker,
            BacktestSignal.signal_type == signal_type,
            BacktestSignal.direction == direction,
            BacktestSignal.recorded_at >= since,
        )
        .first()
        is not None
    )


def record_signal(
    db: Session,
    *,
    user_id: int,
    ticker: str,
    alert_type: str,
    message: str,
    current_price: float,
    regime: str | None = None,
) -> BacktestSignal | None:
    """Record one alert as a backtest signal. Returns the persisted object or None.

    Callers should NOT commit — they can batch-commit alongside other inserts.
    `regime` is the macro regime frozen at record time (Phase 2b); the derived
    alignment is stored alongside it for later aligned-vs-counter analysis.
    Returns None when the same condition was already recorded within
    _DEDUP_WINDOW_HOURS (cross-cycle dedup) or on error.
    """
    try:
        direction = _derive_direction(alert_type, message)
        if _recently_recorded(db, user_id, ticker, alert_type, direction):
            return None  # same open condition already recorded this window
        signal = BacktestSignal(
            user_id=user_id,
            ticker=ticker,
            signal_type=alert_type,
            direction=direction,
            price_at_signal=current_price,
            alert_message=message[:500],
            regime=regime,
            regime_alignment=alignment_for(direction, regime),
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
    # Pending = at least 1 day old, not yet fully evaluated (no outcome_7d), and
    # still inside the evaluable window. The lower age bound both bounds the scan
    # as volume grows and drops signals whose 7d horizon can no longer be fetched.
    cutoff = now - timedelta(days=1)
    floor = now - timedelta(days=_MAX_EVAL_AGE_DAYS)
    pending: list[BacktestSignal] = (
        db.query(BacktestSignal)
        .filter(
            BacktestSignal.user_id == user_id,
            BacktestSignal.recorded_at <= cutoff,
            BacktestSignal.recorded_at >= floor,
            BacktestSignal.outcome_7d.is_(None),  # not fully evaluated yet
        )
        .all()
    )

    if not pending:
        return 0

    # Fetch one price window per ticker wide enough to cover EVERY pending
    # signal's 7-day horizon. A fixed "10d" only reached signals recorded 7-17
    # days ago, so any that missed that sweet spot (a weekend, a skipped cron
    # run) were never evaluable and piled up unbounded. Start from the oldest
    # pending signal, padded for the ±2-day weekend/holiday fallback.
    tickers_needed: set[str] = {s.ticker for s in pending}
    start = min(s.recorded_at for s in pending).date() - timedelta(days=2)
    price_cache: dict[str, float] = {}
    priced = 0

    for ticker in tickers_needed:
        try:
            hist = yf.Ticker(ticker).history(start=start.isoformat())
            if not hist.empty:
                priced += 1
                # Build date → close map
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

    # Per-run visibility: how many were scanned, priced, and filled. Makes a
    # silent zero-throughput regression obvious in the logs instead of invisible.
    logger.info(
        "[backtest-eval] pending=%d tickers=%d priced=%d updated=%d",
        len(pending), len(tickers_needed), priced, updated,
    )
    return updated


def _outcome_value(outcome) -> str | None:
    """Normalize a stored outcome to its string value.

    SQLAlchemy returns the BacktestOutcome *member* on read (e.g.
    ``BacktestOutcome.CORRECT``), so comparing it directly against
    ``BacktestOutcome.CORRECT.value`` ("CORRECT") is always False. Coerce to the
    string value so accuracy counts actually work (member or raw string).
    """
    if outcome is None:
        return None
    return outcome.value if isinstance(outcome, BacktestOutcome) else outcome


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
        rows = [_outcome_value(getattr(s, outcome_attr)) for s in signals]
        rows = [o for o in rows if o is not None]
        correct = sum(1 for o in rows if o == BacktestOutcome.CORRECT.value)
        incorrect = sum(1 for o in rows if o == BacktestOutcome.INCORRECT.value)
        neutral = sum(1 for o in rows if o == BacktestOutcome.NEUTRAL.value)
        acc = round(correct / len(rows) * 100, 1) if rows else None
        return {"evaluated": len(rows), "correct": correct, "incorrect": incorrect, "neutral": neutral, "accuracy_pct": acc}

    by_signal: dict[str, dict] = {}
    for s in evaluated:
        st = s.signal_type
        if st not in by_signal:
            by_signal[st] = {"correct": 0, "total": 0}
        by_signal[st]["total"] += 1
        if _outcome_value(s.outcome_7d) == BacktestOutcome.CORRECT.value:
            by_signal[st]["correct"] += 1
    for st, v in by_signal.items():
        v["accuracy_pct"] = round(v["correct"] / v["total"] * 100, 1) if v["total"] else None

    # Aligned-vs-counter breakdown (Phase 2b): does macro-regime alignment
    # predict outcomes? 7d-based, mirrors by_signal_type. Only signals recorded
    # with a regime contribute; pre-2b/None rows are excluded.
    by_alignment: dict[str, dict] = {}
    for s in evaluated:
        key = s.regime_alignment
        if key is None:
            continue
        bucket = by_alignment.setdefault(key, {"correct": 0, "total": 0})
        bucket["total"] += 1
        if _outcome_value(s.outcome_7d) == BacktestOutcome.CORRECT.value:
            bucket["correct"] += 1
    for v in by_alignment.values():
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
        "by_alignment": by_alignment,
    }


def get_calibration(db: Session, user_id: int, days: int = 30) -> dict:
    """Read-only calibration digest over a recent window.

    Answers the three questions this instrumentation must answer to be trusted,
    so nobody has to hand-query Neon (which is how two silent bugs survived weeks):
      - Is regime alignment predictive?  → by_type_alignment (aligned vs counter)
      - Is the data clean (dedup working)? → dedup_health (rows per ticker-day; ~1 healthy)
      - Is the evaluator alive?           → evaluated_7d share + newest signal
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    signals: list[BacktestSignal] = (
        db.query(BacktestSignal)
        .filter(BacktestSignal.user_id == user_id, BacktestSignal.recorded_at >= since)
        .all()
    )
    evaluated = [s for s in signals if s.outcome_7d is not None]

    # Aligned-vs-counter accuracy split by signal_type — the Phase 2c decision data.
    by_type_alignment: dict[str, dict] = {}
    for s in evaluated:
        if s.regime_alignment not in ("aligned", "counter"):
            continue
        buckets = by_type_alignment.setdefault(s.signal_type, {})
        b = buckets.setdefault(s.regime_alignment, {"correct": 0, "total": 0})
        b["total"] += 1
        if _outcome_value(s.outcome_7d) == BacktestOutcome.CORRECT.value:
            b["correct"] += 1
    for buckets in by_type_alignment.values():
        for b in buckets.values():
            b["accuracy_pct"] = round(b["correct"] / b["total"] * 100, 1) if b["total"] else None

    # Dedup health: rows per (ticker, calendar day). ~1 = healthy; a high number
    # means the same condition is being re-recorded every cycle (firehose regression).
    counts: dict[str, int] = {}
    ticker_days: dict[str, set] = {}
    for s in signals:
        counts[s.signal_type] = counts.get(s.signal_type, 0) + 1
        ticker_days.setdefault(s.signal_type, set()).add((s.ticker, s.recorded_at.date()))
    dedup_health = {
        st: {
            "rows": counts[st],
            "ticker_days": len(ticker_days[st]),
            "rows_per_ticker_day": round(counts[st] / len(ticker_days[st]), 1)
            if ticker_days[st]
            else None,
        }
        for st in counts
    }

    newest = max((s.recorded_at for s in signals), default=None)
    return {
        "window_days": days,
        "since": since.date().isoformat(),
        "total": len(signals),
        "evaluated_7d": len(evaluated),
        "newest": newest.isoformat() if newest else None,
        "by_type_alignment": by_type_alignment,
        "dedup_health": dedup_health,
    }
