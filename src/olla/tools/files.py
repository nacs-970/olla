"""Race-aware UTF-8 file tools with byte-preserving reads and atomic writes."""

import ctypes
import errno
import os
import secrets
import stat
import sys
from pathlib import Path

from olla.tools.base import FileSnapshot, ToolResult

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX runtimes
    fcntl = None


def _validate_backend_support(
    os_module: object = os,
    fcntl_module: object | None = fcntl,
) -> None:
    """Fail at startup when secure POSIX file primitives are unavailable."""
    message = (
        "olla file tools require a POSIX runtime with fcntl.flock, "
        "O_NOFOLLOW/O_DIRECTORY, and dir_fd support; use Linux, macOS, or WSL"
    )
    if (
        getattr(os_module, "name", None) != "posix"
        or fcntl_module is None
        or not hasattr(fcntl_module, "flock")
    ):
        raise RuntimeError(message)

    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os_module, name) for name in required_flags):
        raise RuntimeError(message)

    supports_dir_fd = getattr(os_module, "supports_dir_fd", set())
    dir_fd_functions = tuple(
        getattr(os_module, name, None)
        for name in ("link", "open", "stat", "unlink")
    )
    if any(
        function is None or function not in supports_dir_fd
        for function in dir_fd_functions
    ):
        raise RuntimeError(message)

    supports_follow_symlinks = getattr(
        os_module,
        "supports_follow_symlinks",
        set(),
    )
    follow_functions = (
        getattr(os_module, "link", None),
        getattr(os_module, "stat", None),
    )
    if any(
        function is None or function not in supports_follow_symlinks
        for function in follow_functions
    ):
        raise RuntimeError(message)


_validate_backend_support()


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
    return os.O_NOFOLLOW | os.O_CLOEXEC


def _stale_result(path: str) -> ToolResult:
    return {
        "path": path,
        "stale": True,
        "error": f"refused: {path} changed or appeared before the write",
    }


def _create_temp_file(directory_fd: int, name: str, mode: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _nofollow_flags()
    for _attempt in range(100):
        temp_name = f".olla.{secrets.token_hex(8)}.tmp"
        try:
            return os.open(temp_name, flags, mode, dir_fd=directory_fd), temp_name
        except FileExistsError:
            continue
    raise FileExistsError(f"could not allocate a temporary file for {name}")


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


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _close_descriptor(descriptor: int, description: str) -> str | None:
    """Close one descriptor once and report, rather than raise, any failure."""
    try:
        os.close(descriptor)
    except (OSError, ValueError) as error:
        return f"could not close {description}: {error}"
    return None


def _exchange_files(directory_fd: int, source: str, destination: str) -> None:
    """Atomically exchange two names without an overwrite race."""
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)

    if sys.platform.startswith("linux"):
        exchange = getattr(libc, "renameat2", None)
    elif sys.platform == "darwin":
        exchange = getattr(libc, "renameatx_np", None)
    else:  # pragma: no cover - startup validation limits supported platforms
        exchange = None

    if exchange is None:
        raise NotImplementedError("atomic file exchange is unavailable")

    exchange.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    exchange.restype = ctypes.c_int
    if exchange(
        directory_fd,
        source_bytes,
        directory_fd,
        destination_bytes,
        2,  # RENAME_EXCHANGE on Linux and RENAME_SWAP on macOS.
    ) == 0:
        return

    error_number = ctypes.get_errno()
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise NotImplementedError("atomic file exchange is unavailable")
    raise OSError(error_number, os.strerror(error_number))


def read_file(path: str) -> ToolResult:
    """Read a file's contents as UTF-8 text.

    Returns a ToolResult dict. On success: path, content.
    On error (not found, is a directory, not readable as text): path plus
    an `error` message. Never raises.
    """
    descriptor: int | None = None
    result: ToolResult
    try:
        descriptor = os.open(path, os.O_RDONLY | _nofollow_flags())
        before = os.fstat(descriptor)
        if stat.S_ISDIR(before.st_mode):
            raise IsADirectoryError(path)
        if not stat.S_ISREG(before.st_mode):
            raise OSError(f"not a regular file: {path}")

        data = _read_descriptor(descriptor)
        after = os.fstat(descriptor)

        if _snapshot(before) != _snapshot(after):
            result = {"path": path, "error": f"file changed while reading: {path}"}
        else:
            content = data.decode("utf-8")
            result = {"path": path, "content": content, "snapshot": _snapshot(after)}
    except FileNotFoundError:
        result = {"path": path, "error": f"file not found: {path}"}
    except IsADirectoryError:
        result = {"path": path, "error": f"is a directory: {path}"}
    except (UnicodeDecodeError, OSError, ValueError, NotImplementedError) as e:
        result = {"path": path, "error": f"could not read {path}: {e}"}
    finally:
        if descriptor is not None:
            close_error = _close_descriptor(descriptor, f"read file {path}")
            if close_error is not None:
                result = {"path": path, "error": f"could not read {path}: {close_error}"}
    return result


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
    The payload is encoded before any destination is touched. New and existing
    files are staged separately and published atomically. Never raises.
    """
    p = Path(path)
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError as error:
        return {"path": path, "error": f"could not write {path}: {error}"}

    directory_fd: int | None = None
    target_fd: int | None = None
    staging_fd: int | None = None
    temp_name: str | None = None
    published = False
    result: ToolResult | None = None

    def stage_payload(mode: int) -> None:
        nonlocal staging_fd, temp_name
        staging_fd, temp_name = _create_temp_file(directory_fd, p.name, mode)
        os.fchmod(staging_fd, mode)
        _write_descriptor(staging_fd, encoded)
        descriptor = staging_fd
        staging_fd = None
        close_error = _close_descriptor(descriptor, "staging file")
        if close_error is not None:
            raise OSError(close_error)

    def perform_write() -> ToolResult:
        nonlocal directory_fd, published, target_fd, temp_name
        directory_flags = os.O_RDONLY | os.O_DIRECTORY
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
            stage_payload(0o666)
            assert temp_name is not None
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
            except OSError:
                pass
        else:
            assert target_fd is not None
            stage_payload(stat.S_IMODE(expected_snapshot["mode"]))
            assert temp_name is not None

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

            _exchange_files(directory_fd, temp_name, p.name)
            try:
                displaced_stat = os.stat(
                    temp_name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except (FileNotFoundError, OSError):
                displaced_stat = None
            if displaced_stat is None or not _same_object(
                displaced_stat,
                expected_snapshot,
            ):
                try:
                    _exchange_files(directory_fd, temp_name, p.name)
                except (OSError, NotImplementedError) as rollback_error:
                    return {
                        "path": path,
                        "error": (
                            f"could not write {path}: destination changed during "
                            f"commit and restoration failed: {rollback_error}"
                        ),
                    }
                return _stale_result(path)

            published = True
            os.fsync(directory_fd)
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
                temp_name = None
            except OSError:
                pass

        return {"path": path, "bytes_written": len(encoded)}

    try:
        result = perform_write()
    except FileNotFoundError:
        result = {
            "path": path,
            "error": f"parent directory does not exist: {p.parent}",
        }
    except (OSError, ValueError, NotImplementedError) as error:
        if published:
            result = {
                "path": path,
                "bytes_written": len(encoded),
                "warning": f"write succeeded, but cleanup failed: {error}",
            }
        else:
            result = {"path": path, "error": f"could not write {path}: {error}"}
    finally:
        cleanup_errors = []
        if staging_fd is not None:
            descriptor = staging_fd
            staging_fd = None
            close_error = _close_descriptor(descriptor, "staging file")
            if close_error is not None:
                cleanup_errors.append(close_error)
        if temp_name is not None and directory_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except (OSError, NotImplementedError) as error:
                cleanup_errors.append(
                    f"could not remove temporary file {temp_name}: {error}"
                )
        if target_fd is not None:
            descriptor = target_fd
            target_fd = None
            close_error = _close_descriptor(descriptor, "target file")
            if close_error is not None:
                cleanup_errors.append(close_error)
        if directory_fd is not None:
            descriptor = directory_fd
            directory_fd = None
            close_error = _close_descriptor(descriptor, "parent directory")
            if close_error is not None:
                cleanup_errors.append(close_error)

        if cleanup_errors:
            cleanup_message = "; ".join(cleanup_errors)
            if published:
                if result is None or "error" in result:
                    result = {"path": path, "bytes_written": len(encoded)}
                previous_warning = result.get("warning")
                result["warning"] = (
                    f"{previous_warning}; {cleanup_message}"
                    if previous_warning
                    else f"write succeeded, but cleanup failed: {cleanup_message}"
                )
            else:
                previous_error = result.get("error") if result is not None else None
                result = {
                    "path": path,
                    "error": (
                        f"{previous_error}; cleanup failed: {cleanup_message}"
                        if previous_error
                        else f"could not write {path}: cleanup failed: {cleanup_message}"
                    ),
                }

    assert result is not None
    return result
