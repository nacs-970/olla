---
phase: 01-core-loop-shell-tool-cli
fixed_at: 2026-06-11T00:00:00Z
review_path: .planning/phases/01-core-loop-shell-tool-cli/01-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 5
fixed: 5
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fix Scope:** critical_warning (Critical + Warning findings; Info findings out of scope)
**Findings in scope:** 5 (CR-01, CR-02, WR-01, WR-02, WR-03)
**Fixed:** 5
**Skipped:** 0
**Status:** all_fixed

## Fixed Findings

### CR-01: Empty or whitespace-only `<args>` causes unhandled `IndexError`

**File:** `src/olla/tools/shell.py`
**Fix:** `run_shell()` now checks `argv` after `shlex.split()` and returns
`{"argv": [], "error": "empty command"}` instead of calling
`subprocess.run([], ...)`, which raised `IndexError`.
**Tests added:** `test_empty_args`, `test_whitespace_only_args` in
`tests/test_tools/test_shell.py`.
**Commit:** `fix(01): handle empty and malformed shell args (CR-01, CR-02)`

### CR-02: Malformed quoting in `<args>` raises unhandled `shlex.split` `ValueError`

**Files:** `src/olla/tools/shell.py`, `src/olla/loop.py`
**Fix:**
- `run_shell()` wraps `shlex.split(args_raw)` in `try/except ValueError`,
  returning `{"error": "could not parse command: ..."}` on unbalanced quotes.
- `run_loop()`'s tool branch wraps its own `shlex.split()` call (used for the
  `Step N: running ...` preview) the same way, appending a recoverable
  `Observation: error: could not parse command: ...` and continuing the loop
  instead of crashing.
**Tests added:** `test_unbalanced_quote` (`tests/test_tools/test_shell.py`),
`test_run_loop_malformed_args_recovers` (`tests/test_loop.py`).
**Commits:** `fix(01): handle empty and malformed shell args (CR-01, CR-02)`,
`fix(01): handle malformed args and missing tool-result keys (CR-02, WR-01, WR-03)`

### WR-01: `combined` construction in `run_loop` silently produces empty output for `ToolResult`s missing both `error` and `stdout`/`stderr`

**File:** `src/olla/loop.py`
**Fix:** Added an explicit `elif "stdout" in result or "stderr" in result` branch;
results with neither key now produce `combined = "(no output)"` instead of
silently becoming an empty string, so future tools (Phase 3 file tools) that
return only `argv`/`returncode` don't vanish from the model's context.
**Tests added:** `test_run_loop_tool_result_missing_output_keys` in
`tests/test_loop.py`.
**Commit:** `fix(01): handle malformed args and missing tool-result keys (CR-02, WR-01, WR-03)`

### WR-02: `--dry-run` and `--yes` flags silently accepted but inert

**File:** `src/olla/cli.py`
**Fix:** When either flag is passed, `main()` now prints a one-line notice
(`"Note: --dry-run is not yet enforced (Phase 2); ..."` /
`"Note: --yes is not yet enforced (Phase 2); ..."`) before running the loop,
so users aren't silently surprised that real commands still execute /
no confirmation prompts occur yet.
**Tests added:** `test_dry_run_flag_prints_inert_notice`,
`test_yes_flag_prints_inert_notice` in `tests/test_cli.py`.
**Commit:** `fix(01): notify when --dry-run/--yes flags are inert (WR-02)`

### WR-03: Unbounded message history growth on repeated `none`-type responses

**File:** `src/olla/loop.py`
**Fix:** The assistant's raw `content` is now passed through
`truncate_output()` before being appended to `messages` whenever
`parse_response()` returns `type == "none"` (untagged/non-compliant output),
matching the truncation discipline already applied to tool observations.
`final`/`tool` responses are appended untruncated as before.
**Tests added:** `test_run_loop_truncates_none_response_in_history` in
`tests/test_loop.py`.
**Commit:** `fix(01): handle malformed args and missing tool-result keys (CR-02, WR-01, WR-03)`

## Skipped Findings

None — all 5 in-scope (Critical + Warning) findings were fixed.

## Out of Scope (Info findings, not addressed)

- **IN-01**: `classify_response` ordering in `src/olla/smoke.py` — native-format
  detection precedence vs. `<final>`/`<tool>` compliance check.
- **IN-02**: Magic number `80` (compliance threshold) in `src/olla/smoke.py`
  lacks a named constant.

These were out of scope for this `--fix` run (Info findings excluded unless
`--all` is passed). Re-run `/gsd:code-review 01 --fix --all` to address them.

## Verification

- `tests/test_tools/test_shell.py`, `tests/test_loop.py`, `tests/test_cli.py`
  updated with regression tests for all 5 fixes.
- Full suite: `41 passed` (`.venv/bin/python -m pytest -q`).
- `ruff check src tests`: all checks passed.

---

_Fixed: 2026-06-11T00:00:00Z_
_Fixer: Claude (orchestrator, direct fix after gsd-code-fixer agent declined to act)_
_Iteration: 1 of 1 (no --auto)_
