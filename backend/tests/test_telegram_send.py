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


def test_non_400_errors_do_not_retry():
    err = _http_error(429, "Too Many Requests")
    with patch.object(notification_service.urllib.request, "urlopen", side_effect=err) as op:
        assert send_telegram("hola") is False
    assert op.call_count == 1


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
