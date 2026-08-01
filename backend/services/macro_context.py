"""Macro-regime context from FRED — annotation layer (Phase 2a).

Pulls four macro indicators and classifies a coarse risk regime. This is an
*annotation* layer only: it feeds the VolatilityEdge Claude prompt and a UI
badge. It does NOT change signal scoring or gating (that's a deferred Phase 2b
once this proves out).

Indicators (raw FRED reading, scale=1.0):
  - VIXCLS              CBOE VIX (equity-vol fear gauge), index level
  - T10Y2Y             10y−2y Treasury spread (curve slope), percent points
  - STLFSI4            St. Louis Fed Financial Stress Index, ~0-centred
  - BAMLH0A0HYM2       ICE BofA US High-Yield OAS (credit spread), percent

Storage and sync reuse services.fred_rates (same `fred_rates` table, same
incremental fetch/upsert). No-op without FINVIEW_FRED_API_KEY → macro_context()
returns None and callers simply omit the annotation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.config import settings
from backend.services import fred_rates

logger = logging.getLogger(__name__)

_MACRO_SERIES = ("VIXCLS", "T10Y2Y", "STLFSI4", "BAMLH0A0HYM2")

# Regime thresholds — tunable. Each indicator votes on a risk score
# (positive = risk-off). Kept transparent on purpose; annotation-only so a
# slightly-off threshold only nudges a badge, never a trade signal.
_VIX_HIGH, _VIX_LOW = 25.0, 15.0
_STRESS_HIGH, _STRESS_LOW = 0.0, -0.5
_HY_WIDE, _HY_TIGHT = 5.0, 3.0


def _classify(vix, spread, stress, hy) -> str:
    """Coarse risk regime from the available indicators (missing ones abstain)."""
    score = 0
    if vix is not None:
        score += 1 if vix > _VIX_HIGH else (-1 if vix < _VIX_LOW else 0)
    if spread is not None:
        score += 1 if spread < 0 else 0  # inverted curve → caution
    if stress is not None:
        score += 1 if stress > _STRESS_HIGH else (-1 if stress < _STRESS_LOW else 0)
    if hy is not None:
        score += 1 if hy > _HY_WIDE else (-1 if hy < _HY_TIGHT else 0)
    if score >= 2:
        return "risk_off"
    if score <= -1:
        return "risk_on"
    return "neutral"


def sync_macro() -> int:
    """Incremental sync for the macro series.

    No-op (returns 0) when no FRED API key is configured.
    """
    if not settings.fred_api_key:
        return 0
    from datetime import timedelta

    total = 0
    for series_id in _MACRO_SERIES:
        max_cached = fred_rates._max_cached(series_id)
        if max_cached and (datetime.now(timezone.utc).date() - max_cached).days <= 1:
            continue  # already fresh
        start = (max_cached + timedelta(days=1)).isoformat() if max_cached else None
        rows = fred_rates._fetch_observations(series_id, start, scale=1.0)
        total += fred_rates._upsert(series_id, rows)
    if total:
        logger.info("[macro-sync] added %s macro observations", total)
    return total


def _as_float(v) -> float | None:
    """Decimal/None → plain float/None (JSON-serializable)."""
    return float(v) if v is not None else None


def macro_context() -> dict | None:
    """Current macro regime snapshot, or None when no macro data is cached.

    DB-only (no HTTP). Values are the latest reading within the service's
    look-back window.
    """
    vix = fred_rates.latest_value("VIXCLS")
    spread = fred_rates.latest_value("T10Y2Y")
    stress = fred_rates.latest_value("STLFSI4")
    hy = fred_rates.latest_value("BAMLH0A0HYM2")
    if all(v is None for v in (vix, spread, stress, hy)):
        return None

    vix_f, spread_f, stress_f, hy_f = (
        _as_float(vix),
        _as_float(spread),
        _as_float(stress),
        _as_float(hy),
    )

    as_of = fred_rates._max_cached("VIXCLS") or fred_rates._max_cached("T10Y2Y")
    return {
        "regime": _classify(vix_f, spread_f, stress_f, hy_f),
        "vix": vix_f,
        "yield_spread": spread_f,
        "financial_stress": stress_f,
        "hy_spread": hy_f,
        "as_of": as_of.isoformat() if as_of else None,
    }


def macro_prompt_block() -> str:
    """Render the macro context as a compact block for the Claude prompt."""
    ctx = macro_context()
    if not ctx:
        return "No disponible (FRED no configurado)."

    def fmt(v, suffix=""):
        return f"{v:.2f}{suffix}" if v is not None else "n/d"

    return (
        f"Régimen: {ctx['regime']} (as of {ctx['as_of'] or 'n/d'})\n"
        f"- VIX: {fmt(ctx['vix'])}\n"
        f"- Curva 10a-2a: {fmt(ctx['yield_spread'], '%')}\n"
        f"- Estrés financiero (STLFSI): {fmt(ctx['financial_stress'])}\n"
        f"- Spread High-Yield: {fmt(ctx['hy_spread'], '%')}"
    )
