"""File tools: read_file/write_file read and write UTF-8 text files via pathlib."""

from pathlib import Path

from olla.tools.base import ToolResult


def read_file(path: str) -> ToolResult:
    """Read a file's contents as UTF-8 text.

    Returns a ToolResult dict. On success: path, content.
    On error (not found, is a directory, not readable as text): path plus
    an `error` message. Never raises.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
        return {"path": path, "content": content}
    except FileNotFoundError:
        return {"path": path, "error": f"file not found: {path}"}
    except IsADirectoryError:
        return {"path": path, "error": f"is a directory: {path}"}
    except (UnicodeDecodeError, OSError, ValueError) as e:
        return {"path": path, "error": f"could not read {path}: {e}"}


def write_file(path: str, content: str) -> ToolResult:
    """Write UTF-8 text content to a file.

    Returns a ToolResult dict. On success: path, bytes_written.
    On error (missing parent directory, not writable): path plus an `error`
    message. Never raises. Does not create missing parent directories.
    """
    p = Path(path)
    if not p.parent.exists():
        return {"path": path, "error": f"parent directory does not exist: {p.parent}"}
    try:
        p.write_text(content, encoding="utf-8")
        return {"path": path, "bytes_written": len(content.encode("utf-8"))}
    except (OSError, ValueError) as e:
        return {"path": path, "error": f"could not write {path}: {e}"}
