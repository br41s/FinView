"""LLM scorer for zone-break probability — the AI half of the technical signal.

Runs only on candidates that already passed the deterministic proximity gate
(`zone_proximity`), which is what bounds token spend: most tickers on most days
produce no candidate at all.

**The number this returns is not calibrated.** An LLM saying "73%" is an opinion
with a number attached, not a probability. That's why every scored candidate is
persisted — including the ones below the alert threshold — so aligned-vs-outcome
data can eventually say whether the cut belongs at 70 or somewhere else. Until
then the threshold is a guess, and should be described as one.
"""

import json
import logging
import time


from backend.config import settings
from backend.services.llm_envelope import chat
from backend.services.llm_rules import NOT_ADVICE_RULE_ES

logger = logging.getLogger(__name__)

# break_probability above which a candidate becomes a user-facing alert.
# Uncalibrated (see module docstring) — everything scored is stored regardless,
# so this can be moved on evidence later without losing history.
ALERT_THRESHOLD = 70

# Scores are cached per (ticker, rounded zone level, day). Proximity persists for
# days: without this, every cycle would re-pay the same scoring call for a price
# that hasn't meaningfully moved. Same lesson as geo/analyst.py's event cache.
_SCORE_CACHE: dict[str, tuple[float, dict]] = {}
_SCORE_CACHE_TTL = 6 * 3600  # seconds
_CACHE_MAX = 500

_SYSTEM = (
    "Eres un analista técnico cuantitativo. Evalúas la probabilidad de que un precio "
    "rompa una zona de soporte/resistencia en los próximos 5 días de mercado. "
    "Eres escéptico: la mayoría de los acercamientos a una zona NO acaban en ruptura. "
    "Una zona con muchos toques y mucho volumen es más difícil de romper, no más fácil. "
    + NOT_ADVICE_RULE_ES
)


def _cache_key(ticker: str, level: float) -> str:
    # Rounded to 2dp + day: a price drifting a cent inside the same zone on the
    # same session is the same question, and shouldn't cost a second call.
    day = time.strftime("%Y-%m-%d", time.gmtime())
    return f"{ticker.upper()}:{level:.2f}:{day}"


def _prune_cache() -> None:
    if len(_SCORE_CACHE) <= _CACHE_MAX:
        return
    cutoff = time.time() - _SCORE_CACHE_TTL
    for key in [k for k, (ts, _) in _SCORE_CACHE.items() if ts < cutoff]:
        _SCORE_CACHE.pop(key, None)


def _build_prompt(ticker: str, candidate: dict, indicators: dict) -> str:
    approach = (
        "por debajo (una ruptura sería al alza)"
        if candidate["approach"] == "from_below"
        else "por encima (una ruptura sería a la baja)"
    )
    return (
        f"Ticker: {ticker}\n"
        f"Precio actual: {indicators.get('current_price')}\n"
        f"Zona: {candidate['level']} "
        f"(etiqueta histórica: {candidate['zone_type']})\n"
        f"Distancia a la zona: {candidate['distance_pct'] * 100:.2f}%\n"
        f"El precio se acerca {approach}\n"
        f"Fuerza de la zona (0-1): {candidate.get('strength')}\n"
        f"Toques históricos de la zona: {candidate.get('touches')}\n"
        f"RSI(14): {indicators.get('rsi')}\n"
        f"MACD: {indicators.get('macd_signal')} (histograma {indicators.get('macd_histogram')})\n"
        f"Sesgo de tendencia: {indicators.get('trend_bias_bullish_pct')}% alcista\n\n"
        "Devuelve JSON: {\"break_probability\": <entero 0-100>, "
        "\"rationale\": \"<una frase en español, máximo 140 caracteres>\"}"
    )


def _parse(payload: dict) -> dict | None:
    """Coerce the model's JSON into a usable score, or None if it's unusable.

    The model is asked for an int 0-100 but can return a float, a string, or a
    number outside the range; clamping beats discarding an otherwise fine score,
    but a non-numeric answer is discarded rather than guessed at.
    """
    raw = payload.get("break_probability")
    try:
        prob = int(round(float(raw)))
    except (TypeError, ValueError):
        logger.warning("zone scorer returned non-numeric break_probability: %r", raw)
        return None
    prob = max(0, min(100, prob))
    rationale = str(payload.get("rationale") or "")[:200]
    return {"break_probability": prob, "rationale": rationale}


def score_break_probability(ticker: str, candidate: dict, indicators: dict) -> dict | None:
    """Score one proximity candidate. Returns {break_probability, rationale} or None.

    None means "no score" (no API key, HTTP failure, unparseable answer) and must
    never be treated as a low probability — the caller stores the candidate
    unscored rather than inventing a number.
    """
    if not settings.openrouter_api_key:
        return None

    key = _cache_key(ticker, candidate["level"])
    cached = _SCORE_CACHE.get(key)
    if cached and time.time() - cached[0] < _SCORE_CACHE_TTL:
        return cached[1]

    try:
        content, _ = chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _build_prompt(ticker, candidate, indicators)},
            ],
            context=f"zone scorer {ticker}",
            timeout=20.0,
            response_format={"type": "json_object"},
            temperature=0.2,
            # The default model is a REASONING model: max_tokens covers the
            # chain-of-thought *and* the answer, and the thinking goes first.
            # The answer here is tiny (an int + one sentence), but prod showed
            # the model spending 500 reasoning tokens and hitting the cap with
            # `finish_reason: length` and `content: null` — 200 and 500 both
            # died that way, having produced nothing.
            #
            # Sized for reasoning headroom, not for the answer. If the model
            # is ever swapped for a non-reasoning one this is simply generous.
            #
            # Reasoning stays ON here, unlike the options and geo calls
            # (llm_envelope.NO_REASONING). The headroom has held: no empty
            # answer in the 10 days to 2026-10-05, while those two lost 85.
            # And this number is calibrated against outcomes band by band
            # (zone_calibration): a scorer that stops reasoning is a different
            # scorer, gated on the record of the one before it. Turning it
            # off is a calibration decision, not a token fix.
            max_tokens=2000,
        )
        if content is None:
            return None
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("zone scorer: content is not JSON for %s: %r", ticker, content[:200])
            return None
        if not isinstance(payload, dict):
            logger.warning("zone scorer: JSON is not an object for %s: %r", ticker, payload)
            return None
        result = _parse(payload)
        if result is None:
            return None
        # Cache successes only, so a transient failure retries next cycle.
        _prune_cache()
        _SCORE_CACHE[key] = (time.time(), result)
        return result
    except Exception:
        logger.warning("zone scoring failed for %s", ticker, exc_info=True)
        return None
