"""Tests for olla.cli."""

import pytest
from click.testing import CliRunner

from olla.cli import main
from olla.prompts import SYSTEM_PROMPT


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    monkeypatch.setattr("olla.cli.load_config", lambda *a, **kw: {})


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
        task="do something",
        model="some-model",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_max_steps_option_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--max-steps", "5"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=5,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_max_steps_zero_unlimited(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--max-steps", "0"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=0,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_unlimited_flag_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--unlimited"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=0,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_dry_run_flag_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--dry-run"])

    assert result.exit_code == 0
    assert "--dry-run is not yet enforced" not in result.output
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=True,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_yes_flag_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--yes"])

    assert result.exit_code == 0
    assert "--yes is not yet enforced" not in result.output
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=True,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )


def test_debug_flag_threaded_through(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--debug"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=True,
    )


def test_api_key_and_base_url_passed_to_run_loop(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "do something",
            "--model",
            "openrouter/meta-llama/llama-3.1-8b",
            "--api-key",
            "sk-secret",
            "--base-url",
            "https://custom.api/v1",
        ],
    )

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="openrouter/meta-llama/llama-3.1-8b",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key="sk-secret",
        base_url="https://custom.api/v1",
        debug=False,
    )


def test_smoke_test_flag_calls_run_smoke_test(mocker):
    mock_run_smoke_test = mocker.patch("olla.cli.run_smoke_test")
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["--smoke-test", "--model", "some-model"])

    assert result.exit_code == 0
    mock_run_smoke_test.assert_called_once_with("some-model", api_key=None, base_url=None)
    mock_run_loop.assert_not_called()


def test_smoke_test_with_api_key_and_base_url(mocker):
    mock_run_smoke_test = mocker.patch("olla.cli.run_smoke_test")
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["--smoke-test", "--model", "some-model", "--api-key", "my-key", "--base-url", "https://api.test/v1"],
    )

    assert result.exit_code == 0
    mock_run_smoke_test.assert_called_once_with("some-model", api_key="my-key", base_url="https://api.test/v1")
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
