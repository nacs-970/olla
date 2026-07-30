"""Shared tool-result contract for all olla tools."""

from typing import TypedDict


class FileSnapshot(TypedDict):
    """Identity and version metadata captured from an open file descriptor."""

    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int
    size: int
    mode: int


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
    warning: str
    path: str
    content: str
    snapshot: FileSnapshot
    stale: bool
    bytes_written: int
