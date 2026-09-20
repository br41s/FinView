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
# 5-minute bars spanned by each horizon's sigma lag: the intraday ones directly,
# the daily ones as one session (78 bars) scaled by the square root of the
# trading days spanned. Everything comes from the one intraday series, so the
# daily series is only fetched for symbols that have no 5-minute bars at all.
_SESSION_BARS = 78
_HORIZON_BARS = {GeoHorizon.H1.value: 12, GeoHorizon.H6.value: 72}
_HORIZON_DAYS = {GeoHorizon.D1.value: 1, GeoHorizon.D3.value: 2, GeoHorizon.D7.value: 5}
_MIN_SIGMA_SAMPLES = 10
# A checkpoint with no price at its target is left pending and retried next
# cycle — a Yahoo stall used to burn it as NEUTRAL forever. Three days, not
# seven: a final horizon kept pending keeps its signal ACTIVE, and ACTIVE is
# what the per-user dedup blocks re-tracking on.
_GIVE_UP_AFTER = timedelta(days=3)
# Ten days of 5-minute bars reach past the +7d target with margin; five did
# not (five trading days is seven calendar days to the hour).
_INTRADAY = {"period": "10d", "interval": "5m"}
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


def _threshold_pct(intraday: Series | None, daily: Series | None, horizon: str) -> float | None:
    """Readable-move threshold in %, or None when the series cannot calibrate one.

    None is not the floor: a ticker priced without a calibrated threshold used
    to fall back to 0.1% silently — 45× too loose at +7d — and the resulting
    coin flip wrote confidence_mod into geo_rule_stats. Uncalibrated is
    unmeasurable.
    """
    if horizon in _HORIZON_BARS:
        sigma = _sigma_pct(intraday, _HORIZON_BARS[horizon])
    else:
        days = _HORIZON_DAYS[horizon]
        session = _sigma_pct(intraday, _SESSION_BARS)
        if session is None:
            session = _sigma_pct(daily, 1)
        sigma = session * math.sqrt(days) if session is not None else None
    if sigma is None:
        return None
    return max(_MIN_MOVE_PCT, _SIGMA_K * sigma)


def create_checkpoints(db: Session, signal: GeoSignal) -> None:
    """Create the 5 pending checkpoints for a freshly created signal. Caller commits."""
    base = signal.created_at or datetime.now(timezone.utc)
    for horizon, delay in _HORIZON_DELAYS.items():
        target = (
            add_trading_time(base, delay) if horizon in _TRADING_TIME_HORIZONS else base + delay
        )
        # One naive-UTC column: add_trading_time answers aware, the calendar
        # branch answers whatever created_at was.
        target = target.astimezone(timezone.utc).replace(tzinfo=None) if target.tzinfo else target
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


def _series_for(
    symbols: list[str], budget: Budget | None, cache: dict[str, Series] | None, **spec
) -> dict[str, Series]:
    """Fetch the series for ``symbols``, reusing ``cache`` (one per cron request)
    for whatever was already fetched for another user this cycle."""
    if cache is None:
        return fetch_price_series(symbols, budget=budget, **spec) if symbols else {}
    missing = [s for s in symbols if s not in cache]
    if missing:
        cache.update(fetch_price_series(missing, budget=budget, **spec))
        for s in missing:
            cache.setdefault(s, [])  # remember a miss too: don't re-ask per user
    return {s: cache[s] for s in symbols if cache.get(s)}


def evaluate_pending(
    db: Session,
    user_id: int,
    budget: Budget | None = None,
    series_cache: dict[str, dict[str, Series]] | None = None,
) -> int:
    """Evaluate all due, unscored checkpoints for a user. Returns count evaluated.

    ``series_cache`` is shared across the users of one cron request: the price
    series are the same for everyone, so they are fetched once per request, not
    once per user.

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
    cache = series_cache if series_cache is not None else {}
    intraday = _series_for(symbols, budget, cache.setdefault("5m", {}), **_INTRADAY)
    # The daily series backs only what the intraday one cannot: symbols with no
    # 5-minute bars at all, and targets older than the intraday window. Fetching
    # it for everything doubled the Yahoo footprint for data never read, and it
    # shared the budget the intraday pass had just spent.
    earliest = min((_utc(c.target_at) for c in pending), default=now)
    # "Too few bars to calibrate" is as good as none: TTF=F has ~36 five-minute
    # bars in ten days, so its daily horizons had no sigma and the leg never
    # reached the +7d checkpoint that trains the rules.
    need_daily = sorted(
        sym for sym in symbols
        if sym not in intraday
        or intraday[sym][0][0] > earliest
        or len(intraday[sym]) <= _SESSION_BARS + _MIN_SIGMA_SAMPLES
    )
    daily = _series_for(need_daily, budget, cache.setdefault("1d", {}), **_DAILY)

    evaluated = 0
    uncalibrated: set[str] = set()
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
            threshold = _threshold_pct(bars, daily.get(t.symbol), horizon)
            # A price without a calibrated threshold is unmeasurable, not "0.1%".
            if price is not None and threshold is None and t.symbol not in uncalibrated:
                uncalibrated.add(t.symbol)
                logger.info("geo auditor: %s has no %s sigma — leg unmeasurable", t.symbol, horizon)
            if price is not None and threshold is not None:
                prices[t.symbol] = price
                thresholds[t.symbol] = threshold

        if not prices:
            if now - target < _GIVE_UP_AFTER:
                continue  # retry next cycle: the bars may just not have arrived
            score, detail = None, "sin datos de precio para ningún ticker"
        else:
            score, detail, _ = _score_basket(signal, prices, thresholds)

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
