---
phase: 04-memory-tool
plan: 01
subsystem: tool-runtime
tags: [python, react-loop, scratchpad, bounded-memory, tdd]

requires:
  - phase: 03-file-tools
    provides: Existing non-raising ToolResult adapter and visible Observation pipeline
provides:
  - Invocation-local remember and recall tools wired through the model protocol
  - Bounded atomic Scratchpad with exact value, key, and total-capacity semantics
  - Focused tracer, isolation, boundary, replacement, and failure-state tests
affects: [04-02-memory-protocol-hardening, model-prompt, run-loop]

tech-stack:
  added: []
  patterns:
    - Run-loop-owned invocation-local state
    - Projected-state validation before one dictionary assignment
    - Raw payload preservation followed by tool-specific parsing

key-files:
  created:
    - src/olla/tools/memory.py
    - tests/test_tools/test_memory.py
  modified:
    - src/olla/parser.py
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_loop.py

key-decisions:
  - "Own exactly one Scratchpad inside each run_loop invocation so notes cannot cross runs."
  - "Preserve remember payloads in parse_response, then trim only the key in the memory adapter."
  - "Validate value size, new-key count, and projected total capacity before the single mutation."

patterns-established:
  - "Memory result parity: terminal output and the next model Observation use the same selected ToolResult text."
  - "Atomic bounded replacement: projected_total = current_total - old_length + new_length before assignment."

requirements-completed: [MEM-01]

coverage:
  - id: D1
    description: The model can remember a note, explicitly recall it on a later turn, and use it in a final answer without confirmation or cross-run leakage.
    requirement: MEM-01
    verification:
      - kind: e2e
        ref: tests/test_loop.py#test_run_loop_remember_recall_then_final
        status: pass
      - kind: integration
        ref: tests/test_loop.py#test_run_loop_scratchpad_isolation_between_invocations
        status: pass
    human_judgment: false
  - id: D2
    description: Scratchpad writes enforce exact per-value, key-count, and total-capacity bounds with atomic replacement failures.
    requirement: MEM-01
    verification:
      - kind: unit
        ref: tests/test_tools/test_memory.py
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-07-26
status: complete
---

# Phase 04 Plan 01: Invocation-Local Bounded Memory Summary

**Explicit remember/recall tools backed by a bounded, atomic, invocation-local Scratchpad and the existing Observation pipeline**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-26T16:14:30Z
- **Completed:** 2026-07-26T16:27:48Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added a production remember → recall → final tracer with exact terminal/Observation parity, no confirmation, and fresh memory for every `run_loop` call.
- Preserved raw remember values after the first newline while keeping trimmed, case-sensitive keys and distinct malformed/missing/empty results.
- Enforced 2,000 characters per value, 32 keys, and 16,000 total value characters against projected state, with rejected writes proven non-mutating.

## Task Commits

Each TDD gate and production task was committed atomically:

1. **Task 1 RED: memory tracer and invocation isolation** - `8c5330d` (test)
2. **Task 1 GREEN: parser, loop, prompt, and adapter tracer** - `843a920` (feat)
3. **Task 2 RED: exact boundaries and atomicity contract** - `9f91fb0` (test)
4. **Task 2 GREEN: bounded replacement implementation** - `1354a28` (feat)

## Files Created/Modified

- `src/olla/tools/memory.py` - Immutable call boundary, argument parsers, exact limits, and run-local Scratchpad.
- `src/olla/parser.py` - Preserves opaque remember payloads alongside write-file payloads.
- `src/olla/loop.py` - Owns one Scratchpad and dispatches visible remember/recall calls without safety or confirmation gates.
- `src/olla/prompts.py` - Advertises five tools and teaches one compact remember/recall transcript while retaining shell/file guidance.
- `tests/test_loop.py` - Covers the three-turn tracer, both `yes` modes, Observation history, and cross-invocation isolation.
- `tests/test_tools/test_memory.py` - Covers parsing, exact results, inclusive/exclusive limits, replacement accounting, atomic failures, and instance isolation.

## Decisions Made

- Kept the scratchpad as a standard-library dictionary owned by `run_loop`; persistence, automatic injection, and context compaction remain out of scope.
- Kept tolerant tag extraction in `parse_response` and memory-specific line validation in `tools/memory.py`, preserving the existing protocol boundary.
- Recomputed the bounded total from at most 32 stored values before mutation instead of maintaining a second mutable counter, making replacement accounting directly auditable.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Execution resumed from the existing RED commit and a partially staged production implementation. The prompt contained overlapping user edits, so only the Phase 4 memory additions were applied to the index; all unrelated working-tree hunks remained untouched.

## Verification

- Task 1 gate: `61 passed`
- Task 2 adapter gate: `16 passed`
- Plan-focused memory gate: `18 passed, 59 deselected`
- Full maintained suite: `170 passed`
- Ruff on all plan-owned source/test files: passed
- No package, persistent store, CLI option, automatic note injection, or message-compaction path was added.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-02 can harden dry-run behavior, repetition guards, prompt/parser regressions, and exact error delivery against the production adapter established here.
- No blocker remains for the dependent plan.

## Self-Check

PASSED - summary artifact exists and all four task commits are present in history.

---
*Phase: 04-memory-tool*
*Completed: 2026-07-26*
