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

logger = logging.getLogger(__name__)


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
