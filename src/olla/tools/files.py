"""Race-aware UTF-8 file tools with byte-preserving reads and atomic writes."""

import fcntl
import os
import secrets
import stat
from pathlib import Path

from olla.tools.base import FileSnapshot, ToolResult


def _snapshot(file_stat: os.stat_result) -> FileSnapshot:
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "mtime_ns": file_stat.st_mtime_ns,
        "ctime_ns": file_stat.st_ctime_ns,
        "size": file_stat.st_size,
        "mode": file_stat.st_mode,
    }


def _same_file(file_stat: os.stat_result, expected: FileSnapshot) -> bool:
    return _snapshot(file_stat) == expected


def _same_object(file_stat: os.stat_result, expected: FileSnapshot) -> bool:
    return (
        file_stat.st_dev == expected["device"]
        and file_stat.st_ino == expected["inode"]
    )


def _nofollow_flags() -> int:
    return getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _stale_result(path: str) -> ToolResult:
    return {
        "path": path,
        "stale": True,
        "error": f"refused: {path} changed or appeared before the write",
    }


def _create_temp_file(directory_fd: int, name: str, mode: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _nofollow_flags()
    for _attempt in range(100):
        temp_name = f".{name}.{secrets.token_hex(8)}.tmp"
        try:
            return os.open(temp_name, flags, mode, dir_fd=directory_fd), temp_name
        except FileExistsError:
            continue
    raise FileExistsError(f"could not allocate a temporary file for {name}")


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _write_descriptor(descriptor: int, data: bytes) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written == 0:
            raise OSError("write returned zero bytes")
        remaining = remaining[written:]
    os.fsync(descriptor)


def read_file(path: str) -> ToolResult:
    """Read a file's contents as UTF-8 text.

    Returns a ToolResult dict. On success: path, content.
    On error (not found, is a directory, not readable as text): path plus
    an `error` message. Never raises.
    """
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | _nofollow_flags())
        before = os.fstat(descriptor)
        if stat.S_ISDIR(before.st_mode):
            raise IsADirectoryError(path)
        if not stat.S_ISREG(before.st_mode):
            raise OSError(f"not a regular file: {path}")

        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read()
            after = os.fstat(stream.fileno())

        if _snapshot(before) != _snapshot(after):
            return {"path": path, "error": f"file changed while reading: {path}"}
        content = data.decode("utf-8")
        return {"path": path, "content": content, "snapshot": _snapshot(after)}
    except FileNotFoundError:
        return {"path": path, "error": f"file not found: {path}"}
    except IsADirectoryError:
        return {"path": path, "error": f"is a directory: {path}"}
    except (UnicodeDecodeError, OSError, ValueError) as e:
        return {"path": path, "error": f"could not read {path}: {e}"}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_file(
    path: str,
    content: str,
    *,
    expected_snapshot: FileSnapshot | None = None,
) -> ToolResult:
    """Atomically create a file or update the exact previously read object.

    Returns a ToolResult dict. On success: path, bytes_written.
    Existing destinations require ``expected_snapshot`` from ``read_file``.
    A missing expected destination, a newly appeared destination, symlinks,
    and identity/version changes return a stale result without overwriting it.
    The payload is encoded before any destination is touched. New files are
    staged and published atomically; existing files are updated through the
    verified descriptor with rollback on failure. Never raises.
    """
    p = Path(path)
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError as error:
        return {"path": path, "error": f"could not write {path}: {error}"}

    directory_fd: int | None = None
    target_fd: int | None = None
    temp_name: str | None = None
    published = False
    cleanup_warning: str | None = None
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(p.parent, directory_flags | _nofollow_flags())

        if expected_snapshot is not None:
            try:
                target_fd = os.open(
                    p.name,
                    os.O_RDWR | _nofollow_flags(),
                    dir_fd=directory_fd,
                )
            except (FileNotFoundError, IsADirectoryError, OSError):
                return _stale_result(path)

            fcntl.flock(target_fd, fcntl.LOCK_EX)
            if not _same_file(os.fstat(target_fd), expected_snapshot):
                return _stale_result(path)

        if expected_snapshot is None:
            temp_fd, temp_name = _create_temp_file(directory_fd, p.name, 0o666)
            with os.fdopen(temp_fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    temp_name,
                    p.name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                return _stale_result(path)
            published = True
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
                temp_name = None
            except OSError as cleanup_error:
                try:
                    os.unlink(temp_name, dir_fd=directory_fd)
                    temp_name = None
                except OSError:
                    cleanup_warning = (
                        f"write succeeded, but could not clean up temporary file "
                        f"{temp_name}: {cleanup_error}"
                    )
        else:
            assert target_fd is not None
            try:
                path_stat = os.stat(
                    p.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except (FileNotFoundError, OSError):
                return _stale_result(path)
            if not _same_file(os.fstat(target_fd), expected_snapshot) or not _same_file(
                path_stat, expected_snapshot
            ):
                return _stale_result(path)

            original = _read_descriptor(target_fd)
            try:
                _write_descriptor(target_fd, encoded)
            except (OSError, ValueError) as error:
                try:
                    _write_descriptor(target_fd, original)
                except (OSError, ValueError) as rollback_error:
                    return {
                        "path": path,
                        "error": (
                            f"could not write {path}: {error}; "
                            f"rollback also failed: {rollback_error}"
                        ),
                    }
                return {"path": path, "error": f"could not write {path}: {error}"}

            try:
                path_stat = os.stat(
                    p.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except (FileNotFoundError, OSError):
                return _stale_result(path)
            if not _same_object(path_stat, expected_snapshot):
                return _stale_result(path)

        result: ToolResult = {"path": path, "bytes_written": len(encoded)}
        if cleanup_warning is not None:
            result["warning"] = cleanup_warning
        return result
    except FileNotFoundError:
        return {
            "path": path,
            "error": f"parent directory does not exist: {p.parent}",
        }
    except (OSError, ValueError) as error:
        if published:
            return {
                "path": path,
                "bytes_written": len(encoded),
                "warning": f"write succeeded, but cleanup failed: {error}",
            }
        return {"path": path, "error": f"could not write {path}: {error}"}
    finally:
        if temp_name is not None and directory_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except OSError:
                pass
        if target_fd is not None:
            os.close(target_fd)
        if directory_fd is not None:
            os.close(directory_fd)
