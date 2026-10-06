"""Notification service — ntfy.sh push + email digest + Telegram.

Channels:
- ntfy.sh  → iPhone/Android push (always available if topic configured)
- Email    → Gmail SMTP digest
- Telegram → Bot API text messages (premium spikes + HIGH alerts)
"""

import json
import logging
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import OptionsAlertNotification

logger = logging.getLogger(__name__)

# Telegram rejects any message over 4096 characters outright.
_TELEGRAM_MAX_CHARS = 4096

# Gmail's SMTP handshake has no default deadline in smtplib, so an unreachable
# server holds the socket open until the platform's TCP timeout. The geo cron is
# synchronous inside the Cloud Run request, so that stall is charged straight to
# the 1800 s request deadline.
_SMTP_TIMEOUT = 15

# Exactly one retry, and only for the transient classes. A second failure is a
# real one, and the geo/options cycles are synchronous — burning the request on
# a retry ladder costs more than the alert is worth.
_RETRY_BACKOFF_SECONDS = 1.0


def _is_retryable(exc: BaseException) -> bool:
    """5xx / transport timeout — transient, worth exactly one retry.

    Not 429: Telegram's rate limit carries a retry_after of 30–60 s and the bot
    token is shared with the options agent, so a retry 1 s later extends the
    ban for both. A geo signal that misses keeps notified_at NULL and is
    re-selected next cycle instead.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return 500 <= exc.code < 600
    if isinstance(exc, TimeoutError):  # socket.timeout is TimeoutError on 3.10+
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, TimeoutError)
    return False


def send_ntfy(title: str, message: str, priority: str = "high", tags: str = "chart_with_upwards_trend") -> bool:
    """Send push notification via ntfy.sh."""
    topic = settings.ntfy_topic
    if not topic:
        logger.warning("ntfy not configured (FINVIEW_NTFY_TOPIC unset) — push not sent")
        return False
    url = f"https://ntfy.sh/{topic}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": urllib.parse.quote(title, safe=" "),
            "Priority": priority,
            "Tags": tags,
        },
        method="POST",
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            if attempt == 0 and _is_retryable(exc):
                logger.warning("ntfy send failed (%s) — retrying once", exc)
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            logger.exception("ntfy send failed")
            return False
    return False


def send_email(subject: str, html_body: str) -> bool:
    """Send email via Gmail SMTP."""
    sender = settings.notify_email_from
    password = settings.notify_email_password
    recipient = settings.notify_email_to
    if not all([sender, password, recipient]):
        logger.warning(
            "email not configured (FINVIEW_NOTIFY_EMAIL_FROM/TO/PASSWORD) — digest not sent"
        )
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=_SMTP_TIMEOUT) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        return True
    except Exception:
        logger.exception("Email send failed")
        return False


def send_telegram(text: str, parse_mode: str | None = "Markdown", include_thread: bool = True) -> bool:
    """Send a message via Telegram Bot API.

    Uses only stdlib urllib — no python-telegram-bot dependency needed.
    Returns True on success, False if unconfigured or on error.

    `parse_mode` and `include_thread` are both dropped on the 400 retry: the two
    optional niceties (Markdown formatting, forum-topic routing) are exactly what
    a 400 rejects, and delivering the alert plainly to the main chat beats not
    delivering it. A stale thread_id (e.g. left over after moving from a forum
    group to a private DM) thus self-heals to "delivered".
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        logger.warning(
            "Telegram not configured (FINVIEW_TELEGRAM_BOT_TOKEN/CHAT_ID) — message not sent"
        )
        return False
    # Telegram hard-caps a message at 4096 chars and rejects the whole thing with
    # "message is too long" — a 400 that the plain-text retry can't fix, because
    # it's about length, not formatting. HIGH-gating + dedup keep messages small
    # in normal use, but a cold-start burst (empty dedup + a market-wide event)
    # can still pile up. Truncate so a big burst degrades to "delivered, trimmed"
    # rather than "silently dropped".
    if len(text) > _TELEGRAM_MAX_CHARS:
        text = text[: _TELEGRAM_MAX_CHARS - 20].rstrip() + "\n… (recortado)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body: dict = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        body["parse_mode"] = parse_mode
    # Forum groups: route into the app's topic instead of General. Only valid
    # for forum supergroups — a private chat has no threads, so a stray
    # thread_id there is a 400 ("message thread not found").
    thread_id = settings.telegram_thread_id.strip()
    if include_thread and thread_id.isdigit():
        body["message_thread_id"] = int(thread_id)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(2):
        try:
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
            # A 400 is almost always one of the two optional extras: Markdown
            # formatting (a stray `*`/`_` in alert text) or forum-topic routing (a
            # thread_id that doesn't exist for this chat). Retry once stripping both
            # — the content matters more than the formatting or the topic. Guarded by
            # `parse_mode` so the retry can't recurse.
            if e.code == 400 and parse_mode:
                logger.info("Telegram: retrying as plain text, no thread")
                return send_telegram(text, parse_mode=None, include_thread=False)
            if attempt == 0 and _is_retryable(e):
                logger.warning("Telegram: HTTP %s is transient — retrying once", e.code)
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            return False
        except Exception as exc:
            if attempt == 0 and _is_retryable(exc):
                logger.warning("Telegram send failed (%s) — retrying once", exc)
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            logger.exception("Telegram send failed")
            return False
    return False


# Cross-cycle dedup. An alert that stays true (HIGH_PUT_CALL_RATIO on TEF.MC for
# three hours) is one alert, not one every cycle. Keyed on identity — ticker +
# type, plus the contract for per-contract spikes — never on the message, whose
# numbers drift each cycle and would defeat the dedup. Persisted per user: prod
# scales to zero between cron ticks, so each cycle starts on a fresh instance and
# the in-memory dict this used to be was always empty — every still-true HIGH
# alert was re-pushed every cycle (ntfy answered 429).
_NOTIFY_TTL = timedelta(hours=6)  # re-notify a still-true alert at most once per 6h


def _alert_key(a: dict) -> str:
    parts = [a.get("ticker", ""), a.get("type", "")]
    if a.get("_strike") is not None:  # spikes are per-contract
        parts += [str(a.get("_strike")), str(a.get("_option_type", ""))]
    return "|".join(parts)


def filter_new_alerts(db: Session, user_id: int, alerts: list[dict]) -> list[dict]:
    """Return only the alerts not already notified within the TTL window.

    Marks the returned ones as notified in ``db``; the caller commits.
    """
    if not alerts:
        return []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    keys = {_alert_key(a) for a in alerts}
    rows = {
        r.alert_key: r
        for r in db.query(OptionsAlertNotification).filter(
            OptionsAlertNotification.user_id == user_id,
            OptionsAlertNotification.alert_key.in_(keys),
        )
    }
    fresh = []
    for a in alerts:
        key = _alert_key(a)
        row = rows.get(key)
        if row is not None and now - row.notified_at < _NOTIFY_TTL:
            continue  # already sent this window, or earlier in this same batch
        if row is None:
            row = OptionsAlertNotification(user_id=user_id, alert_key=key, notified_at=now)
            db.add(row)
            rows[key] = row
        else:
            row.notified_at = now
        fresh.append(a)
    return fresh


def _telegram_line(a: dict) -> str:
    if a.get("type") == "PREMIUM_SPIKE":
        return f"⚡ *{a['ticker']}* — spike de prima\n`{a['message']}`"
    return f"🔴 *{a['ticker']}* — {a['type']}\n`{a['message']}`"


def notify_alerts(db: Session, user_id: int, alerts: list[dict]) -> None:
    """Notify on HIGH alerts only, and only those not already pushed.

    MEDIUM/LOW still persist to the Monitor tab — that's for browsing, not for
    pushing. Gating to HIGH plus the cross-cycle dedup is what turns this from
    ~64 emails a day of ~100 rows each into a message only when something new and
    actionable actually fires. All channels agree now: what notifies is HIGH and
    fresh, nothing else.
    """
    if not alerts:
        return
    high = [a for a in alerts if a.get("severity") == "HIGH"]
    fresh = filter_new_alerts(db, user_id, high)
    if not fresh:
        return
    db.commit()

    title = f"⚡ {len(fresh)} alerta(s) HIGH"
    body = "\n".join(f"🔴 [{a['ticker']}] {a['message']}" for a in fresh)

    send_ntfy(title, body, priority="high", tags="warning")
    send_telegram(f"🚨 *{title}*\n\n" + "\n".join(_telegram_line(a) for a in fresh))

    html_rows = "".join(
        f"<tr><td>{a['ticker']}</td><td>{a['type']}</td><td>{a['message']}</td></tr>"
        for a in fresh
    )
    html = f"""
    <h2>📊 {len(fresh)} alerta(s) HIGH de opciones</h2>
    <table border="1" cellpadding="4" cellspacing="0">
    <tr><th>Ticker</th><th>Tipo</th><th>Mensaje</th></tr>
    {html_rows}
    </table>
    """
    send_email(title, html)
