"""Tests for olla.context_trim (REPL-03: tiktoken counting, trim decision, summarization)."""

import requests

from olla import context_trim
from olla.context_trim import (
    FALLBACK_CHARS_PER_TOKEN,
    count_tokens_or_fallback,
    get_encoder,
    should_trim,
    summarize_and_trim,
    warm_encoder,
)


class _FakeEncoder:
    """Deterministic stand-in for a real tiktoken encoder: 1 token per char."""

    def encode(self, text):
        return list(text)


def setup_function(_function):
    context_trim._encoder_cache.clear()


def teardown_function(_function):
    context_trim._encoder_cache.clear()


def test_get_encoder_success_caches_and_returns_encoder(mocker):
    mock_get_encoding = mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    encoder = get_encoder()
    assert encoder is not None
    encoder_again = get_encoder()
    assert encoder_again is encoder
    mock_get_encoding.assert_called_once()


def test_get_encoder_request_exception_falls_back_to_none(mocker, capsys):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding",
        side_effect=requests.exceptions.RequestException("offline"),
    )
    encoder = get_encoder()
    assert encoder is None
    captured = capsys.readouterr()
    assert "token counting unavailable" in captured.out


def test_get_encoder_caches_failure_and_does_not_retry(mocker):
    mock_get_encoding = mocker.patch(
        "olla.context_trim.tiktoken.get_encoding",
        side_effect=requests.exceptions.RequestException("offline"),
    )
    assert get_encoder() is None
    assert get_encoder() is None
    assert mock_get_encoding.call_count == 1


def test_count_tokens_or_fallback_uses_real_encoder(mocker):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    messages = [{"role": "user", "content": "hello"}]
    assert count_tokens_or_fallback(messages) == 5


def test_count_tokens_or_fallback_falls_back_to_char_proxy_on_request_exception(mocker):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding",
        side_effect=requests.exceptions.RequestException("offline"),
    )
    messages = [{"role": "user", "content": "x" * 40}]
    assert count_tokens_or_fallback(messages) == 40 // FALLBACK_CHARS_PER_TOKEN


def test_should_trim_false_for_empty_messages(mocker):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    assert should_trim([], budget=100) is False


def test_should_trim_false_below_threshold(mocker):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    messages = [{"role": "user", "content": "x" * 10}]
    assert should_trim(messages, budget=1000) is False


def test_should_trim_true_at_or_above_threshold(mocker):
    mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    messages = [{"role": "user", "content": "x" * 90}]
    assert should_trim(messages, budget=100, threshold_ratio=0.85) is True


def test_summarize_and_trim_replaces_middle_slice_and_protects_head_and_tail(mocker):
    mock_provider = mocker.MagicMock()
    mock_provider.chat.return_value = "Summary of earlier turns."
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "turn1"},
        {"role": "assistant", "content": "resp1"},
        {"role": "user", "content": "current turn"},
    ]
    system_before = dict(messages[0])
    tail_before = [dict(m) for m in messages[3:]]

    summarize_and_trim(
        messages, protected_from_index=3, provider=mock_provider, model="test-model"
    )

    assert messages[0] == system_before
    assert messages[2:] == tail_before
    assert len(messages) == 3
    assert "<untrusted_summary_digest>" in messages[1]["content"]
    assert "</untrusted_summary_digest>" in messages[1]["content"]
    assert "Summary of earlier turns." in messages[1]["content"]
    assert messages[1]["role"] == "tool"
    mock_provider.chat.assert_called_once()


def test_summarize_and_trim_noop_when_in_progress_turn_is_entire_trimmable_range():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "current"},
    ]
    original = [dict(m) for m in messages]

    class _ExplodingProvider:
        def chat(self, *args, **kwargs):
            raise AssertionError("provider.chat must not be called on a no-op trim")

    summarize_and_trim(
        messages, protected_from_index=1, provider=_ExplodingProvider(), model="m"
    )
    assert messages == original


def test_summarize_and_trim_provider_failure_falls_back_to_placeholder_digest(mocker):
    mock_provider = mocker.MagicMock()
    mock_provider.chat.side_effect = RuntimeError("boom")
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "turn1"},
        {"role": "user", "content": "current"},
    ]

    summarize_and_trim(
        messages, protected_from_index=2, provider=mock_provider, model="m"
    )

    assert len(messages) == 2
    assert "<untrusted_summary_digest>" in messages[1]["content"]
    assert "summarization unavailable" in messages[1]["content"]


def test_warm_encoder_prints_preparing_message_and_warms_cache(mocker, capsys):
    mock_get_encoding = mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    warm_encoder()
    captured = capsys.readouterr()
    assert "preparing token counter" in captured.out
    mock_get_encoding.assert_called_once()


def test_warm_encoder_is_idempotent_via_cache(mocker):
    mock_get_encoding = mocker.patch(
        "olla.context_trim.tiktoken.get_encoding", return_value=_FakeEncoder()
    )
    warm_encoder()
    warm_encoder()
    assert mock_get_encoding.call_count == 1
