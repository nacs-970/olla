"""Debug logging infrastructure for olla."""

import json
import os
from typing import Any

_DEBUG_ENABLED = False


def is_debug() -> bool:
    """Return whether debug mode is enabled."""
    return _DEBUG_ENABLED or os.environ.get("OLLA_DEBUG", "").lower() in ("1", "true", "yes")


def set_debug(enabled: bool) -> None:
    """Set debug mode state."""
    global _DEBUG_ENABLED
    _DEBUG_ENABLED = enabled


def mask_secret(secret: str | None) -> str:
    """Mask secret key for safe debug display."""
    if not secret:
        return "(none)"
    if len(secret) <= 10:
        return secret[:2] + "..." + secret[-2:]
    return secret[:8] + "..." + secret[-4:]


def debug_log(title: str, content: Any = None) -> None:
    """Print formatted debug information if debug mode is active."""
    if not is_debug():
        return

    prefix = "\033[35m[DEBUG]\033[0m"
    if content is None:
        print(f"{prefix} {title}")
        return

    if isinstance(content, (dict, list)):
        try:
            formatted = json.dumps(content, indent=2, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            formatted = str(content)
    else:
        formatted = str(content)

    print(f"{prefix} \033[1m{title}\033[0m:")
    for line in formatted.splitlines():
        print(f"{prefix}   {line}")
