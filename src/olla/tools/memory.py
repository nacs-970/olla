"""Invocation-local scratchpad memory with explicit remember and recall calls."""

from dataclasses import dataclass

from olla.tools.base import ToolResult

MAX_VALUE_CHARS = 2_000
MAX_KEYS = 32
MAX_TOTAL_CHARS = 16_000


@dataclass(frozen=True)
class RememberCall:
    """Normalized arguments for one remember call."""

    key: str
    value: str


def parse_remember_args(
    args_raw: str,
) -> tuple[RememberCall | None, str | None]:
    """Parse a trimmed key line and preserve the remaining value verbatim."""
    key_line, separator, value = args_raw.partition("\n")
    key = key_line.strip()
    if not key:
        return None, "invalid remember: key must not be empty"
    if not separator:
        return (
            None,
            "invalid remember: expected key on first line and value on remaining lines",
        )
    return RememberCall(key=key, value=value), None


def parse_recall_args(args_raw: str) -> tuple[str | None, str | None]:
    """Parse and validate one case-sensitive recall key."""
    key = args_raw.strip()
    if not key:
        return None, "invalid recall: key must not be empty"
    return key, None


class Scratchpad:
    """Store notes for the lifetime of one owning run-loop invocation."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def remember(self, call: RememberCall) -> ToolResult:
        """Store or replace one value and return a non-disclosing acknowledgment."""
        self._values[call.key] = call.value
        if call.value == "":
            return {"content": f"remembered empty: {call.key}"}
        return {"content": f"remembered: {call.key}"}

    def recall(self, key: str) -> ToolResult:
        """Return one explicitly requested note or a recoverable missing-key error."""
        if key not in self._values:
            return {"error": f"memory not found: {key}"}
        value = self._values[key]
        if value == "":
            return {"content": f"memory is empty: {key}"}
        return {"content": value}
