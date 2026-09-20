"""Telegram sender: diagnose the rejection, then still deliver.

Regression origin: premium spikes never arrived. The Bot API returned 400 and
the handler logged only a traceback — the API's own explanation lives in the
response body and was being discarded, leaving "HTTP Error 400: Bad Request"
with nothing to act on.
"""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from backend.config import settings
from backend.services import notification_service
from backend.services.notification_service import send_telegram


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id", "123")
    monkeypatch.setattr(settings, "telegram_thread_id", "")


def _configure_thread(monkeypatch, thread="61"):
    monkeypatch.setattr(settings, "telegram_thread_id", thread)


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code: int, description: str):
    body = json.dumps({"ok": False, "error_code": code, "description": description})
    return urllib.error.HTTPError(
        "https://api.telegram.org/", code, "Bad Request", {}, io.BytesIO(body.encode())
    )


def test_happy_path():
    with patch.object(notification_service.urllib.request, "urlopen", return_value=_Resp()):
        assert send_telegram("hola") is True


def test_unconfigured_is_a_silent_no_op(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    with patch.object(notification_service.urllib.request, "urlopen") as op:
        assert send_telegram("hola") is False
    op.assert_not_called()


def test_400_logs_telegram_s_own_explanation(caplog):
    err = _http_error(400, "Bad Request: can't parse entities: unexpected end of the entity")
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err):
        send_telegram("*roto_")
    assert "can't parse entities" in caplog.text


def test_400_retries_once_without_markdown_and_delivers():
    """The content matters more than the bold. A formatting rejection must not
    lose the alert."""
    calls = []

    def fake(req, timeout=None):
        calls.append(json.loads(req.data))
        if len(calls) == 1:
            raise _http_error(400, "can't parse entities")
        return _Resp()

    with patch.object(notification_service.urllib.request, "urlopen", side_effect=fake):
        assert send_telegram("*roto_") is True
    assert len(calls) == 2
    assert calls[0]["parse_mode"] == "Markdown"
    assert "parse_mode" not in calls[1]  # plain-text retry
    assert calls[1]["text"] == "*roto_"  # same content, unmangled


def test_the_plain_text_retry_cannot_recurse():
    """A 400 that isn't about formatting must not loop."""
    err = _http_error(400, "chat not found")
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err) as op:
        assert send_telegram("hola", parse_mode=None) is False
    assert op.call_count == 1


def test_a_stale_thread_id_self_heals_on_the_retry(monkeypatch):
    """Real prod case: chat moved from a forum group to a private DM, but the old
    thread_id lingered → 'message thread not found'. The retry drops the thread
    and delivers to the main chat, which for a DM is the right place."""
    _configure_thread(monkeypatch, "61")
    calls = []

    def fake(req, timeout=None):
        calls.append(json.loads(req.data))
        if len(calls) == 1:
            raise _http_error(400, "message thread not found")
        return _Resp()

    with patch.object(notification_service.urllib.request, "urlopen", side_effect=fake):
        assert send_telegram("hola") is True
    assert len(calls) == 2
    assert calls[0]["message_thread_id"] == 61  # first try routes to the topic
    assert "message_thread_id" not in calls[1]  # retry drops it


def test_thread_id_is_included_on_the_first_attempt_when_set(monkeypatch):
    _configure_thread(monkeypatch, "61")
    with patch.object(notification_service.urllib.request, "urlopen", return_value=_Resp()) as op:
        send_telegram("hola")
    sent = json.loads(op.call_args.args[0].data)
    assert sent["message_thread_id"] == 61


def test_an_over_limit_message_is_truncated_not_rejected():
    """Telegram hard-rejects >4096 chars ('message is too long'), and the
    plain-text retry can't fix a length problem. Truncate so a big burst still
    delivers."""
    huge = "x" * 9000
    with patch.object(notification_service.urllib.request, "urlopen", return_value=_Resp()) as op:
        assert send_telegram(huge) is True
    sent = json.loads(op.call_args.args[0].data)
    assert len(sent["text"]) <= notification_service._TELEGRAM_MAX_CHARS
    assert sent["text"].endswith("(recortado)")


def test_a_message_at_the_limit_is_left_alone():
    exact = "y" * notification_service._TELEGRAM_MAX_CHARS
    with patch.object(notification_service.urllib.request, "urlopen", return_value=_Resp()) as op:
        send_telegram(exact)
    assert json.loads(op.call_args.args[0].data)["text"] == exact


def test_a_permanent_rejection_is_not_retried():
    """403 is an answer, not a hiccup — retrying it just doubles the latency."""
    err = _http_error(403, "Forbidden")
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err) as op:
        assert send_telegram("hola") is False
    assert op.call_count == 1


def test_a_rate_limit_is_retried_once(monkeypatch):
    """429/5xx/timeout are transient. This used to give up on the first one, so
    a momentary rate limit silently dropped the alert for good.

    Exactly once: the geo and options cycles are synchronous inside the Cloud Run
    request, so a retry ladder is charged to the request deadline.
    """
    monkeypatch.setattr(notification_service.time, "sleep", lambda s: None)
    err = _http_error(429, "Too Many Requests")
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err) as op:
        assert send_telegram("hola") is False
    assert op.call_count == 2


def test_an_unreadable_error_body_still_logs_the_code(caplog):
    err = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err):
        send_telegram("hola", parse_mode=None)
    assert "HTTP 400" in caplog.text


def test_network_failure_is_swallowed():
    with patch.object(
        notification_service.urllib.request, "urlopen", side_effect=OSError("no route")
    ):
        assert send_telegram("hola") is False
