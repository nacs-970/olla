"""Tests for race-aware UTF-8 file reads and writes."""

import os
import stat

import pytest

from olla.tools.files import read_file, write_file


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


def test_write_file_success(tmp_path):
    path = tmp_path / "out.txt"

    result = write_file(str(path), "hello\n")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert result["path"] == str(path)
    assert result["bytes_written"] == 6
    assert "error" not in result


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


def test_failed_descriptor_write_restores_original(tmp_path, mocker):
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


def test_overwrite_does_not_clobber_target_swapped_after_last_check(
    tmp_path, mocker
):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_ftruncate = os.ftruncate
    swapped = False

    def swap_then_truncate(descriptor, length):
        nonlocal swapped
        if not swapped:
            swapped = True
            replacement = tmp_path / "external.txt"
            replacement.write_bytes(b"EXTERNAL")
            os.replace(replacement, path)
        return real_ftruncate(descriptor, length)

    mocker.patch(
        "olla.tools.files.os.ftruncate",
        side_effect=swap_then_truncate,
    )

    result = write_file(
        str(path),
        "MODEL",
        expected_snapshot=snapshot,
    )

    assert result["stale"] is True
    assert path.read_bytes() == b"EXTERNAL"


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
