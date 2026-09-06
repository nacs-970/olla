"""TOML configuration loader for olla."""

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


def get_default_config_path() -> Path:
    """Return canonical config path in ~/.config/olla/config.toml."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "olla" / "config.toml"


def find_config_path(custom_path: str | Path | None = None) -> Path | None:
    """Find existing configuration file path honoring environment and XDG spec."""
    if custom_path:
        p = Path(custom_path)
        return p if p.exists() else None

    env_config = os.environ.get("OLLA_CONFIG")
    if env_config:
        p = Path(env_config)
        return p if p.exists() else None

    # XDG standard location: ~/.config/olla/config.toml
    xdg_path = get_default_config_path()
    if xdg_path.exists():
        return xdg_path

    # Legacy fallback location: ~/.olla/config.toml
    legacy_path = Path.home() / ".olla" / "config.toml"
    if legacy_path.exists():
        return legacy_path

    return None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from TOML file, returning empty dict if not found."""
    target = find_config_path(path)
    if target is None:
        return {}

    try:
        with open(target, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
