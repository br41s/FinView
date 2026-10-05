"""Analyst — correlate a GeoEvent with instruments via fast rules + optional LLM.

Layer 1: fast-rule match (deterministic, the ported IP).
Layer 2: optional LLM deep analysis, gated by the orchestrator on importance ≥ 60.
The LLM reuses FinView's single OpenRouter model (settings.openrouter_model),
shared with the options agent.
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field


from backend.config import settings
from backend.services.llm_envelope import NO_REASONING, chat
from backend.services.llm_rules import NOT_ADVICE_RULE_EN

from .rules import (
    _MAX_BREADTH_FOR_SCOPE,
    BREADTH_RANK,
    INSTRUMENT_BREADTH,
    INSTRUMENT_TRADABILITY,
    FastRule,
    GeoRuleStat,
    allowed_symbols,
    compute_risk,
    effective_confidence,
    match_rules,
    match_templates,
    region_reach,
    scoring_rules,
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
    # Hand-written rules first: a symbol two rules name keeps the first writer's
    # direction, so a template leg that collides with a written one is dropped.
    rules = match_rules(event) + match_templates(event)
    if not rules:
        return [], [], 0.0, ""

    ticker_map: dict[str, AnalystTicker] = {}
    for rule in rules:
        for t in rule.tickers:
            if t.symbol not in ticker_map:
                ticker_map[t.symbol] = AnalystTicker(t.symbol, t.direction, rule.description)

    # Beside a written rule a template adds legs and nothing else (scoring_rules).
    scoring = scoring_rules(rules)
    avg_conf = sum(effective_confidence(r, stats.get(r.id)) for r in scoring) / len(scoring)
    confidence = max(0.0, min(avg_conf * 100, 100.0))
    return rules, list(ticker_map.values()), confidence, rules[0].direction


# The pipeline runs per user but events are global: cache LLM analyses by event id
# so N users cost one call. In-memory only (resets on cold start, like premium_spike).
_LLM_CACHE: dict[str, tuple[float, dict]] = {}
_LLM_CACHE_TTL = 6 * 3600  # seconds

# Both calls below send `reasoning=NO_REASONING` (llm_envelope says why the
# shared model's reasoning is on or off and nothing in between). Prod measured
# 1601–2270 reasoning tokens against a budget of 2000: `content: null`,
# `finish_reason: "length"`, billed in full, 3–8 generative calls a day — and a
# failure is not cached, so the same event spent a call again the next cycle.
# Each call asks for one short JSON object, and the generative one writes its
# chain before it names an instrument. A larger budget only moves the cliff:
# 2000 tokens already take 9–12 s of a 20 s timeout, and the key's monthly
# limit has been hit once.


def _json_object(content: str, context: str, event_id: str) -> dict | None:
    """The model's answer as a JSON object, or None with the answer in the log.

    JSON mode does not make the parse a formality. Prod has had answers that
    did not begin with a JSON value at all and answers cut inside a string, and
    the traceback that used to be logged carried neither. The preview is a
    repr, so text the model echoed from a headline cannot start a log line of
    its own; the length beside the parser's position tells a cut answer from a
    wrapped one. Nothing is repaired: until one has been read, a fix is a guess.
    """
    try:
        body = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning(
            "%s: content is not JSON for %s (%s; %d chars): %r",
            context, event_id, exc, len(content), content[:200],
        )
        return None
    if not isinstance(body, dict):
        logger.warning(
            "%s: JSON is not an object for %s (%d chars): %r",
            context, event_id, len(content), content[:200],
        )
        return None
    return body


def _number(value: object) -> float | None:
    """A finite number out of the model's JSON, or None.

    `json.loads` reads `NaN`, `Infinity` and `1e999` as floats that `int()`
    raises on, and `true` passes `float()` as 1.0. A numeric string is still a
    number: `compute_risk` has always taken "8".
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _percent(value: object) -> float | None:
    number = _number(value)
    return None if number is None else max(0.0, min(100.0, number))


def _text(value: object, limit: int) -> str:
    """The model's text, trimmed and bounded. What is not text is no text."""
    return value.strip()[:limit] if isinstance(value, str) else ""


def _seen(name: str, value: object) -> str:
    """A field as a log line names it: a short repr, like the answer's preview."""
    return f"{name}={repr(value)[:80]}"


# GeoDirection: the column a pick's direction is written to is an enum.
_ENRICHMENT_DIRECTIONS = {"bullish", "bearish", "neutral"}


def _enrichment_pick(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    symbol = _text(entry.get("symbol"), 40)
    direction = _text(entry.get("direction", "neutral"), 20).lower()
    if not symbol or direction not in _ENRICHMENT_DIRECTIONS:
        return None
    return {"symbol": symbol, "direction": direction,
            "rationale": _text(entry.get("rationale"), 200)}


def _validate_enrichment(body: dict) -> tuple[dict, list[str]]:
    """The enrichment's usable fields, and the ones that were there and were not.

    The model's answer is data here too. `analyze_event` reads this object with
    .get() outside any try, in the middle of a cycle, and a cached one is served
    for six hours: `"estimatedImpact": null`, a confidence of "alto" and
    `"affectedTickers": 5` each raised there. Field by field, not all or
    nothing: the enrichment decorates an analysis the rules already made, so a
    field that cannot be used costs that field and the rules' value stands.

    What comes back is in the prompt's own format with only checked values in
    it. Whether a pick is one the event may reach is still `analyze_event`'s
    question (`allowed_symbols`); this one is about shape.
    """
    usable: dict = {}
    ignored: list[str] = []

    def take(source: dict, key: str, read, into: dict, label: str | None = None) -> None:
        if key not in source:
            return
        value = read(source[key])
        if value is None:
            ignored.append(_seen(label or key, source[key]))
        else:
            into[key] = value

    tickers = body.get("affectedTickers")
    if isinstance(tickers, list):
        picks = []
        for i, entry in enumerate(tickers):
            pick = _enrichment_pick(entry)
            if pick is None:
                ignored.append(_seen(f"affectedTickers[{i}]", entry))
            else:
                picks.append(pick)
        if picks:
            usable["affectedTickers"] = picks
    elif "affectedTickers" in body:
        ignored.append(_seen("affectedTickers", tickers))

    take(body, "narrative", lambda v: _text(v, 600) or None, usable)
    take(body, "confidence", _percent, usable)
    take(body, "riskScore", _number, usable)  # compute_risk clamps it to 1–10

    impact = body.get("estimatedImpact")
    if isinstance(impact, dict):
        checked: dict = {}
        take(impact, "returnLow", _number, checked, "estimatedImpact.returnLow")
        take(impact, "returnHigh", _number, checked, "estimatedImpact.returnHigh")
        take(impact, "timeframe", lambda v: _text(v, 40) or None, checked,
             "estimatedImpact.timeframe")
        if checked:
            usable["estimatedImpact"] = checked
    elif "estimatedImpact" in body:
        ignored.append(_seen("estimatedImpact", impact))
    return usable, ignored


def _llm_analyze(event: GeoEvent, existing: list[str]) -> dict | None:
    """OpenRouter deep analysis. Fire-and-forget — returns None on any failure."""
    if not settings.openrouter_api_key:
        return None

    cached = _LLM_CACHE.get(event.id)
    if cached and time.time() - cached[0] < _LLM_CACHE_TTL:
        return cached[1]

    prompt = (
        "You are VolatilityEdge, a senior geopolitical-macro analyst. Analyze this "
        "real-world event and predict its market impact. " + NOT_ADVICE_RULE_EN + "\n\n"
        f"EVENT:\n- Type: {event.type}\n- Title: {event.title}\n"
        f"- Location: {event.latitude:.2f}, {event.longitude:.2f}\n"
        f"- Region: {event.region or 'unknown'}\n"
        f"- Magnitude: {event.magnitude if event.magnitude is not None else 'N/A'}\n"
        f"- Severity: {event.severity or 'N/A'}\n- Source: {event.source}\n\n"
        f"{'Already identified tickers: ' + ', '.join(existing) if existing else ''}\n\n"
        "Add instruments ONLY from this universe (symbol (breadth, tradability)):\n"
        f"{_universe_block(allowed_symbols(event))}\n\n"
        "Respond ONLY in this exact JSON format:\n"
        '{"affectedTickers": [{"symbol": "XX", "direction": "bullish|bearish|neutral", '
        '"rationale": "brief reason"}], "narrative": "2-3 sentence analysis", '
        '"estimatedImpact": {"returnLow": 1.0, "returnHigh": 5.0, "timeframe": "1-5 days"}, '
        '"confidence": 75, "riskScore": 6}'
    )
    try:
        content, _ = chat(
            [{"role": "user", "content": prompt}],
            context="geo LLM",
            timeout=20.0,
            response_format={"type": "json_object"},
            temperature=0.3,
            reasoning=NO_REASONING,
            max_tokens=2000,  # the answer's own ceiling, with reasoning off
        )
        if content is None:
            return None
        # analyze_event reads this with .get() outside any try: an array or a
        # bare string must stop here, not there.
        body = _json_object(content, "geo LLM", event.id)
        if body is None:
            return None
        # Checked before the cache, not at the read: a field that raises in
        # analyze_event would raise again on every cycle a warm instance serves.
        result, ignored = _validate_enrichment(body)
        if not result:
            # `{}`, `{"error": …}`: nothing to enrich with, and not an answer
            # to remember for six hours either.
            logger.warning(
                "geo LLM: answer is not usable for %s (no usable field; %d chars): %r",
                event.id, len(content), content[:200],
            )
            return None
        if ignored:
            logger.warning(
                "geo LLM: ignored fields for %s: %s", event.id, ", ".join(ignored)[:600]
            )
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
#
# The cache is this process's view of `geo_generative_answers`: the orchestrator
# loads it before the pass and stores what the pass added, because the instance
# rarely lives to the next cycle. It is not a store of its own.
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


def _universe_block(allowed: frozenset[str]) -> str:
    """The instruments one event may be related to, as the prompt lists them."""
    lines = []
    for sym in sorted(allowed):
        trad = INSTRUMENT_TRADABILITY.get(sym, ("cash_eu", ""))[0]
        lines.append(f"{sym} ({INSTRUMENT_BREADTH[sym]}, {trad})")
    return ", ".join(lines)


class MalformedAnswer(ValueError):
    """A JSON object that does not answer the question. The message says why."""


def _validate_generated(
    body: object, reach: str = "regional", allowed: frozenset[str] | None = None
) -> dict | None:
    """The model's answer is data, not a decision: every field is checked.

    ``reach`` is the event's own scope (`rules.region_reach`): a pick wider than
    it — a worldwide ETF for a one-district event — is dropped, the same
    invariant every hand-written rule is tested against. ``allowed`` is the
    event's slice of the universe (`rules.allowed_symbols`): another country's
    instrument is dropped whatever the prompt was told.

    Three outcomes, and they differ in what is worth remembering:

    - a proposal;
    - None, a "no": the model said `actionable: false`, or it named
      well-formed picks (a symbol and bullish/bearish) and none is an
      instrument this event may reach. Asked again it is the same event against
      the same gates, so the caller keeps it six hours;
    - MalformedAnswer: the object is not an answer in the format asked for.
      `{}`, `{"error": …}`, a yes with no well-formed pick, no numeric
      confidence or risk, or no thesis. That says nothing about the event, and
      kept as a "no" it would silence it for six hours without a line in the log.
    """
    if not isinstance(body, dict):
        raise MalformedAnswer("not an object")
    actionable = body.get("actionable")
    if actionable is False:
        return None
    if actionable is not True:
        raise MalformedAnswer("actionable is neither true nor false")
    universe = INSTRUMENT_BREADTH if allowed is None else allowed
    max_breadth = _MAX_BREADTH_FOR_SCOPE.get(reach, 1)
    named: list[str] = []  # well-formed picks, whether or not the event may reach them
    tickers = []
    picks = body.get("tickers")
    for t in picks if isinstance(picks, list) else []:
        if not isinstance(t, dict):
            continue
        sym = _text(t.get("symbol"), 40)
        direction = _text(t.get("direction"), 20).lower()
        if not sym or direction not in {"bullish", "bearish"}:
            continue
        named.append(sym)
        if sym not in universe:
            continue
        if BREADTH_RANK[INSTRUMENT_BREADTH[sym]] > max_breadth:
            logger.info("geo generative: %s is wider than a %s event — dropped", sym, reach)
            continue
        tickers.append({"symbol": sym, "direction": direction,
                        "rationale": _text(t.get("rationale"), 200)})
    if not named:
        raise MalformedAnswer("actionable with no well-formed pick")
    if not tickers:
        logger.info("geo generative: none of %r is an instrument the event may reach", named[:5])
        return None
    confidence, risk = _number(body.get("confidence")), _number(body.get("riskScore"))
    if confidence is None or risk is None:
        raise MalformedAnswer("confidence or riskScore is not a number")
    thesis = body.get("thesis")
    if isinstance(thesis, dict):
        chain = tuple(_text(thesis.get(k), 160) for k in ("effect", "flow", "instrument"))
        thesis_text = " → ".join(c for c in chain if c)
    else:
        thesis_text = _text(thesis, 400)
    if not thesis_text:
        raise MalformedAnswer("no thesis")
    return {
        "tickers": tickers[:_GENERATIVE_MAX_TICKERS],
        "confidence": int(max(0, min(_GENERATIVE_MAX_CONFIDENCE, confidence))),
        "riskScore": int(max(1, min(_GENERATIVE_MAX_RISK, risk))),
        "thesis": thesis_text,
        "narrative": _text(body.get("narrative"), 600),
    }


def _llm_generate(event: GeoEvent) -> dict | None:
    """One generative call for an event no rule covers. Cached per event id
    (successes and "not actionable" alike — a no is worth remembering for 6 h;
    an answer that could not be read or used is neither, and is asked again).
    Returns the validated proposal, or None."""
    if not settings.openrouter_api_key:
        return None
    cached = _GENERATIVE_CACHE.get(event.id)
    if cached and time.time() - cached[0] < _LLM_CACHE_TTL:
        return cached[1] or None
    raw = event.raw_data or {}
    allowed = allowed_symbols(event)
    prompt = (
        "You are VolatilityEdge, a senior geopolitical-macro analyst for a Spanish retail "
        "investor. No hand-written rule covers this event. Decide whether it is a tradable "
        "thesis on a 1-5 day horizon, and if so, which instruments move and why. "
        + NOT_ADVICE_RULE_EN
        + "\n\n"
        f"EVENT:\n- Type: {event.type}\n- Title: {event.title}\n"
        f"- Location: {event.latitude:.2f}, {event.longitude:.2f}\n"
        f"- Region: {event.region or 'none'}\n"
        f"- Magnitude: {event.magnitude if event.magnitude is not None else 'N/A'}\n"
        f"- Severity: {event.severity or 'N/A'}\n- Source: {event.source}\n"
        f"- Source URL: {raw.get('sourceUrl') or raw.get('url') or 'N/A'}\n"
        f"- Mentions: {raw.get('numMentions', 'N/A')}\n\n"
        "Choose instruments ONLY from this universe (symbol (breadth, tradability)):\n"
        f"{_universe_block(allowed)}\n\n"
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
        content, _ = chat(
            [{"role": "user", "content": prompt}],
            context="geo generative LLM",
            timeout=20.0,
            response_format={"type": "json_object"},
            temperature=0.2,
            reasoning=NO_REASONING,
            max_tokens=2000,
        )
        if content is None:
            return None
        # Returned before the cache below: an answer that cannot be read is not
        # a "no", and stored it would silence the event for six hours.
        body = _json_object(content, "geo generative LLM", event.id)
        if body is None:
            return None
        try:
            proposal = _validate_generated(body, region_reach(event.region), allowed)
        except MalformedAnswer as exc:
            # Like an answer that would not parse: logged with what it was,
            # never cached.
            logger.warning(
                "geo generative LLM: answer is not usable for %s (%s; %d chars): %r",
                event.id, exc, len(content), content[:200],
            )
            return None
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
    else:
        logger.info("geo generative: %s → not actionable", event.id)
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

    # Not a raw answer: what _validate_enrichment let through, in the same format.
    llm = _llm_analyze(event, [t.symbol for t in tickers]) if use_llm else None

    ticker_map = {t.symbol: t for t in tickers}
    if llm:
        # The enrichment used to append whatever the model named — the one path
        # by which a symbol outside the universe, or another country's company,
        # entered a signal with no breadth, no tradability and often no price.
        allowed = allowed_symbols(event)
        for t in llm.get("affectedTickers", []) or []:
            sym = t.get("symbol") if isinstance(t, dict) else None
            if sym and sym in allowed and sym not in ticker_map:
                ticker_map[sym] = AnalystTicker(
                    sym, t.get("direction", "neutral"), t.get("rationale", "")
                )

    final_conf = confidence if rules else float(llm.get("confidence", 50)) if llm else 50.0
    risk_score = compute_risk(scoring_rules(rules), event, (llm or {}).get("riskScore"), regime)
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
