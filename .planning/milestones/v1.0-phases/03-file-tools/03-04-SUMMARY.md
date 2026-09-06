---
phase: 03-file-tools
plan: 04
subsystem: model-protocol
tags: [python, prompt, shell-recovery, file-tools, uat-gap-closure]

requires:
  - phase: 03-file-tools
    plan: 03
    provides: Safe read/write adapters and confirm-gated file dispatch
provides:
  - Prescriptive malformed-shell recovery for normal and dry-run execution
  - File-tool-first prompt ordering with relative-path examples
  - Explicit prohibition on shell-based file reading and writing
affects: [03-05-safe-existing-file-edits, small-model-tool-selection, phase-04-memory-prompt]

tech-stack:
  added: []
  patterns:
    - Recoverable model-facing Observations for malformed tool arguments
    - Dedicated file tools taught before general shell execution

key-files:
  created: []
  modified:
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_loop.py

key-decisions:
  - "Keep malformed-shell handling in run_loop and change only its model-facing wording."
  - "Use relative paths and place read_file/write_file before shell for weak local models."
  - "Preserve the five-tool protocol and Phase 4 memory examples while tightening file-tool routing."

requirements-completed: [FILE-01, FILE-02]
gap-ids-resolved: [G-03-1, G-03-3]

completed: 2026-07-29
status: complete
---

# Phase 03 Plan 04: Small-Model File-Tool Routing Summary

**Malformed shell calls now receive prescriptive recovery guidance, while the concise system prompt teaches dedicated file tools before shell using relative paths.**

## Accomplishments

- Replaced the cryptic `could not parse command` response with a shell-specific mismatched-quote message that asks the model to fix and retry.
- Kept dry-run side-effect free and normal execution recoverable through the existing Observation loop.
- Moved `read_file` and `write_file` ahead of shell in the five-tool prompt and examples.
- Replaced absolute example paths with relative paths and explicitly prohibited cat/echo/sed/awk file I/O through shell.
- Preserved memory syntax, the remember/recall round trip, final tags, delimiter guidance, and existing runtime behavior.

## Task Commits

1. **Task 1: Improve malformed-shell recovery** — `d923d7e` (`fix`)
2. **Task 2: Prioritize dedicated file tools** — `a7b5a8c` (`fix`)

## Files Modified

- `src/olla/loop.py` — Prescriptive error text in normal and dry-run shell parsing paths.
- `src/olla/prompts.py` — File-tool-first ordering, relative examples, and the shell file-I/O prohibition.
- `tests/test_loop.py` — Assertions for the revised normal and dry-run recovery wording.

## Reconciliation Note

These three files were pre-existing unstaged user-owned changes from the earlier Phase 3 UAT gap closure. On 2026-07-29 the user explicitly authorized reviewing and committing only those intended hunks. No STATE, HANDOFF, UAT, Phase 4 planning, cache, test fixture, or scratch file was staged with either task commit.

The original short `03-04-PLAN.md` draft was normalized into the current structured two-task plan without changing its scope or implementation intent.

## Verification

- Focused malformed-shell and prompt contract selection: `7 passed`
- Maintained suite: `211 passed`
- Ruff on `src` and `tests`: passed
- `git diff --check` on all plan-owned files: passed

## Known Limit

The prompt improvement reduces small-model tool-selection errors but does not make an existing-file overwrite safe. UAT gap `G-03-4` demonstrated that a weak model can still call `write_file` before reading the target. That separate, diagnosed runtime-safety gap is scoped to `03-05-PLAN.md`.

## Self-Check

PASSED — both task commits exist, the structured plan and summary are present, the three implementation/test files are clean, and the maintained suite is green.

---
*Phase: 03-file-tools*
*Completed: 2026-07-29*
