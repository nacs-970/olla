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
        task="do something", model="some-model", max_steps=15, system_prompt=SYSTEM_PROMPT, yes=False, dry_run=False
    )


def test_max_steps_option_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--max-steps", "5"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=5, system_prompt=SYSTEM_PROMPT, yes=False, dry_run=False
    )


def test_dry_run_flag_prints_inert_notice(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--dry-run"])

    assert result.exit_code == 0
    assert "--dry-run is not yet enforced" in result.output
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=15, system_prompt=SYSTEM_PROMPT, yes=False, dry_run=True
    )


def test_yes_flag_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--yes"])

    assert result.exit_code == 0
    assert "--yes is not yet enforced" not in result.output
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=15, system_prompt=SYSTEM_PROMPT, yes=True, dry_run=False
    )


def test_smoke_test_flag_calls_run_smoke_test(mocker):
    mock_run_smoke_test = mocker.patch("olla.cli.run_smoke_test")
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["--smoke-test", "--model", "some-model"])

    assert result.exit_code == 0
    mock_run_smoke_test.assert_called_once_with("some-model")
    mock_run_loop.assert_not_called()


def test_smoke_test_without_model_raises_usage_error(mocker):
    mock_run_smoke_test = mocker.patch("olla.cli.run_smoke_test")
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["--smoke-test"])

    assert result.exit_code != 0
    assert "--model" in result.output
    mock_run_smoke_test.assert_not_called()
    mock_run_loop.assert_not_called()


def test_smoke_test_with_model_does_not_require_task(mocker):
    mocker.patch("olla.cli.run_smoke_test")
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["--smoke-test", "--model", "some-model"])

    assert "TASK argument is required" not in result.output
    assert result.exit_code == 0
    mock_run_loop.assert_not_called()
