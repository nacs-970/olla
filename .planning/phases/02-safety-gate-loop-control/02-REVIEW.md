---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/olla/cli.py
  - src/olla/loop.py
  - src/olla/safety.py
  - tests/test_cli.py
  - tests/test_loop.py
  - tests/test_safety.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-12T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the safety-gate (`safety.py`) and loop-control (`loop.py`, `cli.py`) implementation plus their test suites. The dry-run preview, repetition guard, and CONFIRM/ALLOW/BLOCK plumbing through `run_loop` are implemented coherently and well covered by tests for the scenarios they target.

However, the allowlist design has a critical gap: `check()` only inspects `argv[0]` against the blocklist/allowlist, but two allowlisted binaries (`env`, `find`) can execute **arbitrary subcommands** as their own arguments. This means a model can trivially bypass the entire blocklist and CONFIRM gate — including the "hard-blocked" binaries and `rm` dangerous-target rules — by prefixing the real command with `env` or wrapping it in `find ... -exec`. Given the project's explicit non-negotiable safety requirement ("blocklist, confirm-gating, and dry-run are non-negotiable from v1") and the D-01 comment's claim that the allowlist is "read-only, side-effect-free," this directly contradicts the documented invariant and is a real, exploitable bypass.

Two additional warnings: the repetition guard does not cover BLOCK or declined-CONFIRM outcomes (a model that repeatedly emits the same blocked/declined command runs unguarded until max-steps), and the fork-bomb blocklist rule uses brittle exact-list matching that misses a syntactically valid alternate spelling of the same pattern.

## Critical Issues

### CR-01: Allowlisted `env` and `find` allow arbitrary command execution with zero confirmation

**File:** `src/olla/safety.py:14-28` and `src/olla/safety.py:103-119`
**Issue:**

`check()` classifies a command as `ALLOW` (auto-run, no confirmation, no blocklist re-check of the *effective* command) purely based on `argv[0]` membership in `ALLOWLIST`. `ALLOWLIST` includes `env` and `find`, both of which can execute arbitrary subcommands as part of their normal argument syntax:

- `env CMD [ARGS...]` runs `CMD` with a modified environment when any non-`KEY=VALUE` argument is given. `env rm -rf /` executes `rm -rf /` directly.
- `find ... -exec CMD {} ;` (or `+`) executes `CMD` for every matched path. `find . -exec rm -rf {} \;` deletes recursively with zero confirmation.

Verified directly against the shipped `check()`:

```python
>>> check(['env', 'rm', '-rf', '/'], yes=False)
{'kind': 'ALLOW'}
>>> check(['env', 'sudo', 'ls'], yes=False)
{'kind': 'ALLOW'}
>>> check(['find', '.', '-exec', 'rm', '-rf', '{}', ';'], yes=False)
{'kind': 'ALLOW'}
```

This means:
1. The "hard-blocked" binaries (`sudo`, `su`, `shutdown`, `reboot`, `poweroff`, `halt`) can all be invoked via `env <binary> ...` and run with **zero gate**.
2. The `rm` dangerous-target blocklist (`/`, `~`, `/*`, `$HOME`, `.`) is bypassed entirely via `env rm -rf /` or `find . -exec rm -rf / ;`.
3. `dd`/`mkfs*` raw-device blocks are bypassable the same way (`env dd if=/dev/zero of=/dev/sda`).

This contradicts the D-01 comment's claim that `ALLOWLIST` contains only "read-only, side-effect-free commands" and undermines the entire safety design — a 0.6B-7B model emitting `env rm -rf /` (which is a plausible hallucination pattern, e.g. "set env var then run command") would execute it with no confirmation and no observable warning.

**Fix:**

Remove `env` and `find` from the whole-binary allowlist (both are not actually side-effect-free in the general case), or special-case them:

```python
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
    # "env" and "find" removed: both can execute arbitrary subcommands
    # (env CMD..., find ... -exec CMD ...) and must go through CONFIRM.
}
```

If `env`/`find` are needed for read-only use (e.g. `env` to inspect variables, `find` to search paths), add a targeted check that demotes them to `CONFIRM` (or `BLOCK`) when dangerous flags/arguments are present:

```python
def _blocklist_match(argv: list[str]) -> str | None:
    ...
    # env with any non-KEY=VALUE argument executes an arbitrary command.
    if binary == "env":
        for arg in argv[1:]:
            if "=" not in arg.split("/")[-1]:
                return "'env' with a command argument can execute arbitrary commands"

    # find with -exec/-execdir/-ok/-okdir executes arbitrary commands.
    if binary == "find" and any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in argv[1:]):
        return "'find' with -exec/-execdir/-ok/-okdir can execute arbitrary commands"
```

At minimum, `env` and `find` should not be in the auto-run `ALLOWLIST` — fall through to `CONFIRM` so a human reviews the actual argv before it runs.

## Warnings

### WR-01: Repetition guard does not cover BLOCK or declined-CONFIRM outcomes

**File:** `src/olla/loop.py:97-123`
**Issue:**

The repetition guard (`prev_sig`/`repeat_count`, intended to detect "model likely stuck") is only updated when execution reaches line 114 — i.e., after a `BLOCK` or a declined `CONFIRM` has already taken the `continue` branch at lines 103 and 111-112. A model that repeatedly emits the exact same `BLOCK`ed command (e.g. `rm -rf /`, 15 times in a row) or the exact same `CONFIRM`-tier command that a user keeps declining will never trip the "same shell call repeated 3x — model likely stuck" guard, and will run all the way to `max_steps` instead of stopping early at 3 repeats.

This is the same "model likely stuck" scenario the guard is meant to catch, just for a different decision tier — the current implementation only catches it for commands that actually executed.

**Fix:** Compute the signature and update `prev_sig`/`repeat_count` before branching on the decision (or in all three branches), and check `repeat_count >= 3` regardless of which branch is taken:

```python
sig = ("shell", tuple(argv))
if sig == prev_sig:
    repeat_count += 1
else:
    prev_sig = sig
    repeat_count = 1

if repeat_count >= 3:
    print("olla stopped: same shell call repeated 3x — model likely stuck")
    return

if decision["kind"] == "BLOCK":
    ...
    continue

if decision["kind"] == "CONFIRM" and not yes:
    ...
    if not approved:
        ...
        continue

print(f"Step {step}: running {argv}...")
...
```

### WR-02: Fork-bomb blocklist rule uses brittle exact-list matching, misses common alternate spelling

**File:** `src/olla/safety.py:55-56, 92-94`
**Issue:**

`_FORK_BOMB_TOKENS = [":(){", ":|:&", "};:"]` and `_blocklist_match` checks `argv == _FORK_BOMB_TOKENS` (exact 3-element list equality). This only matches the spaced form `:(){ :|:& };:`. The equally valid, unspaced form `:(){:|:&};:` produces `shlex.split` → `[':(){:|:&};:']`, a single-element list that does **not** equal `_FORK_BOMB_TOKENS`, so it falls through to `CONFIRM` (since `:(){:|:&};:` is not in `ALLOWLIST`) instead of `BLOCK`.

Verified:
```python
>>> shlex.split(':(){ :|:& };:')
[':(){', ':|:&', '};:']   # matches _FORK_BOMB_TOKENS -> BLOCK
>>> shlex.split(':(){:|:&};:')
[':(){:|:&};:']           # does not match -> CONFIRM
```

While `CONFIRM` still requires a human (or `--yes`) to proceed, the D-03 comment frames this rule as a hard block for a pattern with "no safe invocation," and the exact-list approach gives a false sense of coverage — any whitespace variation defeats it.

**Fix:** Match on a normalized/substring basis instead of exact list equality, e.g. check whether the joined argv contains the fork-bomb signature regardless of tokenization:

```python
import re

_FORK_BOMB_RE = re.compile(r":\s*\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")

# in _blocklist_match:
if _FORK_BOMB_RE.search(" ".join(argv)):
    return "fork-bomb pattern detected"
```

## Info

### IN-01: `run_shell` re-parses `args_raw` that `run_loop` already parsed

**File:** `src/olla/loop.py:90, 127`
**Issue:**

`run_loop` calls `shlex.split(parsed["args_raw"])` at line 90 to obtain `argv` for the safety check, then at line 127 passes the original raw string `parsed["args_raw"]` to `run_shell`, which calls `shlex.split` again internally (`src/olla/tools/shell.py:16`). This is redundant — `shlex.split` is deterministic so the two calls always agree, but it's wasted work and a minor coupling smell (two call sites must stay in sync on parsing semantics).

**Fix:** Have `run_shell` accept the already-parsed `argv` directly (or add an `argv`-accepting variant), avoiding double parsing:

```python
# tools/shell.py
def run_shell(argv: list[str], timeout: int = 30) -> ToolResult:
    if not argv:
        return {"argv": argv, "error": "empty command"}
    try:
        result = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout)
        ...
```

```python
# loop.py
result = run_shell(argv)
```

---

_Reviewed: 2026-06-12T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
