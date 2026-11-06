"""Tests for the shared OpenRouter envelope parser.

Anything that talks to an external service gets tests for the ugly paths, not
just the happy one. A 200 means the server answered — nothing more.
"""

import logging
from unittest.mock import MagicMock, patch

from backend.services import llm_envelope
from backend.services.llm_envelope import chat, extract_content

CTX = "test"


def test_reads_the_message_content():
    body = {"choices": [{"message": {"content": "## 1. Resumen\nAll clear."}}]}

    content, error = extract_content(body, CTX)

    assert content == "## 1. Resumen\nAll clear."
    assert error is None


def test_null_content_yields_an_error_not_silence():
    """The regression: this used to return no text *and* no error.

    options_agent surfaced that as (None, None), which the UI could not tell
    apart from "AI not configured".
    """
    body = {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}

    content, error = extract_content(body, CTX)

    assert content is None
    assert error is not None
    # finish_reason is the field that explains *why*, so it must reach the user.
    assert "length" in error


def test_whitespace_only_content_counts_as_empty():
    body = {"choices": [{"message": {"content": "   \n\t "}}]}

    content, error = extract_content(body, CTX)

    assert content is None
    assert error is not None


def test_missing_choices_is_reported():
    content, error = extract_content({"usage": {"total_tokens": 12}}, CTX)

    assert content is None
    assert error == "The model returned no choices"


def test_empty_choices_list_is_reported():
    content, error = extract_content({"choices": []}, CTX)

    assert content is None
    assert error == "The model returned no choices"


def test_missing_message_key_is_reported():
    """Some providers return a choice without a message at all."""
    content, error = extract_content({"choices": [{"finish_reason": "stop"}]}, CTX)

    assert content is None
    assert error is not None


def test_a_hostile_envelope_never_raises():
    """Whatever comes back, the caller gets a tuple — never an exception."""
    for body in ({"choices": "not-a-list"}, {"choices": [None]}, {"choices": [[]]}):
        content, error = extract_content(body, CTX)

        assert content is None
        assert error is not None


def test_non_string_content_is_rejected():
    """A structured content block is not text we can render."""
    body = {"choices": [{"message": {"content": [{"type": "text", "text": "hi"}]}}]}

    content, error = extract_content(body, CTX)

    assert content is None
    assert error is not None


# --- the request itself -----------------------------------------------------


def _ok_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": "hola"}, "finish_reason": "stop"}]}
    return resp


def _sent_json(**params):
    with patch.object(llm_envelope.settings, "openrouter_api_key", "test-key"), \
         patch.object(llm_envelope.httpx, "post", return_value=_ok_response()) as post:
        content, error = chat([{"role": "user", "content": "hi"}], context=CTX, **params)
    assert (content, error) == ("hola", None)
    return post.call_args.kwargs["json"]


def test_every_request_asks_for_providers_that_do_not_keep_or_train_on_the_prompt():
    assert _sent_json()["provider"] == {"data_collection": "deny"}
    assert _sent_json(max_tokens=50, reasoning=llm_envelope.NO_REASONING)["provider"] == {
        "data_collection": "deny"
    }


def test_a_caller_cannot_weaken_the_policy():
    assert _sent_json(provider={"data_collection": "allow"})["provider"] == {"data_collection": "deny"}


def test_the_other_params_still_go_through():
    body = _sent_json(max_tokens=50, temperature=0.2)
    assert body["model"] == llm_envelope.settings.openrouter_model
    assert (body["max_tokens"], body["temperature"]) == (50, 0.2)


def test_the_shared_policy_constant_is_not_mutated_by_a_call():
    _sent_json()
    assert llm_envelope.PROVIDER_POLICY == {"data_collection": "deny"}


# ── reasoning asked off and spent anyway ─────────────────────────────
#
# Production, 2026-10-17 to 2026-11-05: AXA and AENA (twice) in the AI reader and four
# options-agent calls came back 200, empty, `finish_reason: "length"`, with
# `reasoning_tokens == completion_tokens`, from revisions that sent {"effort": "none"}.
# AENA failed the same way the next night: nothing is cached on a failure, so it would
# have been retried, and lost, every night.


def _reasoned_away(provider="SomeHost"):
    return {
        "provider": provider,
        "model": "deepseek/deepseek-v4.1-flash",
        "choices": [
            {
                "message": {"content": None, "reasoning": "Let me think…", "reasoning_details": []},
                "finish_reason": "length",
            }
        ],
        "usage": {
            "completion_tokens": 2000,
            "completion_tokens_details": {"reasoning_tokens": 2000},
        },
    }


def _answered(provider="OtherHost"):
    return {
        "provider": provider,
        "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
    }


def _posts(bodies):
    """Patch httpx.post to answer 200 with each body in turn; returns the bodies sent."""
    sent, queue = [], list(bodies)

    def fake_post(*a, **k):
        sent.append(k["json"])
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = queue.pop(0)
        return resp

    return sent, patch.object(llm_envelope.httpx, "post", side_effect=fake_post)


def _chat_off(**params):
    return chat(
        [{"role": "user", "content": "hi"}],
        context=CTX,
        reasoning=llm_envelope.NO_REASONING,
        max_tokens=2000,
        **params,
    )


def test_reasoning_asked_off_and_spent_anyway_is_asked_once_more_the_other_way(caplog):
    sent, post = _posts([_reasoned_away(), _answered()])
    with (
        patch.object(llm_envelope.settings, "openrouter_api_key", "k"),
        post,
        caplog.at_level(logging.WARNING),
    ):
        content, error = _chat_off()

    assert (content, error) == ('{"ok": true}', None)
    assert [r["reasoning"] for r in sent] == [
        llm_envelope.NO_REASONING,
        llm_envelope.REASONING_DISABLED,
    ]
    # Same request otherwise: same budget, same policy.
    assert sent[0]["max_tokens"] == sent[1]["max_tokens"] == 2000
    assert sent[1]["provider"] == {"data_collection": "deny"}
    # The log says which route ignored the setting and whether the second answered.
    assert "[reasoning-retry] first answer by SomeHost, second by OtherHost: answered" in caplog.text


def test_when_the_second_try_fails_too_the_error_is_the_second_ones_and_it_stops_there(caplog):
    sent, post = _posts([_reasoned_away("A"), _reasoned_away("B"), _answered()])
    with patch.object(llm_envelope.settings, "openrouter_api_key", "k"), post:
        content, error = _chat_off()

    assert content is None and "length" in error
    assert len(sent) == 2  # one retry, never a loop
    assert "first answer by A, second by B: failed too" in caplog.text


def test_the_empty_answer_logs_the_route_and_model_that_gave_it(caplog):
    with caplog.at_level(logging.WARNING):
        extract_content(_reasoned_away("SomeHost"), CTX)
    assert "provider=SomeHost model=deepseek/deepseek-v4.1-flash" in caplog.text


def test_a_call_that_never_asked_for_reasoning_off_is_not_retried():
    sent, post = _posts([_reasoned_away(), _answered()])
    with patch.object(llm_envelope.settings, "openrouter_api_key", "k"), post:
        content, _ = chat([{"role": "user", "content": "hi"}], context=CTX, max_tokens=2000)
    assert content is None and len(sent) == 1  # the zone scorer keeps reasoning on, on purpose


def test_a_plain_truncation_is_not_a_reasoning_failure():
    """`length` with no reasoning tokens is an answer that was too long: asking again
    the same way cannot help."""
    body = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"completion_tokens": 2000, "completion_tokens_details": {"reasoning_tokens": 0}}}
    sent, post = _posts([body, _answered()])
    with patch.object(llm_envelope.settings, "openrouter_api_key", "k"), post:
        content, _ = _chat_off()
    assert content is None and len(sent) == 1


def test_an_http_error_is_not_retried():
    sent = []

    def fake_post(*a, **k):
        sent.append(k["json"])
        resp = MagicMock()
        resp.status_code = 502
        resp.text = "bad gateway"
        return resp

    with patch.object(llm_envelope.settings, "openrouter_api_key", "k"), \
         patch.object(llm_envelope.httpx, "post", side_effect=fake_post):
        content, error = _chat_off()
    assert content is None and "502" in error and len(sent) == 1


def test_a_malformed_usage_block_never_raises_out_of_the_check():
    body = _reasoned_away()
    body["usage"] = {"completion_tokens_details": "n/a"}
    sent, post = _posts([body])
    with patch.object(llm_envelope.settings, "openrouter_api_key", "k"), post:
        content, error = _chat_off()
    assert content is None and error and len(sent) == 1
