"""Directory listing and file search tools."""

import os
import re

from olla.tools.base import ToolResult


def _human_size(size: int) -> str:
    """Format bytes into a human-readable string like '1.2K' or '3.4M'."""
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024.0:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}{unit}"
        size /= 1024.0
    return f"{size:.1f}P"


def list_dir(path: str) -> ToolResult:
    """List directory contents with sizes and markers, directories first."""
    try:
        entries = list(os.scandir(path))
    except FileNotFoundError:
        return {"path": path, "error": f"directory not found: {path}"}
    except NotADirectoryError:
        return {"path": path, "error": f"not a directory: {path}"}
    except OSError as error:
        return {"path": path, "error": f"could not list {path}: {error}"}

    def sort_key(entry: os.DirEntry) -> tuple[bool, str]:
        return (not entry.is_dir(follow_symlinks=False), entry.name)

    entries.sort(key=sort_key)

    lines = []
    total = len(entries)

    for shown, entry in enumerate(entries):
        if shown >= 50:
            lines.append(f"... {total - 50} more entries not shown")
            break

        if entry.is_symlink():
            try:
                target = os.readlink(entry.path)
            except OSError:
                target = "???"
            lines.append(f"[l] {entry.name} -> {target}")
        else:
            is_dir = entry.is_dir(follow_symlinks=False)
            marker = "[d]" if is_dir else "[f]"
            try:
                size = entry.stat(follow_symlinks=False).st_size
                size_str = _human_size(size)
            except OSError:
                size_str = "???"
            lines.append(f"{marker} {entry.name} {size_str}")

    return {"path": path, "content": "\n".join(lines)}


def grep_files(pattern: str, path: str, recursive: bool = False) -> ToolResult:
    """Search for a case-sensitive regex pattern in text files."""
    try:
        regex = re.compile(pattern)
    except re.error as error:
        return {"path": path, "error": f"invalid regex {pattern!r}: {error}"}

    lines = []
    limit = 25

    def scan_file(file_path: str) -> bool:
        """Scan one file. Return True if cap reached, False otherwise."""
        try:
            with open(file_path, "rb") as f:
                head = f.read(8000)
                if b"\x00" in head:
                    return False

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        text = line.rstrip("\n")
                        lines.append(f"{file_path}:{i}:{text}")
                        if len(lines) >= limit:
                            lines.append("... more matches not shown")
                            return True
        except OSError:
            pass
        return False

    if not recursive:
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False) and scan_file(entry.path):
                        break
        except OSError as error:
            return {"path": path, "error": f"could not scan {path}: {error}"}
    else:
        for root, dirnames, filenames in os.walk(path, followlinks=False):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            capped = False
            for name in filenames:
                full_path = os.path.join(root, name)
                if not os.path.islink(full_path) and scan_file(full_path):
                    capped = True
                    break
            if capped:
                break

    return {"path": path, "content": "\n".join(lines)}
