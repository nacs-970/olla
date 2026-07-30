"""Tests for race-aware UTF-8 file reads and writes."""

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
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
    assert result["snapshot"]["digest"] == file_tools._digest_bytes(
        b"hello from file\n"
    )
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


def test_new_file_syncs_staging_and_parent_directory(tmp_path, mocker):
    path = tmp_path / "out.txt"
    real_fsync = os.fsync
    synced_kinds = []

    def record_fsync(descriptor):
        synced_kinds.append(
            "directory"
            if stat.S_ISDIR(os.fstat(descriptor).st_mode)
            else "file"
        )
        return real_fsync(descriptor)

    mocker.patch("olla.tools.files.os.fsync", side_effect=record_fsync)

    result = write_file(str(path), "durable")

    assert "error" not in result
    assert path.read_bytes() == b"durable"
    assert "file" in synced_kinds
    assert synced_kinds[-1] == "directory"


def test_new_file_directory_sync_failure_returns_durability_warning(
    tmp_path, mocker
):
    path = tmp_path / "out.txt"
    real_fsync = os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory sync failed")
        return real_fsync(descriptor)

    mocker.patch(
        "olla.tools.files.os.fsync",
        side_effect=fail_directory_fsync,
    )

    result = write_file(str(path), "durable")

    assert result["bytes_written"] == 7
    assert "directory durability could not be confirmed" in result["warning"]
    assert path.read_bytes() == b"durable"


def test_new_file_and_staging_respect_restrictive_umask(tmp_path):
    script = textwrap.dedent(
        """
        import os
        import stat
        import sys

        import olla.tools.files as file_tools

        directory = sys.argv[1]
        target = os.path.join(directory, "out.txt")
        real_unlink = os.unlink

        def preserve_staging(path, *args, **kwargs):
            if str(path).startswith(".olla."):
                raise OSError("preserve staging for mode inspection")
            return real_unlink(path, *args, **kwargs)

        os.umask(0o077)
        file_tools.os.unlink = preserve_staging
        result = file_tools.write_file(target, "secret")
        entries = [os.path.join(directory, name) for name in os.listdir(directory)]
        modes = [stat.S_IMODE(os.stat(path).st_mode) for path in entries]
        assert result["bytes_written"] == 6
        assert len(entries) == 2
        assert all(mode == 0o600 for mode in modes), modes
        """
    )

    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )


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


def test_in_place_edit_at_exchange_is_restored_as_stale(tmp_path, mocker):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    mutated = False

    def mutate_then_exchange(directory_fd, source, destination):
        nonlocal mutated
        if not mutated:
            mutated = True
            path.write_bytes(b"EXTERNAL")
        return real_exchange(directory_fd, source, destination)

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=mutate_then_exchange,
    )

    result = write_file(
        str(path),
        "MODEL",
        expected_snapshot=snapshot,
    )

    assert result["stale"] is True
    assert path.read_bytes() == b"EXTERNAL"
    assert list(tmp_path.iterdir()) == [path]


def test_same_size_edit_with_restored_mtime_is_restored_as_stale(
    tmp_path, mocker
):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    mutated = False

    def mutate_then_exchange(directory_fd, source, destination):
        nonlocal mutated
        if not mutated:
            mutated = True
            path.write_bytes(b"EXTERNAL")
            os.utime(
                path,
                ns=(path.stat().st_atime_ns, snapshot["mtime_ns"]),
            )
        return real_exchange(directory_fd, source, destination)

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=mutate_then_exchange,
    )

    result = write_file(str(path), "MODEL", expected_snapshot=snapshot)

    assert result["stale"] is True
    assert path.read_bytes() == b"EXTERNAL"
    assert list(tmp_path.iterdir()) == [path]


def test_rollback_failure_preserves_displaced_file_and_reports_publication(
    tmp_path, mocker
):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    exchange_count = 0

    def mutate_then_fail_rollback(directory_fd, source, destination):
        nonlocal exchange_count
        exchange_count += 1
        if exchange_count == 1:
            path.write_bytes(b"EXTERNAL")
            return real_exchange(directory_fd, source, destination)
        raise OSError("forced rollback failure")

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=mutate_then_fail_rollback,
    )

    result = write_file(
        str(path),
        "MODEL",
        expected_snapshot=snapshot,
    )

    assert result["bytes_written"] == 5
    assert result["commit_uncertain"] is True
    assert "replacement remains published" in result["warning"]
    assert path.read_bytes() == b"MODEL"
    recovery = result["recovery_path"]
    assert os.path.dirname(recovery) == str(tmp_path)
    assert os.path.basename(recovery).startswith(".olla.")
    assert Path(recovery).read_bytes() == b"EXTERNAL"


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


def test_create_rejects_substituted_staging_name(tmp_path, mocker):
    path = tmp_path / "new.txt"
    real_link = os.link

    def substitute_then_link(source, destination, **kwargs):
        source_fd = kwargs["src_dir_fd"]
        os.unlink(source, dir_fd=source_fd)
        attacker_fd = os.open(
            source,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=source_fd,
        )
        os.write(attacker_fd, b"ATTACKER")
        os.close(attacker_fd)
        return real_link(source, destination, **kwargs)

    mocker.patch("olla.tools.files.os.link", side_effect=substitute_then_link)

    result = write_file(str(path), "MODEL")

    assert result["commit_uncertain"] is True
    assert path.read_bytes() == b"ATTACKER"


def test_create_rejects_modified_staging_payload(tmp_path, mocker):
    path = tmp_path / "new.txt"
    real_link = os.link

    def modify_then_link(source, destination, **kwargs):
        source_fd = kwargs["src_dir_fd"]
        attacker_fd = os.open(source, os.O_WRONLY, dir_fd=source_fd)
        os.ftruncate(attacker_fd, 0)
        os.write(attacker_fd, b"ATTACKER")
        os.close(attacker_fd)
        return real_link(source, destination, **kwargs)

    mocker.patch("olla.tools.files.os.link", side_effect=modify_then_link)

    result = write_file(str(path), "MODEL")

    assert result["stale"] is True
    assert not path.exists()


def test_create_does_not_delete_concurrent_destination_replacement(
    tmp_path, mocker
):
    path = tmp_path / "new.txt"
    real_link = os.link

    def replace_after_link(source, destination, **kwargs):
        result = real_link(source, destination, **kwargs)
        external = tmp_path / "external.tmp"
        external.write_bytes(b"EXTERNAL")
        os.replace(external, path)
        return result

    mocker.patch("olla.tools.files.os.link", side_effect=replace_after_link)

    result = write_file(str(path), "MODEL")

    assert result["commit_uncertain"] is True
    assert path.read_bytes() == b"EXTERNAL"
    assert Path(result["recovery_path"]).read_bytes() == b"MODEL"


def test_overwrite_rolls_back_substituted_staging_name(tmp_path, mocker):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    substituted = False

    def substitute_then_exchange(directory_fd, source, destination):
        nonlocal substituted
        if not substituted:
            substituted = True
            os.unlink(source, dir_fd=directory_fd)
            attacker_fd = os.open(
                source,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            os.write(attacker_fd, b"ATTACKER")
            os.close(attacker_fd)
        return real_exchange(directory_fd, source, destination)

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=substitute_then_exchange,
    )

    result = write_file(str(path), "MODEL", expected_snapshot=snapshot)

    assert result["commit_uncertain"] is True
    assert path.read_bytes() == b"ATTACKER"
    assert Path(result["recovery_path"]).read_bytes() == b"ORIGINAL"
    assert not any(entry.read_bytes() == b"MODEL" for entry in tmp_path.iterdir())


def test_overwrite_rolls_back_modified_staging_payload(tmp_path, mocker):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files
    modified = False

    def modify_then_exchange(directory_fd, source, destination):
        nonlocal modified
        if not modified:
            modified = True
            attacker_fd = os.open(source, os.O_WRONLY, dir_fd=directory_fd)
            os.ftruncate(attacker_fd, 0)
            os.write(attacker_fd, b"ATTACKER")
            os.close(attacker_fd)
        return real_exchange(directory_fd, source, destination)

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=modify_then_exchange,
    )

    result = write_file(str(path), "MODEL", expected_snapshot=snapshot)

    assert result["stale"] is True
    assert path.read_bytes() == b"ORIGINAL"
    assert list(tmp_path.iterdir()) == [path]


def test_overwrite_does_not_replace_concurrent_destination_replacement(
    tmp_path, mocker
):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"ORIGINAL")
    snapshot = read_file(str(path))["snapshot"]
    real_exchange = file_tools._exchange_files

    def replace_after_exchange(directory_fd, source, destination):
        result = real_exchange(directory_fd, source, destination)
        external = tmp_path / "external.tmp"
        external.write_bytes(b"EXTERNAL")
        os.replace(external, path)
        return result

    mocker.patch(
        "olla.tools.files._exchange_files",
        side_effect=replace_after_exchange,
    )

    result = write_file(str(path), "MODEL", expected_snapshot=snapshot)

    assert result["commit_uncertain"] is True
    assert path.read_bytes() == b"EXTERNAL"
    assert Path(result["recovery_path"]).read_bytes() == b"ORIGINAL"


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


def test_create_staging_close_failure_after_publication_returns_warning(
    tmp_path, mocker
):
    path = tmp_path / "new.txt"
    real_close_descriptor = file_tools._close_descriptor

    def fail_staging_close(descriptor, description):
        if description == "staging file":
            os.close(descriptor)
            return "could not close staging file: close failed"
        return real_close_descriptor(descriptor, description)

    mocker.patch(
        "olla.tools.files._close_descriptor",
        side_effect=fail_staging_close,
    )

    result = write_file(str(path), "MODEL")

    assert "error" not in result
    assert "close failed" in result["warning"]
    assert path.read_bytes() == b"MODEL"


def test_create_close_failure_after_publication_returns_warning(tmp_path, mocker):
    path = tmp_path / "new.txt"
    real_close_descriptor = file_tools._close_descriptor

    def fail_directory_close(descriptor, description):
        if description == "parent directory":
            os.close(descriptor)
            return "could not close parent directory: close failed"
        return real_close_descriptor(descriptor, description)

    mocker.patch(
        "olla.tools.files._close_descriptor",
        side_effect=fail_directory_close,
    )

    result = write_file(str(path), "MODEL")

    assert "error" not in result
    assert "close failed" in result["warning"]
    assert path.read_bytes() == b"MODEL"
