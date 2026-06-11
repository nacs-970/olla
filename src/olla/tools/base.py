"""Shared tool-result contract for all olla tools."""

from typing import TypedDict


class ToolResult(TypedDict, total=False):
    """Shape returned by every tool implementation (shell, and future file tools).

    `total=False` allows partial dicts — e.g. error-only results from
    FileNotFoundError/timeout cases that omit stdout/stderr.
    """

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    error: str
