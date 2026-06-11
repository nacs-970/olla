"""Shell tool: shlex.split() + subprocess.run(shell=False)."""

import shlex
import subprocess

from olla.tools.base import ToolResult


def run_shell(args_raw: str, timeout: int = 30) -> ToolResult:
    """Run a shell command safely via shlex.split() + subprocess.run(shell=False).

    Returns a ToolResult dict. On success: argv, returncode, stdout, stderr.
    On FileNotFoundError or timeout: argv plus an `error` message.
    """
    argv = shlex.split(args_raw)
    try:
        result = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout)
        return {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError:
        return {"argv": argv, "error": f"command not found: {argv[0]}"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "error": f"command timed out after {timeout}s"}
