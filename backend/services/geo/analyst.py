"""Analyst — correlate a GeoEvent with instruments via fast rules + optional LLM.

Layer 1: fast-rule match (deterministic, the ported IP).
Layer 2: optional LLM deep analysis, gated by the orchestrator on importance ≥ 60.
The LLM reuses FinView's single OpenRouter model (settings.openrouter_model),
shared with the options agent.
"""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from backend.config import settings

from .rules import (
    _MAX_BREADTH_FOR_SCOPE,
    BREADTH_RANK,
    INSTRUMENT_BREADTH,
    INSTRUMENT_TRADABILITY,
    FastRule,
    GeoRuleStat,
    compute_risk,
    effective_confidence,
    match_rules,
    region_reach,
)
from .sentinel import GeoEvent

logger = logging.getLogger(__name__)


@dataclass
class AnalystTicker:
    symbol: str
    direction: str  # bullish | bearish | neutral
    rationale: str


@dataclass
class AnalystResult:
    event: GeoEvent
    matched_rules: list[FastRule]
    tickers: list[AnalystTicker]
    confidence: float  # 0-100
    risk_score: int  # 0-10
    direction: str  # thesis text
    return_low: float = 1.0
    return_high: float = 5.0
    timeframe: str = "1-5 days"
    llm_narrative: str | None = None
    extra_data: dict = field(default_factory=dict)


def correlate_with_rules(
    event: GeoEvent, stats: dict[str, GeoRuleStat]
) -> tuple[list[FastRule], list[AnalystTicker], float, str]:
    rules = match_rules(event)
    if not rules:
        return [], [], 0.0, ""

    ticker_map: dict[str, AnalystTicker] = {}
    for rule in rules:
        for t in rule.tickers:
            if t.symbol not in ticker_map:
                ticker_map[t.symbol] = AnalystTicker(t.symbol, t.direction, rule.description)

    avg_conf = sum(effective_confidence(r, stats.get(r.id)) for r in rules) / len(rules)
    confidence = max(0.0, min(avg_conf * 100, 100.0))
    return rules, list(ticker_map.values()), confidence, rules[0].direction


# The pipeline runs per user but events are global: cache LLM analyses by event id
# so N users cost one call. In-memory only (resets on cold start, like premium_spike).
_LLM_CACHE: dict[str, tuple[float, dict]] = {}
_LLM_CACHE_TTL = 6 * 3600  # seconds


def _llm_analyze(event: GeoEvent, existing: list[str]) -> dict | None:
    """OpenRouter deep analysis. Fire-and-forget — returns None on any failure."""
    if not settings.openrouter_api_key:
        return None

    cached = _LLM_CACHE.get(event.id)
    if cached and time.time() - cached[0] < _LLM_CACHE_TTL:
        return cached[1]

    prompt = (
        "You are VolatilityEdge, a senior geopolitical-macro analyst. Analyze this "
        "real-world event and predict its market impact.\n\n"
        f"EVENT:\n- Type: {event.type}\n- Title: {event.title}\n"
        f"- Location: {event.latitude:.2f}, {event.longitude:.2f}\n"
        f"- Region: {event.region or 'unknown'}\n"
        f"- Magnitude: {event.magnitude if event.magnitude is not None else 'N/A'}\n"
        f"- Severity: {event.severity or 'N/A'}\n- Source: {event.source}\n\n"
        f"{'Already identified tickers: ' + ', '.join(existing) if existing else ''}\n\n"
        "Respond ONLY in this exact JSON format:\n"
        '{"affectedTickers": [{"symbol": "XX", "direction": "bullish|bearish|neutral", '
        '"rationale": "brief reason"}], "narrative": "2-3 sentence analysis", '
        '"estimatedImpact": {"returnLow": 1.0, "returnHigh": 5.0, "timeframe": "1-5 days"}, '
        '"confidence": 75, "riskScore": 6}'
    )
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                # Reasoning model: this budget covers the chain-of-thought before
                # the answer. Prod measured 500 reasoning tokens alone, so 500
                # total left nothing for the JSON. See zone_scorer for the full
                # post-mortem.
                "max_tokens": 2000,
            },
            timeout=20.0,
        )
        if resp.status_code != 200:
            logger.warning("geo LLM HTTP %s", resp.status_code)
            return None
        # A 200 doesn't guarantee text: the default model reasons first, and if
        # max_tokens runs out mid-thought it returns `content: null` with
        # `finish_reason: length`. json.loads(None) raises, which the outer
        # except would swallow into a generic "geo LLM analysis failed" — the
        # exact shape of bug that hid in zone_scorer for a full prod cycle.
        body = resp.json()
        choices = body.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not isinstance(content, str) or not content.strip():
            logger.warning(
                "geo LLM: 200 with no content — finish_reason=%r usage=%s",
                choices[0].get("finish_reason") if choices else None,
                body.get("usage"),
            )
            return None
        result = json.loads(content)
        # Cache only successes so transient failures retry next cycle.
        if len(_LLM_CACHE) > 500:
            cutoff = time.time() - _LLM_CACHE_TTL
            for key in [k for k, (ts, _) in _LLM_CACHE.items() if ts < cutoff]:
                _LLM_CACHE.pop(key, None)
        _LLM_CACHE[event.id] = (time.time(), result)
        return result
    except Exception:
        logger.warning("geo LLM analysis failed", exc_info=True)
        return None


# ── Generative path: events no rule covers ────────────────────────────
# A hand-written rule used to be the only way any event became a signal; a
# coup, a strike, a cyber incident or a quake outside every box was dropped at
# `if not a.tickers`. A salient unmatched event now gets one generative call
# that must pick from the tradable universe; the result is a signal with no
# matched rules (so it never teaches geo_rule_stats) and a "generated" stamp.
_GENERATIVE_CACHE: dict[str, tuple[float, dict]] = {}
_GENERATIVE_MAX_TICKERS = 3  # the paging bar for a generated thesis lives in advisor
# The model sets both factors of importance for a generated thesis, and the
# event title it reasons from is external text. Cap what it can claim so a
# crafted headline cannot manufacture importance 100: 85 × 0.8 → 68 at most.
_GENERATIVE_MAX_CONFIDENCE = 85
_GENERATIVE_MAX_RISK = 8


def has_fresh_generative(event_id: str) -> bool:
    cached = _GENERATIVE_CACHE.get(event_id)
    return bool(cached and time.time() - cached[0] < _LLM_CACHE_TTL)


def _universe_block() -> str:
    lines = []
    for sym in sorted(INSTRUMENT_BREADTH):
        trad = INSTRUMENT_TRADABILITY.get(sym, ("cash_eu", ""))[0]
        lines.append(f"{sym} ({INSTRUMENT_BREADTH[sym]}, {trad})")
    return ", ".join(lines)


def _validate_generated(body: object, reach: str = "regional") -> dict | None:
    """The model's answer is data, not a decision: every field is checked.

    ``reach`` is the event's own scope (`rules.region_reach`): a pick wider than
    it — a worldwide ETF for a one-district event — is dropped, the same
    invariant every hand-written rule is tested against.
    """
    if not isinstance(body, dict) or body.get("actionable") is not True:
        return None
    allowed = _MAX_BREADTH_FOR_SCOPE.get(reach, 1)
    tickers = []
    for t in body.get("tickers") or []:
        if not isinstance(t, dict):
            continue
        sym = str(t.get("symbol") or "").strip()
        direction = str(t.get("direction") or "").strip().lower()
        if sym not in INSTRUMENT_BREADTH or direction not in {"bullish", "bearish"}:
            continue
        if BREADTH_RANK[INSTRUMENT_BREADTH[sym]] > allowed:
            logger.info("geo generative: %s is wider than a %s event — dropped", sym, reach)
            continue
        tickers.append({"symbol": sym, "direction": direction,
                        "rationale": str(t.get("rationale") or "")[:200]})
    if not tickers:
        return None
    try:
        confidence = max(0, min(_GENERATIVE_MAX_CONFIDENCE, int(body.get("confidence"))))
        risk = max(1, min(_GENERATIVE_MAX_RISK, int(body.get("riskScore"))))
    except (TypeError, ValueError):
        return None
    thesis = body.get("thesis")
    if isinstance(thesis, dict):
        chain = tuple(str(thesis.get(k) or "").strip()[:160] for k in ("effect", "flow", "instrument"))
        thesis_text = " → ".join(c for c in chain if c)
    else:
        thesis_text = str(thesis or "")[:400]
    if not thesis_text:
        return None
    return {
        "tickers": tickers[:_GENERATIVE_MAX_TICKERS],
        "confidence": confidence,
        "riskScore": risk,
        "thesis": thesis_text,
        "narrative": str(body.get("narrative") or "")[:600],
    }


def _llm_generate(event: GeoEvent) -> dict | None:
    """One generative call for an event no rule covers. Cached per event id
    (successes and "not actionable" alike — a no is worth remembering for 6 h).
    Returns the validated proposal, or None."""
    if not settings.openrouter_api_key:
        return None
    cached = _GENERATIVE_CACHE.get(event.id)
    if cached and time.time() - cached[0] < _LLM_CACHE_TTL:
        return cached[1] or None
    raw = event.raw_data or {}
    prompt = (
        "You are VolatilityEdge, a senior geopolitical-macro analyst for a Spanish retail "
        "investor. No hand-written rule covers this event. Decide whether it is a tradable "
        "thesis on a 1-5 day horizon, and if so, which instruments move and why.\n\n"
        f"EVENT:\n- Type: {event.type}\n- Title: {event.title}\n"
        f"- Location: {event.latitude:.2f}, {event.longitude:.2f}\n"
        f"- Region: {event.region or 'none'}\n"
        f"- Magnitude: {event.magnitude if event.magnitude is not None else 'N/A'}\n"
        f"- Severity: {event.severity or 'N/A'}\n- Source: {event.source}\n"
        f"- Source URL: {raw.get('sourceUrl') or raw.get('url') or 'N/A'}\n"
        f"- Mentions: {raw.get('numMentions', 'N/A')}\n\n"
        "Choose instruments ONLY from this universe (symbol (breadth, tradability)):\n"
        f"{_universe_block()}\n\n"
        "Be strict: most events are not tradable. A local event may only target instruments "
        "whose price it plausibly moves; a worldwide ETF needs a worldwide transmission. "
        "If in doubt, answer actionable=false.\n"
        "Respond ONLY in this exact JSON format:\n"
        '{"actionable": true, "thesis": {"effect": "what physically happens", '
        '"flow": "the price or flow it moves", "instrument": "why the instrument follows"}, '
        '"tickers": [{"symbol": "XX", "direction": "bullish|bearish", "rationale": "brief"}], '
        '"confidence": 0, "riskScore": 1, "narrative": "2-3 sentences"}'
    )
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": 2000,
            },
            timeout=20.0,
        )
        if resp.status_code != 200:
            logger.warning("geo generative LLM HTTP %s", resp.status_code)
            return None
        choices = resp.json().get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not isinstance(content, str) or not content.strip():
            logger.warning("geo generative LLM: 200 with no content")
            return None
        proposal = _validate_generated(json.loads(content), region_reach(event.region))
    except Exception:
        logger.warning("geo generative LLM analysis failed", exc_info=True)
        return None
    if len(_GENERATIVE_CACHE) > 500:
        cutoff = time.time() - _LLM_CACHE_TTL
        for key in [k for k, (ts, _) in _GENERATIVE_CACHE.items() if ts < cutoff]:
            _GENERATIVE_CACHE.pop(key, None)
    _GENERATIVE_CACHE[event.id] = (time.time(), proposal or {})
    if proposal:
        logger.info("geo generative: %s → %s (conf %s)", event.id,
                    ",".join(t["symbol"] for t in proposal["tickers"]), proposal["confidence"])
    return proposal


def analyze_unmatched(event: GeoEvent, regime: str | None = None) -> AnalystResult | None:
    """A generated analysis for an event no rule matched, or None."""
    proposal = _llm_generate(event)
    if not proposal:
        return None
    event.raw_data["generated"] = True
    event.raw_data["llmConfidence"] = proposal["confidence"]
    event.raw_data["llmThesis"] = proposal["thesis"]
    event.raw_data["llmNarrative"] = proposal["narrative"]
    return AnalystResult(
        event=event,
        matched_rules=[],
        tickers=[AnalystTicker(t["symbol"], t["direction"], t["rationale"]) for t in proposal["tickers"]],
        confidence=float(proposal["confidence"]),
        risk_score=compute_risk([], event, proposal["riskScore"], regime),
        direction=proposal["thesis"],
        llm_narrative=proposal["narrative"],
    )


def analyze_event(
    event: GeoEvent,
    stats: dict[str, GeoRuleStat],
    use_llm: bool = False,
    regime: str | None = None,
) -> AnalystResult:
    rules, tickers, confidence, direction = correlate_with_rules(event, stats)

    llm = _llm_analyze(event, [t.symbol for t in tickers]) if use_llm else None

    ticker_map = {t.symbol: t for t in tickers}
    if llm:
        for t in llm.get("affectedTickers", []) or []:
            sym = t.get("symbol")
            if sym and sym not in ticker_map:
                ticker_map[sym] = AnalystTicker(
                    sym, t.get("direction", "neutral"), t.get("rationale", "")
                )

    final_conf = confidence if rules else float(llm.get("confidence", 50)) if llm else 50.0
    risk_score = compute_risk(rules, event, (llm or {}).get("riskScore"), regime)
    impact = (llm or {}).get("estimatedImpact", {})
    return AnalystResult(
        event=event,
        matched_rules=rules,
        tickers=list(ticker_map.values()),
        confidence=final_conf,
        risk_score=risk_score,
        direction=direction or (llm or {}).get("narrative") or event.title,
        return_low=float(impact.get("returnLow", 1.0)),
        return_high=float(impact.get("returnHigh", 5.0)),
        timeframe=impact.get("timeframe", "1-5 days"),
        llm_narrative=(llm or {}).get("narrative"),
    )
