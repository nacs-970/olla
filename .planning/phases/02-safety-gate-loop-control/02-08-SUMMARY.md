---
phase: 02-safety-gate-loop-control
plan: 08
subsystem: safety
tags: [typing, typeddict, python-compat, pep655, pytest]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: safety.py Decision TypedDict and check() classifier (02-01..02-07)
provides:
  - src/olla/safety.py importable on Python >=3.10 (no PEP 655 `NotRequired`/`Required` dependency)
  - Static regression test guarding against reintroduction of Python-3.11-only typing symbols
affects: [02-safety-gate-loop-control, future-cli-startup-on-3.10]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TypedDict(total=False) used instead of PEP 655 NotRequired/Required to keep typing.TypedDict usage compatible with the project's >=3.10 floor"
    - "Static source-text regression test (inspect.getsourcefile + read) to catch forward-incompatible typing symbols on any Python version, including dev machines newer than the declared floor"

key-files:
  created: []
  modified:
    - src/olla/safety.py
    - tests/test_safety.py

key-decisions:
  - "Adopted Option 3 from 02-VERIFICATION.md round 5 (CR-01): drop NotRequired entirely, use `class Decision(TypedDict, total=False):` rather than adding typing_extensions as a dependency"
  - "total=False is a type-checker-only relaxation; check() always sets `kind` on every return path so there is no practical behavioral difference vs. NotRequired"

patterns-established:
  - "When a typing symbol requires Python >=3.11 (PEP 655 NotRequired/Required) but the project floor is >=3.10, use TypedDict(total=False) plus a static source-grep regression test rather than adding typing_extensions"

requirements-completed: [LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04]

# Metrics
duration: ~10min
completed: 2026-06-14
---

# Phase 02 Plan 08: CR-01 Python 3.10 Import Compatibility Summary

**Removed `typing.NotRequired` (PEP 655, Python 3.11+) from `src/olla/safety.py`'s `Decision` TypedDict, switching to `TypedDict(total=False)` so `import olla.safety` (and the whole `olla` CLI import chain) succeeds on the project's declared `>=3.10` floor, with zero classification-behavior change and a new static regression test.**

## Performance

- **Duration:** ~10 min
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Fixed the sole blocking gap (CR-01) from 02-VERIFICATION.md round 5: `safety.py` line 7 no longer imports `NotRequired`, eliminating the `ImportError` that previously broke `olla.safety` -> `olla.loop` -> `olla.cli` on Python 3.10
- `Decision` is now `class Decision(TypedDict, total=False):` with `reason: str` and an explanatory comment that deliberately avoids the literal symbols `NotRequired`/`Required[` (so it doesn't trip the new regression test)
- Added `test_safety_module_has_no_python311_only_typing_symbols`, a portable static-source regression test that greps `safety.py`'s own source for `NotRequired`/`Required[` and fails on any Python version (including this dev machine's 3.14), with an inline documented manual-verification note (`python3.10 -c "import olla.safety"`) for environments with a 3.10/3.11 interpreter
- Added `test_decision_is_importable` confirming `Decision` remains exported from `olla.safety`
- All 125 pre-existing tests remain green plus 2 new tests = 127 passed total (the plan's must_haves estimated "126"; the actual count of new tests added per the `<action>` steps is 2, not 1 — both are part of the same CR-01 regression safeguard and both pass)
- `check()`'s ALLOW/CONFIRM/BLOCK classification and `reason` strings are byte-for-byte identical to pre-fix behavior for all spot-checked cases (`ls` -> ALLOW, `rm -rf /` -> BLOCK with reason, `git status` -> CONFIRM, `sudo ls` with `yes=True` -> BLOCK with reason)

## Task Commits

Each task was committed atomically (TDD: test -> fix):

1. **Task 1 (RED): add failing static regression test for CR-01** - `222363e` (test)
2. **Task 1 (GREEN): drop NotRequired from safety.py Decision for py3.10 compat** - `cf6d16a` (fix)

_No REFACTOR commit needed — the fix was already a minimal 2-line change with no cleanup required._

## Files Created/Modified
- `src/olla/safety.py` - Changed import to `from typing import Literal, TypedDict` (line 7) and `Decision` to `class Decision(TypedDict, total=False):` with `reason: str` and an updated comment (lines 10-14). No other lines changed.
- `tests/test_safety.py` - Added `import inspect` and `Decision` to the existing `from olla.safety import ...` line; added `test_safety_module_has_no_python311_only_typing_symbols` and `test_decision_is_importable` after `test_empty_argv_blocks_with_reason`. No existing tests modified.

## Decisions Made
- Followed the plan's Option 3 exactly: no `typing_extensions` dependency added, `pyproject.toml`'s `requires-python = ">=3.10"` unchanged, CLAUDE.md unchanged.
- Used `inspect.getsourcefile(check)` + plain file read (not `pathlib`) to locate `safety.py`'s source text for the static regression test, per the plan's "either approach is acceptable" guidance.

## Deviations from Plan

### Auto-fixed Issues

None — no Rule 1/2/3 auto-fixes were needed. This was a clean 2-line fix plus 2 new test functions, exactly as scoped.

**Minor count clarification (not a deviation, documentation note):** The plan's `must_haves.truths` and `<done>` text say "126 total" (125 pre-existing + 1 new static regression test). The plan's own `<action>` step 5, however, specifies adding THREE things: (a) the static regression test, (b) a documented manual-verification comment (non-test, no count impact), and (c) "a small sanity test (or extend an existing one) confirming Decision is still exported." I implemented (c) as a separate new test function (`test_decision_is_importable`) rather than extending an existing test, per the plan's explicit "or extend an existing one" alternative being optional. Result: 127 passed (125 + 2 new tests), not 126. All acceptance criteria that reference specific counts elsewhere (`grep -c NotRequired` = 0, `grep -c "class Decision(TypedDict, total=False):"` = 1, `grep -c "from typing import Literal, TypedDict"` = 1) are satisfied exactly as specified. The "126" figure in the plan appears to be an off-by-one in the plan's own bookkeeping (it lists 3 sub-deliverables in step 5 but counted only 1 toward the total); both new tests are part of the same CR-01 regression safeguard requested by the plan and both pass.

---

**Total deviations:** 0 auto-fixed. One documentation note (test-count clarification, no code/behavior impact).
**Impact on plan:** None — plan executed as written; the only difference from the plan's literal "126" figure is that the plan itself specified two new test deliverables in step 5 (static regression test + Decision-export sanity test), both implemented as separate functions.

## Issues Encountered

**Worktree path resolution (process note, not a code issue):** The plan's verification/acceptance commands use absolute paths to the main repo (`cd /home/nacs/Documents/git/olla && PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q`). This plan was executed in a git worktree at `.claude/worktrees/agent-a7f235a7810350e84`. All verification commands were adapted to run against the worktree's copies of `src/` and `tests/` (using the main repo's `.venv` interpreter, which has pytest/ollama/rich installed, but with `PYTHONPATH` and test paths pointed at the worktree). Confirmed via `inspect.getsourcefile(olla.safety)` that the worktree's `safety.py` was the one being tested, not the main repo's stale copy.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CR-01 (the sole remaining blocking gap from 02-VERIFICATION.md round 5) is closed: `import olla.safety` no longer depends on any Python-3.11-only typing symbol.
- All 127 tests pass (125 pre-existing + 2 new), zero failures, zero modifications to existing tests.
- `pyproject.toml` and `CLAUDE.md` are unchanged — `requires-python = ">=3.10"` floor preserved without adding `typing_extensions`.
- Residuals explicitly out of scope and unchanged: WR-01 (rule-4 `rm -rf /.`-family vs rule-7 `chmod/chown` asymmetry), `env -S` wrap-and-recurse (T-02-07-05), shell-chained `-c` bypass of rule 6b (T-02-06-05/T-02-07-04), recursion-depth limit on `_blocklist_match` (INFO-level). None of these are claimed as fixed or regressed by this plan.
- The phase should now be in a state where 02-VERIFICATION.md round 6 can re-run and confirm CR-01 closure with no new gaps from this plan's narrow 2-line change.

## Known Stubs

None.

## Threat Flags

None - no new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan changes only a type annotation mechanism (`NotRequired` -> `TypedDict(total=False)`) and adds 2 test functions; the threat register in 02-08-PLAN.md (T-02-08-01 through T-02-08-SC) was followed exactly, with T-02-08-01 (the `mitigate` item) resolved as planned.

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-14*

## Self-Check: PASSED

- FOUND: src/olla/safety.py
- FOUND: tests/test_safety.py
- FOUND: .planning/phases/02-safety-gate-loop-control/02-08-SUMMARY.md
- FOUND commit: 222363e (test - RED)
- FOUND commit: cf6d16a (fix - GREEN)
- FOUND commit: f8355cb (docs - summary)
