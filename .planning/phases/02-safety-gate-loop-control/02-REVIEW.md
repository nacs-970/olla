---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/olla/cli.py
  - src/olla/loop.py
  - src/olla/safety.py
  - src/olla/tools/shell.py
  - tests/test_cli.py
  - tests/test_loop.py
  - tests/test_safety.py
  - tests/test_tools/test_shell.py
findings:
  critical: 3
  warning: 4
  info: 3
  total: 10
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-13T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The safety gate (`safety.py`) is well-structured for the cases it explicitly enumerates — `env` and `find -exec` wrapping are correctly recursed, the fork-bomb regex is carefully anchored to avoid false positives on data arguments, and `yes` correctly does not change `BLOCK`/`CONFIRM` classification. The ReAct loop (`loop.py`) correctly threads truncation, repetition detection, and the dry-run preview through the safety gate, and all 96 tests in the listed test files pass (verified locally).

However, the blocklist has a critical, exploitable gap: **`bash`/`sh`/`zsh -c "<command>"` is only checked for the fork-bomb pattern, not for any other D-03 rule** (hard-blocked binaries, dangerous `rm` targets, raw-device `dd`/`mkfs`, `chmod -R /`). A model emitting `bash -c "sudo rm -rf /"` (or the equivalent via `find -exec sh -c ... ;`) receives `CONFIRM` instead of `BLOCK`, and with `--yes` it executes unconditionally — completely defeating the "no safe invocation" guarantee documented for `sudo`/`su`/etc. This is the same wrap-and-recurse problem the code already solves correctly for `env` and `find -exec`, just not extended to the shell `-c` family. Two related blocklist coverage gaps (`chmod --recursive /` long-flag, and `rm -rf //`) are also reachable end-to-end under `--yes` and should be fixed alongside it.

A secondary, lower-severity issue: `call_model()` (and `run_smoke_test`, which calls it with `think=True`) will raise an uncaught `KeyError: 'content'` if Ollama returns a message where only `thinking` is populated and `content` is entirely absent from the response payload — a real shape for thinking-capable models. This is not currently reachable from `run_loop` (which always calls with `think=False`, where `content` is reliably populated), but it is reachable from the smoke-test diagnostic path.

## Critical Issues

### CR-01: `bash`/`sh`/`zsh -c "<command>"` bypasses the entire D-03 blocklist except the fork-bomb check

**File:** `src/olla/safety.py:177-181`
**Issue:**
`_blocklist_match` recurses into the wrapped command for `env ...` (step 2) and `find -exec ...` (step 3), but the only handling for `bash`/`sh`/`zsh -c "<command>"` is step (6b), which `.search()`es the `-c` argument **only for the fork-bomb regex**:

```python
# (6b) Fork-bomb pattern passed as the command string to bash/sh/zsh -c.
if binary in ("bash", "sh", "zsh") and "-c" in argv:
    c_index = argv.index("-c")
    if len(argv) > c_index + 1 and _FORK_BOMB_RE.search(argv[c_index + 1]):
        return "fork-bomb pattern detected"
```

Every other D-03 rule (hard-blocked binaries, dangerous `rm` targets, raw-block-device `dd`/`mkfs`, `chmod/chown -R /`) is never evaluated against the contents of the `-c` string. As a result:

```python
check(["bash", "-c", "sudo rm -rf /"], yes=False)  # -> CONFIRM (should be BLOCK)
check(["bash", "-c", "sudo rm -rf /"], yes=True)   # -> CONFIRM, executes unconditionally
check(["sh", "-c", "dd if=/dev/zero of=/dev/sda"], yes=False)  # -> CONFIRM
```

Verified end-to-end: with `--yes`, `run_loop` passes `["bash", "-c", "sudo rm -rf /"]` straight to `run_shell`, which calls `subprocess.run(["bash", "-c", "sudo rm -rf /"], shell=False, ...)` — `bash` itself interprets the `-c` string, so `sudo rm -rf /` actually runs. This is exactly the "no safe invocation" case `_HARD_BLOCKED_BINARIES` was designed to prevent, reached via a one-line wrapper. The same gap is reachable via `find . -exec sh -c "sudo rm -rf /" ;`, which recurses into `_blocklist_match(["sh","-c","sudo rm -rf /"])` and hits the same hole.

No test exercises `bash -c "sudo ..."` or `bash -c "rm -rf /"` — only the fork-bomb variant (`test_fork_bomb_via_bash_dash_c_blocks`) is covered, masking this gap.

**Fix:** Extend the existing wrap-and-recurse pattern (already used for `env`/`find`) to `bash`/`sh`/`zsh -c`: tokenize the `-c` argument with `shlex.split()` and recursively run `_blocklist_match` on the result, in addition to (not instead of) the fork-bomb check.

```python
# (6b) bash/sh/zsh -c "<command>" wraps a command — recursively gate it,
# in addition to the fork-bomb check.
if binary in ("bash", "sh", "zsh") and "-c" in argv:
    c_index = argv.index("-c")
    if len(argv) > c_index + 1:
        c_string = argv[c_index + 1]
        if _FORK_BOMB_RE.search(c_string):
            return "fork-bomb pattern detected"
        try:
            wrapped = shlex.split(c_string)
        except ValueError:
            wrapped = []
        if wrapped:
            reason = _blocklist_match(wrapped)
            if reason is not None:
                return f"'{binary} -c' wraps a blocked command: {reason}"
```

(Requires `import shlex` at the top of `safety.py`.) Add regression tests mirroring `test_run_loop_env_unset_sudo_with_yes_still_blocks` for `bash -c "sudo rm -rf /"` and `find . -exec sh -c "sudo rm -rf /" ;`.

---

### CR-02: `chmod`/`chown -R /` blocklist rule only matches short combined flags, not `--recursive`

**File:** `src/olla/safety.py:183-186`
**Issue:**

```python
# (7) chmod/chown -R (including combined short flags like -Rf) on /.
if binary in ("chmod", "chown") and "/" in argv:
    if any(a.startswith("-") and not a.startswith("--") and "R" in a for a in argv[1:]):
        return f"'{binary} -R' targeting '/' is destructive"
```

The `not a.startswith("--")` guard intentionally excludes long-form flags, but `--recursive` is a valid GNU `chmod`/`chown` flag and is not matched by anything else in `_blocklist_match`. As a result:

```python
check(["chmod", "--recursive", "777", "/"], yes=False)  # -> CONFIRM (should be BLOCK)
```

With `--yes`, `chmod --recursive 777 /` reaches `run_shell` and executes — recursively chmod'ing the entire filesystem to `777`, exactly the outcome rule (7) was written to prevent for the `-R` spelling.

**Fix:** Also match `--recursive` (and do the same for `chown`):

```python
if binary in ("chmod", "chown") and "/" in argv:
    has_recursive = any(
        (a.startswith("-") and not a.startswith("--") and "R" in a) or a == "--recursive"
        for a in argv[1:]
    )
    if has_recursive:
        return f"'{binary} -R' targeting '/' is destructive"
```

Add a regression test: `check(["chmod", "--recursive", "777", "/"], yes=False)["kind"] == "BLOCK"`.

---

### CR-03: `_RM_DANGEROUS_TARGETS` does not cover `//`, `///`, etc. (kernel-equivalent to `/`)

**File:** `src/olla/safety.py:45-51`
**Issue:**

```python
_RM_DANGEROUS_TARGETS: set[str] = {
    "/",
    "~",
    "/*",
    "$HOME",
    ".",
}
```

On Linux, multiple leading slashes in a path are collapsed to a single `/` by the kernel's path-resolution — `rm -rf //` and `rm -rf ///` are functionally identical to `rm -rf /`. Neither is in `_RM_DANGEROUS_TARGETS`, so:

```python
check(["rm", "-rf", "//"], yes=False)   # -> CONFIRM (should be BLOCK)
check(["rm", "-rf", "///"], yes=False)  # -> CONFIRM (should be BLOCK)
```

With `--yes`, `rm -rf //` reaches `run_shell` and executes a full-filesystem delete — the exact scenario `_RM_DANGEROUS_TARGETS` exists to stop for the single-slash spelling. A small model paraphrasing "delete the root directory" could plausibly emit `//` (e.g., copy-pasted from a path that already ended in `/`).

**Fix:** Either add `//`/`///` as literal entries, or normalize repeated leading slashes before the membership check (without using `os.path` resolution, per the existing "literal token" design note in the file's comments):

```python
def _normalize_rm_target(arg: str) -> str:
    """Collapse repeated leading slashes (// , /// , ...) to a single '/'
    for D-03 matching — Linux path resolution treats them identically."""
    return re.sub(r"^/{2,}$", "/", arg)

# in _blocklist_match, rule (4):
if binary == "rm":
    for arg in argv[1:]:
        if _normalize_rm_target(arg) in _RM_DANGEROUS_TARGETS:
            return f"'rm' targeting '{arg}' is a dangerous deletion target"
```

Add regression tests for `//` and `///`.

## Warnings

### WR-01: `call_model` raises uncaught `KeyError: 'content'` when `think=True` and the model returns only `thinking`

**File:** `src/olla/loop.py:24-27`
**Issue:**

```python
def call_model(model: str, messages: list[dict], think: bool = False) -> str:
    """Call ollama.chat() with the stop-sequences and context size for the ReAct loop."""
    response = ollama.chat(model=model, messages=messages, options={"stop": ["</args>", "Observation:"], "num_ctx": 8192}, think=think)
    return response["message"]["content"]
```

`ollama`'s `ChatResponse`/`Message` are pydantic models with custom `__getitem__`/`__contains__`: a key is only considered "present" if it was explicitly set during validation OR its declared default is non-`None`. `Message.content` defaults to `None`. If a thinking-capable model (e.g., Qwen3 with `think=True`) returns a response where only `message.thinking` is populated and `content` is omitted from the JSON entirely, `"content" in response["message"]` is `False` and `response["message"]["content"]` raises `KeyError: 'content'` (verified empirically against `ollama==0.6.2`):

```python
>>> resp = ChatResponse.model_validate({
...     "model": "qwen3", "created_at": "...", "done": True,
...     "message": {"role": "assistant", "thinking": "Let me think..."}
... })
>>> resp["message"]["content"]
KeyError: 'content'
```

`run_loop` always calls `call_model(model, messages)` with the default `think=False`, where Ollama reliably populates `content` (even if empty string), so this path is not currently reachable from the main agent loop. However, `run_smoke_test` (`src/olla/smoke.py`) explicitly iterates `think_mode in (False, True)` and calls `call_model(model, messages, think=think_mode)` — an uncaught `KeyError` here crashes the smoke test entirely for any model that omits `content` under `think=True`, rather than reporting it as `non_compliant`/`reverted_to_native_format`.

**Fix:** Use safe access with a default, consistent with the tolerant-parsing philosophy elsewhere in the codebase:

```python
def call_model(model: str, messages: list[dict], think: bool = False) -> str:
    response = ollama.chat(model=model, messages=messages, options={"stop": ["</args>", "Observation:"], "num_ctx": 8192}, think=think)
    message = response["message"]
    return message["content"] if "content" in message else ""
```

---

### WR-02: Dry-run preview says "would prompt for confirmation" even when `--yes` would skip the prompt

**File:** `src/olla/loop.py:60-67`
**Issue:**

```python
decision = check(argv, yes=yes)
if decision["kind"] == "ALLOW":
    verdict = "auto-approved (read-only allowlist)"
elif decision["kind"] == "CONFIRM":
    verdict = "would prompt for confirmation"
else:
    verdict = f"BLOCKED: {decision['reason']}"
```

In the real (non-dry-run) loop, `decision["kind"] == "CONFIRM" and not yes` is the actual gating condition (`loop.py:116`) — if `yes=True`, a `CONFIRM`-tier command runs without any prompt. But the dry-run preview's `CONFIRM` branch always prints "would prompt for confirmation", regardless of `yes`. Running `olla --dry-run --yes "..."` against a `git status`-style command prints:

```
Step 1 would run: ['git', 'status'] — would prompt for confirmation
```

even though the real run with `--yes` would execute it immediately with no prompt. This makes `--dry-run --yes` (a natural combination for previewing what an automated/unattended run will do) misleading.

**Fix:**

```python
if decision["kind"] == "ALLOW":
    verdict = "auto-approved (read-only allowlist)"
elif decision["kind"] == "CONFIRM":
    verdict = "auto-approved (--yes)" if yes else "would prompt for confirmation"
else:
    verdict = f"BLOCKED: {decision['reason']}"
```

---

### WR-03: `env -S "<command>"` remains an unprotected wrap-and-recurse instance, same class as CR-01

**File:** `src/olla/safety.py:63-66, 96-98`
**Issue:**
`_unwrap_env`'s docstring and `test_env_split_string_flag_wrapping_sudo_confirms` both document that `env -S "sudo rm -rf /"` intentionally returns `CONFIRM`, with the rationale "`-S` consumes its argument as a single string for env to re-split itself; `_unwrap_env` does not parse into that string". This is the same class of gap as CR-01 (a command string embedded in a single argv token, to be split by the wrapped interpreter at runtime, is not recursively gated). Once CR-01 is fixed for `bash/sh/zsh -c`, `env -S "..."` is the next most obvious instance of the same pattern — and a model that discovers `bash -c` is now blocked has an easy fallback (`env -S "sudo rm -rf /"`).

**Fix:** After fixing CR-01, extend the same `shlex.split()` + recurse treatment to `env -S`/`--split-string`'s argument:

```python
if argv[i] in ("-S", "--split-string"):
    try:
        return shlex.split(argv[i + 1])
    except (ValueError, IndexError):
        return []
```

Update `test_env_split_string_flag_wrapping_sudo_confirms` to assert `BLOCK` instead, since the current test codifies the bypass as expected behavior rather than testing a deliberate design boundary.

---

### WR-04: Repetition guard does not track non-`shell` tool calls or unparseable args, allowing identical-failure loops to run to `max_steps`

**File:** `src/olla/loop.py:83-95`
**Issue:**
The repeat-detection signature (`sig = ("shell", tuple(argv))`, lines 97-102) is only computed inside the `parsed["tool"] == "shell"` and successfully-`shlex.split()`-parsed branch. If the model repeatedly emits:
- `<tool>write_file</tool>...` (unknown tool), or
- `<tool>shell</tool><args>echo "unterminated</args>` (unparseable args),

`prev_sig`/`repeat_count` are never updated, so the "same call repeated 3x — model likely stuck" early-exit never fires for these cases. The loop will instead consume all `max_steps` iterations making the identical failing call each time, only stopping via the `Reached max steps (...)` message. This is a less severe failure than the `shell` case (it does still terminate within `max_steps`, and doesn't execute anything), but it's an inconsistency in the "model likely stuck" detection — the explicit repetition tests (`test_run_loop_repetition_guard_aborts_before_third_call`, etc.) only cover the successfully-parsed `shell` path.

**Fix:** Compute a signature for these cases too, e.g. `sig = ("unknown_tool", parsed["tool"])` or `sig = ("parse_error", parsed["args_raw"])`, and run it through the same `prev_sig`/`repeat_count`/`>= 3` check before appending the observation and `continue`-ing.

## Info

### IN-01: Untruncated assistant `<tool>`/`<args>` content can grow message history unbounded

**File:** `src/olla/loop.py:76-77`
**Issue:**

```python
history_content = truncate_output(content) if parsed["type"] == "none" else content
messages.append({"role": "assistant", "content": history_content})
```

Truncation via `MAX_OBSERVATION_CHARS` is only applied when `parsed["type"] == "none"`. For `type == "tool"` (and `type == "final"`, though that returns immediately), the raw, untruncated `content` — including the full `<args>...</args>` payload — is appended to `messages` verbatim. A model that emits a very large `<args>` blob (e.g., embedding a large file's contents in a heredoc-style argument) will have that full blob preserved in context for every subsequent turn, working against the stated per-turn token-overhead goal for small models. This is likely an intentional trade-off (truncating `<args>` could corrupt the command), but worth a comment noting the asymmetry, or an explicit cap on `args_raw` length with a corrective re-prompt similar to the `none`-type path.

**Fix:** Add a comment explaining why `tool`/`final` content is exempted from truncation, or apply a separate (larger) cap to `args_raw` specifically with a "command too long, please simplify" corrective message.

---

### IN-02: `--max-steps` accepts zero/negative values without validation, producing a confusing message

**File:** `src/olla/cli.py:14`, `src/olla/loop.py:73, 146`
**Issue:** `@click.option("--max-steps", default=15, show_default=True, type=int)` has no minimum constraint. `--max-steps 0` or a negative value causes `range(1, max_steps + 1)` to be empty, so the loop body never executes and `ollama.chat` is never called — `run_loop` immediately prints `Reached max steps (0) without a <final> answer.` (or `(-1)`). Not a crash, but a confusing UX for an obviously-invalid input (the user gets a "max steps reached" message without any step having been attempted).

**Fix:** Add `click.IntRange(min=1)` to the `--max-steps` option:

```python
@click.option("--max-steps", default=15, show_default=True, type=click.IntRange(min=1))
```

---

### IN-03: `_blocklist_match` recursion (`env`, `find -exec`, and the proposed `bash -c` fix) has no depth limit

**File:** `src/olla/safety.py:142-156`
**Issue:** `_blocklist_match` recurses into wrapped commands for `env` and `find -exec` via plain recursive calls with no depth limit. Currently this is bounded in practice (the recursion only continues if the wrapped binary is itself `env` or `find`), but if CR-01's fix adds a third recursive case (`bash -c "..."`), combinations like `bash -c "env env env env ... sudo rm -rf /"` increase the plausibility of a deeply nested chain assembled by string concatenation from a hallucinating model. A `RecursionError` during `_blocklist_match` would propagate out of `check()` uncaught, crashing `run_loop`.

**Fix:** Add a small depth counter/limit (e.g., 10) to `_blocklist_match`, returning a conservative result (e.g., treat as unmatched/CONFIRM, or BLOCK with "too deeply nested to safety-check") once exceeded, rather than letting `RecursionError` propagate:

```python
def _blocklist_match(argv: list[str], _depth: int = 0) -> str | None:
    if _depth > 10:
        return "command nesting too deep to safety-check"
    ...
    # pass _depth + 1 to recursive calls
```

---

_Reviewed: 2026-06-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
