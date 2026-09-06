"""Unit tests for olla TOML configuration loading."""

from pathlib import Path

from click.testing import CliRunner

from olla.cli import main
from olla.config import find_config_path, get_default_config_path, load_config
from olla.providers import OpenAICompatProvider, get_provider


def test_get_default_config_path(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = Path.home() / ".config" / "olla" / "config.toml"
    assert get_default_config_path() == expected

    custom_xdg = tmp_path / "custom_xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_xdg))
    assert get_default_config_path() == custom_xdg / "olla" / "config.toml"


def test_find_config_path_custom_path(tmp_path):
    cfg_file = tmp_path / "config.toml"
    assert find_config_path(cfg_file) is None

    cfg_file.write_text('default_model = "test-model"\n')
    assert find_config_path(cfg_file) == cfg_file


def test_find_config_path_env_var(monkeypatch, tmp_path):
    cfg_file = tmp_path / "custom.toml"
    monkeypatch.setenv("OLLA_CONFIG", str(cfg_file))
    assert find_config_path() is None

    cfg_file.write_text('default_model = "test-model"\n')
    assert find_config_path() == cfg_file


def test_find_config_path_xdg_and_legacy(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLA_CONFIG", raising=False)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert find_config_path() is None

    # Legacy ~/.olla/config.toml
    legacy_dir = fake_home / ".olla"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "config.toml"
    legacy_file.write_text('default_model = "legacy-model"\n')
    assert find_config_path() == legacy_file

    # XDG ~/.config/olla/config.toml should take precedence over legacy
    xdg_dir = fake_home / ".config" / "olla"
    xdg_dir.mkdir(parents=True)
    xdg_file = xdg_dir / "config.toml"
    xdg_file.write_text('default_model = "xdg-model"\n')
    assert find_config_path() == xdg_file


def test_load_config_not_found(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLA_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    assert load_config() == {}


def test_load_config_invalid_toml(tmp_path):
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("invalid = [toml\n")
    assert load_config(bad_toml) == {}


def test_load_config_valid(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        default_model = "openrouter/anthropic/claude-3.5-sonnet"
        api_key = "global-key"

        [openrouter]
        api_key = "router-key"
        base_url = "https://openrouter.ai/api/v1"
        """
    )
    data = load_config(cfg_file)
    assert data["default_model"] == "openrouter/anthropic/claude-3.5-sonnet"
    assert data["api_key"] == "global-key"
    assert data["openrouter"]["api_key"] == "router-key"


def test_cli_reads_default_model_from_config(mocker, tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('default_model = "qwen2.5:3b"\n')
    monkeypatch.setenv("OLLA_CONFIG", str(cfg_file))

    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()
    result = runner.invoke(main, ["do something"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once()
    assert mock_run_loop.call_args.kwargs["model"] == "qwen2.5:3b"


def test_cli_flag_overrides_config_model(mocker, tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('default_model = "qwen2.5:3b"\n')
    monkeypatch.setenv("OLLA_CONFIG", str(cfg_file))

    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()
    result = runner.invoke(main, ["do something", "--model", "custom-model"])

    assert result.exit_code == 0
    assert mock_run_loop.call_args.kwargs["model"] == "custom-model"


def test_provider_loads_keys_from_config(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        [openrouter]
        api_key = "cfg-openrouter-key"

        [openai]
        api_key = "cfg-openai-key"
        base_url = "https://custom.openai.api/v1"
        """
    )
    monkeypatch.setenv("OLLA_CONFIG", str(cfg_file))

    # Test openrouter provider using nested config
    provider_or, _ = get_provider("openrouter/meta-llama/llama-3.1-8b")
    assert isinstance(provider_or, OpenAICompatProvider)
    assert provider_or.api_key == "cfg-openrouter-key"

    # Test openai provider using nested config
    provider_oa, _ = get_provider("openai/gpt-4o")
    assert isinstance(provider_oa, OpenAICompatProvider)
    assert provider_oa.api_key == "cfg-openai-key"
    assert provider_oa.base_url == "https://custom.openai.api/v1"


def test_flat_keys_in_config(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
        openrouter_api_key = "flat-or-key"
        openrouter_base_url = "https://custom-flat.router/v1"
        """
    )
    monkeypatch.setenv("OLLA_CONFIG", str(cfg_file))

    provider, _ = get_provider("openrouter/meta-llama/llama-3.1-8b")
    assert provider.api_key == "flat-or-key"
    assert provider.base_url == "https://custom-flat.router/v1"
