---
phase: 03-file-tools
plan: 05
subsystem: file-safety
tags: [python, pathlib, difflib, file-tools, confirmation, uat-gap-closure]

requires:
  - phase: 03-file-tools
    plan: 04
    provides: File-tool-first prompting and recoverable malformed-shell guidance
provides:
  - Complete same-resolved-target read prerequisite for existing-file overwrites
  - Exact freshness checks before preview and immediately before write
  - Bounded create previews and unified overwrite diffs with resolved paths
  - Compact same-file edit protocol separating scratchpad memory from file contents
affects: [file-tool-safety, small-model-editing, future-write-tools]

tech-stack:
  added: []
  patterns:
    - Invocation-local read snapshots keyed by resolved pathlib Path
    - Optimistic freshness validation around human confirmation
    - Local-only bounded content and unified-diff previews

key-files:
  created: []
  modified:
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_loop.py
    - tests/test_prompts.py

key-decisions:
  - "Treat only a successful, completely observed same-resolved-path read as authority to overwrite an existing file."
  - "Make --yes bypass only Confirm.ask; path resolution, classification, preview, and freshness checks always run."
  - "Keep write_file as full replacement and enforce edit safety entirely in run_loop orchestration and the model prompt."

patterns-established:
  - "Read-derived overwrite: resolve, read fully, compare before preview, compare after approval, then replace."
  - "Race-safe creation: a target absent at preview must remain absent immediately before write."

requirements-completed: [FILE-01, FILE-02]

coverage:
  - id: D1
    description: "Existing targets cannot be overwritten without a complete same-run read and exact freshness checks around confirmation."
    requirement: FILE-02
    verification:
      - kind: integration
        ref: "tests/test_loop.py#existing-file prerequisite, stale snapshot, confirmation race, and alias regressions"
        status: pass
    human_judgment: false
  - id: D2
    description: "Create and overwrite operations disclose resolved path, byte counts, and bounded content or unified-diff previews; malformed paths recover safely."
    requirement: FILE-02
    verification:
      - kind: unit
        ref: "tests/test_loop.py#preview disclosure and malformed path regressions"
        status: pass
    human_judgment: false
  - id: D3
    description: "The prompt teaches same-file read-observe-write editing, and a real filesystem regression preserves every unrequested byte."
    requirement: FILE-01
    verification:
      - kind: integration
        ref: "tests/test_prompts.py and tests/test_loop.py#test_run_loop_same_target_edit_preserves_unrequested_bytes"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-07-29
status: complete
---

# Phase 03 Plan 05: Guarded Existing-File Edits Summary

**Existing-file writes now require a complete fresh same-target read, display a bounded unified diff, and revalidate the target after approval before replacing it.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-28T20:32:32Z
- **Completed:** 2026-07-28T20:43:16Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added invocation-local exact-content snapshots keyed by resolved path, so aliases share authority while failed or truncated observations never authorize overwrite.
- Revalidated target identity, existence, and bytes before preview and after approval; stale files and absent-to-existing races are refused without calling `write_file`.
- Added resolved-path create/overwrite labels with byte counts and bounded proposed-content or unified-diff previews, including safe malformed-path handling in normal and dry-run modes.
- Replaced the blind overwrite prompt example with a same-path read/Observation/write edit transcript and explicit file-versus-scratchpad rules.
- Proved with a real temporary file that a requested one-line edit preserves prefix, suffix, blank lines, and trailing newline exactly.

## Task Commits

Each task was committed atomically:

1. **Task 1: Enforce one safe existing-file overwrite path end to end** — `838366c` (`feat`)
2. **Task 2: Teach the same-file edit contract and prove unrelated content survives** — `2f1f24a` (`feat`)

## Files Created/Modified

- `src/olla/loop.py` — Safe path resolution, read snapshots, freshness/race checks, and bounded write previews.
- `src/olla/prompts.py` — Compact same-file edit sequence, preservation rule, stale retry guidance, and file/memory separation.
- `tests/test_loop.py` — Model-independent safety, preview, race, malformed-path, and exact-preservation regressions.
- `tests/test_prompts.py` — Prompt ordering, edit transcript, creation/edit distinction, and scratchpad-boundary contracts.

## Decisions Made

- A read authorizes overwrite only when its exact raw contents fit completely in the model Observation; truncated reads remain useful for inspection but not destructive editing.
- The resolved path is the snapshot identity and the actual path passed to file tools, preventing alias changes after validation from redirecting a write.
- `--yes` skips only the interactive question. It does not skip previews, existing-file prerequisites, or either freshness check.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `state.advance-plan` inherited the orchestrator's temporary `Plan: 1 of 5` execution marker and advanced it to `2 of 5` even though 03-05 was the only incomplete plan. The closeout corrected STATE to `5 of 5` and restored Phase 3's completed ROADMAP status after the required SDK mutations.

## Authentication Gates

None.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Verification

- Focused prompt and loop suites: `97 passed`
- Maintained suite: `228 passed`
- Ruff on `src` and `tests`: passed
- `git diff --check` on all plan-owned files: passed
- Task commits contain only their explicit owned files; protected HANDOFF, Phase 04 planning, cache, and scratch files remain untouched.

## Threat Flags

None - all added file-access, confirmation, path-resolution, and freshness surfaces were explicitly covered by the plan threat model.

## Next Phase Readiness

- G-03-4 is closed by deterministic runtime policy and model-independent regressions rather than model capacity.
- Phase 3 file tools retain full-replacement parser fidelity, new-file creation, memory dispatch, repetition guards, dry-run behavior, and G-03-1/G-03-3 guidance.
- Phase 3 is ready for verification and UAT retest.

## Self-Check: PASSED

- FOUND: summary and all four modified implementation/test files.
- FOUND: task commits `838366c` and `2f1f24a`.
- PASSED: focused, maintained-suite, Ruff, and diff-check verification.

---
*Phase: 03-file-tools*
*Completed: 2026-07-29*
