"""Tests for race-aware UTF-8 file reads and writes."""

import os
import stat
from types import SimpleNamespace

import pytest

import olla.tools.files as file_tools
from olla.tools.files import _validate_backend_support, read_file, write_file


def test_read_file_success(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_text("hello from file\n")

    result = read_file(str(path))

    assert result["path"] == str(path)
    assert result["content"] == "hello from file\n"
    assert "error" not in result


def test_read_file_not_found(tmp_path):
    path = tmp_path / "nope.txt"

    result = read_file(str(path))

    assert "error" in result
    assert str(path) in result["error"]
    assert "content" not in result


def test_read_file_close_failure_returns_error(tmp_path, mocker):
    path = tmp_path / "hello.txt"
    path.write_text("hello", encoding="utf-8")
    mocker.patch(
        "olla.tools.files.os.close",
        side_effect=OSError("close failed"),
    )

    result = read_file(str(path))

    assert "close failed" in result["error"]
    assert "content" not in result


def test_backend_validation_rejects_non_posix_with_actionable_error():
    unsupported_os = SimpleNamespace(name="nt")

    with pytest.raises(RuntimeError, match="POSIX runtime") as raised:
        _validate_backend_support(unsupported_os, None)

    assert "Linux, macOS, or WSL" in str(raised.value)


def test_write_file_success(tmp_path):
    path = tmp_path / "out.txt"

    result = write_file(str(path), "hello\n")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert result["path"] == str(path)
    assert result["bytes_written"] == 6
    assert "error" not in result


def test_write_file_accepts_basename_near_filesystem_name_max(tmp_path):
    name_max = os.pathconf(tmp_path, "PC_NAME_MAX")
    path = tmp_path / ("x" * (name_max - 1))

    result = write_file(str(path), "content")

    assert "error" not in result
    assert path.read_text(encoding="utf-8") == "content"


def test_write_file_missing_parent_dir_errors(tmp_path):
    path = tmp_path / "nonexistent_dir" / "out.txt"

    result = write_file(str(path), "content")

    assert "error" in result
    assert "parent directory" in result["error"]
    assert not path.parent.exists()


def test_read_file_null_byte_path_returns_error():
    # CR-01 regression: null byte in path raises ValueError inside pathlib —
    # read_file must catch it and return an error dict, never propagate.
    result = read_file("some\x00path")

    assert "error" in result
    assert "content" not in result


def test_write_file_null_byte_path_returns_error():
    # CR-01 regression: null byte in path raises ValueError inside pathlib —
    # write_file must catch it and return an error dict, never propagate.
    result = write_file("/tmp/x\x00y", "content")

    assert "error" in result
    assert "bytes_written" not in result


@pytest.mark.parametrize(
    "raw",
    [b"first\r\nsecond\r\n", b"first\rsecond\r", b"no final newline"],
)
def test_read_and_write_preserve_newline_bytes(tmp_path, raw):
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_bytes(raw)

    read_result = read_file(str(source))
    write_result = write_file(str(destination), read_result["content"])

    assert "error" not in read_result
    assert "snapshot" in read_result
    assert "error" not in write_result
    assert write_result["bytes_written"] == len(raw)
    assert destination.read_bytes() == raw


def test_encoding_failure_preserves_existing_file(tmp_path):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]

    result = write_file(
        str(path),
        "invalid \ud800 payload",
        expected_snapshot=snapshot,
    )

    assert "error" in result
    assert path.read_bytes() == b"ORIGINAL"


def test_failed_staging_write_preserves_original(tmp_path, mocker):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_write = os.write
    failed = False

    def fail_first_write(descriptor, data):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("disk full")
        return real_write(descriptor, data)

    mocker.patch("olla.tools.files.os.write", side_effect=fail_first_write)

    result = write_file(
        str(path),
        "replacement",
        expected_snapshot=snapshot,
    )

    assert "disk full" in result["error"]
    assert path.read_bytes() == b"ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]


def test_interrupted_staging_write_preserves_complete_original(tmp_path, mocker):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    mocker.patch(
        "olla.tools.files.os.write",
        side_effect=KeyboardInterrupt,
    )

    with pytest.raises(KeyboardInterrupt):
        write_file(
            str(path),
            "replacement",
            expected_snapshot=snapshot,
        )

    assert path.read_bytes() == b"ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]


def test_stale_exchange_preserves_target_and_displaced_original(
    tmp_path, mocker
):
    path = tmp_path / "existing.txt"
    moved = tmp_path / "moved.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    swapped = False

    def swap_then_exchange(directory_fd, source, destination):
        nonlocal swapped
        if not swapped:
            swapped = True
            path.rename(moved)
            path.write_bytes(b"EXTERNAL")
        return real_exchange(directory_fd, source, destination)

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=swap_then_exchange,
    )

    result = write_file(
        str(path),
        "MODEL",
        expected_snapshot=snapshot,
    )

    assert result["stale"] is True
    assert path.read_bytes() == b"EXTERNAL"
    assert moved.read_bytes() == b"ORIGINAL"
    assert sorted(entry.name for entry in tmp_path.iterdir()) == [
        "existing.txt",
        "moved.txt",
    ]


def test_atomic_overwrite_preserves_existing_mode(tmp_path):
    path = tmp_path / "executable.sh"
    path.write_text("old\n", encoding="utf-8")
    path.chmod(0o751)
    snapshot = read_file(str(path))["snapshot"]

    result = write_file(
        str(path),
        "new\n",
        expected_snapshot=snapshot,
    )

    assert "error" not in result
    assert path.read_bytes() == b"new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o751


def test_recreated_identical_file_is_stale(tmp_path):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"same content\n")
    snapshot = read_file(str(path))["snapshot"]
    path.unlink()
    path.write_bytes(b"same content\n")

    result = write_file(
        str(path),
        "model replacement\n",
        expected_snapshot=snapshot,
    )

    assert result["stale"] is True
    assert path.read_bytes() == b"same content\n"


def test_new_file_publish_never_overwrites_appeared_target(tmp_path):
    path = tmp_path / "new.txt"
    path.write_bytes(b"EXTERNAL")

    result = write_file(str(path), "model payload")

    assert result["stale"] is True
    assert path.read_bytes() == b"EXTERNAL"


def test_new_file_publish_does_not_follow_destination_symlink(tmp_path):
    referent = tmp_path / "referent.txt"
    referent.write_bytes(b"REFERENT")
    path = tmp_path / "new.txt"
    os.symlink(referent, path)

    result = write_file(str(path), "model payload")

    assert result["stale"] is True
    assert path.is_symlink()
    assert referent.read_bytes() == b"REFERENT"


def test_create_retries_one_shot_temp_cleanup_failure(tmp_path, mocker):
    path = tmp_path / "new.txt"
    real_unlink = os.unlink
    attempts = 0

    def fail_once(target, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("temporary cleanup failed")
        return real_unlink(target, *args, **kwargs)

    mocker.patch("olla.tools.files.os.unlink", side_effect=fail_once)

    result = write_file(str(path), "MODEL")

    assert "error" not in result
    assert "warning" not in result
    assert path.read_bytes() == b"MODEL"
    assert list(tmp_path.iterdir()) == [path]


def test_create_reports_persistent_temp_cleanup_failure_as_warning(
    tmp_path, mocker
):
    path = tmp_path / "new.txt"
    mocker.patch(
        "olla.tools.files.os.unlink",
        side_effect=OSError("temporary cleanup failed"),
    )

    result = write_file(str(path), "MODEL")

    assert "error" not in result
    assert "cleanup" in result["warning"]
    assert path.read_bytes() == b"MODEL"
    leftovers = [entry for entry in tmp_path.iterdir() if entry != path]
    assert len(leftovers) == 1


def test_create_close_failure_before_publication_returns_error(tmp_path, mocker):
    path = tmp_path / "new.txt"
    mocker.patch(
        "olla.tools.files.os.close",
        side_effect=OSError("close failed"),
    )

    result = write_file(str(path), "MODEL")

    assert "close failed" in result["error"]
    assert not path.exists()


def test_create_close_failure_after_publication_returns_warning(tmp_path, mocker):
    path = tmp_path / "new.txt"
    real_close = os.close
    close_count = 0

    def fail_directory_close(descriptor):
        nonlocal close_count
        close_count += 1
        if close_count == 2:
            raise OSError("close failed")
        return real_close(descriptor)

    mocker.patch("olla.tools.files.os.close", side_effect=fail_directory_close)

    result = write_file(str(path), "MODEL")

    assert "error" not in result
    assert "close failed" in result["warning"]
    assert path.read_bytes() == b"MODEL"
