"""Tests for olla.repl."""

from unittest.mock import MagicMock

from olla.providers import ProviderError
from olla.repl import main_loop


def test_main_loop_dispatches_two_turns_with_shared_session(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = ["do a", "do b", EOFError()]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    assert mock_run_loop.call_count == 2
    first_call, second_call = mock_run_loop.call_args_list
    assert first_call.kwargs["session"] is second_call.kwargs["session"]
    assert first_call.kwargs["model"] == "m"
    assert second_call.kwargs["model"] == "m"


def test_main_loop_provider_init_failure_prints_and_returns(mocker, capsys):
    mocker.patch("olla.repl.get_provider", side_effect=ProviderError("boom"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_not_called()
    assert "boom" in capsys.readouterr().out
