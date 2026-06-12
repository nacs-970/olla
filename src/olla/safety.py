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

# D-03: fork-bomb pattern, matched via regex so both the spaced 3-token form
# (`:(){`, `:|:&`, `};:`) and the unspaced single-token form (`:(){:|:&};:`)
# are caught. Matched with .match() (anchored at position 0 of the joined
# argv) rather than .search(), so that argv[0] itself being fork-bomb syntax
# is BLOCKed, but the same text appearing later as a *data* argument to an
# unrelated command (e.g. `echo "...:(){ :|:& };:..."`) is not (WR-02 false
# positive). The separate `bash/sh/zsh -c <command>` case is checked
# explicitly below with .search() against just that argument, since that
# argument *is* the command to be executed by the shell.
_FORK_BOMB_RE = re.compile(r":\s*\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")

# find flags that introduce a wrapped command terminated by ';' or '+'.
_FIND_EXEC_FLAGS: set[str] = {"-exec", "-execdir", "-ok", "-okdir"}

# env flags that take a separate following argument (must skip both tokens
# when unwrapping, else the flag's argument is mistaken for the wrapped
# command's binary name) (CR-01).
_ENV_FLAGS_WITH_ARG: set[str] = {"-u", "--unset", "-C", "--chdir", "-a", "--argv0", "-S", "--split-string"}


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
    assignments to find where the wrapped command begins. Flags in
    `_ENV_FLAGS_WITH_ARG` (e.g. `-u FOO`, `-C /tmp`) consume their following
    argument as well, so both tokens are skipped (CR-01). Returns `[]` if
    no wrapped command is found (e.g. `env` alone, `env -i`, or `env -S
    "..."` where the wrapped command is embedded in a single string argument
    rather than as separate argv elements)."""
    i = 1
    while i < len(argv):
        if argv[i] in _ENV_FLAGS_WITH_ARG:
            i += 2
            continue
        if argv[i].startswith("-"):
            i += 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[i]):
            i += 1
            continue
        return argv[i:]
    return []


def _unwrap_find_exec(argv: list[str]) -> list[list[str]]:
    """Return the wrapped command argvs from every `-exec`/`-execdir`/`-ok`/
    `-okdir ... ;` (or `+`) clause in a `find` invocation (CR-01: a single
    `find` call may chain multiple -exec clauses, any of which may wrap a
    blocked command). Empty clauses are skipped. Returns `[]` if no
    exec-style flag is present."""
    clauses: list[list[str]] = []
    for i, arg in enumerate(argv):
        if arg in _FIND_EXEC_FLAGS:
            wrapped: list[str] = []
            for tok in argv[i + 1:]:
                if tok in (";", "+"):
                    break
                wrapped.append(tok)
            if wrapped:
                clauses.append(wrapped)
    return clauses


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

    # (3) find -exec/-execdir/-ok/-okdir wraps a command — recursively gate
    # every clause (a single find call may chain multiple -exec clauses).
    if binary == "find":
        for wrapped in _unwrap_find_exec(argv):
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

    # (6) Fork-bomb pattern: argv[0] (joined with the rest) is itself
    # fork-bomb syntax, anchored so data arguments to other commands don't
    # false-positive (WR-02).
    joined = " ".join(argv)
    if _FORK_BOMB_RE.match(joined):
        return "fork-bomb pattern detected"

    # (6b) Fork-bomb pattern passed as the command string to bash/sh/zsh -c.
    if binary in ("bash", "sh", "zsh") and "-c" in argv:
        c_index = argv.index("-c")
        if len(argv) > c_index + 1 and _FORK_BOMB_RE.search(argv[c_index + 1]):
            return "fork-bomb pattern detected"

    # (7) chmod/chown -R (including combined short flags like -Rf) on /.
    if binary in ("chmod", "chown") and "/" in argv:
        if any(a.startswith("-") and not a.startswith("--") and "R" in a for a in argv[1:]):
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
