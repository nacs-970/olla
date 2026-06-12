---
phase: 02-safety-gate-loop-control
plan: 02
subsystem: safety
tags: [dry-run, repetition-guard, ReAct-loop, safety-gate, cli]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: "02-01's olla.safety.check(argv, yes) -> Decision (ALLOW/CONFIRM/BLOCK) contract, run_loop's dry_run parameter (unused placeholder), and the gate-dispatch shell-tool branch"
provides:
  - "run_loop --dry-run early-return branch: exactly one ollama.chat call, dispatches on parse_response type, reuses olla.safety.check() for the shell-tool verdict (auto-approved / would prompt for confirmation / BLOCKED: <reason>), never calls run_shell or Confirm.ask"
  - "run_loop repetition guard: (tool, tuple(argv)) signature tracked across iterations; 3rd consecutive identical signature aborts with a distinct diagnostic before the 3rd run_shell call"
  - "SAFE-03 regression test proving the repetition-guard message and the max-steps message never shadow each other"
  - "cli.py --dry-run flag fully wired to run_loop(dry_run=True), inert notice removed"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dry-run as a structurally separate early-return branch at the top of run_loop (before the main for-loop) - never falls through to execution paths, verified by run_shell.call_count == 0 / Confirm.ask.call_count == 0 across all 6 dispatch shapes"
    - "Repetition signature (tool_name, tuple(argv)) tracked via prev_sig/repeat_count, checked only on the path that has already passed BLOCK/CONFIRM-decline continues - so denied/blocked calls never pollute the streak"
    - "Single print-site for 'Step N: running...' - collapsed from two call sites (CONFIRM branch + ALLOW else-branch) into one, after the repetition check"

key-files:
  created: []
  modified:
    - src/olla/loop.py
    - src/olla/cli.py
    - tests/test_loop.py
    - tests/test_cli.py

key-decisions:
  - "Repetition check placed AFTER the BLOCK-continue and CONFIRM-decline-continue but BEFORE the single 'Step N: running...' print/run_shell call - required collapsing the pre-existing dual print sites (CONFIRM branch printed before Confirm.ask; ALLOW branch printed in an else) into one, since the repetition abort must happen before any print for the 3rd repeated call. Verified no existing test asserted on the CONFIRM-branch print location, so this was a safe non-behavioral restructure."
  - "BLOCK-tier dry-run verdict reason is asserted against the live olla.safety.check() return value (not a hardcoded string) - keeps the test coupled to the real gate logic per D-09's 'verdict is computed by running the gate-check logic, not argv alone' requirement."

patterns-established:
  - "Early-return preview branches (dry-run) mirror the main loop's first-iteration call shape exactly (call_model + parse_response) to guarantee preview accuracy matches real execution"

requirements-completed: [SAFE-01, LOOP-04, SAFE-03]

# Metrics
duration: ~25min
completed: 2026-06-12
---

# Phase 02 Plan 02: Dry-Run Preview + Repetition Guard Summary

**`--dry-run` now makes exactly one model call and prints a real safety-gate verdict (ALLOW/CONFIRM/BLOCK via `olla.safety.check()`) without executing anything; a repetition guard aborts after 3 identical consecutive shell calls with a diagnostic distinct from the "Reached max steps" message, backed by a SAFE-03 regression test.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `run_loop(..., dry_run=True)` is a structurally separate early-return branch: one `ollama.chat` call, dispatches on `parse_response`'s 4 shapes (`final`, `none`, unknown-tool, shell), and for shell calls reuses `check(argv, yes=yes)` to print one of three verdicts (`auto-approved (read-only allowlist)`, `would prompt for confirmation`, `BLOCKED: <reason>`)
- All 6 dry-run dispatch shapes (final, none, unknown-tool, shell-ALLOW, shell-CONFIRM, shell-BLOCK) plus the malformed-args case verified to never call `run_shell` or `Confirm.ask`
- Repetition guard: `(tool, tuple(argv))` signature tracked across loop iterations; 3rd consecutive identical signature prints `"olla stopped: same shell call repeated 3x — model likely stuck"` and returns BEFORE the 3rd `run_shell` call
- 2x-repeat-then-different and BLOCK-interrupted sequences proceed normally (no false abort)
- SAFE-03 regression test (`test_run_loop_max_steps_with_varied_shell_calls`) confirms varied non-repeating shell calls still hit `"Reached max steps (N) without a <final> answer."` and this is never accompanied by the repetition message
- `src/olla/cli.py` no longer prints the inert "--dry-run is not yet enforced" notice; `--dry-run` was already threaded to `run_loop(dry_run=...)` since 02-01

## Task Commits

Each task followed the RED/GREEN TDD cycle and was committed atomically:

1. **Task 1: Add --dry-run single-call preview branch**
   - `a2ba029` (test) - 7 failing tests for the 6 dry-run dispatch shapes + malformed-args
   - `9bca488` (feat) - dry-run early-return branch in `run_loop`, reuses `check(argv, yes=yes)`
2. **Task 2: Add repetition guard, wire --dry-run in cli.py, add SAFE-03 regression test**
   - `9ad8ce4` (test) - failing tests for repetition-abort, 2x-repeat-then-different, BLOCK-interrupted, SAFE-03, and `--dry-run` CLI wiring
   - `167b9c1` (feat) - repetition guard with `prev_sig`/`repeat_count`, single print-site restructure, removed inert `--dry-run` notice from `cli.py`

**Plan metadata:** (this commit)

## Files Created/Modified
- `src/olla/loop.py` - Added `if dry_run:` early-return branch (one `call_model` + `parse_response` call, dispatches on type, reuses `check()` for shell verdict); added `prev_sig`/`repeat_count` repetition tracking in the main loop, repetition-abort check placed after BLOCK/CONFIRM-decline continues and before the (now single) "Step N: running..." print + `run_shell` call
- `src/olla/cli.py` - Removed the 2-line inert "--dry-run is not yet enforced (Phase 2)" notice; `run_loop(..., dry_run=dry_run)` call unchanged (already correct from 02-01)
- `tests/test_loop.py` - Added 7 dry-run tests (`test_dry_run_final_response_prints_preview_and_stops`, `test_dry_run_none_response_prints_preview_and_stops`, `test_dry_run_unknown_tool_prints_preview_and_stops`, `test_dry_run_allow_tier_prints_preview_and_stops`, `test_dry_run_confirm_tier_prints_preview_and_stops`, `test_dry_run_block_tier_prints_preview_and_stops`, `test_dry_run_malformed_args_prints_error_and_stops`) and 4 repetition/SAFE-03 tests (`test_run_loop_repetition_guard_aborts_before_third_call`, `test_run_loop_two_repeats_then_different_proceeds_normally`, `test_run_loop_block_interrupted_sequence_does_not_abort`, `test_run_loop_max_steps_with_varied_shell_calls`); added `from olla.safety import check` import
- `tests/test_cli.py` - Replaced `test_dry_run_flag_prints_inert_notice` with `test_dry_run_flag_threaded_through` (asserts the notice is GONE and `run_loop` receives `dry_run=True`)

## Decisions Made
- **Single print-site restructure for "Step N: running..."**: The pre-02-02 code printed "Step N: running..." in two places (once inside the `CONFIRM and not yes` branch before `Confirm.ask`, once in the `else` for ALLOW/yes-bypass paths). The plan requires the repetition-abort check to fire BEFORE this print on the 3rd repeated call, which is only possible with one print site reachable from all three paths (ALLOW, CONFIRM-approved, yes-bypass). Collapsed to a single print after the repetition check. Verified safe: no test asserted on the CONFIRM-branch print location specifically, and the full 77-test suite (including all pre-existing CONFIRM/ALLOW tests) passes unchanged.
- **BLOCK-tier dry-run test derives its expected reason from `check()`** rather than hardcoding the blocklist message string, per the plan's "reason matches whatever check() returns for this case" instruction — keeps the test from drifting if 02-01's blocklist wording changes.

## Deviations from Plan

None - plan executed as written. The single print-site restructure was explicitly anticipated by the plan's task ordering note ("the repetition check must sit AFTER the BLOCK/CONFIRM-decline continue points... but BEFORE the existing 'Step N: running...' print and run_shell call") and required no behavior change beyond consolidating duplicate print statements.

## Issues Encountered

- Confirmed (per 02-01's noted issue) that `pytest` must run with `PYTHONPATH=src` against the shared `.venv` at the main repo root; verified the editable install resolves into THIS worktree's `src/olla` (not the main repo's) via `python -c "import olla.loop; print(olla.loop.__file__)"` before trusting any test results.

## Next Phase Readiness
- Phase 2 (Safety Gate + Loop Control) is now functionally complete: confirm-gate dispatch (02-01) + dry-run preview + repetition guard (02-02) cover ROADMAP Phase 2 success criteria 1-4
- Full test suite: 77/77 passing (`pytest tests/` - includes all Phase 1, 02-01, and 02-02 tests, no regressions)
- Verification greps confirmed: `"olla stopped: same shell call repeated 3x"` present in `loop.py`; `"Reached max steps"` message unchanged; `"dry-run is not yet enforced"` absent from `cli.py`; `"check(argv, yes=yes)"` appears twice in `loop.py` (gate dispatch + dry-run verdict)
- No blockers for Phase 3

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-12*
