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

from .rules import FastRule, GeoRuleStat, effective_confidence, match_rules
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
                "max_tokens": 500,
            },
            timeout=20.0,
        )
        if resp.status_code != 200:
            logger.warning("geo LLM HTTP %s", resp.status_code)
            return None
        content = resp.json()["choices"][0]["message"]["content"]
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


def analyze_event(
    event: GeoEvent, stats: dict[str, GeoRuleStat], use_llm: bool = False
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
    risk_score = (
        int(llm["riskScore"]) if llm and "riskScore" in llm
        else min(round(final_conf / 15), 10)
    )
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
