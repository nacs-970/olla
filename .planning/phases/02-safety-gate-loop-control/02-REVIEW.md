---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/olla/cli.py
  - src/olla/loop.py
  - src/olla/safety.py
  - src/olla/tools/shell.py
  - tests/test_cli.py
  - tests/test_loop.py
  - tests/test_safety.py
  - tests/test_tools/test_shell.py
  - pyproject.toml
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
**Files Reviewed:** 9
**Status:** issues_found

## Summary

This is a re-review after the 02-05 gap-closure round, which fixed the three CR-01/02/03 issues from the prior `02-REVIEW.md` (`bash/sh/zsh -c` wrap-and-recurse, `chmod/chown --recursive`, and `rm -rf //`/`///` normalization). All 109 tests pass (`.venv/bin/python -m pytest tests/ -q`), and those three specific bypasses are now correctly classified `BLOCK` — verified empirically against the live code.

However, each of the three narrow fixes left an **equivalent-form hole** that a model (or an attacker shaping model output) can trivially reach:

1. **`bash -lc "sudo rm -rf /"` (and `-ic`, `-cx`, etc. — any combined short-flag form containing `c`) is not recognized as `bash -c`** because rule (6b) checks `"-c" in argv` as an exact-token match. `bash -lc "..."` is valid bash syntax (login shell + command string) and falls straight through to `CONFIRM`. Under `--yes`, this executes `sudo rm -rf /` unattended — the exact scenario the CR-01 fix was written to close, defeated by a one-character flag-combination change.

2. **The `//`/`///` normalization added for CR-03 was applied only to the `rm` rule (rule 4)**, not to the `chmod`/`chown -R` rule (rule 7, which still does an exact `"/" in argv` check) or the `dd`/`mkfs*` raw-device rule (rule 5, which does an exact `fnmatch(path, "/dev/*")`). `chmod -R 777 //`, `chown -R user //`, `dd of=//dev/sda`, and `mkfs.ext4 //dev/sda` are all `CONFIRM` and execute unattended under `--yes` — each one is the same destructive action the corresponding rule was written to block for the single-slash spelling.

3. The previously-identified Warnings (`call_model` `KeyError` on `think=True`, dry-run `CONFIRM` verdict ignoring `--yes`, `env -S` wrap-and-recurse gap, repetition guard scope) and Info items remain unaddressed in `loop.py`/`safety.py`, which are otherwise unchanged since the prior review.

## Critical Issues

### CR-01: `bash`/`sh`/`zsh` with combined short flags (`-lc`, `-ic`, `-cx`, ...) bypass the `-c` wrap-and-recurse check entirely

**File:** `src/olla/safety.py:202-215`
**Issue:**

```python
if binary in ("bash", "sh", "zsh") and "-c" in argv:
    c_index = argv.index("-c")
    ...
```

`"-c" in argv` is an exact-token membership check. Bash (and sh/zsh) support combining single-letter flags into one token — `bash -lc "cmd"` (login shell + `-c`), `bash -ic "cmd"` (interactive + `-c`), `bash -xc "cmd"` (trace + `-c`) are all valid and run `cmd` via `-c` exactly like `bash -c "cmd"`. None of these tokens equal the literal string `"-c"`, so the entire rule (6b) block — including the fork-bomb check AND the new CR-01 shlex-split-and-recurse — is skipped.

Verified empirically against the live code:

```python
>>> check(["bash", "-lc", "sudo rm -rf /"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["bash", "-c",  "sudo rm -rf /"], yes=True)
{'kind': 'BLOCK', 'reason': "'bash -c' wraps a blocked command: 'sudo' is blocked outright (no safe invocation)"}
```

This is the same destructive end-to-end path described in the prior CR-01 finding (`run_loop` → `decision["kind"] == "CONFIRM"` and `yes=True` → `run_shell(["bash", "-lc", "sudo rm -rf /"])` → `bash` interprets `-lc` and runs `sudo rm -rf /`). A model that has been corrected once for `bash -c "sudo ..."` (observed `blocked by safety policy`) has an obvious, syntactically-valid one-character escape: prepend any other single-letter flag to `c`.

No test exercises `bash -lc`/`-ic`/`-xc`/etc. — `test_bash_dash_c_sudo_rm_rf_root_blocks` and friends only cover the bare `-c` token.

**Fix:** Detect any argv token that is a combined short-flag bundle containing `c` (i.e., starts with `-`, doesn't start with `--`, and contains `c`), not just the literal `"-c"`. The wrapped command is still the *next* argv element after that token:

```python
# (6b) bash/sh/zsh -c "<command>" (including combined short-flag forms like
# -lc, -ic, -xc): recursively gate the wrapped command, in addition to the
# fork-bomb check.
if binary in ("bash", "sh", "zsh"):
    c_index = next(
        (i for i, a in enumerate(argv) if a.startswith("-") and not a.startswith("--") and "c" in a),
        None,
    )
    if c_index is not None and len(argv) > c_index + 1:
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

Add regression tests for `check(["bash", "-lc", "sudo rm -rf /"], yes=True)["kind"] == "BLOCK"` and at least one other combined form (`-ic`).

---

### CR-02: `chmod`/`chown -R` rule (7) was not updated for `//`/`///` — `chmod -R 777 //` and `chown -R user //` remain `CONFIRM`

**File:** `src/olla/safety.py:219-224`
**Issue:**

```python
if binary in ("chmod", "chown") and "/" in argv:
    if any(
        (a.startswith("-") and not a.startswith("--") and "R" in a) or a == "--recursive"
        for a in argv[1:]
    ):
        return f"'{binary} -R' targeting '/' is destructive"
```

The CR-03 fix from 02-05 introduced `_normalize_rm_target()` to collapse `//`/`///` to `/` for the `rm` rule (rule 4), based on the documented fact that "Linux path resolution treats repeated leading slashes as equivalent to `/`". That same fact applies equally to `chmod -R`/`chown -R` — but rule (7)'s guard is still the exact membership test `"/" in argv`, which does not match `"//"` or `"///"`.

Verified empirically:

```python
>>> check(["chmod", "-R", "777", "//"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["chown", "-R", "user", "//"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["chmod", "--recursive", "777", "//"], yes=True)
{'kind': 'CONFIRM'}
```

Under `--yes`, `chmod -R 777 //` reaches `run_shell` and executes a full-filesystem recursive chmod to `777` — the exact outcome rule (7) exists to prevent, just spelled with a doubled leading slash.

**Fix:** Reuse `_normalize_rm_target` (consider renaming it to something binary-agnostic, e.g. `_normalize_slash_target`, since it's no longer `rm`-specific) and apply it when checking for `/`:

```python
if binary in ("chmod", "chown") and any(_normalize_rm_target(a) == "/" for a in argv[1:]):
    if any(
        (a.startswith("-") and not a.startswith("--") and "R" in a) or a == "--recursive"
        for a in argv[1:]
    ):
        return f"'{binary} -R' targeting '/' is destructive"
```

Add regression tests: `check(["chmod", "-R", "777", "//"], yes=True)["kind"] == "BLOCK"` and the `chown` equivalent.

---

### CR-03: `dd`/`mkfs*` raw-device rule (5) does not normalize `//dev/...`, allowing `dd of=//dev/sda` to bypass the device-write block

**File:** `src/olla/safety.py:182-185, 92-101`
**Issue:**

```python
def _is_dangerous_device_arg(arg: str) -> bool:
    path = arg.split("=")[-1]
    if not fnmatch.fnmatch(path, _DEVICE_GLOB):  # "/dev/*"
        return False
    device_name = path.removeprefix("/dev/")
    return device_name.startswith(_DEVICE_PREFIXES)
```

`_DEVICE_GLOB = "/dev/*"` and `removeprefix("/dev/")` both require an exact single-leading-slash `/dev/` prefix. A doubled-slash path like `//dev/sda` does not match `fnmatch("//dev/sda", "/dev/*")` (the `*` would need to match `/dev/sda` against a pattern that already starts with `/dev/`, but the literal string starts with `//`), so `_is_dangerous_device_arg` returns `False` and the whole `dd`/`mkfs*` rule is skipped.

Verified empirically:

```python
>>> check(["dd", "if=/dev/zero", "of=//dev/sda"], yes=True)
{'kind': 'CONFIRM'}
>>> check(["mkfs.ext4", "//dev/sda"], yes=True)
{'kind': 'CONFIRM'}
```

Under `--yes`, `dd if=/dev/zero of=//dev/sda` reaches `run_shell` — and since the kernel treats `//dev/sda` identically to `/dev/sda`, this zeroes the raw block device, exactly the outcome `_is_dangerous_device_arg` exists to prevent.

**Fix:** Normalize the path portion (collapse leading `//`, `///`, ... to `/`) before the `fnmatch`/`removeprefix` checks, using the same normalization helper as CR-02:

```python
def _is_dangerous_device_arg(arg: str) -> bool:
    path = arg.split("=")[-1]
    path = re.sub(r"^/{2,}", "/", path)  # normalize //dev/... -> /dev/...
    if not fnmatch.fnmatch(path, _DEVICE_GLOB):
        return False
    device_name = path.removeprefix("/dev/")
    return device_name.startswith(_DEVICE_PREFIXES)
```

Note this normalization only needs to collapse a *leading* run of slashes (not anchor the whole string, unlike `_normalize_rm_target`), since `of=//dev/sda` and `//dev/sda` both need `//dev` -> `/dev` regardless of what follows. Add regression tests for `dd ... of=//dev/sda` and `mkfs.ext4 //dev/sda`.

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

`ollama`'s `Message` pydantic model defaults `content` to `None`, and its `__getitem__`/`__contains__` treat a field as absent if it was never set during validation and its default is `None`. If a thinking-capable model (e.g. Qwen3 with `think=True`) returns a response where only `message.thinking` is populated and `content` is omitted from the JSON entirely, `response["message"]["content"]` raises `KeyError: 'content'` (verified empirically against `ollama==0.6.2`).

`run_loop` always calls `call_model(model, messages)` with `think=False`, where `content` is reliably populated, so this is not reachable from the main agent loop. But `run_smoke_test` (`src/olla/smoke.py`) explicitly calls `call_model(model, messages, think=True)` for the second half of its `think_mode in (False, True)` loop — an uncaught `KeyError` here crashes the entire smoke test for any model that omits `content` under `think=True`, instead of classifying the response as `non_compliant`/`reverted_to_native_format` as the smoke test is designed to do.

**Fix:**

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

In the real (non-dry-run) loop, the actual gating condition is `decision["kind"] == "CONFIRM" and not yes` (`loop.py:116`) — if `yes=True`, a `CONFIRM`-tier command runs without any prompt. The dry-run preview's `CONFIRM` branch always prints "would prompt for confirmation" regardless of `yes`, so `olla --dry-run --yes "..."` against a `git status`-style command prints a verdict that does not match what the real run would do.

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

### WR-03: `env -S "<command>"` remains an unprotected wrap-and-recurse instance, same class as CR-01/CR-02/CR-03 above

**File:** `src/olla/safety.py:75, 114-126`
**Issue:** `_ENV_FLAGS_WITH_ARG` includes `-S`/`--split-string`, so `_unwrap_env(["env", "-S", "sudo rm -rf /"])` skips both tokens and returns `[]` (no wrapped command found) — `test_env_split_string_flag_wrapping_sudo_confirms` documents this as intentional, returning `CONFIRM`. But `env -S "<command>"` re-splits its argument into a command at runtime, exactly like `bash -c "<command>"` — the same class of "command embedded as a single string argument" that CR-01 was fixed for. A model that discovers `bash -c "sudo ..."` and its `-lc` variant (CR-01 above) are blocked has `env -S "sudo rm -rf /"` as a further fallback.

```python
>>> check(["env", "-S", "sudo rm -rf /"], yes=True)
{'kind': 'CONFIRM'}
```

**Fix:** After fixing CR-01, extend the same `shlex.split()` + recurse treatment to `-S`/`--split-string`'s argument inside `_unwrap_env` (or as a separate check in `_blocklist_match` for `binary == "env"`):

```python
if argv[i] in ("-S", "--split-string"):
    try:
        return shlex.split(argv[i + 1])
    except (ValueError, IndexError):
        return []
```

Update `test_env_split_string_flag_wrapping_sudo_confirms` to assert `BLOCK`.

---

### WR-04: Repetition guard does not track non-`shell` tool calls or unparseable args, allowing identical-failure loops to run to `max_steps`

**File:** `src/olla/loop.py:83-102`
**Issue:** The repeat-detection signature (`sig = ("shell", tuple(argv))`, computed only at lines 97-102) is only reached when `parsed["tool"] == "shell"` AND `shlex.split(parsed["args_raw"])` succeeds. If the model repeatedly emits an unknown tool (`<tool>write_file</tool>...`) or unparseable shell args (`<tool>shell</tool><args>echo "unterminated</args>`), `prev_sig`/`repeat_count` are never updated, so the "same call repeated 3x — model likely stuck" early exit never fires for these cases — the loop instead consumes all `max_steps` iterations making the identical failing call each time.

**Fix:** Compute a signature for these cases too (e.g. `("unknown_tool", parsed["tool"])` or `("parse_error", parsed["args_raw"])`) and run it through the same `prev_sig`/`repeat_count`/`>= 3` check before appending the observation and `continue`-ing.

## Info

### IN-01: Untruncated assistant `<tool>`/`<args>` content can grow message history unbounded

**File:** `src/olla/loop.py:76-77`
**Issue:**

```python
history_content = truncate_output(content) if parsed["type"] == "none" else content
messages.append({"role": "assistant", "content": history_content})
```

Truncation via `MAX_OBSERVATION_CHARS` is only applied when `parsed["type"] == "none"`. For `type == "tool"`, the raw, untruncated `content` (including the full `<args>...</args>` payload) is appended to `messages` verbatim. A model that emits a very large `<args>` blob has that full blob preserved in context for every subsequent turn, working against the stated per-turn token-overhead goal for small models. Likely an intentional trade-off (truncating `<args>` could corrupt the command), but worth a comment explaining the asymmetry.

**Fix:** Add a comment explaining why `tool`-type content is exempted from truncation, or apply a separate (larger) cap to `args_raw` specifically with a corrective re-prompt similar to the `none`-type path.

---

### IN-02: `--max-steps` accepts zero/negative values without validation, producing a confusing message

**File:** `src/olla/cli.py:14`
**Issue:** `@click.option("--max-steps", default=15, show_default=True, type=int)` has no minimum constraint. `--max-steps 0` (or negative) makes `range(1, max_steps + 1)` empty in `loop.py:73`, so the loop body never executes and `run_loop` immediately prints `Reached max steps (0) without a <final> answer.` — not a crash, but a confusing message for an obviously-invalid input.

**Fix:**

```python
@click.option("--max-steps", default=15, show_default=True, type=click.IntRange(min=1))
```

---

### IN-03: `_blocklist_match` recursion (`env`, `find -exec`, `bash/sh/zsh -c`) has no depth limit

**File:** `src/olla/safety.py:148-226`
**Issue:** `_blocklist_match` recurses into wrapped commands for `env`, `find -exec`, and (since 02-05) `bash/sh/zsh -c`, with no depth limit. A pathological input chaining many wrappers (e.g. `bash -c "env env env env ... sudo rm -rf /"`, or `env env env ... env sudo ls`) could in principle drive `_blocklist_match` toward Python's recursion limit; a `RecursionError` here would propagate out of `check()` uncaught and crash `run_loop`. Tested 50 levels of `env` nesting without issue, but the lack of an explicit bound means correctness depends on the model never producing a sufficiently long chain — and the CR-01 fix to this review adds a third recursive case, making longer chains via `bash -c "<deeply nested>"` more plausible.

**Fix:** Add a small depth counter/limit (e.g. 10) to `_blocklist_match`, returning a conservative result (e.g. `"command nesting too deep to safety-check"`, treated as `BLOCK`) once exceeded rather than letting `RecursionError` propagate:

```python
def _blocklist_match(argv: list[str], _depth: int = 0) -> str | None:
    if _depth > 10:
        return "command nesting too deep to safety-check"
    ...
    # pass _depth + 1 to each recursive call
```

---

_Reviewed: 2026-06-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
