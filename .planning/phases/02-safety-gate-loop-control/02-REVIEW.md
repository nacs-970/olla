---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-13T00:00:00Z
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

**Reviewed:** 2026-06-13T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a re-review after 02-03 (gap closure for CR-01, WR-01, WR-02 from the prior 02-REVIEW.md). The full test suite passes (88 tests).

The repetition-guard reordering (WR-01) is sound: `sig`/`repeat_count` are now computed immediately after `argv` is parsed, before `decision = check(argv, yes=yes)`, so a 3x-repeated BLOCK or declined-CONFIRM call now aborts before `max_steps`. `_blocklist_match`'s `if not argv` short-circuit in `check()` prevents the empty-argv crash that the new code path could otherwise hit.

However, **CR-01 (the env/find ALLOWLIST bypass) is only partially closed.** The recursive `_unwrap_env`/`_unwrap_find_exec` helpers correctly handle the simple cases tested (`env rm -rf /`, `env sudo ls`, `find / -exec sudo rm {} ;`), but both have enumeration gaps that let a "hard-blocked, no safe invocation" binary (e.g. `sudo`) reach **CONFIRM** instead of **BLOCK** — for example `env -u FOO sudo rm -rf /` and `find . -exec true ; -exec sudo rm -rf / ;`. Per `loop.py:116` (`if decision["kind"] == "CONFIRM" and not yes:`), a CONFIRM decision under `--yes` skips the prompt entirely and runs unconfirmed — which directly contradicts the tested invariant in `test_yes_does_not_change_block_kind` / `test_run_loop_block_tier_with_yes_still_blocks` that hard-blocked binaries stay blocked regardless of `--yes`. This is the same root cause as the original CR-01 (incomplete modeling of how a wrapper binary introduces a subcommand), now manifesting one tier lower.

Additionally, the WR-02 fork-bomb fix (switching from exact-list matching to a regex over `" ".join(argv)`) trades a false negative for a new false positive: a harmless `echo` of the fork-bomb string as data (e.g. documentation, a warning message) now gets BLOCKed, where it previously resolved to ALLOW (since `echo` is allowlisted and the old exact-3-token-list check never matched a 2-element argv).

A pre-existing issue (in scope for this review, not part of 02-03's diff) is also noted: rule (7) for `chmod`/`chown -R /` only matches the exact token `-R`, so combined short flags like `-Rf` bypass it down to CONFIRM.

## Critical Issues

### CR-01 (re-opened, narrower): `env`/`find -exec` unwrap helpers miss flag-with-argument and multi-clause forms, letting hard-blocked binaries reach CONFIRM and execute unconfirmed under `--yes`

**File:** `src/olla/safety.py:78-104`
**Issue:**

`_unwrap_env` assumes any non-flag, non-`KEY=VALUE` token is the start of the wrapped command. This breaks for `env` flags that take a **separate argument**, such as `-C DIR` (`--chdir`), `-u NAME` (`--unset`), `-a ARG` (`--argv0`), and `-S STRING` (`--split-string`). The argument to these flags is itself a non-`-`-prefixed, non-`KEY=VALUE` token, so `_unwrap_env` mistakes it for the wrapped command's binary:

```python
>>> _unwrap_env(["env", "-u", "FOO", "sudo", "rm", "-rf", "/"])
['FOO', 'sudo', 'rm', '-rf', '/']   # "FOO" is treated as argv[0] of the wrapped command
>>> _blocklist_match(['FOO', 'sudo', 'rm', '-rf', '/'])
None   # "FOO" matches nothing -> falls through
>>> check(["env", "-u", "FOO", "sudo", "rm", "-rf", "/"], yes=False)
{'kind': 'CONFIRM'}   # should be BLOCK ("sudo" is hard-blocked)
```

Similarly, `_unwrap_find_exec` only inspects the **first** `-exec`/`-execdir`/`-ok`/`-okdir` clause it encounters and stops (`for i, arg in enumerate(argv): ... return wrapped`). A `find` invocation with multiple `-exec` clauses has every clause after the first executed unchecked:

```python
>>> check(["find", ".", "-exec", "true", ";", "-exec", "sudo", "rm", "-rf", "/", ";"], yes=False)
{'kind': 'CONFIRM'}   # second clause "sudo rm -rf /" never inspected; should be BLOCK
```

Both cases land at `CONFIRM`, not `ALLOW` — so interactively, a human still sees a prompt. But `loop.py:116` skips the CONFIRM prompt entirely when `yes=True`:

```python
if decision["kind"] == "CONFIRM" and not yes:
    ...prompt...
```

This means running olla with `--yes` and a model that emits `env -u FOO sudo rm -rf /` (or the multi-`-exec` find form) executes `sudo rm -rf /` with **zero gating** — directly violating the invariant encoded by `test_yes_does_not_change_block_kind` and `test_run_loop_block_tier_with_yes_still_blocks` (hard-blocked binaries must stay BLOCK regardless of `--yes`). This is the same class of bug as the original CR-01 (allowlist/blocklist classification based on an incomplete model of how a wrapper introduces a subcommand) — 02-03 closed the cases it tested but did not close the general case.

**Fix:**

For `_unwrap_env`, track which env flags consume a following argument and skip that argument too:

```python
_ENV_FLAGS_WITH_ARG: set[str] = {"-u", "--unset", "-C", "--chdir", "-a", "--argv0", "-S", "--split-string"}

def _unwrap_env(argv: list[str]) -> list[str]:
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in _ENV_FLAGS_WITH_ARG:
            i += 2  # skip flag and its argument
            continue
        if arg.startswith("-"):
            i += 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", arg):
            i += 1
            continue
        return argv[i:]
    return []
```

(Note: `--chdir=DIR`/`--unset=NAME`/etc. with `=` are already handled correctly since they start with `-`.)

For `_unwrap_find_exec`, check **all** `-exec`-family clauses, not just the first, and BLOCK if any clause is dangerous:

```python
def _unwrap_find_exec(argv: list[str]) -> list[list[str]]:
    """Return all wrapped-command argvs from `find ... -exec ... ;|+` clauses."""
    clauses: list[list[str]] = []
    i = 0
    while i < len(argv):
        if argv[i] in _FIND_EXEC_FLAGS:
            wrapped: list[str] = []
            for tok in argv[i + 1:]:
                if tok in (";", "+"):
                    break
                wrapped.append(tok)
            if wrapped:
                clauses.append(wrapped)
            i += 1 + len(wrapped) + 1
            continue
        i += 1
    return clauses

# in _blocklist_match:
if binary == "find":
    for wrapped in _unwrap_find_exec(argv):
        reason = _blocklist_match(wrapped)
        if reason is not None:
            return f"'find' -exec wraps a blocked command: {reason}"
```

Given the `--yes` interaction, treat this as the same severity as the original CR-01: a model-emitted `env`/`find` wrapper around `sudo`/`rm -rf /`/etc. must resolve to `BLOCK`, not `CONFIRM`, for the documented "stays blocked regardless of `--yes`" guarantee to hold.

## Warnings

### WR-02 (regression): Fork-bomb regex now false-positives on the pattern as literal data

**File:** `src/olla/safety.py:60, 145-146`
**Issue:**

`_FORK_BOMB_RE.search(" ".join(argv))` matches the fork-bomb signature anywhere in the joined argv string, including inside a quoted string argument that is pure data (not shell syntax). Before WR-02, the check was `argv == _FORK_BOMB_TOKENS` (exact 3-element equality), so a 2-element argv like `["echo", ":(){ :|:& };:"]` never matched and `echo` (allowlisted) resolved to `ALLOW`.

After WR-02, the same command is BLOCKed:

```python
>>> check(["echo", "Avoid running :(){ :|:& };: it's a fork bomb"], yes=False)
{'kind': 'BLOCK', 'reason': 'fork-bomb pattern detected'}
```

This is a genuinely harmless command (printing a warning/documentation string) that now cannot run at all — a usability regression introduced by the fix for the unspaced-fork-bomb gap (WR-02). The fix correctly closed a false negative but opened a false positive on the same surface.

**Fix:** Restrict the fork-bomb check to `argv[0]` (or the unwrapped command's `argv[0]`/full argv when the entire command *is* the fork-bomb pattern, e.g. via `bash -c`), rather than matching arbitrary substrings of arbitrary arguments:

```python
# Only flag when the fork-bomb pattern is itself the command being run
# (argv[0] or the sole argument to a shell -c invocation), not when it
# appears as a string literal inside another command's arguments.
if _FORK_BOMB_RE.search(argv[0]):
    return "fork-bomb pattern detected"
if binary in ("bash", "sh", "zsh") and "-c" in argv:
    c_index = argv.index("-c")
    if len(argv) > c_index + 1 and _FORK_BOMB_RE.search(argv[c_index + 1]):
        return "fork-bomb pattern detected"
```

### WR-03 (pre-existing): `chmod`/`chown -R /` rule misses combined short flags

**File:** `src/olla/safety.py:148-150`
**Issue:**

Rule (7) checks `"-R" in argv and "/" in argv` — an exact-token match. Combined short flags bypass it:

```python
>>> check(["chmod", "-Rf", "777", "/"], yes=False)
{'kind': 'CONFIRM'}   # "-Rf" != "-R", so the rule never fires
```

`chmod -Rf 777 /` is just as destructive as `chmod -R 777 /` (recursive chmod on root), but resolves to `CONFIRM` instead of `BLOCK`. This is in scope for this review (not part of the 02-03 diff, but a real gap in the D-03 blocklist that adversarial review should surface) — it follows the same "combined-flags evade exact-token matching" pattern as the original `_FORK_BOMB_TOKENS` issue.

**Fix:** Match any `-` flag token that contains `R` (and starts with `-`, not `--`) alongside `chmod`/`chown`:

```python
if binary in ("chmod", "chown") and "/" in argv:
    if any(a.startswith("-") and not a.startswith("--") and "R" in a for a in argv[1:]):
        return f"'{binary} -R' targeting '/' is destructive"
```

(GNU long-form `--recursive` should also be checked if relevant to this project's supported coreutils.)

## Info

### IN-01: `run_shell` re-parses `args_raw` that `run_loop` already parsed

**File:** `src/olla/loop.py:90, 127`
**Issue:**

`run_loop` calls `shlex.split(parsed["args_raw"])` at line 90 to obtain `argv` for the safety check (and now also for the repetition-guard signature), then at line 127 passes the original raw string `parsed["args_raw"]` to `run_shell`, which calls `shlex.split` again internally (`src/olla/tools/shell.py:16`). Still present after 02-03 — carried forward from the prior review, unaddressed.

**Fix:** Have `run_shell` accept the already-parsed `argv` directly:

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

_Reviewed: 2026-06-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
