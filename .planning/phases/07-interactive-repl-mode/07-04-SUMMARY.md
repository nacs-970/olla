---
phase: 07-interactive-repl-mode
plan: 04
subsystem: cli
tags: [repl, prompt_toolkit, key-bindings, react-loop, gap-closure]

# Dependency graph
requires:
  - phase: 07-interactive-repl-mode
    provides: "07-01's SessionState-injectable run_loop() and minimal main_loop() REPL entry point; 07-02's full FileHistory/multiline PromptSession construction this plan extends"
provides:
  - "A real Alt+Enter keyboard path in the REPL that inserts a newline without submitting, closing REPL-01's multiline-editing clause"
  - "Automated cross-turn proof that a stale read snapshot refuses write_file across a REPL turn boundary, closing 07-01's routed-to-human prohibition"
affects: []

# Actuals (#2632)
actuals:
  tokens: 1319
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_build_key_bindings() factory returning a KeyBindings instance with exactly one registered binding, passed to PromptSession via key_bindings= alongside the existing history=/multiline= kwargs — the same pattern 07-02 established for other PromptSession construction kwargs"

key-files:
  created: []
  modified:
    - src/olla/repl.py
    - tests/test_repl.py
    - tests/test_loop.py

key-decisions:
  - "No production-code change was needed for Task 2 — _execute_write_file()'s freshness check already operates on a plain read_snapshots dict parameter regardless of whether it originated from a fresh one-shot construction or a session-persisted SessionState.read_snapshots, confirmed unchanged during 07-01's SessionState refactor. This plan is test-only for that gap."

requirements-completed: [REPL-01, REPL-02]

coverage:
  - id: D1
    description: "PromptSession is constructed with a key_bindings= kwarg (a KeyBindings instance with exactly one binding on escape,enter) whose handler inserts a newline into the buffer rather than submitting, and plain Enter still submits unchanged (multiline stays False)"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_session_construction_uses_file_history_and_multiline"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_alt_enter_key_binding_inserts_newline_without_submitting"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session"
        status: pass
    human_judgment: false
  - id: D2
    description: "A stale (externally modified between two REPL turns) read snapshot does not satisfy the read-before-write precondition for write_file on the same shared SessionState.read_snapshots, without an intervening re-read"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_stale_snapshot_is_refused_across_repl_turn_boundary"
        status: pass
    human_judgment: false
  - id: D3
    description: "No existing test in tests/test_repl.py or tests/test_loop.py was weakened, removed, or had its assertions relaxed by this plan"
    verification:
      - kind: unit
        ref: "tests/test_repl.py -x (16 passed) and tests/test_loop.py -x (150 passed), full suite (468 passed, 465-test baseline + 3 new tests, no regressions)"
        status: pass
    human_judgment: false

# Metrics
duration: 3min
completed: 2026-09-14
status: complete
---

# Phase 7 Plan 4: Multiline Editing + Cross-Turn Stale-Snapshot Gap Closure Summary

**REPL gains a real Alt+Enter-inserts-newline key binding proven through prompt_toolkit's own key-binding resolution (not a kwarg-presence check), and 07-01's cross-turn stale-read-snapshot prohibition is now directly proven by an automated test with zero production code change.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-14T18:15:51Z
- **Completed:** 2026-09-14T18:18:30Z
- **Tasks:** 2 completed
- **Files modified:** 3 (`src/olla/repl.py`, `tests/test_repl.py`, `tests/test_loop.py`)

## Accomplishments
- `src/olla/repl.py` gained `_build_key_bindings()` — a `KeyBindings` factory registering exactly one binding on `(Keys.Escape, Keys.ControlM)` (Alt+Enter) whose handler calls `event.current_buffer.insert_text("\n")`, wired into `main_loop()`'s `PromptSession` via a new `key_bindings=` kwarg alongside the unchanged `history=`/`multiline=False` construction
- Three layered tests prove the fix genuinely works: a strengthened construction test (`multiline is False` and `key_bindings` is a real `KeyBindings` instance, not a presence check), a direct-handler test proving `insert_text("\n")` is called and `validate_and_handle` (submit) is never called, and a real, unmocked `PromptSession` driven via `create_pipe_input()` proving the keystroke sequence `line1`, Alt+Enter, `line2`, Enter resolves to `"line1\nline2"` through prompt_toolkit's own key-binding merge/priority machinery
- Every existing exit-semantics test (single/double Ctrl+C, EOFError) in `tests/test_repl.py` passes unchanged — plain Enter/Ctrl+C/Ctrl+D behavior is untouched
- `tests/test_loop.py` gained `test_run_loop_stale_snapshot_is_refused_across_repl_turn_boundary`: two separate `run_loop()` calls share one `SessionState`; the target file is read in turn 1, modified externally (no tool call) between turns, then a `write_file` attempt with no intervening re-read in turn 2 is refused — `Confirm.ask` and `write_file` are never called, the file on disk is untouched, and the refusal observation (containing "changed" and "read_file") reaches the next model call's messages
- No production code change was required for the staleness closure — `_execute_write_file()`'s freshness check is unchanged by the 07-01 `SessionState` refactor and has no dependency on whether `read_snapshots` came from a fresh construction or a session-persisted object

## Task Commits

Each task was committed atomically via TDD (Task 1) or a direct test-only addition (Task 2):

1. **Task 1: Real multiline editing — Alt+Enter inserts a newline, plain Enter still submits** — TDD cycle:
   - RED: `f21d7a8` (test) — `_build_key_bindings` import fails to collect (`ImportError: cannot import name '_build_key_bindings' from 'olla.repl'`), confirmed via `pytest tests/test_repl.py -x`
   - GREEN: `949d1c2` (feat) — `timeout 30 pytest tests/test_repl.py -x` passes (16 passed, exit 0, no hang); full suite 467 passed
   - REFACTOR: none needed — `ruff check` was already clean after GREEN
2. **Task 2: Cross-turn negative staleness test — externally modified read snapshot refuses write across REPL turns** — `069f2e5` (test) — `pytest tests/test_loop.py -k "stale_snapshot_is_refused_across_repl_turn_boundary" -x` passes on first run against the existing (unmodified) `_execute_write_file()` implementation

**Plan metadata:** (this commit, once written)

## Files Created/Modified
- `src/olla/repl.py` - new `_build_key_bindings()` factory; `PromptSession` gains a `key_bindings=` kwarg
- `tests/test_repl.py` - strengthened `test_session_construction_uses_file_history_and_multiline`; new `test_alt_enter_key_binding_inserts_newline_without_submitting` and `test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session`
- `tests/test_loop.py` - new `test_run_loop_stale_snapshot_is_refused_across_repl_turn_boundary`

## Decisions Made
- Task 2's closure is test-only, as planned during 07-04's planning phase: code inspection confirmed `_execute_write_file()`'s freshness check takes `read_snapshots` as a plain dict parameter with no branch on its origin, so the existing single-invocation staleness logic already covers the cross-turn case correctly — only test coverage was missing.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their `<action>` specifications precisely, and the empirical verification the plan cited from its own planning phase (prompt_toolkit key-sequence normalization, the pipe-input smoke test) was independently re-confirmed during execution.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the mechanical `gsd_run check tdd-red-evidence` gate was not invoked. RED/GREEN discipline was followed manually for Task 1 (the only `tdd="true"` task in this plan):
- **RED** (`f21d7a8`, `test(07-04): ...`): new tests and import committed before `_build_key_bindings` existed in `src/olla/repl.py`. `pytest tests/test_repl.py -x` failed at collection (`ImportError: cannot import name '_build_key_bindings' from 'olla.repl'`) — a genuine RED caused by the new API surface not existing yet, not a fixture crash or unrelated failure.
- **GREEN** (`949d1c2`, `feat(07-04): ...`): implemented `_build_key_bindings()` and wired it into `main_loop()`'s `PromptSession`. Same test file now passes in full (16 passed, run under the plan's mandatory `timeout 30` wrapper, exit 0); full suite 467 passed (465-test baseline + 2 new tests), no regressions.
- **REFACTOR**: not needed — `ruff check src/olla/repl.py tests/test_repl.py` was already clean after GREEN.

Task 2 is `type="auto"` (no `tdd="true"`), executed directly per its `<action>`/`<acceptance_criteria>` with the standard single-commit discipline; its test passed against the unmodified production code on first run, confirming the planning-time code-inspection conclusion that no source change was needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. No new dependencies were added this plan.

## Next Phase Readiness
- Both gaps 07-VERIFICATION.md found in Phase 7 are closed: REPL-01's multiline-editing clause is genuinely deliverable and proven through prompt_toolkit's own key-binding resolution (not a kwarg-presence check), and 07-01's cross-turn stale-snapshot prohibition is directly proven by an automated test rather than resting on code-level inference.
- Full regression: `pytest tests/test_repl.py tests/test_loop.py -x` (166 passed) and full suite `pytest -q` (468 passed — 465-test baseline recorded in 07-03-SUMMARY.md + 3 new tests this plan, no regressions).
- The plan-level `<verification>`'s additional real-terminal sanity check (launching `olla --model <local-model>` interactively and pressing Alt+Enter at a live TTY) was explicitly marked non-required belt-and-suspenders in 07-04-PLAN.md — the automated `test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session` test is what actually gates this plan's pass/fail, and it passed. This automated executor session has no interactive TTY available to additionally exercise that manual step; a human with a terminal may still wish to confirm it directly, but it does not block phase completion.
- Deferred, non-blocking housekeeping carried over from the plan: `07-VALIDATION.md` is still an unfilled template despite 07-01/02/03/04 having executed — out of scope for this gap-closure plan, flagged for a future `/gsd-validate-phase 07` pass.
- No blockers. Re-run `/gsd-verify-work` (or equivalent phase verification) to confirm both gaps close and flip Phase 7's status from `gaps_found` to verified.

---
*Phase: 07-interactive-repl-mode*
*Completed: 2026-09-14*

## Self-Check: PASSED

All key files present on disk (`src/olla/repl.py`, `tests/test_repl.py`, `tests/test_loop.py`, this SUMMARY.md). All three commit hashes (`f21d7a8`, `949d1c2`, `069f2e5`) found in `git log --oneline --all`. Task-level `<acceptance_criteria>` re-verified: `pytest tests/test_repl.py -x` (16 passed), `pytest tests/test_repl.py -k "session_construction or alt_enter" -x` (3 passed, exactly matching the named criterion), `pytest tests/test_loop.py -k "stale_snapshot_is_refused_across_repl_turn_boundary" -x` (1 passed), `pytest tests/test_loop.py -x` (150 passed, including both pre-existing staleness tests unchanged). Plan-level `<verification>` re-run: `pytest tests/test_repl.py tests/test_loop.py -x` (166 passed) and full suite `pytest -q` (468 passed, no regressions vs. the 465-test pre-plan baseline recorded in 07-03-SUMMARY.md).
