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
from datetime import datetime, timezone
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


# Cross-cycle dedup, by episode. An alert that stays true (HIGH_PUT_CALL_RATIO on
# TEF.MC for three days) is one notification, sent when it appears; it is sent
# again only after a cycle that analyzed its ticker without it (it cleared) and a
# later one where it is back. A row in options_alert_notifications is an active
# episode: inserted when notified, deleted when cleared.
#
# Keyed on identity — ticker + type, plus the contract for per-contract spikes —
# never on the message, whose numbers drift each cycle and would defeat the dedup.
# Persisted per user: prod scales to zero between cron ticks, so an in-memory
# record was always empty and every still-true alert was re-pushed every cycle.
#
# Clearing is by cycle, not by clock: the cron does not run overnight or at
# weekends, so "unseen for N hours" would end every episode each night. And only a
# ticker that was analyzed can clear — a failed fetch says nothing about the alert.


def _alert_key(a: dict) -> str:
    parts = [a.get("ticker", ""), a.get("type", "")]
    if a.get("_strike") is not None:  # spikes are per-contract
        parts += [str(a.get("_strike")), str(a.get("_option_type", ""))]
    return "|".join(parts)


def filter_new_alerts(
    db: Session, user_id: int, alerts: list[dict], analyzed_tickers: set[str]
) -> tuple[list[dict], int]:
    """Return the alerts that start an episode, and how many episodes cleared.

    ``alerts`` is this cycle's full HIGH set; ``analyzed_tickers`` every ticker
    the cycle got data for. Writes the episode changes to ``db``; the caller
    commits.
    """
    current: dict[str, dict] = {}
    for a in alerts:
        current.setdefault(_alert_key(a), a)  # the same alert twice is one
    active = {
        r.alert_key: r
        for r in db.query(OptionsAlertNotification).filter(
            OptionsAlertNotification.user_id == user_id
        )
    }
    cleared = 0
    for key, row in active.items():
        if key not in current and key.split("|", 1)[0] in analyzed_tickers:
            db.delete(row)
            cleared += 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh = []
    for key, a in current.items():
        if key in active:
            continue  # same episode, already notified
        db.add(OptionsAlertNotification(user_id=user_id, alert_key=key, notified_at=now))
        fresh.append(a)
    return fresh, cleared


# Telegram parses these as legacy Markdown, where an unbalanced * _ ` [ makes it
# reject the whole message. The line used to carry the alert type outside any
# entity, and HIGH_PUT_CALL_RATIO's three underscores opened an italic that never
# closed: every message with a P/C alert came back 400 and went out on the plain
# retry with its asterisks showing.
_MD_SPECIALS = "*_`["


def _md_escape(text: str) -> str:
    for ch in _MD_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


def _telegram_line(a: dict) -> str:
    """One line per alert. The type is left out: the message already names it."""
    icon = "⚡" if a.get("type") == "PREMIUM_SPIKE" else "🔴"
    return f"{icon} *{_md_escape(a['ticker'])}* · {_md_escape(a['message'])}"


def notify_alerts(
    db: Session, user_id: int, alerts: list[dict], analyzed_tickers: set[str]
) -> None:
    """Notify on HIGH alerts only, once per episode.

    Called every cycle, alerts or not: a cycle without an alert is what ends its
    episode. MEDIUM/LOW still persist to the Monitor tab — that's for browsing,
    not for pushing. All channels agree: what notifies is HIGH and new.
    """
    high = [a for a in alerts if a.get("severity") == "HIGH"]
    fresh, cleared = filter_new_alerts(db, user_id, high, analyzed_tickers)
    db.commit()
    # One line per cycle, sends or not: without it, "no HIGH fired" and "sent at
    # 07:00, held back at 07:30" read the same in the logs.
    logger.info(
        "options notify: user=%d high=%d sent=%d suppressed=%d cleared=%d %s",
        user_id, len(high), len(fresh), len(high) - len(fresh), cleared,
        [_alert_key(a) for a in fresh],
    )
    if not fresh:
        return

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
