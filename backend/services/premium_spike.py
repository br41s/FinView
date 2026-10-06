"""Premium spike detector — a contract's premium against its own previous close.

A spike is a contract that traded this session at ≥ SPIKE_MULTIPLIER × its
previous close, as published by the source: Yahoo's ``change`` column and MEFF's
``Prev`` column, carried on each contract as ``prevClose``. Stateless on purpose.

It used to learn an in-memory EMA per (ticker, type, strike), and that produced
noise, not signal, for two reasons. The key had no expiration, while a chain
holds several (three on Yahoo, every listed one on Eurex), so one cycle fed the
same strike's near and far expiries into one EMA and a far expiry's time value
read as a +150% "spike". And prod scales to zero between cron ticks, so the
baseline was rebuilt from that mix on every cycle. In the 7 days to 2026-10-05,
1,236 of 1,250 spike hits were Eurex London tickers.

Eurex publishes one daily settlement per contract and no previous one, so its
contracts carry no ``prevClose`` and never spike: a settlement does not move
between two cycles of the same day.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────────────

# Premium must be at least this multiple of the previous close to fire (+150%)
SPIKE_MULTIPLIER: float = 2.5

# Minimum previous close (in currency units): a 0.04 → 0.10 move is +150% on a
# contract nobody trades, not a signal.
MIN_PREMIUM: float = 0.10


# ── Public API ──────────────────────────────────────────────────────────────

def detect_spikes(ticker: str, options_data: dict) -> list[dict]:
    """Scan calls + puts for premium spikes; at most one alert for the ticker.

    ``options_data`` holds ``"calls"`` and ``"puts"``, each a list of contract
    dicts as returned by ``options_scraper.fetch_options``.
    """
    # Raw per-contract hits, collapsed into one alert per ticker: when an
    # underlying moves, every strike spikes together — IWDA.AS fired on 17
    # adjacent strikes at once, which is one event, not 17 signals.
    hits: list[dict] = []

    for option_type in ("calls", "puts"):
        ot_label = "call" if option_type == "calls" else "put"
        for contract in options_data.get(option_type) or []:
            try:
                premium = float(contract.get("lastPrice") or 0)
                prev = float(contract.get("prevClose") or 0)
                volume = int(contract.get("volume") or 0)
                strike = float(contract.get("strike") or 0)
            except (TypeError, ValueError):
                continue

            # No trade this session means lastPrice is an older print, and its
            # change is against a close that is not yesterday's.
            if volume <= 0 or prev < MIN_PREMIUM:
                continue
            if premium >= SPIKE_MULTIPLIER * prev:
                pct = round((premium / prev - 1) * 100)
                hits.append({"option_type": ot_label, "strike": strike, "pct": pct})
                logger.info("PREMIUM_SPIKE %s %s K=%s exp=%s: %.2f vs prev close %.2f",
                            ticker, ot_label, strike, contract.get("expiration"), premium, prev)

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
    msg = f"{n} {contratos} ({breakdown}), {pct_range} sobre el cierre anterior"

    return {
        "ticker": ticker,
        "type": "PREMIUM_SPIKE",
        "severity": "HIGH",
        "message": msg,
        "_spike_count": n,
    }
