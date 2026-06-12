"""Pure safety-gate decision: blocklist/allowlist check against resolved argv."""

import fnmatch
from typing import Literal, NotRequired, TypedDict


class Decision(TypedDict):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]
    reason: NotRequired[str]  # present only when kind == "BLOCK"


# D-01: whole-binary allowlist — read-only, side-effect-free commands that
# auto-run without a confirm prompt. Matches argv[0] only (D-02).
ALLOWLIST: set[str] = {
    "ls",
    "pwd",
    "cat",
    "echo",
    "find",
    "grep",
    "head",
    "tail",
    "wc",
    "file",
    "date",
    "whoami",
    "env",
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

# D-03: fork-bomb pattern, matched as an exact argv equality.
_FORK_BOMB_TOKENS = [":(){", ":|:&", "};:"]


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


def _blocklist_match(argv: list[str]) -> str | None:
    """Return a human-readable BLOCK reason if argv matches a D-03 blocklist
    rule, else None. Checked in order; first match wins."""
    binary = argv[0]

    # (1) Hard-blocked binaries — no safe invocation.
    if binary in _HARD_BLOCKED_BINARIES:
        return f"'{binary}' is blocked outright (no safe invocation)"

    # (2) rm targeting a dangerous path.
    if binary == "rm":
        for arg in argv[1:]:
            if arg in _RM_DANGEROUS_TARGETS:
                return f"'rm' targeting '{arg}' is a dangerous deletion target"

    # (3) dd / mkfs* targeting a raw block device.
    if binary == "dd" or fnmatch.fnmatch(binary, "mkfs*"):
        for arg in argv[1:]:
            if _is_dangerous_device_arg(arg):
                return f"'{binary}' targeting raw block device '{arg}' is destructive"

    # (4) Fork-bomb pattern.
    if argv == _FORK_BOMB_TOKENS:
        return "fork-bomb pattern detected"

    # (5) chmod/chown -R on /.
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
