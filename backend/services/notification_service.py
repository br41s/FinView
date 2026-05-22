"""Notification service — ntfy.sh push + email digest + Telegram.

Channels:
- ntfy.sh  → iPhone/Android push (always available if topic configured)
- Email    → Gmail SMTP digest
- Telegram → Bot API text messages (premium spikes + HIGH alerts)
"""

import json
import logging
import smtplib
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


def send_telegram(text: str) -> bool:
    """Send a Markdown-formatted message via Telegram Bot API.

    Uses only stdlib urllib — no python-telegram-bot dependency needed.
    Returns True on success, False if unconfigured or on error.
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
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
    medium = [a for a in alerts if a.get("severity") == "MEDIUM"]

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
