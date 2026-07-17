"""Notification service — ntfy.sh push + email digest + Telegram.

Channels:
- ntfy.sh  → iPhone/Android push (always available if topic configured)
- Email    → Gmail SMTP digest
- Telegram → Bot API text messages (premium spikes + HIGH alerts)
"""

import json
import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import settings

logger = logging.getLogger(__name__)


def send_ntfy(title: str, message: str, priority: str = "high", tags: str = "chart_with_upwards_trend") -> bool:
    """Send push notification via ntfy.sh."""
    topic = settings.ntfy_topic
    if not topic:
        return False
    try:
        url = f"https://ntfy.sh/{topic}"
        data = message.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Title": urllib.parse.quote(title, safe=" "),
                "Priority": priority,
                "Tags": tags,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        logger.exception("ntfy send failed")
        return False


def send_email(subject: str, html_body: str) -> bool:
    """Send email via Gmail SMTP."""
    sender = settings.notify_email_from
    password = settings.notify_email_password
    recipient = settings.notify_email_to
    if not all([sender, password, recipient]):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        return True
    except Exception:
        logger.exception("Email send failed")
        return False


def send_telegram(text: str, parse_mode: str | None = "Markdown") -> bool:
    """Send a message via Telegram Bot API.

    Uses only stdlib urllib — no python-telegram-bot dependency needed.
    Returns True on success, False if unconfigured or on error.
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            body["parse_mode"] = parse_mode
        # Forum groups: route into the app's topic instead of General.
        thread_id = settings.telegram_thread_id.strip()
        if thread_id.isdigit():
            body["message_thread_id"] = int(thread_id)
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        # Telegram explains every rejection in the response body
        # ({"ok": false, "error_code": 400, "description": "..."}). Logging only
        # the traceback throws that away and leaves a bare "400: Bad Request"
        # to guess at — which is exactly what happened in prod: spikes silently
        # never arrived and the logs couldn't say why.
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        logger.error("Telegram send failed: HTTP %s — %s", e.code, detail)
        # A 400 on a formatted message is usually the formatting: Telegram's
        # legacy Markdown rejects the whole message over one stray `*` or `_`,
        # and alert text carries tickers and free-form reasons we don't control.
        # The content matters more than the bold, so retry once as plain text.
        # Guarded by `parse_mode` so the retry can't recurse.
        if e.code == 400 and parse_mode:
            logger.info("Telegram: retrying without Markdown")
            return send_telegram(text, parse_mode=None)
        return False
    except Exception:
        logger.exception("Telegram send failed")
        return False


def notify_spike_telegram(spike_alerts: list[dict]) -> None:
    """Send premium spike alerts to Telegram.

    Each spike gets its own message to keep them actionable and scannable.
    Silently skips if Telegram is not configured.
    """
    for alert in spike_alerts:
        ticker = alert["ticker"]
        msg = alert["message"]
        # Structured Markdown message
        text = (
            f"⚡ *PREMIUM SPIKE DETECTADO*\n"
            f"*{ticker}*\n"
            f"`{msg}`"
        )
        send_telegram(text)


def notify_alerts(alerts: list[dict]) -> None:
    """Send aggregated alert notifications through configured channels."""
    if not alerts:
        return

    # Build summary
    high = [a for a in alerts if a.get("severity") == "HIGH"]

    title = f"⚡ {len(alerts)} Options Alerts"
    lines = []
    for a in alerts:
        icon = "🔴" if a["severity"] == "HIGH" else "🟡"
        lines.append(f"{icon} [{a['ticker']}] {a['message']}")
    body = "\n".join(lines)

    # Push notification (ntfy)
    if high:
        send_ntfy(title, body, priority="high", tags="warning")
    else:
        send_ntfy(title, body, priority="default", tags="chart_with_upwards_trend")

    # Telegram — HIGH alerts only (avoid noise)
    if high:
        high_lines = "\n".join(
            f"🔴 *{a['ticker']}* — {a['type']}\n`{a['message']}`" for a in high
        )
        send_telegram(f"🚨 *{len(high)} alertas HIGH*\n\n{high_lines}")

    # Email digest
    html_rows = "".join(
        f"<tr><td>{a['ticker']}</td><td>{a['type']}</td>"
        f"<td>{a['severity']}</td><td>{a['message']}</td></tr>"
        for a in alerts
    )
    html = f"""
    <h2>📊 Options Alerts</h2>
    <table border="1" cellpadding="4" cellspacing="0">
    <tr><th>Ticker</th><th>Type</th><th>Severity</th><th>Message</th></tr>
    {html_rows}
    </table>
    """
    send_email(title, html)
