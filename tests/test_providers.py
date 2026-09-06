"""Unit tests for olla provider layer."""

from unittest.mock import MagicMock, patch

import pytest

from olla.providers import (
    OllamaProvider,
    OpenAICompatProvider,
    ProviderError,
    StreamChunk,
    get_provider,
    stream_with_stop_buffer,
)


def test_default_routing_ollama():
    """Unprefixed model names route to OllamaProvider."""
    provider, model_id = get_provider("qwen2.5:3b")
    assert isinstance(provider, OllamaProvider)
    assert model_id == "qwen2.5:3b"
    assert provider.model == "qwen2.5:3b"


def test_ollama_prefix_routing():
    """Models with 'ollama/' prefix route to OllamaProvider with prefix stripped."""
    provider, model_id = get_provider("ollama/llama3.2:1b")
    assert isinstance(provider, OllamaProvider)
    assert model_id == "llama3.2:1b"
    assert provider.model == "llama3.2:1b"


def test_openrouter_routing(monkeypatch):
    """Models with 'openrouter/' prefix route to OpenAICompatProvider."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    provider, model_id = get_provider("openrouter/meta-llama/llama-3.1-8b")
    assert isinstance(provider, OpenAICompatProvider)
    assert model_id == "meta-llama/llama-3.1-8b"
    assert provider.model == "meta-llama/llama-3.1-8b"
    assert provider.api_key == "sk-or-test-key"
    assert provider.base_url == "https://openrouter.ai/api/v1"


def test_openai_routing(monkeypatch):
    """Models with 'openai/' prefix route to OpenAICompatProvider."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    provider, model_id = get_provider("openai/gpt-4o-mini")
    assert isinstance(provider, OpenAICompatProvider)
    assert model_id == "gpt-4o-mini"
    assert provider.model == "gpt-4o-mini"
    assert provider.api_key == "sk-openai-test-key"
    assert provider.base_url == "https://api.openai.com/v1"


def test_missing_api_key_raises_provider_error(monkeypatch):
    """Missing API key for remote models raises ProviderError immediately."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="Missing API key"):
        get_provider("openrouter/meta-llama/llama-3.1-8b")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="Missing API key"):
        get_provider("openai/gpt-4o-mini")


def test_stream_stop_buffer_filters_stop_sequence():
    """Verify stop sequence is buffered and never emitted, halting stream."""
    chunks = [
        StreamChunk(text="hello <tool>run"),
        StreamChunk(text="_shell</tool><args>ls"),
        StreamChunk(text="</ar"),
        StreamChunk(text="gs>"),
        StreamChunk(text="extra text after stop"),
    ]
    result = list(stream_with_stop_buffer(iter(chunks), stop_seq="</args>"))
    result_text = "".join(c.text for c in result)

    assert result_text == "hello <tool>run_shell</tool><args>ls"
    assert "</args>" not in result_text
    assert "</ar" not in result_text
    assert "extra text" not in result_text


def test_stream_stop_buffer_normal_text_without_stop():
    """Normal text streams completely when stop sequence is absent."""
    chunks = [
        StreamChunk(text="Once upon a time "),
        StreamChunk(text="in a land far away, "),
        StreamChunk(text="there was a robot."),
    ]
    result = list(stream_with_stop_buffer(iter(chunks), stop_seq="</args>"))
    result_text = "".join(c.text for c in result)
    assert result_text == "Once upon a time in a land far away, there was a robot."


def test_stream_stop_buffer_preserves_thoughts():
    """Reasoning chunks pass through stream buffer."""
    chunks = [
        StreamChunk(text="thinking about life", is_thought=True),
        StreamChunk(text="Done thinking. <args>test", is_thought=False),
        StreamChunk(text="</args>", is_thought=False),
    ]
    result = list(stream_with_stop_buffer(iter(chunks), stop_seq="</args>"))
    assert len(result) == 2
    assert result[0].is_thought is True
    assert result[0].text == "thinking about life"
    assert result[1].is_thought is False
    assert result[1].text == "Done thinking. <args>test"


def test_retry_backoff_on_429():
    """OpenAICompatProvider retries on HTTP 429 and succeeds on subsequent try."""
    provider = OpenAICompatProvider(
        model="meta-llama/llama-3.1-8b",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        timeout=10.0,
    )

    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.read.return_value = b'{"error": "rate limited"}'

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "Hello world"}}]}',
        "data: [DONE]",
    ]

    context_429 = MagicMock()
    context_429.__enter__.return_value = mock_resp_429
    context_429.__exit__.return_value = None

    context_200 = MagicMock()
    context_200.__enter__.return_value = mock_resp_200
    context_200.__exit__.return_value = None

    with (
        patch("httpx.Client.stream", side_effect=[context_429, context_200]),
        patch("time.sleep") as mock_sleep,
    ):
        output = provider.chat([{"role": "user", "content": "hi"}])
        assert output == "Hello world"
        mock_sleep.assert_called_once_with(1.0)


def test_retry_exhaustion_raises_provider_error():
    """Exceeding max retries on 500 raises ProviderError."""
    provider = OpenAICompatProvider(
        model="meta-llama/llama-3.1-8b",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
    )

    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.read.return_value = b'{"error": "internal server error"}'

    context_500 = MagicMock()
    context_500.__enter__.return_value = mock_resp_500
    context_500.__exit__.return_value = None

    with (
        patch("httpx.Client.stream", return_value=context_500),
        patch("time.sleep"),
        pytest.raises(ProviderError, match="API error \\(500\\) after retries"),
    ):
        provider.chat([{"role": "user", "content": "hi"}])


def test_context_length_dynamic_lookup():
    """Provider queries /models endpoint for model context_length."""
    provider = OpenAICompatProvider(
        model="meta-llama/llama-3.1-8b",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "meta-llama/llama-3.1-8b", "context_length": 131072},
            {"id": "other/model", "context_length": 8192},
        ]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        context_len = provider.get_context_length()
        assert context_len == 131072


def test_inline_think_tag_parsing():
    """Model emitting <think>...</think> in content produces thought chunks."""
    provider = OpenAICompatProvider(
        model="deepseek/deepseek-r1",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "<think>pondering problem</think>final answer"}}]}',
        "data: [DONE]",
    ]

    context = MagicMock()
    context.__enter__.return_value = mock_resp
    context.__exit__.return_value = None

    with patch("httpx.Client.stream", return_value=context):
        chunks = list(provider.stream_chat([{"role": "user", "content": "hi"}]))
        assert len(chunks) == 2
        assert chunks[0].is_thought is True
        assert chunks[0].text == "pondering problem"
        assert chunks[1].is_thought is False
        assert chunks[1].text == "final answer"
