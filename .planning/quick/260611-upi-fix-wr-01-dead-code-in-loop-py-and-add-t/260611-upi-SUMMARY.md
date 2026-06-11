---
phase: 01-core-loop-shell-tool-cli
plan: quick-260611-upi
subsystem: core-loop
tags: [react-loop, dispatch, dead-code, tdd]

# Dependency graph
requires:
  - phase: 01-core-loop-shell-tool-cli
    provides: run_loop, run_shell, parse_response (existing tool-handling branch)
provides:
  - Fixed combined-output computation (content-based "(no output)" check)
  - Tool-name dispatch guard in run_loop (only "shell" reaches run_shell)
affects: [03-additional-tools]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tool-name dispatch guard at top of `if parsed[\"type\"] == \"tool\":` block — short-circuits to an `unknown tool '<name>'` Observation before shlex.split/print/run_shell, establishing the extension point for future tools (write_file, read_file)."

key-files:
  created: []
  modified:
    - src/olla/loop.py
    - tests/test_loop.py

key-decisions:
  - "Combined both fixes into 2 commits (one per task: Task A = fix, Task B = feat), per the plan's explicit success criterion 'Two separate commits, one per task' — RED/GREEN verification was still performed for both tasks before each commit."

patterns-established:
  - "Tool dispatch: `if parsed[\"tool\"] != \"shell\": ... continue` at the top of the tool-handling branch is the pattern Phase 3 should extend with `elif`/dict-dispatch for new tool names."

requirements-completed: [LOOP-01, LOOP-02]

# Metrics
duration: 15min
completed: 2026-06-11
---

# Phase 01 Quick Task 260611-upi: Dead-code fix and tool-name dispatch in run_loop Summary

**Fixed run_loop's dead-code "(no output)" branch (WR-01) and added a tool-name dispatch guard so only `shell` reaches `run_shell`, returning `unknown tool '<name>'` for anything else (Finding 2)**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 2 (`src/olla/loop.py`, `tests/test_loop.py`)

## Accomplishments
- Fixed WR-01: `run_loop`'s combined-output branch now checks `if not combined:` (string content) instead of `elif "stdout" in result or "stderr" in result:` (key presence, always true on success) — a real no-output success (e.g. `touch file`) now correctly produces `Observation: (no output)` instead of an empty `Observation: `.
- Added tool-name dispatch (Finding 2): `run_loop` now checks `parsed["tool"] != "shell"` at the top of the tool-handling branch and short-circuits to `Observation: unknown tool '<name>'` without calling `shlex.split`, printing "Step N: running...", or invoking `run_shell`. Establishes the dispatch point Phase 3 will extend with new tool names (`write_file`, `read_file`).
- Both fixes verified RED before implementation: confirmed the repointed/new tests fail against pre-fix `loop.py`, then pass after the fix.

## Task Commits

Each task was committed atomically:

1. **Task A: Fix WR-01 dead-code in combined-output branch** - `f967c22` (fix)
2. **Task B: Add tool-name dispatch (unknown-tool branch) in run_loop** - `7f69865` (feat)

_Note: per the plan's explicit success criteria ("Two separate commits, one per task"), each task's RED test changes and GREEN implementation changes were committed together as a single commit per task — RED was verified (test run, confirmed failing) before applying the GREEN implementation in both cases._

## Files Created/Modified
- `src/olla/loop.py` - Tool-handling branch: rewrote combined-output computation to a content-based `if not combined:` check (Task A); added a `parsed["tool"] != "shell"` dispatch guard at the top of the tool branch returning `Observation: unknown tool '<name>'` (Task B).
- `tests/test_loop.py` - Renamed `test_run_loop_tool_result_missing_output_keys` to `test_run_loop_tool_result_real_no_output_success` and repointed its mock to the real `run_shell` success shape (`stdout`/`stderr` keys present as empty strings) (Task A); added `test_run_loop_unknown_tool_returns_observation` covering the unknown-tool dispatch path, asserting `run_shell` is not called (Task B).

## Decisions Made
- Combined RED+GREEN changes into one commit per task (2 commits total) rather than 4 separate `test`/`feat` commits, per the plan's explicit success criteria ("Two separate commits, one per task. Task A: WR-01 fix, Task B: tool dispatch."). This plan is `type: execute` (not `type: tdd`), so the plan-level TDD gate-sequence validation does not apply — RED/GREEN verification was performed manually before each commit (confirmed each new/repointed test fails on pre-fix code, then passes post-fix).

## Deviations from Plan

None - plan executed exactly as written. Both fixes match the `<action>` blocks verbatim (combined-output branch rewritten to the exact two-branch form specified; dispatch guard added at the exact location specified, before `shlex.split` and the "Step N: running..." print).

## Issues Encountered

- The `cd /home/nacs/Documents/git/olla && PYTHONPATH=src .venv/bin/python -m pytest ...` command from the plan's `<verify>` blocks resolves to the **main repo checkout**, not this worktree (`/home/nacs/Documents/git/olla/.claude/worktrees/agent-ad422a31808ec0900`). Running it as written would test the main repo's unmodified `tests/test_loop.py` (still showing the old `test_run_loop_tool_result_missing_output_keys` name) rather than this worktree's edited files. Resolved by running pytest from the worktree's cwd (no `cd`) using the main repo's `.venv` interpreter directly: `PYTHONPATH=src /home/nacs/Documents/git/olla/.venv/bin/python -m pytest tests/ -q`. All verification commands below were run this way and confirm 42/42 passing in the worktree's tree.

## Next Phase Readiness
- Both open warnings from the Phase 01 checkpoint audit (01-AUDIT.md Findings 1 and 2) are now closed. `src/olla/loop.py`'s tool-handling branch has a clean dispatch point (`if parsed["tool"] != "shell": ... continue`) ready for Phase 3 to extend with additional tool names (`write_file`, `read_file`, etc.).
- Full test suite: 42/42 passing (41 baseline + 1 net new from Task B; Task A renamed/repointed an existing test).

---
*Phase: 01-core-loop-shell-tool-cli*
*Completed: 2026-06-11*

## Self-Check: PASSED

- FOUND: src/olla/loop.py
- FOUND: tests/test_loop.py
- FOUND: .planning/quick/260611-upi-fix-wr-01-dead-code-in-loop-py-and-add-t/260611-upi-SUMMARY.md
- FOUND: commit f967c22 (Task A)
- FOUND: commit 7f69865 (Task B)
- Full test suite: 42/42 passing
