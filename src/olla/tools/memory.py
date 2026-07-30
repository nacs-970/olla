"""Invocation-local scratchpad memory with explicit remember and recall calls."""

from dataclasses import dataclass

from olla.tools.base import ToolResult

MAX_KEY_CHARS = 128
MAX_VALUE_CHARS = 2_000
MAX_KEYS = 32
MAX_TOTAL_CHARS = 16_000


@dataclass(frozen=True)
class RememberCall:
    """Normalized arguments for one remember call."""

    key: str
    value: str


def _validate_key(key: str, tool: str) -> tuple[str | None, str | None]:
    """Normalize one public key and reject unreachable protocol states."""
    normalized = key.strip()
    if not normalized:
        return None, f"invalid {tool}: key must not be empty"
    if len(normalized.splitlines()) > 1:
        return None, f"invalid {tool}: key must be one line"
    if len(normalized) > MAX_KEY_CHARS:
        return (
            None,
            (
                f"memory key too large: {len(normalized)} characters; "
                f"maximum is {MAX_KEY_CHARS}"
            ),
        )
    return normalized, None


def parse_remember_args(
    args_raw: str,
) -> tuple[RememberCall | None, str | None]:
    """Parse a trimmed key line and preserve the remaining value verbatim."""
    key_line, separator, value = args_raw.partition("\n")
    key, error = _validate_key(key_line, "remember")
    if error is not None:
        return None, error
    if not separator:
        return (
            None,
            "invalid remember: expected key on first line and value on remaining lines",
        )
    if len(value) > MAX_VALUE_CHARS:
        return (
            None,
            (
                f"memory value too large: {len(value)} characters; "
                f"maximum is {MAX_VALUE_CHARS}"
            ),
        )
    assert key is not None
    return RememberCall(key=key, value=value), None


def parse_recall_args(args_raw: str) -> tuple[str | None, str | None]:
    """Parse and validate one case-sensitive recall key."""
    return _validate_key(args_raw, "recall")


class Scratchpad:
    """Store notes for the lifetime of one owning run-loop invocation."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def remember(self, call: RememberCall) -> ToolResult:
        """Store or replace one value and return a non-disclosing acknowledgment."""
        key, error = _validate_key(call.key, "remember")
        if error is not None:
            return {"error": error}
        assert key is not None
        if len(call.value) > MAX_VALUE_CHARS:
            return {
                "error": (
                    f"memory value too large: {len(call.value)} characters; "
                    f"maximum is {MAX_VALUE_CHARS}"
                )
            }

        is_new = key not in self._values
        old_length = 0 if is_new else len(self._values[key])
        current_total = sum(len(value) for value in self._values.values())
        projected_total = current_total - old_length + len(call.value)

        if is_new and len(self._values) >= MAX_KEYS:
            return {"error": f"memory key limit reached: maximum is {MAX_KEYS}"}
        if projected_total > MAX_TOTAL_CHARS:
            return {
                "error": (
                    "memory capacity exceeded: "
                    f"write would use {projected_total} of {MAX_TOTAL_CHARS} characters"
                )
            }

        self._values[key] = call.value
        if call.value == "":
            return {"content": f"remembered empty: {key}"}
        return {"content": f"remembered: {key}"}

    def recall(self, key: str) -> ToolResult:
        """Return one explicitly requested note or a recoverable missing-key error."""
        normalized_key, error = _validate_key(key, "recall")
        if error is not None:
            return {"error": error}
        assert normalized_key is not None
        if normalized_key not in self._values:
            return {"error": f"memory not found: {normalized_key}"}
        value = self._values[normalized_key]
        if value == "":
            return {"content": f"memory is empty: {normalized_key}"}
        return {"content": value}
