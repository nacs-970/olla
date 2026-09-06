"""Tests for olla.tools.shell.run_shell."""

from olla.tools.shell import run_shell


def test_echo_success():
    result = run_shell(["echo", "hello"])
    assert result["argv"] == ["echo", "hello"]
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["stderr"] == ""


def test_nonzero_exit():
    result = run_shell(["false"])
    assert result["argv"] == ["false"]
    assert result["returncode"] == 1


def test_command_not_found():
    result = run_shell(["nonexistent-command-xyz"])
    assert result["argv"] == ["nonexistent-command-xyz"]
    assert "command not found" in result["error"]


def test_timeout():
    result = run_shell(["sleep", "5"], timeout=1)
    assert "timed out" in result["error"]


def test_multi_word_arg_stays_single_argv_element():
    # shlex-parsing is now the caller's responsibility (olla.loop, covered by
    # tests/test_loop.py); run_shell receives an already-parsed argv list and
    # passes it straight to subprocess.run without re-splitting.
    result = run_shell(["echo", "hello world"])
    assert result["argv"] == ["echo", "hello world"]
    assert "hello world" in result["stdout"]


def test_empty_argv_errors():
    result = run_shell([])
    assert result["argv"] == []
    assert "empty command" in result["error"]


def test_permission_denied(tmp_path):
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o644)  # no execute bit
    result = run_shell([str(script)])
    assert "permission denied" in result["error"]


# Malformed-quoting handling (formerly test_unbalanced_quote) is now the
# caller's responsibility via shlex.split() in olla.loop, covered by
# tests/test_loop.py::test_run_loop_malformed_args_recovers.
