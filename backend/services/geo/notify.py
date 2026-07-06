"""Geo notifications — reuse FinView's notification_service channels.

Fire-and-forget: a notification failure must never break the pipeline cycle.
"""

import logging

from backend.models import GeoSignal
from backend.services.notification_service import send_email, send_ntfy, send_telegram

logger = logging.getLogger(__name__)

# Telegram messages use parse_mode=Markdown; an unescaped *_`[ in an external
# news headline makes the Bot API reject the whole message with a 400.
_MD_SPECIALS = "*_`["


def _md_escape(text: str) -> str:
    for ch in _MD_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


def notify_signal(signal: GeoSignal, importance: int) -> None:
    try:
        tickers = ", ".join(t.symbol for t in signal.tickers) or "—"
        headline = signal.headline[:80]
        title = f"🌍 Geo: {headline}"
        body = (
            f"{signal.direction.upper()} · importance {importance} · "
            f"risk {signal.risk_score}/10\nTickers: {tickers}"
        )
        send_ntfy(title, body, priority="high" if importance >= 80 else "default",
                  tags="earth_americas")
        send_telegram(
            f"*🌍 Geo señal · {signal.direction.upper()}*\n"
            f"{_md_escape(headline)}\n"
            f"Importance {importance} · risk {signal.risk_score}/10\n"
            f"Tickers: {_md_escape(tickers)}"
        )
        rows = "".join(
            f"<tr><td>{t.symbol}</td><td>{t.direction}</td></tr>" for t in signal.tickers
        )
        html = (
            f"<h2>🌍 {headline}</h2>"
            f"<p>{signal.direction.upper()} · importance {importance} · "
            f"risk {signal.risk_score}/10 · {signal.location or ''}</p>"
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>Ticker</th><th>Direction</th></tr>{rows}</table>"
        )
        send_email(title, html)
    except Exception:
        logger.warning("geo notification failed for signal %s", signal.id, exc_info=True)
