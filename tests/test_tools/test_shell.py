"""Tests for olla.tools.shell.run_shell."""

from olla.tools.shell import run_shell


def test_echo_success():
    result = run_shell("echo hello")
    assert result["argv"] == ["echo", "hello"]
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["stderr"] == ""


def test_nonzero_exit():
    result = run_shell("false")
    assert result["argv"] == ["false"]
    assert result["returncode"] == 1


def test_command_not_found():
    result = run_shell("nonexistent-command-xyz")
    assert result["argv"] == ["nonexistent-command-xyz"]
    assert "command not found" in result["error"]


def test_timeout():
    result = run_shell("sleep 5", timeout=1)
    assert "timed out" in result["error"]


def test_quoted_argument_survives_shlex():
    result = run_shell('echo "hello world"')
    assert result["argv"] == ["echo", "hello world"]
    assert "hello world" in result["stdout"]


def test_empty_args():
    result = run_shell("")
    assert result["argv"] == []
    assert "empty command" in result["error"]


def test_whitespace_only_args():
    result = run_shell("   ")
    assert result["argv"] == []
    assert "empty command" in result["error"]


def test_unbalanced_quote():
    result = run_shell('echo "unterminated')
    assert "could not parse command" in result["error"]
    assert "argv" not in result
