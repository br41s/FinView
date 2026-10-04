"""The ladder — a signal read tier by tier, from the companies there out to the world.

A basket used to be one list and one score. An event that hurts a country shows
up first, and most clearly, in the companies that earn only there; then in the
country's market; and only sometimes in the commodity or sector the rest of the
world prices. Reading the three separately says how far an event has actually
travelled — and is the measurement any later claim that "a local reaction makes
the national one more likely" has to rest on.

This module is that reading and nothing else: pure functions over what the
auditor stored on each leg. Nothing here moves a confidence. The lift a
confirmed narrow tier lends a wider one is deliberately not implemented — it
ships once `/geo/accuracy` has enough resolved ladders to derive it, the way
`auditor.learned_confidence_mod` is derived, never as a hand-set step.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from .rules import instrument_tier

TIERS = ("local", "national", "international")

# One leg against its own noise.
CONFIRMS, CONTRADICTS, FLAT = "confirms", "contradicts", "flat"
# One tier of a signal.
PENDING, CONFIRMED, CONTRADICTED, UNREADABLE = "pending", "confirmed", "contradicted", "unreadable"


def leg_state(direction: str, change_pct: float, threshold_pct: float) -> str:
    """How one leg reads: it moved as the thesis said, against it, or not readably.

    A move no larger than the leg's own noise is *undetermined*, not wrong. It
    used to count as a miss, which made the intraday checkpoints unwinnable:
    prices.py returned the last daily close, so at +1h and +6h the price was the
    very close the signal was priced at, the change was exactly 0.00 %, and every
    basket scored 0. A leg with no direction says nothing either way.
    """
    if direction not in ("bullish", "bearish") or abs(change_pct) <= threshold_pct:
        return FLAT
    return CONFIRMS if (direction == "bullish") == (change_pct > 0) else CONTRADICTS


@dataclass(frozen=True)
class TierState:
    tier: str
    state: str
    legs: int  # legs the signal carries in this tier
    confirms: int
    contradicts: int


def tier_states(legs: Iterable[tuple[str, str | None]]) -> list[TierState]:
    """The state of each tier a signal carries, narrowest first.

    ``legs`` is (symbol, leg state) for every leg, with None for one that has no
    reading yet. A tier is:

    - **pending** while none of its legs has been read;
    - **confirmed** when more of its legs moved with the thesis than against it;
    - **contradicted** when more moved against it;
    - **unreadable** when they were read and decided nothing — none moved more
      than its noise, or they split evenly.

    A tie is not a confirmation: the same rule the basket score follows, where
    1-for-2 is NEUTRAL rather than half right.
    """
    by_tier: dict[str, list[str | None]] = {}
    for symbol, state in legs:
        by_tier.setdefault(instrument_tier(symbol), []).append(state)
    out: list[TierState] = []
    for tier in TIERS:
        states = by_tier.get(tier)
        if not states:
            continue
        confirms, contradicts = states.count(CONFIRMS), states.count(CONTRADICTS)
        if all(s is None for s in states):
            state = PENDING
        elif confirms > contradicts:
            state = CONFIRMED
        elif contradicts > confirms:
            state = CONTRADICTED
        else:
            state = UNREADABLE
        out.append(TierState(tier, state, len(states), confirms, contradicts))
    return out
