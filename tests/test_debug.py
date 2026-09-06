"""Unit tests for olla debug logging infrastructure."""

from unittest.mock import MagicMock

import pytest

from olla.debug import debug_log, is_debug, mask_secret, set_debug
from olla.loop import run_loop


@pytest.fixture(autouse=True)
def reset_debug(monkeypatch):
    set_debug(False)
    monkeypatch.delenv("OLLA_DEBUG", raising=False)
    yield
    set_debug(False)


def test_is_debug_and_set_debug():
    assert is_debug() is False
    set_debug(True)
    assert is_debug() is True
    set_debug(False)
    assert is_debug() is False


def test_is_debug_from_env_var(monkeypatch):
    monkeypatch.setenv("OLLA_DEBUG", "1")
    assert is_debug() is True

    monkeypatch.setenv("OLLA_DEBUG", "true")
    assert is_debug() is True

    monkeypatch.setenv("OLLA_DEBUG", "0")
    assert is_debug() is False


def test_mask_secret():
    assert mask_secret(None) == "(none)"
    assert mask_secret("") == "(none)"
    assert mask_secret("short") == "sh...rt"
    assert mask_secret("sk-or-v1-abcdef1234567890") == "sk-or-v1...7890"


def test_debug_log_when_disabled(capsys):
    set_debug(False)
    debug_log("Secret title", {"data": 123})
    captured = capsys.readouterr()
    assert captured.out == ""


def test_debug_log_when_enabled(capsys):
    set_debug(True)
    debug_log("Test title", {"key": "val"})
    captured = capsys.readouterr()
    assert "[DEBUG]" in captured.out
    assert "Test title" in captured.out
    assert '"key": "val"' in captured.out


def test_run_loop_logs_in_debug_mode(mocker, capsys):
    mock_provider = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.is_thought = False
    mock_chunk.text = "<final>Done</final>"
    mock_provider.stream_chat.return_value = [mock_chunk]

    mocker.patch("olla.loop.get_provider", return_value=(mock_provider, "mock-model"))

    run_loop(
        task="testing debug mode",
        model="mock-model",
        max_steps=1,
        system_prompt="sys",
        debug=True,
    )

    captured = capsys.readouterr()
    assert "[DEBUG]" in captured.out
    assert "Loop initialization" in captured.out
    assert "Step 1/1" in captured.out
    assert "Raw model response" in captured.out
    assert "Done" in captured.out
