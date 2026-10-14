"""Tests for the shared OpenRouter envelope parser.

Anything that talks to an external service gets tests for the ugly paths, not
just the happy one. A 200 means the server answered — nothing more.
"""

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
