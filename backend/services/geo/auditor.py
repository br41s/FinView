"""Auditor — outcome tracking for geo signals across 5 horizons.

Reuses the backtest concept (BacktestOutcome verdict) but writes to geo_checkpoints
(basket scoring, row-per-horizon) rather than the options-shaped BacktestSignal,
which is per-ticker/daily and would be corrupted by geo's basket/intraday model.
The final (+7d) checkpoint resolves the signal and feeds learned confidence_mod
back into geo_rule_stats.
"""

import json
import logging
import math
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models import (
    BacktestOutcome,
    GeoCheckpoint,
    GeoHorizon,
    GeoRuleStat,
    GeoSignal,
    GeoSignalStatus,
)
from backend.services.prices import fetch_price_series
from backend.services.yahoo_budget import Budget

from .trading_time import add_trading_time

logger = logging.getLogger(__name__)

Series = list[tuple[datetime, float]]

# Horizon → delay. The two intraday horizons are *trading* time on the US
# session (see trading_time.py); the daily ones are calendar days.
_HORIZON_DELAYS: dict[str, timedelta] = {
    GeoHorizon.H1.value: timedelta(hours=1),
    GeoHorizon.H6.value: timedelta(hours=6),
    GeoHorizon.D1.value: timedelta(days=1),
    GeoHorizon.D3.value: timedelta(days=3),
    GeoHorizon.D7.value: timedelta(days=7),
}
_FINAL_HORIZON = GeoHorizon.D7.value
_TRADING_TIME_HORIZONS = frozenset({GeoHorizon.H1.value, GeoHorizon.H6.value})
# Below this move a ticker is unreadable rather than wrong: it is excluded from
# the basket instead of counting against it. This is the floor; the working
# threshold is scaled to each ticker's own noise (see _threshold_pct).
_MIN_MOVE_PCT = 0.1
# Measured (2026-09-20 audit) on the ten most common basket symbols: median
# |move| is 0.24% at +1h and ~1.0% at +1d, so a flat 0.1% dead zone excluded
# nothing in-hours and every in-hours checkpoint was a coin flip on noise.
# A ticker has to move more than 0.75 of its own horizon sigma to be readable.
_SIGMA_K = 0.75
# 5-minute bars spanned by each intraday horizon; trading days per daily horizon.
_HORIZON_BARS = {GeoHorizon.H1.value: 12, GeoHorizon.H6.value: 72}
_HORIZON_DAYS = {GeoHorizon.D1.value: 1, GeoHorizon.D3.value: 3, GeoHorizon.D7.value: 5}
_MIN_SIGMA_SAMPLES = 10
# A checkpoint with no price at its target is left pending and retried next
# cycle — a Yahoo stall used to burn it as NEUTRAL forever. After this long the
# bars are gone from the intraday window and it is recorded as unmeasurable.
_GIVE_UP_AFTER = timedelta(days=7)
_INTRADAY = {"period": "5d", "interval": "5m"}
_DAILY = {"period": "1mo", "interval": "1d"}
_CONFIDENCE_MOD_CLAMP = 0.3


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _as_of(series: Series | None, target: datetime) -> float | None:
    """Last close at or before ``target`` — the bar the checkpoint is about."""
    if not series:
        return None
    stamps = [ts for ts, _ in series]
    idx = bisect_right(stamps, target)
    return series[idx - 1][1] if idx else None


def _sigma_pct(series: Series | None, lag: int) -> float | None:
    """Std of percentage changes over ``lag`` bars, from the series' own history."""
    if not series or len(series) <= lag + _MIN_SIGMA_SAMPLES:
        return None
    closes = [c for _, c in series]
    moves = [
        (closes[i] - closes[i - lag]) / closes[i - lag] * 100
        for i in range(lag, len(closes))
        if closes[i - lag] > 0
    ]
    if len(moves) < _MIN_SIGMA_SAMPLES:
        return None
    mean = sum(moves) / len(moves)
    return math.sqrt(sum((m - mean) ** 2 for m in moves) / (len(moves) - 1))


def _threshold_pct(intraday: Series | None, daily: Series | None, horizon: str) -> float:
    if horizon in _HORIZON_BARS:
        sigma = _sigma_pct(intraday, _HORIZON_BARS[horizon])
    else:
        one_day = _sigma_pct(daily, 1)
        sigma = one_day * math.sqrt(_HORIZON_DAYS[horizon]) if one_day is not None else None
    if sigma is None:
        return _MIN_MOVE_PCT
    return max(_MIN_MOVE_PCT, _SIGMA_K * sigma)


def create_checkpoints(db: Session, signal: GeoSignal) -> None:
    """Create the 5 pending checkpoints for a freshly created signal. Caller commits."""
    base = signal.created_at or datetime.now(timezone.utc)
    for horizon, delay in _HORIZON_DELAYS.items():
        target = (
            add_trading_time(base, delay) if horizon in _TRADING_TIME_HORIZONS else base + delay
        )
        db.add(
            GeoCheckpoint(
                user_id=signal.user_id,
                signal_id=signal.id,
                horizon=horizon,
                target_at=target,
            )
        )


def _score_basket(
    signal: GeoSignal,
    prices: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> tuple[float | None, str, int]:
    """Return (score 0-100 or None, detail string, measurable-ticker count).

    ``thresholds`` is the per-ticker readable-move threshold in %; absent, the
    flat floor applies.
    """
    correct = total = 0
    parts: list[str] = []
    for t in signal.tickers:
        cur = prices.get(t.symbol)
        at = float(t.price_at_signal) if t.price_at_signal is not None else 0.0
        if cur is None or at <= 0:
            continue
        change = (cur - at) / at * 100
        floor = (thresholds or {}).get(t.symbol, _MIN_MOVE_PCT)
        parts.append(
            f"{t.symbol}: {'+' if change >= 0 else ''}{change:.2f}% (σ {floor:.2f}%)"
        )
        # t.direction reads back as a GeoDirection member (Enum values_callable, no
        # str mixin), so a raw `== "bullish"` is always False on a DB-read ticker —
        # the same enum boundary as the horizon check above. Normalize before compare.
        direction = getattr(t.direction, "value", t.direction)
        if direction == "neutral":
            continue
        # A move too small to read is *undetermined*, not wrong, so it stays out of
        # the denominator entirely. It used to count as a miss, which made the
        # intraday checkpoints unwinnable: prices.py returns the last **daily
        # close**, so at +1h and +6h `cur` is the very same close the signal was
        # priced at, change is exactly 0.00%, and every basket scored 0 → INCORRECT.
        # Two of the five checkpoints were red by construction, the accuracy read
        # 0%, and the +7d resolution fed that back into the rules as failure.
        if abs(change) <= floor:
            continue
        total += 1
        if (direction == "bullish" and change > 0) or (direction == "bearish" and change < 0):
            correct += 1
    if total == 0:
        return None, ", ".join(parts), 0
    return round(correct / total * 100, 2), ", ".join(parts), total


def _update_rule_stats(db: Session, signal: GeoSignal, is_correct: bool) -> None:
    try:
        rule_ids = json.loads(signal.matched_rule_ids) if signal.matched_rule_ids else []
    except ValueError:
        rule_ids = []
    delta = 0.02 if is_correct else -0.03
    for rid in rule_ids:
        stat = db.get(GeoRuleStat, rid)
        if stat is None:
            continue
        stat.total_signals = (stat.total_signals or 0) + 1
        stat.correct_signals = (stat.correct_signals or 0) + (1 if is_correct else 0)
        stat.accuracy = stat.correct_signals / stat.total_signals if stat.total_signals else None
        mod = float(stat.confidence_mod or 0) + delta
        stat.confidence_mod = max(-_CONFIDENCE_MOD_CLAMP, min(_CONFIDENCE_MOD_CLAMP, mod))
        stat.updated_at = datetime.now(timezone.utc)


def _outcome(score: float | None) -> str:
    """Ties are not wins: a 1-for-2 basket is undetermined, not 50% correct."""
    if score is None or score == 50:
        return BacktestOutcome.NEUTRAL.value
    return BacktestOutcome.CORRECT.value if score > 50 else BacktestOutcome.INCORRECT.value


def evaluate_pending(db: Session, user_id: int, budget: Budget | None = None) -> int:
    """Evaluate all due, unscored checkpoints for a user. Returns count evaluated.

    Each checkpoint is scored against the bar at its own target time, from the
    series fetched once per cycle: intraday when the target is inside the
    5-minute window, the daily close otherwise. A checkpoint none of whose
    tickers has a price is left pending for the next cycle, up to
    ``_GIVE_UP_AFTER``; it used to be stamped NEUTRAL on the spot, so one Yahoo
    stall burned every window that was due that cycle.
    """
    now = datetime.now(timezone.utc)
    pending: list[GeoCheckpoint] = (
        db.query(GeoCheckpoint)
        .filter(
            GeoCheckpoint.user_id == user_id,
            GeoCheckpoint.target_at <= now,
            GeoCheckpoint.outcome.is_(None),
        )
        .all()
    )
    if not pending:
        return 0

    signal_ids = {c.signal_id for c in pending}
    signals = {
        s.id: s
        for s in db.query(GeoSignal).filter(GeoSignal.id.in_(signal_ids)).all()
    }
    symbols = sorted({t.symbol for s in signals.values() for t in s.tickers})
    intraday = fetch_price_series(symbols, budget=budget, **_INTRADAY) if symbols else {}
    daily = fetch_price_series(symbols, budget=budget, **_DAILY) if symbols else {}

    evaluated = 0
    for chk in pending:
        signal = signals.get(chk.signal_id)
        if signal is None:
            continue
        horizon = getattr(chk.horizon, "value", chk.horizon)
        target = _utc(chk.target_at)
        prices: dict[str, float] = {}
        thresholds: dict[str, float] = {}
        for t in signal.tickers:
            bars = intraday.get(t.symbol)
            use_intraday = bool(bars) and bars[0][0] <= target
            price = _as_of(bars if use_intraday else daily.get(t.symbol), target)
            if price is not None:
                prices[t.symbol] = price
            thresholds[t.symbol] = _threshold_pct(bars, daily.get(t.symbol), horizon)

        if not prices:
            if now - target < _GIVE_UP_AFTER:
                continue  # retry next cycle: the bars may just not have arrived
            score, detail, total = None, "sin datos de precio para ningún ticker", 0
        else:
            score, detail, total = _score_basket(signal, prices, thresholds)

        chk.score = score
        chk.outcome = _outcome(score)
        chk.detail = detail[:1000] if detail else None
        chk.evaluated_at = now
        evaluated += 1

        if horizon == _FINAL_HORIZON:
            signal.status = GeoSignalStatus.RESOLVED.value
            # Only a measurable outcome teaches the rules anything. An unscored
            # basket used to arrive here as `is_correct=False` and cost every
            # matched rule 0.03 — silence punished exactly like being wrong.
            if chk.outcome != BacktestOutcome.NEUTRAL.value:
                _update_rule_stats(db, signal, is_correct=chk.outcome == BacktestOutcome.CORRECT.value)

    if evaluated:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit geo checkpoint evaluations")
            return 0
    return evaluated
