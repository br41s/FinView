"""Geo notifications — reuse FinView's notification_service channels.

Fire-and-forget: a notification failure must never break the pipeline cycle.
"""

import logging

from backend.models import GeoSignal
from backend.services.notification_service import send_ntfy, send_telegram

logger = logging.getLogger(__name__)


def notify_signal(signal: GeoSignal, importance: int) -> None:
    try:
        tickers = ", ".join(t.symbol for t in signal.tickers) or "—"
        title = f"🌍 Geo: {signal.headline[:80]}"
        body = (
            f"{signal.direction.upper()} · importance {importance} · "
            f"risk {signal.risk_score}/10\nTickers: {tickers}"
        )
        send_ntfy(title, body, priority="high" if importance >= 80 else "default",
                  tags="earth_americas")
        send_telegram(f"*{title}*\n{body}")
    except Exception:
        logger.warning("geo notification failed for signal %s", signal.id, exc_info=True)
