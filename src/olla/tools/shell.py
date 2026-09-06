"""Shell tool: subprocess.run(shell=False) over a pre-parsed argv."""

import subprocess

from olla.tools.base import ToolResult


def run_shell(argv: list[str], timeout: int = 30) -> ToolResult:
    """Run a shell command safely via subprocess.run(shell=False).

    `argv` must already be parsed (e.g. via shlex.split() by the caller).
    Returns a ToolResult dict. On success: argv, returncode, stdout, stderr.
    On FileNotFoundError or timeout: argv plus an `error` message.
    """
    if not argv:
        return {"argv": argv, "error": "empty command"}
    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError:
        return {"argv": argv, "error": f"command not found: {argv[0]}"}
    except PermissionError:
        return {"argv": argv, "error": f"permission denied: {argv[0]}"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "error": f"command timed out after {timeout}s"}
