---
phase: 01-core-loop-shell-tool-cli
reviewed: 2026-06-11T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - src/olla/cli.py
  - src/olla/__init__.py
  - src/olla/loop.py
  - src/olla/parser.py
  - src/olla/prompts.py
  - src/olla/smoke.py
  - src/olla/tools/base.py
  - src/olla/tools/__init__.py
  - src/olla/tools/shell.py
  - tests/__init__.py
  - tests/test_cli.py
  - tests/test_loop.py
  - tests/test_parser.py
  - tests/test_smoke.py
  - tests/test_tools/__init__.py
  - tests/test_tools/test_shell.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-06-11T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This is a small, focused walking-skeleton implementation (parser, shell tool, ReAct loop, CLI, smoke test) and the architecture matches the plan well: `shlex.split()` + `subprocess.run(shell=False)` correctly avoids shell injection, the regex-based tag parser is appropriately tolerant of malformed model output, and `truncate_output()` correctly shares one truncated string between the printed preview and the message history (LOOP-03).

However, the review found two crash-causing (BLOCKER) gaps in the model-output -> shell execution path that are very plausible to hit with small/weak local models (the project's stated target audience): an empty `<args></args>` tag crashes `subprocess.run` with an unhandled `IndexError`, and malformed quoting in `<args>` crashes both `loop.py` and `shell.py` with an unhandled `shlex.split` `ValueError`. Both would take down the entire CLI process mid-loop with a raw traceback instead of a graceful error/observation — directly undermining the "agent loop must not crash on bad model output" expectation that the tolerant parser was built to satisfy. Phase 1's threat model explicitly defers *malicious* command filtering to Phase 2 (acceptable), but these are not security-policy gaps — they are unhandled-input crashes in code this phase owns and tested.

Additional warnings cover the silent error-swallowing for `parsed["type"] == "none"` history growth (no cap, contributing to context bloat that the project explicitly wants to avoid), a latent type-confusion in `run_loop`'s `combined` construction relative to `ToolResult`'s `total=False` contract, and the `--dry-run`/`--yes` no-op flags being silently accepted with no user-visible indication they currently do nothing. Info items note minor duplication and a magic-number/threshold note in `smoke.py`.

## Critical Issues

### CR-01: Empty or whitespace-only `<args>` causes unhandled `IndexError`, crashing the whole CLI

**File:** `src/olla/tools/shell.py:15-17`
**Issue:** `run_shell()` calls `argv = shlex.split(args_raw)` and then unconditionally calls `subprocess.run(argv, shell=False, ...)`. If `args_raw` is empty or whitespace-only (e.g. the model emits `<tool>shell</tool><args></args>` or `<args>   </args>`, both of which are valid per the parser's tolerant grammar — `ARGS_RE` happily captures an empty string), `shlex.split("")` returns `[]`. Calling `subprocess.run([], ...)` raises `IndexError: list index out of range` from inside `subprocess`'s own argument handling, *before* any of `run_shell`'s `except FileNotFoundError` / `except subprocess.TimeoutExpired` clauses can catch it.

This propagates straight up through `run_loop()` (`src/olla/loop.py:47`, `result = run_shell(parsed["args_raw"])`), which has no try/except around the call either, crashing the entire `olla` process with a raw traceback on what is a completely plausible, non-malicious small-model output (e.g. a 0.6B model emitting `<tool>shell</tool><args></args>` while "thinking out loud").

Verified directly:
```python
>>> import subprocess
>>> subprocess.run([], shell=False, capture_output=True, text=True, timeout=5)
IndexError: list index out of range
```

**Fix:**
```python
# src/olla/tools/shell.py
def run_shell(args_raw: str, timeout: int = 30) -> ToolResult:
    argv = shlex.split(args_raw)
    if not argv:
        return {"argv": argv, "error": "empty command"}
    try:
        result = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout)
        ...
```

### CR-02: Malformed quoting in `<args>` raises unhandled `shlex.split` `ValueError`, crashing the whole CLI

**File:** `src/olla/loop.py:45`, `src/olla/tools/shell.py:15`
**Issue:** `shlex.split()` raises `ValueError("No closing quotation")` (and similar) for unbalanced quotes — e.g. model output `<args>echo "hello</args>` (an unterminated double quote, easy for a small model to produce, especially given the `</args>` stop-sequence can truncate generation mid-quote per LOOP-02/D-anything). Verified directly:
```python
>>> shlex.split('echo "unterminated')
ValueError: No closing quotation
```
This call happens **twice** with no exception handling in either location:
1. `src/olla/loop.py:45` — `argv = shlex.split(parsed["args_raw"])`, used only for the `print(f"Step {step}: running {argv}...")` line, executed *before* `run_shell()` is even called.
2. `src/olla/tools/shell.py:15` — `argv = shlex.split(args_raw)` inside `run_shell()`, outside the `try` block.

Either occurrence raises an uncaught `ValueError` that crashes the agent loop mid-run. Given the system prompt's stop-sequence (`</args>`) can truncate the model's output exactly inside a quoted argument, this is not an edge case — it's a likely failure mode for the project's target small models (0.6B-4B).

**Fix:** Catch `ValueError` from `shlex.split()` in both places and turn it into a recoverable `Observation:` rather than a crash, e.g. in `loop.py`:
```python
try:
    argv = shlex.split(parsed["args_raw"])
except ValueError as e:
    preview = f"error: could not parse command: {e}"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue
```
and defensively also guard inside `run_shell()` (since it's a public function other callers may use directly):
```python
try:
    argv = shlex.split(args_raw)
except ValueError as e:
    return {"error": f"could not parse command: {e}"}
```

## Warnings

### WR-01: `combined` construction in `run_loop` relies on `ToolResult`'s `total=False` shape in a way that's fragile and untested for the success path with missing keys

**File:** `src/olla/loop.py:48-51`
**Issue:**
```python
if "error" in result:
    combined = result["error"]
else:
    combined = result.get("stdout", "") + result.get("stderr", "")
```
This works for the two shapes `run_shell()` actually returns today (success: `argv`/`returncode`/`stdout`/`stderr`; error: `argv`/`error`). But `ToolResult` is a shared `total=False` contract explicitly documented as being reused by future Phase 3 file tools (per `tools/base.py` docstring and the plan's `key_links`). A future tool that returns, say, `{"argv": [...], "returncode": 0}` with no `stdout`/`stderr` keys at all (not unreasonable for a "write succeeded, no output" tool) would silently produce `combined = ""` — masking a tool's success/failure entirely from both the user and the model's context, with no indication anything ran. This isn't a bug in the current code path (covered by `test_run_loop_tool_then_final`), but it's a correctness landmine for the very next phase that reuses this dispatch logic, and there's no test exercising a `ToolResult` that has neither `error` nor `stdout`/`stderr`.

**Fix:** Either document this constraint explicitly at the `run_loop` call site (a comment noting "every ToolResult must populate `error` or at least one of `stdout`/`stderr`"), or make the fallback explicit so silent empty-output isn't indistinguishable from "no observation yet":
```python
if "error" in result:
    combined = result["error"]
elif "stdout" in result or "stderr" in result:
    combined = result.get("stdout", "") + result.get("stderr", "")
else:
    combined = "(no output)"
```

### WR-02: `--dry-run` and `--yes` flags are silently accepted but do nothing — no user feedback that they're inert

**File:** `src/olla/cli.py:13,15`
**Issue:** `--dry-run` and `--yes` are declared as `is_flag=True` options and parsed by click, but `main()` never reads `dry_run` or `yes` at all — they're unused parameters. This is intentional per the plan (Phase 2 will wire them up), but as shipped, a user who runs `olla "rm -rf /tmp/foo" --model X --dry-run` gets **zero indication** that `--dry-run` had no effect and the command will execute for real. For a project whose CLAUDE.md explicitly states "blocklist, confirm-gating, and dry-run are non-negotiable from v1" as safety constraints, silently accepting `--dry-run` without honoring it is a footgun: a user relying on the flag's name/semantics could be surprised that a real, irreversible shell command ran.
**Fix:** At minimum, until Phase 2 lands, either (a) print a one-line notice when `--dry-run` is passed (e.g. `"Note: --dry-run is not yet enforced (Phase 2); the agent may execute real commands."`), or (b) reject it with `click.UsageError` until implemented, rather than accepting it silently. Given Phase 2 is the very next phase and this is documented in the threat model as a tracked/scheduled deferral (T-01-05), a warning print is the lower-friction fix.

### WR-03: Unbounded message history growth on repeated `none`-type responses has no cap, contradicting the "minimize per-turn token overhead" core value

**File:** `src/olla/loop.py:57-62`
**Issue:** Every time `parse_response()` returns `{"type": "none", ...}`, `run_loop` appends both the assistant's full raw response (line 38) and a corrective re-prompt (lines 57-62) to `messages`, with no truncation of the assistant message and no cap on how many corrective rounds accumulate before `max_steps` is reached. For a small/weak model that repeatedly fails to produce recognizable tags (a documented risk per the smoke test's whole reason for existing — D-07/D-08), `messages` grows by two full messages per step for up to `max_steps` (default 15) iterations, with the raw (untruncated) assistant content potentially being long prose each time. This directly works against the project's stated core value ("Minimal per-turn token overhead so 2-4B models... don't drift into wrong answers under a bloated context") — exactly the failure mode `num_ctx=8192` and `truncate_output()` were introduced to avoid for tool output, but the same discipline isn't applied to repeated raw "none" assistant messages.
**Fix:** Not necessarily a Phase 1 blocker since `max_steps` bounds total iterations, but worth tracking — e.g. truncate the appended assistant `content` for `none`-type responses too (`truncate_output(content)` before appending at line 38), or cap consecutive `none` responses with an early exit before `max_steps` is reached.

## Info

### IN-01: `classify_response` ordering means a response containing both compliant and "reverted" markers is always reported as compliant

**File:** `src/olla/smoke.py:27-33`
**Issue:** `classify_response` checks `OLLA_FINAL_RE`/`OLLA_TOOL_RE` first and returns `"compliant"` immediately if either matches, before checking the native-format regexes. A model response that starts with a native Qwen-style `<tool_call>{...}` block (a "reverted to native format" signal) but *also* happens to contain a literal `<final>` substring anywhere (e.g. inside an explanatory sentence the model wrote) would be classified `"compliant"` even though it actually reverted to native tool-call syntax. This is a minor edge case for the smoke-test classifier (test-support code, not production agent logic) and likely rare in practice, but worth noting since the smoke test's entire purpose (D-07/D-08) is to detect format drift accurately.
**Fix:** Consider checking native-format regexes first (or in addition), e.g. `if NATIVE_QWEN_RE.search(content) or NATIVE_GEMMA_RE.search(content): return "reverted_to_native_format"` before the compliant check — or document the precedence choice as intentional ("any olla-tag presence counts as compliant regardless of accompanying native-format noise") if that's the desired behavior.

### IN-02: Magic number `80` (compliance threshold) and `2 * len(FIXED_PROMPTS)` repeated without named constants

**File:** `src/olla/smoke.py:57`, `tests/test_smoke.py:35`
**Issue:** The `80` (percent) compliance threshold from D-08 is a hardcoded magic number embedded directly in the `if think_mode is False and compliance_pct < 80:` conditional, with no named constant (e.g. `COMPLIANCE_THRESHOLD_PCT = 80`). This is a minor maintainability nit — if the threshold ever needs tuning (likely, given D-08 frames it as a "flagged for follow-up" heuristic), it's currently buried in a conditional rather than declared alongside `FIXED_PROMPTS` at module scope.
**Fix:**
```python
COMPLIANCE_THRESHOLD_PCT = 80  # D-08: below this, flag for follow-up

...
if think_mode is False and compliance_pct < COMPLIANCE_THRESHOLD_PCT:
```

---

_Reviewed: 2026-06-11T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
