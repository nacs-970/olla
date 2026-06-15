"""File tools: read_file reads a UTF-8 text file via pathlib."""

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
    except (UnicodeDecodeError, OSError) as e:
        return {"path": path, "error": f"could not read {path}: {e}"}
