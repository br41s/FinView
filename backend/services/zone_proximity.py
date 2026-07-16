"""Proximity gate for technical signals — pure, no AI, no I/O.

The deterministic half of the Zonas Clave signal pipeline: given the zones
`zonas_clave_analyzer` already computed, decide which ones the price is close
enough to that a break is worth *asking about*. Only what survives this gate is
sent to the LLM scorer (`zone_scorer`), which is what keeps token cost bounded —
most tickers, most days, produce zero candidates.

Deliberately separate from `zonas_clave_analyzer`, which is pure TA and should
stay free of signal/AI concerns.
"""

import logging

logger = logging.getLogger(__name__)

# How close (relative to price) a zone must be to become a candidate.
#
# Floor is set by _CLUSTER_THRESHOLD (1.5%) in zonas_clave_analyzer: pivots
# within 1.5% of each other are merged into one zone, so anything under that is
# *inside* the zone rather than near it. 2% leaves a margin outside the cluster
# without firing on a ticker that's an average session away.
PROXIMITY_THRESHOLD = 0.02

# Break direction. Deliberately derived from where price sits relative to the
# level, NOT from the zone's historical `zone_type`: a level built from pivot
# highs is labelled "resistance" forever, but once price trades above it, it
# acts as support and a break *downward* is the move. Trusting the stale label
# would invert the direction on every flipped level.
_BULLISH = "BULLISH"
_BEARISH = "BEARISH"


def _candidate(zone: dict, current_price: float, threshold: float) -> dict | None:
    level = zone.get("level")
    if level is None or current_price <= 0:
        return None
    try:
        level = float(level)
    except (TypeError, ValueError):
        return None
    if level <= 0:
        return None

    distance_pct = abs(level - current_price) / current_price
    if distance_pct > threshold:
        return None

    approaching_from_below = current_price < level
    return {
        "level": level,
        # Historical label, kept as context for the scorer: a "resistance" the
        # price now sits above is a flipped level, which is information.
        "zone_type": zone.get("zone_type", "unknown"),
        "distance_pct": round(distance_pct, 6),
        "approach": "from_below" if approaching_from_below else "from_above",
        "direction": _BULLISH if approaching_from_below else _BEARISH,
        "strength": zone.get("strength"),
        "touches": zone.get("touches"),
    }


def detect_proximity_candidates(
    zones: list[dict],
    current_price: float,
    threshold: float = PROXIMITY_THRESHOLD,
) -> list[dict]:
    """Return the zones price is within `threshold` of, nearest first.

    Each candidate carries the distance, the approach side, the break direction
    implied by that side, and the zone's own strength/touches — everything the
    scorer needs, with no further lookups.

    Price exactly on a level counts as approaching from above (BEARISH): with
    zero distance there's no side to infer, and treating it as a pending
    breakdown is the conservative read.
    """
    if not zones or current_price <= 0:
        return []
    candidates = [
        c for c in (_candidate(z, current_price, threshold) for z in zones) if c is not None
    ]
    candidates.sort(key=lambda c: c["distance_pct"])
    return candidates
