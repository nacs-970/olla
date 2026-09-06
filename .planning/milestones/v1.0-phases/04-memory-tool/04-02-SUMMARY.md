---
phase: 04-memory-tool
plan: 02
subsystem: tool-runtime
tags: [python, parser, system-prompt, dry-run, scratchpad, tdd]

requires:
  - phase: 04-memory-tool
    plan: 01
    provides: Invocation-local bounded Scratchpad and production remember/recall dispatch
provides:
  - Verbatim remember-payload and five-tool prompt contract coverage
  - Redacted memory dry-run previews with parser-only validation
  - Normal-mode privacy, error parity, repetition, and lifecycle integration coverage
affects: [phase-verification, model-protocol, run-loop]

tech-stack:
  added: []
  patterns:
    - Opaque args preserve literal tool data while final tags outside args retain precedence
    - Dry-run validates with pure parsers and never accesses the stateful adapter
    - Contract tests use focused semantic assertions instead of full prompt snapshots

key-files:
  created:
    - tests/test_prompts.py
  modified:
    - src/olla/parser.py
    - src/olla/loop.py
    - tests/test_parser.py
    - tests/test_loop.py

key-decisions:
  - "A final tag outside an opaque args payload wins over remember/write_file, while literal final-tag text inside args remains data."
  - "Memory dry-run uses only parse_remember_args or parse_recall_args and renders key/count metadata without adapter access."

patterns-established:
  - "Dry-run privacy boundary: parse and report normalized metadata, then return before state lookup or mutation."
  - "Memory repetition signatures use normalized keys and values; the third identical call aborts before adapter execution."

requirements-completed: [MEM-01]

coverage:
  - id: D1
    description: Remember payloads retain significant characters, recall keys are trimmed, and the prompt teaches exactly five tools with one complete memory transcript.
    requirement: MEM-01
    verification:
      - kind: unit
        ref: tests/test_parser.py and tests/test_prompts.py
        status: pass
    human_judgment: false
  - id: D2
    description: Memory dry-run validates and previews calls without state access, disclosure, safety classification, or confirmation.
    requirement: MEM-01
    verification:
      - kind: integration
        ref: tests/test_loop.py#test_dry_run_memory_preview_is_non_accessing
        status: pass
      - kind: integration
        ref: tests/test_loop.py#test_dry_run_memory_errors_are_exact_and_non_accessing
        status: pass
    human_judgment: false
  - id: D3
    description: Normal memory results and errors preserve Observation parity, privacy, repetition control, and invocation isolation.
    requirement: MEM-01
    verification:
      - kind: integration
        ref: tests/test_loop.py#test_run_loop_memory_results_match_observations
        status: pass
      - kind: e2e
        ref: tests/test_loop.py#test_run_loop_remember_recall_then_final
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-07-27
status: complete
---

# Phase 04 Plan 02: Memory Protocol and Lifecycle Hardening Summary

**Verbatim memory protocol contracts and redacted parser-only dry runs backed by deterministic privacy, Observation, repetition, and isolation tests**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-26T17:23:09Z
- **Completed:** 2026-07-26T17:30:32Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Locked remember character fidelity, trimmed recall keys, final precedence, the exact five-tool prompt, all prior shell/file guidance, and one compact memory round trip.
- Added dry-run remember/recall handling that validates through pure parsers, reports only normalized key/count metadata, and never reads or mutates Scratchpad state.
- Proved no-confirm/no-safety dispatch, write-value redaction, exact result-to-Observation parity, normalized repetition guards, and cross-invocation isolation.

## Task Commits

Each TDD gate and production task was committed atomically:

1. **Task 1 RED: parser fidelity and prompt contracts** - `09f2b04` (test)
2. **Task 1 GREEN: final precedence for opaque memory calls** - `844e9fe` (fix)
3. **Task 2 RED: dry-run and lifecycle hardening** - `9d9d061` (test)
4. **Task 2 GREEN: safe memory dry-run previews** - `c418e09` (feat)

## Files Created/Modified

- `tests/test_prompts.py` - Semantic five-tool, memory-format, transcript, prior-guidance, and no-compaction assertions.
- `tests/test_parser.py` - Verbatim remember payload, trimmed recall, missing-args, and final-precedence regressions.
- `src/olla/parser.py` - Restores final precedence outside opaque args without corrupting literal remembered content.
- `tests/test_loop.py` - Covers dry-run non-access, privacy, error parity, no-confirm behavior, normalized repetition, and reset behavior.
- `src/olla/loop.py` - Adds pure-parser dry-run branches for remember and recall.

## Decisions Made

- Treated `<final>` inside an opaque remember/write payload as literal data, but preserved the established final-over-tool behavior when the final tag appears outside the args span.
- Kept dry-run validation on the existing public pure parsers rather than adding preview methods or touching the Scratchpad instance.
- Used focused prompt assertions that tolerate harmless path/example wording edits while enforcing all five tool names, formats, restrictions, and transcript semantics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored final precedence for opaque-payload tools**
- **Found during:** Task 1 (parser character fidelity and prompt contract)
- **Issue:** The raw remember/write-file fast path returned a tool before checking a final tag outside the args payload, contradicting the parser's established final precedence.
- **Fix:** Detect a final tag outside the matched opaque args span before returning the raw tool payload; literal final-tag text inside args remains preserved data.
- **Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
- **Verification:** Task 1 contract suite passed, including both final precedence and verbatim args cases.
- **Committed in:** `844e9fe`

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** The fix restores an existing parser invariant without widening the protocol or changing memory scope.

## Issues Encountered

- `src/olla/loop.py` and `tests/test_loop.py` contained user-owned unstaged shell-error hunks. Interactive hunk staging committed only the Phase 4 additions and left all user changes untouched.

## Verification

- Task 1 parser/prompt gate: `23 passed`
- Task 2 focused memory-loop gate: `19 passed, 49 deselected`
- Plan suite: `107 passed`
- End-to-end tracer: `2 passed`
- Full maintained suite: `200 passed`
- Ruff across `src` and `tests`: passed
- No package, persistence, schema, CLI option, automatic note injection, eviction, or context-compaction path was added.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 04 implementation is complete with D-01 through D-16 covered across plans 04-01 and 04-02.
- The phase is ready for its configured post-execution review and verification gates; optional live Ollama smoke testing remains non-blocking.

## Self-Check

PASSED - summary artifact exists and all four task commits are present in history.

---
*Phase: 04-memory-tool*
*Completed: 2026-07-27*
