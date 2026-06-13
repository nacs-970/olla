---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/olla/safety.py
  - tests/test_safety.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

This review covers `src/olla/safety.py` (entirely new in this diff range) and `tests/test_safety.py` (62 tests, all passing — `.venv/bin/python -m pytest tests/test_safety.py -q` → `62 passed`). The module implements the D-01..D-04 risk-tiered ALLOW/CONFIRM/BLOCK decision logic, including the round-3/round-4 equivalent-form hardening (`bash -lc`, doubled-leading-slash, dot-segment root targets) from the prior `02-REVIEW.md`. Those three previously-identified CR-01/02/03 issues are verified fixed against the live code.

One **critical** issue was found: the module imports `typing.NotRequired`, which is Python 3.11+ (PEP 655), but `pyproject.toml` declares `requires-python = ">=3.10"` with no `typing_extensions` fallback dependency — this will crash at import time (`ImportError`) on the project's own declared minimum Python version.

The remaining findings are inconsistencies and documented residual gaps in the blocklist's equivalent-form coverage: an asymmetry where the round-4 dot-segment normalization was applied to `chmod`/`chown -R` (rule 7) but not to `rm` (rule 4) — leaving the strictly more destructive `rm -rf /.` as `CONFIRM` while `chmod -R 777 /.` is `BLOCK` — plus the previously-documented `env -S` and shell-chained `bash -c "...; sudo ..."` residuals, both of which become unattended-execution risks under `--yes`.

## Critical Issues

### CR-01: `from typing import NotRequired` requires Python 3.11+, but the project declares `requires-python = ">=3.10"` with no fallback

**File:** `src/olla/safety.py:7`
**Issue:**

```python
from typing import Literal, NotRequired, TypedDict


class Decision(TypedDict):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]
    reason: NotRequired[str]  # present only when kind == "BLOCK"
```

`typing.NotRequired` was added in Python 3.11 (PEP 655). `pyproject.toml` declares `requires-python = ">=3.10"` (matching CLAUDE.md's stated "Python >=3.10" floor) and lists no `typing_extensions` dependency. On a genuine Python 3.10 interpreter, `pip install olla` succeeds (the version constraint is satisfied), but `import olla.safety` — and therefore `import olla` itself, since `safety` is a core module used by `loop`/`cli` — raises:

```
ImportError: cannot import name 'NotRequired' from 'typing'
```

This crashes the entire CLI at startup on 3.10, not just a degraded code path. `Literal`, `TypedDict`, `match` statements, `X | Y` union syntax, `list[str]`, and `str.removeprefix` are all available since 3.10/3.8, so `NotRequired` is the *only* symbol in this file requiring 3.11+ — this is an isolated, easily-fixed incompatibility, not a sign the whole module needs a floor bump.

This was not caught by the local dev environment because the project's `.venv` runs Python 3.14, where `NotRequired` is available.

**Fix:** Pick one:

1. Bump the floor to match reality:
```toml
# pyproject.toml
requires-python = ">=3.11"
```
(and update CLAUDE.md's stated ">=3.10" constraint accordingly), **or**

2. Keep the >=3.10 floor and use the `typing_extensions` backport:
```python
from typing import Literal, TypedDict
from typing_extensions import NotRequired
```
```toml
# pyproject.toml
dependencies = [
    "ollama>=0.6.2",
    "click>=8.1,<9",
    "rich>=13",
    "typing_extensions>=4.0; python_version < '3.11'",
]
```
**or**

3. Drop `NotRequired` and use `total=False` with a comment, since `Decision` only has one optional key:
```python
class Decision(TypedDict, total=False):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]  # NB: total=False makes ALL keys optional;
    reason: str                                  # acceptable here since callers always set `kind`.
```
(Option 3 is the cheapest but weakens the type-checker guarantee that `kind` is always present — option 1 or 2 is preferred.)

## Warnings

### WR-01: Round-4 dot-segment normalization (rule 7) was not applied to `rm`'s dangerous-target check (rule 4) — `rm -rf /.` stays `CONFIRM` while `chmod -R 777 /.` is `BLOCK`

**File:** `src/olla/safety.py:183-186, 235-243`
**Issue:**

Rule 7 (`chmod`/`chown -R`) was hardened in 02-07 to treat dot-segment forms as equivalent to `/`:

```python
if binary in ("chmod", "chown") and any(
    _normalize_slash_target(a) == "/" or os.path.normpath(a).rstrip("/") == ""
    for a in argv[1:]
):
```

Rule 4 (`rm`) only normalizes doubled leading slashes and checks set membership against the literal `_RM_DANGEROUS_TARGETS = {"/", "~", "/*", "$HOME", "."}`:

```python
if binary == "rm":
    for arg in argv[1:]:
        if _normalize_slash_target(arg) in _RM_DANGEROUS_TARGETS:
            return f"'rm' targeting '{arg}' is a dangerous deletion target"
```

`os.path.normpath("/.")`, `os.path.normpath("/..")`, and `os.path.normpath("/foo/..")` all resolve to `"/"`, but none of these literal strings are in `_RM_DANGEROUS_TARGETS`, and `_normalize_slash_target` (anchored to doubled-slash-only forms) doesn't touch them either. Verified empirically:

```python
>>> check(["rm", "-rf", "/."], yes=True)
{'kind': 'CONFIRM'}
>>> check(["rm", "-rf", "/.."], yes=True)
{'kind': 'CONFIRM'}
>>> check(["rm", "-rf", "/foo/.."], yes=True)
{'kind': 'CONFIRM'}
>>> check(["chmod", "-R", "777", "/."], yes=True)
{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}
```

This is the same equivalent-form class the 02-07 round closed for `chmod`/`chown`, but `rm -rf <path>` is strictly more destructive than `chmod -R 777 <path>` — and under `--yes`, a `CONFIRM`-tier `rm -rf /.` runs unattended. The 02-07 summary notes this as accepted residual T-02-07-03 with rationale "lower severity due to `--preserve-root` default" — but `--preserve-root` is `rm`'s *default* only for the literal `/` argument; GNU coreutils' `--preserve-root` does protect `/.`/`/..` style arguments too in modern versions, but this is a property of the *target system's* `rm` binary, not something this module verifies — relying on it as the safety backstop is fragile, and it provides no protection at all for `/*` (e.g. `rm -rf /foo/../*`, `rm -rf /*` itself is already in `_RM_DANGEROUS_TARGETS` but `/foo/../*` is not).

**Fix:** Apply the same `os.path.normpath(a).rstrip("/") == ""` disjunct used in rule 7 to rule 4's target check, or extend `_normalize_slash_target` to cover dot-segment forms for both rules:

```python
if binary == "rm":
    for arg in argv[1:]:
        if _normalize_slash_target(arg) in _RM_DANGEROUS_TARGETS or os.path.normpath(arg).rstrip("/") == "":
            return f"'rm' targeting '{arg}' is a dangerous deletion target"
```

Add regression tests: `check(["rm", "-rf", "/."], yes=True)["kind"] == "BLOCK"`, and the `/..`, `/foo/..` variants.

---

### WR-02: `env -S`/`--split-string` remains an unprotected wrap-and-recurse path (documented residual T-02-07-05) — under `--yes`, `env -S "sudo rm -rf /"` runs unattended

**File:** `src/olla/safety.py:76, 111-133`
**Issue:**

`_ENV_FLAGS_WITH_ARG` includes `-S`/`--split-string`, so `_unwrap_env(["env", "-S", "sudo rm -rf /"])` skips both tokens (`-S` and its argument) and returns `[]` — no wrapped command is found, so rule 2 (`env wraps a blocked command`) never fires:

```python
>>> check(["env", "-S", "sudo rm -rf /"], yes=True)
{'kind': 'CONFIRM'}
```

`env -S "<command>"` re-splits its single string argument into a command at runtime via `wordsplit(3)`-like semantics — functionally identical to `bash -c "<command>"`, which rule 6b *does* shlex-split and recurse into. This means a model that has `bash -c "sudo ..."` (and its `-lc`/`-ic`/`-xc` combined-flag variants) blocked has `env -S "sudo rm -rf /"` as a remaining one-step escape. This is documented as accepted residual T-02-07-05 in `02-07-SUMMARY.md`, but it sits in the same vulnerability class as the CR-01 `bash -c` fix and represents a live unattended-execution path under `--yes`.

**Fix:** Extend `_unwrap_env` (or add a dedicated check in `_blocklist_match` for `binary == "env"`) to shlex-split and recurse into `-S`/`--split-string`'s argument, mirroring rule 6b:

```python
def _unwrap_env(argv: list[str]) -> list[str]:
    i = 1
    while i < len(argv):
        if argv[i] in ("-S", "--split-string") and i + 1 < len(argv):
            try:
                return shlex.split(argv[i + 1])
            except ValueError:
                return []
        if argv[i] in _ENV_FLAGS_WITH_ARG:
            i += 2
            continue
        ...
```

Update `test_env_split_string_flag_wrapping_sudo_confirms` to assert `BLOCK` (and rename it accordingly), and add a fork-bomb-via-`env -S` regression test mirroring rule 6b's `_FORK_BOMB_RE.search(c_string)` check.

---

### WR-03: Shell-chained commands inside `bash/sh/zsh -c "..."` (`&&`, `;`, `|`) bypass rule 6b's single-command recursion (documented residual T-02-06-05) — under `--yes`, `bash -c "true; sudo rm -rf /"` runs unattended

**File:** `src/olla/safety.py:212-228`
**Issue:**

Rule 6b shlex-splits the `-c` string and recurses `_blocklist_match` against the resulting argv as a *single* command:

```python
try:
    wrapped = shlex.split(c_string)
except ValueError:
    wrapped = []
if wrapped:
    reason = _blocklist_match(wrapped)
```

`shlex.split("true; sudo rm -rf /")` returns `["true;", "sudo", "rm", "-rf", "/"]` — a single flat list where `argv[0]` is `"true;"`, not `"sudo"`. `_blocklist_match` checks `argv[0]` (`"true;"`) against `_HARD_BLOCKED_BINARIES`/`ALLOWLIST`/etc., none of which match, so the entire chained command falls through to `CONFIRM`:

```python
>>> check(["bash", "-c", "true; sudo rm -rf /"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["bash", "-c", "echo hi && sudo rm -rf /"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["bash", "-c", "echo hi | sudo tee /etc/passwd"], yes=True)
{'kind': 'CONFIRM'}
```

This is documented as accepted residual T-02-06-05 ("shell-chained `-c` via `&&`/`;`/`|`"), and the project's own research notes frame the blocklist as "a speed-bump, not a boundary." Still, this is the most direct remaining bypass of the `bash -c "sudo ..."` protection added for CR-01/round-3: a model corrected once for `bash -c "sudo rm -rf /"` (observed `blocked by safety policy`) can trivially retry as `bash -c "echo retrying; sudo rm -rf /"`, which is `CONFIRM`, and under `--yes` executes the `sudo rm -rf /` half unattended with zero further gating.

**Fix:** No clean general fix exists without a real shell-command parser (out of scope per the project's "no XML parser for malformed tags" precedent applies analogously here — don't add a shell-grammar dependency for this). A pragmatic partial mitigation: split `c_string` on common shell metacharacters (`;`, `&&`, `||`, `|`, newline) via regex *before* `shlex.split`, and recurse `_blocklist_match` against each resulting segment independently:

```python
for segment in re.split(r"&&|\|\||[;|\n]", c_string):
    segment = segment.strip()
    if not segment:
        continue
    try:
        wrapped = shlex.split(segment)
    except ValueError:
        continue
    if wrapped:
        reason = _blocklist_match(wrapped)
        if reason is not None:
            return f"'{binary} -c' wraps a blocked command: {reason}"
```

This is itself imperfect (doesn't handle quoting that legitimately contains `;`/`|`, e.g. `bash -c 'echo "a;b"'` would be over-split — but over-blocking toward `CONFIRM`/`BLOCK` is the safe failure direction here). At minimum, document this residual more prominently in `safety.py`'s module docstring so future readers don't assume rule 6b is a complete `-c` defense.

## Info

### IN-01: `_blocklist_match` recursion (env, find -exec, bash/sh/zsh -c) has no explicit depth limit

**File:** `src/olla/safety.py:155-245`
**Issue:** `_blocklist_match` recurses for `env` (rule 2), `find -exec` (rule 3), and `bash/sh/zsh -c` (rule 6b), with no depth bound. Empirically, a 200-level `env env env ... sudo ls` chain resolves cleanly (`BLOCK`, with a correspondingly long nested reason string) well within Python's default recursion limit (1000). A pathological chain deep enough to hit `RecursionError` (~300+ levels for `env`, fewer for `bash -c` since each level requires `shlex.split` + nested quoting) would propagate an uncaught `RecursionError` out of `check()`. This is a low-probability input shape for a small local model to emit, but `check()`'s contract (return a `Decision`, never raise) would be silently broken.

**Fix:** Add a small depth counter (e.g. limit 10), returning a conservative `BLOCK` once exceeded:

```python
def _blocklist_match(argv: list[str], _depth: int = 0) -> str | None:
    if _depth > 10:
        return "command nesting too deep to safety-check"
    ...
    # pass _depth + 1 to each recursive call
```

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
