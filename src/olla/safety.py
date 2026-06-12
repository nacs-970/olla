"""Pure safety-gate decision: blocklist/allowlist check against resolved argv."""

import fnmatch
import re
from typing import Literal, NotRequired, TypedDict


class Decision(TypedDict):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]
    reason: NotRequired[str]  # present only when kind == "BLOCK"


# D-01: whole-binary allowlist — read-only, side-effect-free commands that
# auto-run without a confirm prompt. Matches argv[0] only (D-02).
# `env` and `find` are excluded: both can execute arbitrary subcommands via
# their arguments (not side-effect-free), so they fall through to CONFIRM by
# default and are further gated below via _unwrap_env/_unwrap_find_exec.
ALLOWLIST: set[str] = {
    "ls",
    "pwd",
    "cat",
    "echo",
    "grep",
    "head",
    "tail",
    "wc",
    "file",
    "date",
    "whoami",
}

# D-03: binaries that are blocked outright — no safe invocation exists.
_HARD_BLOCKED_BINARIES: set[str] = {
    "sudo",
    "su",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
}

# D-03: literal (unexpanded) rm targets that are dangerous. Match the literal
# token as the model emits it — do not call os.path.expanduser/os.environ
# (RESEARCH Pitfall 3).
_RM_DANGEROUS_TARGETS: set[str] = {
    "/",
    "~",
    "/*",
    "$HOME",
    ".",
}

# D-03: dd/mkfs* targeting raw block devices.
_DEVICE_GLOB = "/dev/*"
_DEVICE_PREFIXES = ("sd", "nvme", "hd")

# D-03: fork-bomb pattern, matched via regex over the joined argv so both the
# spaced 3-token form (`:(){`, `:|:&`, `};:`) and the unspaced single-token
# form (`:(){:|:&};:`) are caught (WR-02).
_FORK_BOMB_RE = re.compile(r":\s*\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")

# find flags that introduce a wrapped command terminated by ';' or '+'.
_FIND_EXEC_FLAGS: set[str] = {"-exec", "-execdir", "-ok", "-okdir"}


def _is_dangerous_device_arg(arg: str) -> bool:
    """Return True if `arg` (possibly `key=value`-shaped, e.g. dd's `of=...`)
    refers to a raw block device under /dev/sd*, /dev/nvme*, or /dev/hd*."""
    # dd uses if=/of= prefixes; mkfs* takes a bare path. Strip any "key="
    # prefix before matching so both shapes are handled uniformly.
    path = arg.split("=")[-1]
    if not fnmatch.fnmatch(path, _DEVICE_GLOB):
        return False
    device_name = path.removeprefix("/dev/")
    return device_name.startswith(_DEVICE_PREFIXES)


def _unwrap_env(argv: list[str]) -> list[str]:
    """Return the wrapped command argv from an `env ...` invocation.

    Skips env's own flags (e.g. `-i`, `-u`) and leading `KEY=VALUE`
    assignments to find where the wrapped command begins. Returns `[]` if
    no wrapped command is found (e.g. `env` alone, or `env -i`)."""
    for i, arg in enumerate(argv[1:], start=1):
        if arg.startswith("-"):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", arg):
            continue
        return argv[i:]
    return []


def _unwrap_find_exec(argv: list[str]) -> list[str]:
    """Return the wrapped command argv from a `find ... -exec ... ;` (or `+`)
    invocation. Returns `[]` if no exec-style flag is present."""
    for i, arg in enumerate(argv):
        if arg in _FIND_EXEC_FLAGS:
            wrapped: list[str] = []
            for tok in argv[i + 1:]:
                if tok in (";", "+"):
                    break
                wrapped.append(tok)
            return wrapped
    return []


def _blocklist_match(argv: list[str]) -> str | None:
    """Return a human-readable BLOCK reason if argv matches a D-03 blocklist
    rule, else None. Checked in order; first match wins."""
    binary = argv[0]

    # (1) Hard-blocked binaries — no safe invocation.
    if binary in _HARD_BLOCKED_BINARIES:
        return f"'{binary}' is blocked outright (no safe invocation)"

    # (2) env wraps a command — recursively gate the wrapped command.
    if binary == "env":
        wrapped = _unwrap_env(argv)
        if wrapped:
            reason = _blocklist_match(wrapped)
            if reason is not None:
                return f"'env' wraps a blocked command: {reason}"

    # (3) find -exec/-execdir/-ok/-okdir wraps a command — recursively gate it.
    if binary == "find":
        wrapped = _unwrap_find_exec(argv)
        if wrapped:
            reason = _blocklist_match(wrapped)
            if reason is not None:
                return f"'find' -exec wraps a blocked command: {reason}"

    # (4) rm targeting a dangerous path.
    if binary == "rm":
        for arg in argv[1:]:
            if arg in _RM_DANGEROUS_TARGETS:
                return f"'rm' targeting '{arg}' is a dangerous deletion target"

    # (5) dd / mkfs* targeting a raw block device.
    if binary == "dd" or fnmatch.fnmatch(binary, "mkfs*"):
        for arg in argv[1:]:
            if _is_dangerous_device_arg(arg):
                return f"'{binary}' targeting raw block device '{arg}' is destructive"

    # (6) Fork-bomb pattern.
    if _FORK_BOMB_RE.search(" ".join(argv)):
        return "fork-bomb pattern detected"

    # (7) chmod/chown -R on /.
    if binary in ("chmod", "chown") and "-R" in argv and "/" in argv:
        return f"'{binary} -R' targeting '/' is destructive"

    return None


def check(argv: list[str], yes: bool) -> Decision:
    """Classify a resolved shell argv as ALLOW, CONFIRM, or BLOCK.

    `yes` does not change the gate decision (D-04); it only affects whether
    loop.py prompts for a CONFIRM result.
    """
    if not argv:
        return {"kind": "BLOCK", "reason": "empty command"}

    reason = _blocklist_match(argv)
    if reason is not None:
        return {"kind": "BLOCK", "reason": reason}

    if argv[0] in ALLOWLIST:
        return {"kind": "ALLOW"}

    return {"kind": "CONFIRM"}
