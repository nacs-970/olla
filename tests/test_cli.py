"""Tests for olla.cli."""

from click.testing import CliRunner

from olla.cli import main
from olla.prompts import SYSTEM_PROMPT


def test_missing_model_raises_usage_error(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something"])

    assert result.exit_code != 0
    assert "--model" in result.output
    mock_run_loop.assert_not_called()


def test_missing_task_raises_usage_error(mocker):
    mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, [])

    assert result.exit_code != 0
    assert "TASK" in result.output


def test_task_and_model_call_run_loop_with_defaults(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=15, system_prompt=SYSTEM_PROMPT
    )


def test_max_steps_option_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--max-steps", "5"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=5, system_prompt=SYSTEM_PROMPT
    )
