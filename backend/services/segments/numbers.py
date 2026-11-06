"""The deterministic half of segment extraction: reading amounts and checking sums.

Nothing a model says is published on its own word. A segment breakdown is kept
only if its lines add up to the total revenue the report tags in its income
statement, and every amount a model read from a note must appear verbatim in
that note. Both checks live here, away from any network or model call, so they
can be tested exhaustively.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from itertools import combinations

# How far the sum of segment lines may drift from the reported total and still
# count as the same number. Notes round each line to the unit they are presented
# in (usually millions), so five lines can each lose up to half a unit.
TOLERANCE = Decimal("0.005")

# Brute-forcing every subset is 2**n; past this many members we only try "all".
MAX_PARTITION_MEMBERS = 16

# Notes present figures in units, thousands or millions; the total is tagged in
# units. The scale that makes the lines add up is the one the note used.
SCALES = (Decimal(1), Decimal(1_000), Decimal(1_000_000), Decimal(1_000_000_000))


def reconciles(parts_sum: Decimal, total: Decimal) -> bool:
    """True when the segment lines add up to the reported total revenue."""
    if total <= 0:
        return False
    return abs(parts_sum - total) <= total * TOLERANCE


def parse_amount(raw: str) -> Decimal | None:
    """Read an amount as printed in a European or US annual report.

    "16.982" is sixteen thousand (Spanish thousands separator), "1,234.5" and
    "1.234,5" are the same number, "(448)" and "-448" are negative. A single
    separator followed by exactly three digits is read as a thousands separator:
    financial tables do not print three decimals.
    """
    s = raw.strip().replace("−", "-").replace(" ", "").replace(" ", "")
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()-+")
    if not s or not re.fullmatch(r"[\d.,]+", s) or not s[0].isdigit():
        return None

    if "." in s and "," in s:
        decimal_sep = "." if s.rfind(".") > s.rfind(",") else ","
        thousands = "," if decimal_sep == "." else "."
        s = s.replace(thousands, "").replace(decimal_sep, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        parts = s.split(sep)
        thousands_only = len(parts) > 2 or len(parts[-1]) == 3
        s = s.replace(sep, "" if thousands_only else ".")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def appears_in(raw: str, text: str) -> bool:
    """True when `raw` is printed in `text` as a whole number, not inside a longer one."""
    token = raw.strip()
    if not token:
        return False
    return re.search(rf"(?<![\d.,]){re.escape(token)}(?![\d])", text) is not None


def scale_to_total(values: list[Decimal], total: Decimal) -> Decimal | None:
    """The presentation scale under which `values` add up to `total`, or None."""
    raw_sum = sum(values, Decimal(0))
    for scale in SCALES:
        if reconciles(raw_sum * scale, total):
            return scale
    return None


def leaf_rows(values: list[Decimal]) -> list[int] | None:
    """Indexes of the rows left after dropping every row that sums the rows next to it.

    A note prints a group's lines and then (or before) the group's own subtotal, and the
    model sometimes copies both. Searching every subset for the one that adds up is not
    safe here: 17 rows, 12 of them leaves, gave a coincidental larger subset in 2 of 15
    random trials, with up to 14 equal-size candidates, and Naturgy has 19. A subtotal
    is a row that equals a run of 2+ rows directly before or after it, to within the
    rounding of the figures printed, and that is a structure a coincidence rarely has.

    None when no row is a subtotal or fewer than two are left: nothing to rescue.
    """
    if len(values) < 3:
        return None
    # Each printed figure is rounded to its last digit; a run of k plus the subtotal may
    # drift (k + 1) half-units apart.
    unit = Decimal(1).scaleb(min(min(v.as_tuple().exponent for v in values), 0))
    subtotals: set[int] = set()
    for i, value in enumerate(values):
        if value == 0:
            continue
        for k in range(2, len(values)):
            slack = (k + 1) * unit / 2
            before = values[i - k : i] if i >= k else []
            after = values[i + 1 : i + 1 + k]
            for run in (before, after):
                if len(run) == k and abs(sum(run, Decimal(0)) - value) <= slack:
                    subtotals.add(i)
    kept = [i for i in range(len(values)) if i not in subtotals]
    return kept if subtotals and len(kept) >= 2 else None


def pick_partition(values: dict[str, Decimal], total: Decimal) -> list[str] | None:
    """The largest set of members whose values add up to `total`.

    An XBRL axis mixes levels: Apple tags Product and Service, and also iPhone,
    Mac, iPad, Wearables and Service, all on the same axis. Both sets add up to
    total revenue; the finer one says more, so the largest set wins. A
    coincidental match between unrelated members is possible in principle and
    vanishingly unlikely with real figures at this tolerance.
    """
    members = sorted(values)
    if reconciles(sum(values.values(), Decimal(0)), total):
        return members
    if len(members) > MAX_PARTITION_MEMBERS:
        return None
    for size in range(len(members) - 1, 1, -1):
        for subset in combinations(members, size):
            if reconciles(sum((values[m] for m in subset), Decimal(0)), total):
                return list(subset)
    return None
