"""Spanish IRPF savings-base estimator — v1 (individual return only).

Pure tax math, no DB. Given the savings-income components and a taxpayer
profile, it computes:

  saldo RCM + saldo G/P  ──compensación (cap 25%)──▶  base imponible del ahorro
  base × escala estatal del ahorro                 ──▶  cuota íntegra del ahorro
  − parte del mínimo personal/familiar no absorbida por la base general
  − retenciones (brokers + manuales)               ──▶  resultado (a ingresar/devolver)

Why this is the clean first slice: the savings-base scale is uniform across
Spain. It is the sum of a state scale (Ley 35/2006 art. 66) and an autonomic
scale (art. 76) that, for the savings base, is fixed equal to the state one —
communities may modify the general-base scale but NOT the savings scale. So the
combined savings rate does not depend on the autonomous community. The general
base (employment, real estate…) does — that is deferred.

Rate tables — VERIFIED against the BOE consolidated Ley 35/2006 (IRPF):
  · savings scale            arts. 66 + 76 (state half × 2; see per-year note below)
  · mínimo del contribuyente art. 57  (5.550 € · +1.150 >65 · +1.400 >75)
  · mínimo descendientes     art. 58  (2.400/2.700/4.000/4.500 €)
  · mínimo discapacidad      art. 60  (3.000 € · 9.000 € ≥65%)
  · compensación RCM↔G/P     art. 49  (límite 25%)

Savings scale per year (combined = state+autonomic, both halves equal):
  · 2023 → 19/21/23/27/28%  (27%/28% brackets introduced by Ley 31/2022, ef. 1-1-2023)
  · 2024 → 19/21/23/27/28%  (top half 14% ×2; unchanged from 2023)
  · 2025 → 19/21/23/27/30%  (top half raised to 15% ×2 by Ley 7/2024, ef. 1-1-2025)
Minimums and the 25% compensation cap are unchanged across 2023–2025.

v1 modelling simplifications (deliberately not applied; all would only REDUCE
the taxpayer's bill, so the estimate is conservative):
  · descendientes: +2.800 € por hijo <3 años (art. 58.2) not modelled
  · discapacidad: +3.000 € gastos de asistencia (art. 60) not modelled
  · ascendientes (art. 59) not modelled
  · autonomic minimums: a few CCAA raise the personal/family minimum for their
    half of the quota; v1 uses the state minimum for both halves.
Age >65/>75 is applied as ≥65/≥75 (AEAT practical interpretation at 31-Dec).

2023, 2024 and 2025 are encoded. The result exposes `rates_year_used` so the UI
can warn when it differs from the requested year (we fall back to the latest
encoded year rather than guess).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_CENTS = Decimal("0.01")


# ── Per-year rate tables — verified vs BOE Ley 35/2006 (see module docstring) ─
# Combined (state + autonomic) savings scale: ascending
# (upper_bound_exclusive | None for the top, rate). State half in BOE art. 66.
_SAVINGS_SCALE: dict[int, list[tuple[Decimal | None, Decimal]]] = {
    2024: [
        (Decimal("6000"), Decimal("0.19")),
        (Decimal("50000"), Decimal("0.21")),
        (Decimal("200000"), Decimal("0.23")),
        (Decimal("300000"), Decimal("0.27")),
        (None, Decimal("0.28")),
    ],
    # 2025: only the >300.000 € bracket changed (28% → 30%), Ley 7/2024.
    2025: [
        (Decimal("6000"), Decimal("0.19")),
        (Decimal("50000"), Decimal("0.21")),
        (Decimal("200000"), Decimal("0.23")),
        (Decimal("300000"), Decimal("0.27")),
        (None, Decimal("0.30")),
    ],
}

# Mínimo personal y familiar (BOE arts. 57/58/60). age_over_75 is ADDITIONAL to
# age_over_65 (a >75 taxpayer gets base + over_65 + over_75).
# Descendants are tiered by birth order (1st, 2nd, 3rd, 4th+).
_MINIMUM: dict[int, dict[str, Decimal]] = {
    2024: {
        "base": Decimal("5550"),
        "age_over_65": Decimal("1150"),
        "age_over_75": Decimal("1400"),
        "disability_general": Decimal("3000"),   # ≥33% and <65%
        "disability_severe": Decimal("9000"),     # ≥65%
        "descendant_1": Decimal("2400"),
        "descendant_2": Decimal("2700"),
        "descendant_3": Decimal("4000"),
        "descendant_4plus": Decimal("4500"),
    },
}

# RCM ↔ G/P cross-compensation cap, fraction of the positive balance (BOE art. 49).
_COMPENSATION_CAP: dict[int, Decimal] = {2024: Decimal("0.25")}

# Minimums and the compensation cap are unchanged for 2025 (Ley 7/2024 only
# touched the savings-scale top bracket), so 2025 reuses the 2024 values.
_MINIMUM[2025] = _MINIMUM[2024]
_COMPENSATION_CAP[2025] = _COMPENSATION_CAP[2024]

# 2023 is identical to 2024: the 27% (200–300k) and 28% (>300k) savings brackets
# were introduced for 2023 by Ley 31/2022 (ef. 1-1-2023); minimums (unchanged
# since Ley 26/2014) and the 25% cap also match. Reuse to avoid drift.
_SAVINGS_SCALE[2023] = _SAVINGS_SCALE[2024]
_MINIMUM[2023] = _MINIMUM[2024]
_COMPENSATION_CAP[2023] = _COMPENSATION_CAP[2024]


def _latest_year(table: dict[int, object]) -> int:
    return max(table)


def resolve_year(requested: int) -> int:
    """Year whose encoded rates we actually use (latest available fallback)."""
    return requested if requested in _SAVINGS_SCALE else _latest_year(_SAVINGS_SCALE)


# ── Inputs / output ─────────────────────────────────────────────────────────
@dataclass
class SavingsInputs:
    """Already-aggregated savings figures (brokers + manual entries)."""

    rcm_net: Decimal = Decimal("0")      # casilla 27 (intereses) + 29 (dividendos)
    gains: Decimal = Decimal("0")        # casilla 332 — ganancias por transmisión (≥0)
    losses: Decimal = Decimal("0")       # casilla 337 — pérdidas (≤0)
    withholdings: Decimal = Decimal("0")  # retenciones del ahorro (≥0)
    # Pending savings losses carried from prior years (art. 49). Positive
    # magnitudes; each compensates the current same-type positive balance.
    prior_rcm_loss: Decimal = Decimal("0")
    prior_gp_loss: Decimal = Decimal("0")


@dataclass
class TaxpayerProfile:
    """Personal data that shapes the minimum and its allocation."""

    age: int | None = None
    disability: str | None = None        # None | "general" | "severe"
    descendants: int = 0
    # Net general-base income (employment, etc.). Absorbs the minimum first;
    # only the remainder falls on the savings base. 0 → full minimum on savings.
    general_base: Decimal = Decimal("0")


@dataclass
class SavingsEstimate:
    rates_year_used: int
    rcm_net: Decimal
    gp_net: Decimal
    savings_base: Decimal
    rcm_carryforward: Decimal            # negative balance carried 4 years
    gp_carryforward: Decimal
    prior_rcm_loss_applied: Decimal      # prior-year RCM loss used this year
    prior_gp_loss_applied: Decimal       # prior-year G/P loss used this year
    personal_minimum: Decimal
    minimum_on_savings: Decimal
    gross_quota: Decimal                 # cuota íntegra del ahorro (pre-minimum)
    quota: Decimal                       # cuota tras mínimo, floored at 0
    withholdings: Decimal
    result: Decimal                      # >0 a ingresar · <0 a devolver
    breakdown: list[dict] = field(default_factory=list)  # per-bracket detail


# ── Core math ───────────────────────────────────────────────────────────────
def progressive_tax(base: Decimal, year: int) -> tuple[Decimal, list[dict]]:
    """Apply the savings scale to a positive base. Returns (tax, per-bracket)."""
    scale = _SAVINGS_SCALE[resolve_year(year)]
    if base <= 0:
        return Decimal("0"), []
    tax = Decimal("0")
    detail: list[dict] = []
    lower = Decimal("0")
    for upper, rate in scale:
        span_top = base if upper is None else min(base, upper)
        if span_top <= lower:
            break
        taxable = span_top - lower
        bracket_tax = taxable * rate
        tax += bracket_tax
        detail.append({
            "from": lower, "to": span_top, "rate": rate, "tax": bracket_tax,
        })
        lower = span_top
        if upper is not None and base <= upper:
            break
    return tax, detail


def compensate(rcm_net: Decimal, gp_net: Decimal, year: int) -> tuple[Decimal, Decimal, Decimal]:
    """Cross-compensate RCM and G/P balances (cap 25% of the positive side).

    Returns (savings_base, rcm_carryforward, gp_carryforward). A negative
    remainder on either side is carried forward (≤0); it does not enter the base.
    """
    cap = _COMPENSATION_CAP[resolve_year(year)]

    if rcm_net >= 0 and gp_net >= 0:
        return rcm_net + gp_net, Decimal("0"), Decimal("0")

    if rcm_net >= 0 and gp_net < 0:
        comp = min(-gp_net, rcm_net * cap)
        base = rcm_net - comp
        return base, Decimal("0"), gp_net + comp        # gp remainder ≤ 0

    if rcm_net < 0 and gp_net >= 0:
        comp = min(-rcm_net, gp_net * cap)
        base = gp_net - comp
        return base, rcm_net + comp, Decimal("0")        # rcm remainder ≤ 0

    # both negative
    return Decimal("0"), rcm_net, gp_net


def personal_minimum(profile: TaxpayerProfile, year: int) -> Decimal:
    m = _MINIMUM[resolve_year(year)]
    total = m["base"]
    if profile.age is not None:
        if profile.age >= 65:
            total += m["age_over_65"]
        if profile.age >= 75:
            total += m["age_over_75"]
    if profile.disability == "general":
        total += m["disability_general"]
    elif profile.disability == "severe":
        total += m["disability_severe"]
    tiers = [m["descendant_1"], m["descendant_2"], m["descendant_3"], m["descendant_4plus"]]
    for i in range(max(profile.descendants, 0)):
        total += tiers[min(i, 3)]
    return total


def estimate_savings(inputs: SavingsInputs, profile: TaxpayerProfile, year: int) -> SavingsEstimate:
    used = resolve_year(year)
    rcm_net = inputs.rcm_net
    gp_net = inputs.gains + inputs.losses        # losses are ≤ 0

    # Prior-year pending losses compensate the current SAME-TYPE positive balance
    # first (art. 49). Conservative: the leftover's cross-compensation against the
    # other component (25%) is not modelled, so a large prior loss may stay unused.
    prior_rcm_applied = min(max(rcm_net, Decimal("0")), max(inputs.prior_rcm_loss, Decimal("0")))
    prior_gp_applied = min(max(gp_net, Decimal("0")), max(inputs.prior_gp_loss, Decimal("0")))
    rcm_after = rcm_net - prior_rcm_applied
    gp_after = gp_net - prior_gp_applied

    base, rcm_cf, gp_cf = compensate(rcm_after, gp_after, year)

    minimum = personal_minimum(profile, year)
    # Minimum hits the general base first; only the remainder lands on savings.
    minimum_on_savings = max(Decimal("0"), minimum - max(profile.general_base, Decimal("0")))
    minimum_applied = min(minimum_on_savings, base)

    gross_quota, detail = progressive_tax(base, year)
    quota_minimum, _ = progressive_tax(minimum_applied, year)
    quota = max(Decimal("0"), gross_quota - quota_minimum)

    result = quota - inputs.withholdings

    q = lambda d: d.quantize(_CENTS)  # noqa: E731
    return SavingsEstimate(
        rates_year_used=used,
        rcm_net=q(rcm_net),
        gp_net=q(gp_net),
        savings_base=q(base),
        rcm_carryforward=q(rcm_cf),
        gp_carryforward=q(gp_cf),
        prior_rcm_loss_applied=q(prior_rcm_applied),
        prior_gp_loss_applied=q(prior_gp_applied),
        personal_minimum=q(minimum),
        minimum_on_savings=q(minimum_on_savings),
        gross_quota=q(gross_quota),
        quota=q(quota),
        withholdings=q(inputs.withholdings),
        result=q(result),
        breakdown=[
            {**b, "rate": b["rate"], "tax": q(b["tax"]), "from": q(b["from"]), "to": q(b["to"])}
            for b in detail
        ],
    )
