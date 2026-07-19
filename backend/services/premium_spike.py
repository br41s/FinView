"""Premium spike detector — identifies unusual option premium increases.

Compares the current last_price (option premium) of each contract against a
rolling in-memory baseline for the same (ticker, option_type, strike) key.
When the current premium is ≥ SPIKE_MULTIPLIER × baseline it emits a
PREMIUM_SPIKE alert with severity HIGH.

The baseline is updated every cycle using exponential moving average (EMA)
so it adapts to gradually rising premiums without triggering false positives.

No external dependencies — pure stdlib + what is already in the project.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────────────

# Premium must be at least this multiple of the EMA baseline to fire
SPIKE_MULTIPLIER: float = 2.5

# Minimum absolute premium (in currency units) to avoid noise on near-zero contracts
MIN_PREMIUM: float = 0.10

# Minimum number of baseline samples before we start firing alerts
MIN_SAMPLES: int = 3

# EMA smoothing factor α ∈ (0, 1]. Smaller = slower adaptation (more stable baseline)
EMA_ALPHA: float = 0.3


# ── Baseline store ──────────────────────────────────────────────────────────

class _Key(NamedTuple):
    ticker: str
    option_type: str  # "call" | "put"
    strike: float


@dataclass
class _Baseline:
    ema: float
    samples: int = 0
    last_seen: datetime = field(default_factory=datetime.utcnow)


# Per-user baseline store: user_id → { _Key → _Baseline }
_baselines: dict[int, dict[_Key, _Baseline]] = {}


def _get_store(user_id: int) -> dict[_Key, _Baseline]:
    if user_id not in _baselines:
        _baselines[user_id] = {}
    return _baselines[user_id]


# ── Public API ──────────────────────────────────────────────────────────────

def detect_spikes(
    user_id: int,
    ticker: str,
    options_data: dict,
) -> list[dict]:
    """Scan calls + puts for premium spikes.

    Parameters
    ----------
    user_id:
        Owner — baselines are isolated per user so users with different
        watchlists don't bleed into each other.
    ticker:
        Underlying symbol (e.g. "AAPL", "IBE.MC").
    options_data:
        Dict with keys ``"calls"`` and ``"puts"``, each a list of option
        contract dicts as returned by ``options_scraper.fetch_options``.

    Returns
    -------
    list[dict]
        Zero or more alert dicts compatible with the existing alert schema:
        ``{"ticker", "type", "severity", "message"}``.
    """
    store = _get_store(user_id)
    # Raw per-contract hits, collected then collapsed into one alert per ticker.
    # When an underlying moves, every strike spikes together — IWDA.AS fired on 17
    # adjacent strikes at once, which is one event, not 17 signals. The baseline
    # is still learned per contract (below); only the *output* is aggregated.
    hits: list[dict] = []

    for option_type in ("calls", "puts"):
        contracts = options_data.get(option_type) or []
        ot_label = "call" if option_type == "calls" else "put"

        for contract in contracts:
            try:
                strike = float(contract.get("strike") or 0)
                premium = float(contract.get("lastPrice") or contract.get("last_price") or 0)
            except (TypeError, ValueError):
                continue

            if premium < MIN_PREMIUM or strike <= 0:
                continue

            key = _Key(ticker=ticker, option_type=ot_label, strike=strike)
            baseline = store.get(key)

            if baseline is None:
                # First observation — initialise baseline, no alert yet
                store[key] = _Baseline(ema=premium, samples=1)
                continue

            # Update EMA
            new_ema = EMA_ALPHA * premium + (1 - EMA_ALPHA) * baseline.ema
            baseline.ema = new_ema
            baseline.samples += 1
            baseline.last_seen = datetime.utcnow()

            # Check for spike only once we have enough history
            if baseline.samples < MIN_SAMPLES:
                continue

            if baseline.ema > 0 and premium >= SPIKE_MULTIPLIER * baseline.ema:
                pct = round((premium / baseline.ema - 1) * 100)
                hits.append({"option_type": ot_label, "strike": strike, "premium": premium, "pct": pct})
                logger.info("PREMIUM_SPIKE %s %s K=%s: %.2f vs baseline %.2f",
                            ticker, ot_label, strike, premium, baseline.ema)

    alert = _aggregate_ticker_spikes(ticker, hits)
    return [alert] if alert else []


def _aggregate_ticker_spikes(ticker: str, hits: list[dict]) -> dict | None:
    """Collapse a ticker's per-contract spikes into one HIGH alert, or None.

    Direction is kept in the message (calls vs puts), since call-only flow reads
    bullish and put-only bearish, but the whole ticker is one notification. The
    aggregate deliberately carries no ``_strike``/``_option_type`` so the
    cross-cycle dedup keys on (ticker, PREMIUM_SPIKE) — one push per ticker per
    window, not one per strike.
    """
    if not hits:
        return None

    calls = [h for h in hits if h["option_type"] == "call"]
    puts = [h for h in hits if h["option_type"] == "put"]
    pcts = [h["pct"] for h in hits]
    lo, hi = min(pcts), max(pcts)

    parts = []
    if calls:
        parts.append(f"{len(calls)} call{'s' if len(calls) != 1 else ''}")
    if puts:
        parts.append(f"{len(puts)} put{'s' if len(puts) != 1 else ''}")
    breakdown = " + ".join(parts)
    pct_range = f"+{lo}%" if lo == hi else f"+{lo}% a +{hi}%"

    n = len(hits)
    contratos = "contrato con spike" if n == 1 else "contratos con spike"
    msg = f"{n} {contratos} ({breakdown}), {pct_range} sobre baseline"

    return {
        "ticker": ticker,
        "type": "PREMIUM_SPIKE",
        "severity": "HIGH",
        "message": msg,
        "_spike_count": n,
    }


def reset_baselines(user_id: int) -> None:
    """Clear all baselines for a user (e.g. on watchlist change)."""
    _baselines.pop(user_id, None)
