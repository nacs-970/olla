---
phase: 03-file-tools
plan: 02
subsystem: cli-agent
tags: [python, ollama, react-loop, file-io, pathlib, confirm-gate]

# Dependency graph
requires:
  - phase: 03-file-tools
    provides: read_file tool, ToolResult contract, if/elif/else dispatch scaffold, generalized repetition guard (03-01)
provides:
  - write_file(path, content) tool with never-raise contract (src/olla/tools/files.py)
  - Tool-conditional parser fix preserving write_file <args> content verbatim (fences, trailing newline)
  - loop.py write_file dispatch (dry-run preview + confirm-gated normal-loop write)
  - SYSTEM_PROMPT documentation for write_file path/content encoding and </args> caveat
  - SC2/SC3 satisfied: confirm-gate shows resolved path; read-then-write end-to-end works through run_loop
affects: [04-polish, future phases touching loop.py dispatch or parser.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tool-conditional parsing: parser.py checks original (pre-fence-strip) content for write_file before falling back to the generic fence-strip + <final>/<tool> path, preserving file-content fidelity for exactly one tool"
    - "write_file args encoding: first line of <args> is the path, remainder (via partition('\\n')) is file content"
    - "Unconditional confirm-gate for write_file (no safety.check() — distinct from shell's ALLOW/CONFIRM/BLOCK tiers)"

key-files:
  created: []
  modified:
    - src/olla/parser.py
    - src/olla/tools/base.py
    - src/olla/tools/files.py
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_parser.py
    - tests/test_tools/test_files.py
    - tests/test_loop.py

key-decisions:
  - "parser.py special-cases write_file by matching TOOL_RE/ARGS_RE against the original content BEFORE fence-stripping, returning args_raw verbatim; all other tools fall through to the unchanged fence-strip + strip() path"
  - "write_file does not auto-create missing parent directories (T-03-09, accepted) — errors with 'parent directory does not exist'"
  - "write_file confirm-gate is unconditional (no safety.check() routing) since it never produces a shell argv"
  - "Repurposed test_run_loop_unknown_tool_returns_observation to use 'browse' instead of 'write_file' now that write_file is a recognized tool"

patterns-established:
  - "Tool-conditional parsing branch for tools whose <args> payload is opaque content rather than a command string"

requirements-completed: [FILE-02]

# Metrics
duration: ~25min
completed: 2026-06-15
---

# Phase 3 Plan 2: write_file Tool Summary

**write_file tool with confirm-gated, resolved-path-displaying writes; parser fix preserves file-content fences/newlines verbatim for write_file while leaving all other tool parsing unchanged**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-15T13:55:00Z
- **Completed:** 2026-06-15T14:03:00Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- `write_file(path, content)` added to `src/olla/tools/files.py`, mirroring `read_file`'s never-raise contract; errors on missing parent directory without creating it
- Fixed Pitfall 1: `parse_response` now preserves write_file `<args>` content verbatim (interior code fences and trailing newlines survive), while all 7 pre-existing parser tests remain green for shell/read_file/final parsing
- `loop.py` dispatches `write_file` in both dry-run (preview only) and normal-loop (repetition guard -> confirm-gate showing `Path(path).resolve()` -> write -> Observation) paths
- SC2 satisfied: confirm prompt shows the resolved absolute path before any write; declining performs no write; `--yes` skips the prompt
- SC3 satisfied: `test_run_loop_read_then_write_end_to_end` exercises a full read_file -> write_file -> final sequence through `run_loop`
- SYSTEM_PROMPT extended to document all 3 tools (`shell`, `read_file`, `write_file`), the path-then-content encoding for write_file, and a terse `</args>` caveat (Pitfall 5, documentation-only)
- Repetition guard now covers `write_file` (Pitfall 3 fully resolved across shell/read_file/write_file)
- Repurposed `test_run_loop_unknown_tool_returns_observation` to use `browse` (Pitfall 2 fully resolved: write_file is no longer an "unknown tool")

## Task Commits

Each task was committed atomically (TDD RED/GREEN):

1. **Task 1: Write failing tests for parser fix, write_file tool, and SC3 integration** - `b5680a3` (test)
2. **Task 2: Fix parser, implement write_file, wire confirm-gate dispatch, extend SYSTEM_PROMPT** - `3fa97eb` (feat)

_Note: `test_write_file_without_args_tag_returns_none` passed from the start (regression guard for the existing combined-match fallback), as specified by the plan's `<done>` criteria for Task 1._

## Files Created/Modified
- `src/olla/parser.py` - Added tool-conditional write_file branch checking original content before fence-strip/strip; unchanged fallback for all other tools
- `src/olla/tools/base.py` - Added `bytes_written: int` to `ToolResult`
- `src/olla/tools/files.py` - Added `write_file(path, content) -> ToolResult` (never-raise, no auto-mkdir)
- `src/olla/loop.py` - Added `Path` and `write_file` imports; added `write_file` branches to dry-run and normal-loop dispatch with repetition guard and unconditional confirm-gate
- `src/olla/prompts.py` - Extended SYSTEM_PROMPT to 3 tools, added write_file encoding example and `</args>` caveat
- `tests/test_parser.py` - Added 3 write_file parser tests (fence preservation, trailing newline preservation, missing-args-tag regression guard)
- `tests/test_tools/test_files.py` - Added `write_file` import and 2 tests (success, missing parent dir)
- `tests/test_loop.py` - Added 8 new tests (confirm approved/declined/yes-skip/resolved-path-shown, dry-run preview, repetition guard, SC3 read-then-write) and repurposed the unknown-tool test to use `browse`

## Decisions Made
- Followed the plan's mandated "Option A" parser fix exactly: original (pre-fence-strip) `content` is checked for a `write_file` tool+args pair first; everything else falls through unchanged to the existing fence-strip/strip logic
- `write_file` confirm-gate has no `safety.check()` call — it's a distinct unconditional-confirm path from shell's ALLOW/CONFIRM/BLOCK tiers, per RESEARCH Pattern 3 (don't fake a shell argv for write_file)
- No new dependencies; `.venv` was provisioned for this worktree via `uv venv` + `uv pip install -e ".[dev]"` (already required by the project's declared dev dependencies, mirroring 03-01's precedent)

## Deviations from Plan

None - plan executed exactly as written. `.venv` provisioning was an environment-setup necessity (this worktree had no `.venv`, mirroring the 03-01 precedent), not a code deviation — no new or undeclared dependencies were introduced.

## Issues Encountered
None.

## Known Stubs
None - write_file is fully wired into the loop dispatch (dry-run and normal-loop), confirm-gated, and exercised by the SC3 end-to-end test.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- FILE-02 fully satisfied: `read_file` and `write_file` are both implemented, confirm-gated where required, dispatched correctly in dry-run and normal loop, and covered by the repetition guard
- All Phase 3 pitfalls (1, 2, 3, 5) addressed per this plan's success criteria; Pitfall 4 (sandbox jail) was explicitly rejected by RESEARCH and not attempted
- Full test suite green: 146 tests passing (up from 134 after 03-01; 12 new tests added, 1 existing test repurposed)
- Ready for Phase 4 (polish) or any phase building on the file-tools dispatch pattern

---
*Phase: 03-file-tools*
*Completed: 2026-06-15*

## Self-Check: PASSED

- FOUND: `.planning/phases/03-file-tools/03-02-SUMMARY.md`
- FOUND: `def write_file` in `src/olla/tools/files.py`
- FOUND: `partition` in `src/olla/loop.py`
- FOUND: `write_file` in `src/olla/prompts.py`
- FOUND: commit `b5680a3` (test RED)
- FOUND: commit `3fa97eb` (feat GREEN)
- FOUND: commit `35f7ae7` (docs SUMMARY)
</content>
