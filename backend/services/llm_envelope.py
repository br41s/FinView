"""Shared parsing for OpenRouter chat-completion responses.

A 200 does not guarantee text. Models come back with ``content: null`` — the
whole token budget went to reasoning, or the provider put the answer somewhere
else — and the envelope shape varies between providers. FinView learned this the
hard way in ``zone_scorer``, which shipped without tests and spent its first
production cycle calling ``json.loads(None)`` once per ticker.

That lesson lived only in ``zone_scorer``. ``options_agent`` still did

    text = response.json()["choices"][0]["message"]["content"]

inside a broad ``except``, which does not raise on a null content — it returns
``(None, None)``: no analysis and *no error message*, so the UI could not tell a
failed call from "AI not configured". This module is the one place that knows
how to read the envelope, so both callers get a diagnosable answer.
"""

from __future__ import annotations

import logging

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# The shared model reasons before it answers, and max_tokens pays for the
# reasoning and the answer alike: a call that thinks through its whole budget
# comes back 200 with `content: null` and `finish_reason: "length"`, billed in
# full. On deepseek-v4-flash that cannot be made smaller, only switched off:
# OpenRouter's catalogue (GET /api/v1/models, the `reasoning` object) lists no
# effort below its default ("high") and no reasoning budget, and
# `reasoning.exclude` only hides tokens that are still spent. A caller that
# would rather have the answer passes `reasoning=NO_REASONING`.
# A model whose reasoning is mandatory (`reasoning.mandatory` there) rejects
# this with a 4xx: read the new model's entry before changing openrouter_model.
NO_REASONING = {"effort": "none"}


def chat(
    messages: list[dict], *, context: str, timeout: float = 60.0, **params
) -> tuple[str | None, str | None]:
    """One OpenRouter chat completion. Returns ``(content, error)`` like extract_content.

    Six call sites built this request by hand; one of them read
    ``choices[0].message.content`` raw and turned a null into a 500. Transport
    errors and non-200s come back as ``error`` too, so callers have exactly one
    branch to write. ``params`` are passed through (max_tokens, temperature,
    response_format, reasoning).
    """
    if not settings.openrouter_api_key:
        return None, "FINVIEW_OPENROUTER_API_KEY not configured."
    try:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={"model": settings.openrouter_model, "messages": messages, **params},
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("%s: OpenRouter request failed — %s: %s", context, type(exc).__name__, exc)
        return None, f"{type(exc).__name__}: {exc}"
    if resp.status_code != 200:
        body = str(resp.text)[:300]
        logger.warning("%s: OpenRouter HTTP %s — %s", context, resp.status_code, body)
        return None, f"OpenRouter HTTP {resp.status_code}: {body}"
    try:
        body = resp.json()
    except ValueError:
        logger.warning("%s: OpenRouter 200 with a non-JSON body", context)
        return None, "The model's response was not JSON"
    return extract_content(body, context)


def extract_content(body: dict, context: str) -> tuple[str | None, str | None]:
    """Pull the message text out of a chat completion.

    Returns ``(content, error)``. Exactly one is non-None: either usable text, or
    a short reason suitable for showing to the user and logging. ``context``
    names the caller ("zone scorer", "options agent AAPL") so a log line is
    traceable back to a cycle.
    """
    try:
        choices = body.get("choices") or []
        if not choices:
            logger.warning("%s: 200 with no choices — keys=%s", context, sorted(body))
            return None, "The model returned no choices"

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content, None

        finish_reason = choices[0].get("finish_reason")
        logger.warning(
            "%s: 200 with empty content — finish_reason=%r message_keys=%s usage=%s",
            context,
            finish_reason,
            sorted(message),
            body.get("usage"),
        )
        # finish_reason is the single most useful field for diagnosing this:
        # "length" means the budget ran out, anything else usually means the
        # provider put the answer in a field we do not read.
        return None, f"The model returned no text (finish_reason={finish_reason!r})"
    except Exception:
        logger.warning("%s: unparseable response envelope", context, exc_info=True)
        return None, "The model's response could not be parsed"
