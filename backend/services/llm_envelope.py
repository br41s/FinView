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
# The other way OpenRouter documents to switch it off. `chat()` falls back to it once,
# see `_reasoned_though_off`.
REASONING_DISABLED = {"enabled": False}

# Every request asks OpenRouter to route only to providers that neither store the prompt nor
# train on it. The options assistant forwards free text typed by users, so this is not a
# per-caller choice: it is applied last in `chat()` and `params` cannot override it. It
# replaces the account-wide Zero Data Retention switch, which left some models with no
# provider. A model with no provider left answers 404 and the caller gets the usual error.
# Free (`:free`) models all train on prompts, so none of them can be the shared model.
PROVIDER_POLICY = {"data_collection": "deny"}


def chat(
    messages: list[dict], *, context: str, timeout: float = 60.0, **params
) -> tuple[str | None, str | None]:
    """One OpenRouter chat completion. Returns ``(content, error)`` like extract_content.

    Six call sites built this request by hand; one of them read
    ``choices[0].message.content`` raw and turned a null into a 500. Transport
    errors and non-200s come back as ``error`` too, so callers have exactly one
    branch to write. ``params`` are passed through (max_tokens, temperature,
    response_format, reasoning); ``provider`` is not one of them, see PROVIDER_POLICY.

    A call that asked for ``NO_REASONING`` and still spent its whole budget thinking is
    asked once more (`_reasoned_though_off`).
    """
    if not settings.openrouter_api_key:
        return None, "FINVIEW_OPENROUTER_API_KEY not configured."
    content, error, body = _post(messages, context, timeout, params)
    if content is None and _reasoned_though_off(body, params):
        first = _served_by(body)
        retry = {**params, "reasoning": REASONING_DISABLED}
        content, error, body = _post(messages, context, timeout, retry)
        logger.warning(
            "%s: [reasoning-retry] first answer by %s, second by %s: %s",
            context,
            first,
            _served_by(body),
            "answered" if content is not None else "failed too",
        )
    return content, error


def _post(
    messages: list[dict], context: str, timeout: float, params: dict
) -> tuple[str | None, str | None, dict | None]:
    """One request. ``(content, error, body)``; ``body`` is the parsed 200, else None."""
    try:
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": messages,
                **params,
                "provider": dict(PROVIDER_POLICY),
            },
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("%s: OpenRouter request failed — %s: %s", context, type(exc).__name__, exc)
        return None, f"{type(exc).__name__}: {exc}", None
    if resp.status_code != 200:
        body = str(resp.text)[:300]
        logger.warning("%s: OpenRouter HTTP %s — %s", context, resp.status_code, body)
        return None, f"OpenRouter HTTP {resp.status_code}: {body}", None
    try:
        body = resp.json()
    except ValueError:
        logger.warning("%s: OpenRouter 200 with a non-JSON body", context)
        return None, "The model's response was not JSON", None
    content, error = extract_content(body, context)
    return content, error, body if isinstance(body, dict) else None


def _reasoned_though_off(body: dict | None, params: dict) -> bool:
    """True when ``reasoning: none`` was sent and the 200 shows the model reasoned anyway.

    Production, 2026-10-17 to 2026-11-05: seven answers (the AI reader's AXA and AENA twice,
    the options agent four times) came back empty with ``finish_reason: "length"`` and
    ``reasoning_tokens`` equal to ``completion_tokens``, from revisions that sent
    ``{"effort": "none"}``. The setting is honoured nearly always (empty answers fell from
    85 in ten days to about five in sixteen once it was sent), and the catalogue lists
    ``reasoning`` on every endpoint of the model, so some route ignores it only now and then.
    OpenRouter picks the route per request, and the failed call is billed in full, so one
    more request with the other documented spelling is cheaper than failing until the next
    cycle: the AI reader would retry AENA every night, and an options chat would answer 502.
    Not verified live (no key outside Cloud Run): `[reasoning-retry]` in the logs says whether
    the second request answers, and which provider served each.
    """
    if not body or params.get("reasoning") != NO_REASONING:
        return False
    try:
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") or {}
        spent = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        return choice.get("finish_reason") == "length" and spent > 0
    except Exception:
        return False


def _served_by(body: dict | None) -> str:
    return str((body or {}).get("provider") or "unknown")


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
            "%s: 200 with empty content — finish_reason=%r message_keys=%s usage=%s "
            "provider=%s model=%s",
            context,
            finish_reason,
            sorted(message),
            body.get("usage"),
            body.get("provider"),
            body.get("model"),
        )
        # finish_reason is the single most useful field for diagnosing this:
        # "length" means the budget ran out, anything else usually means the
        # provider put the answer in a field we do not read.
        return None, f"The model returned no text (finish_reason={finish_reason!r})"
    except Exception:
        logger.warning("%s: unparseable response envelope", context, exc_info=True)
        return None, "The model's response could not be parsed"
