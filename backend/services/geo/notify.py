"""Geo notifications — reuse FinView's notification_service channels.

Fire-and-forget for the *cycle*, not for the record: a notification failure must
never break the pipeline, but it must never be invisible either. Prod ran seven
days with zero notification log lines and no way to tell "sent" from "swallowed",
because all three sender return values were discarded and one `try` wrapped the
whole fan-out (a Telegram exception silently dropped email). Each channel now
gets its own `try`, its return value is kept, and the caller learns which
channels actually delivered.
"""

import logging
import time

from backend.models import GeoSignal
from backend.services.notification_service import send_email, send_ntfy, send_telegram

logger = logging.getLogger(__name__)

# Telegram messages use parse_mode=Markdown; an unescaped *_`[ in an external
# news headline makes the Bot API reject the whole message with a 400.
_MD_SPECIALS = "*_`["

CHANNELS = ("ntfy", "telegram", "email")
# One delivery per event, not per user. The cron runs every user's cycle in one
# request against one set of channel credentials (there are no per-user
# channels yet), so three accounts meant three identical pushes to one phone —
# which is exactly what happened on the first cycle the gate ever opened.
# Process-local, like every geo cache: it only has to span one cron request.
_DELIVERED: dict[str, tuple[float, dict[str, bool]]] = {}
_DELIVERED_TTL = 6 * 3600


def _md_escape(text: str) -> str:
    for ch in _MD_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


def _ev(value) -> str:
    """The `.value` of an enum member, or the raw string.

    `direction` is a `_geo_enum` column: it reads back as a `GeoDirection`
    *member* once the session has refreshed the row — and the orchestrator
    commits the persist phase before it notifies. So `signal.direction.upper()`
    raised `AttributeError` on every notification of a committed signal, which
    the old catch-all swallowed as a generic "notification failed".
    """
    return value.value if hasattr(value, "value") else str(value)


def notify_signal(
    signal: GeoSignal, importance: int, skip: frozenset[str] | set[str] = frozenset()
) -> dict[str, bool]:
    """Push one signal to every channel; return per-channel delivery.

    The returned dict always carries all three keys, so `any(...)` answers
    "did this reach anyone" and `False` for a channel means either unconfigured,
    rejected, raised or skipped — the log line says which. `skip` is the
    orchestrator's per-cycle breaker: a channel that already failed this cycle
    is not retried on every remaining signal.
    """
    delivered = dict.fromkeys(CHANNELS, False)
    key = f"{signal.source}:{signal.external_id}"
    prior = _DELIVERED.get(key)
    if prior and time.time() - prior[0] < _DELIVERED_TTL and any(prior[1].values()):
        logger.info(
            "geo notification: signal %s already delivered for another user (%s)", signal.id, key
        )
        return dict(prior[1])
    try:
        tickers = ", ".join(t.symbol for t in signal.tickers) or "—"
        headline = signal.headline[:80]
        direction = _ev(signal.direction).upper()
        title = f"🌍 Geo: {headline}"
        body = (
            f"{direction} · importance {importance} · "
            f"risk {signal.risk_score}/10\nTickers: {tickers}"
        )
        telegram_text = (
            f"*🌍 Geo señal · {direction}*\n"
            f"{_md_escape(headline)}\n"
            f"Importance {importance} · risk {signal.risk_score}/10\n"
            f"Tickers: {_md_escape(tickers)}"
        )
        rows = "".join(
            f"<tr><td>{t.symbol}</td><td>{_ev(t.direction)}</td></tr>"
            for t in signal.tickers
        )
        html = (
            f"<h2>🌍 {headline}</h2>"
            f"<p>{direction} · importance {importance} · "
            f"risk {signal.risk_score}/10 · {signal.location or ''}</p>"
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>Ticker</th><th>Direction</th></tr>{rows}</table>"
        )
    except Exception:
        logger.warning(
            "geo notification: could not build payload for signal %s", signal.id, exc_info=True
        )
        return delivered

    senders = (
        ("ntfy", lambda: send_ntfy(
            title, body,
            priority="high" if importance >= 80 else "default",
            tags="earth_americas",
        )),
        ("telegram", lambda: send_telegram(telegram_text)),
        ("email", lambda: send_email(title, html)),
    )
    # One try per channel: a Telegram exception used to take email down with it,
    # producing a partial fan-out with no record of which half arrived.
    for channel, send in senders:
        if channel in skip:
            continue
        try:
            sent = bool(send())
        except Exception:
            logger.warning(
                "geo notification: channel %s raised for signal %s",
                channel, signal.id, exc_info=True,
            )
            continue
        delivered[channel] = sent
        if not sent:
            logger.warning(
                "geo notification: channel %s did not deliver signal %s "
                "(unconfigured or rejected)",
                channel, signal.id,
            )
    ok = [c for c in CHANNELS if delivered[c]]
    failed = [c for c in CHANNELS if not delivered[c]]
    if ok:
        _DELIVERED[key] = (time.time(), dict(delivered))
    logger.info(
        "geo notification: signal %s (importance %s) delivered via %s, failed %s",
        signal.id, importance, ",".join(ok) or "none", ",".join(failed) or "none",
    )
    return delivered
