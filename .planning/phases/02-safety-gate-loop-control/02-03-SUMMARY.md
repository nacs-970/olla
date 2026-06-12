---
phase: 02-safety-gate-loop-control
plan: 03
subsystem: safety
tags: [safety-gate, blocklist, allowlist, repetition-guard, gap-closure]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: "safety.check() decision module (D-01..D-08) and loop.py confirm-gate dispatch from 02-01; repetition guard from 02-02"
provides:
  - "safety.py ALLOWLIST without env/find, with recursive _unwrap_env/_unwrap_find_exec gating so env- and find -exec-wrapped dangerous commands resolve to BLOCK/CONFIRM instead of ALLOW (CR-01)"
  - "_FORK_BOMB_RE regex matching both spaced and unspaced fork-bomb argv forms (WR-02)"
  - "loop.py repetition guard ordered before BLOCK/CONFIRM dispatch so 3x repeated BLOCKed/declined shell calls abort without ever reaching run_shell (WR-01)"
affects: [03-cli-and-distribution, 02-safety-gate-loop-control]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Recursive _blocklist_match: env/find-exec wrapper unwrapping re-invokes the same classifier on the unwrapped argv, naturally handling nested wrappers"
    - "Repetition signature/counter computed immediately after argv parse, before any decision branching, so it covers every shell-call attempt (ALLOW, CONFIRM, BLOCK alike)"

key-files:
  created: []
  modified:
    - src/olla/safety.py
    - tests/test_safety.py
    - src/olla/loop.py
    - tests/test_loop.py

key-decisions:
  - "Removed env/find from ALLOWLIST entirely rather than special-casing argv[1] — both binaries can execute arbitrary subcommands via arguments, so they now default to CONFIRM and are further gated by recursive unwrap rules"
  - "Fork-bomb detection switched from exact 3-token list equality to a regex over the joined argv, covering both spaced and unspaced spellings without enumerating variants"
  - "Repetition guard relocated to run on every shell-call attempt (before BLOCK/CONFIRM), closing the WR-01 gap where a model stuck repeating a blocked command could run until max_steps"

patterns-established:
  - "Safety-gate unwrap helpers (_unwrap_env, _unwrap_find_exec) return [] for 'no wrapped command found', and callers only recurse when the result is non-empty — avoids argv[0]-on-empty-list crashes"

requirements-completed: [SAFE-02, SAFE-04, LOOP-04]

# Metrics
duration: ~20min
completed: 2026-06-13
---

# Phase 02 Plan 03: Safety Gap Closure (CR-01, WR-01, WR-02) Summary

**Closed the env/find ALLOWLIST bypass (CR-01 blocker) via recursive argv unwrapping, fixed the unspaced fork-bomb regex (WR-02), and reordered the repetition guard to cover BLOCKed/declined shell-call repeats (WR-01)**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files modified:** 4 (src/olla/safety.py, tests/test_safety.py, src/olla/loop.py, tests/test_loop.py)

## Accomplishments

- `ALLOWLIST` no longer contains `env`/`find` — both can execute arbitrary subcommands via arguments and are no longer auto-approved
- `_unwrap_env` and `_unwrap_find_exec` extract the wrapped command from `env [FLAGS] [KEY=VALUE...] CMD...` and `find ... -exec/-execdir/-ok/-okdir CMD... ;|+`, and `_blocklist_match` recursively re-classifies the wrapped command
- `env rm -rf /`, `env sudo ls`, `env dd if=/dev/zero of=/dev/sda`, and `find / -exec sudo rm {} ;` all now resolve to `BLOCK`; `find . -exec rm -rf {} ;` resolves to `CONFIRM` (not `ALLOW`); `env FOO=bar ls -la` resolves to `CONFIRM`
- `_FORK_BOMB_RE` regex replaces the exact-list `_FORK_BOMB_TOKENS` equality, matching both the spaced 3-token form and the unspaced single-token form `:(){:|:&};:`
- `loop.py`'s repetition signature/counter now computes immediately after argv parsing, before `decision = check(argv, yes=yes)` — a 3rd consecutive identical BLOCKed (or declined-CONFIRM) shell call now triggers `"olla stopped: same shell call repeated 3x — model likely stuck"` without ever calling `run_shell`

## Task Commits

Each task followed RED -> GREEN TDD:

1. **Task 1: Fix safety.py ALLOWLIST bypass (CR-01) and fork-bomb matching (WR-02)**
   - RED: `c515662` - test(02-03): add failing tests for CR-01 env/find ALLOWLIST bypass and fork-bomb regex
   - GREEN: `81cdcb4` - feat(02-03): close CR-01 ALLOWLIST bypass and WR-02 fork-bomb gap in safety.py
2. **Task 2: Repetition guard covers BLOCK and declined-CONFIRM repeats (WR-01)**
   - RED: `eacbac5` - test(02-03): add failing test for repetition guard covering BLOCK repeats (WR-01)
   - GREEN: `6ef00d3` - feat(02-03): move repetition guard before BLOCK/CONFIRM dispatch (WR-01)

## Files Created/Modified

- `src/olla/safety.py` - Removed env/find from ALLOWLIST; added `_unwrap_env`, `_unwrap_find_exec`, `_FIND_EXEC_FLAGS`, `_FORK_BOMB_RE`; `_blocklist_match` recursively unwraps env/find-exec and uses regex fork-bomb matching (renumbered rules (1)-(7))
- `tests/test_safety.py` - Removed env/find from `test_allowlist_members_allow`; added 10 new tests covering env-wrap BLOCK/CONFIRM cases, find -exec BLOCK/CONFIRM cases, env/find-not-in-ALLOWLIST, and unspaced fork-bomb BLOCK
- `src/olla/loop.py` - Moved sig/repeat_count computation and `repeat_count >= 3` abort to immediately after argv parsing, before `decision = check(argv, yes=yes)`; removed the now-duplicate block from its old location
- `tests/test_loop.py` - Added `test_run_loop_repeated_block_triggers_repetition_guard` proving 3x identical BLOCKed `rm -rf /` calls abort with the repetition message before `run_shell` is ever called

## Decisions Made

- Removed `env`/`find` from `ALLOWLIST` entirely (not special-cased) — both fall through to `CONFIRM` by default and are further restricted via recursive unwrap-and-reclassify rules inserted as new rules (2) and (3) in `_blocklist_match`, ahead of the rm/dd/fork-bomb/chmod rules (renumbered to (4)-(7))
- `_unwrap_env`/`_unwrap_find_exec` return `[]` when no wrapped command is found (e.g. bare `env`, `env -i`, or `find` with no `-exec`-family flag); callers only recurse on non-empty results, avoiding an `argv[0]` crash on an empty list
- Nested wrapping (e.g. `env env rm -rf /`) is naturally handled by the recursive `_blocklist_match` call — each `env`/`find` layer re-enters the same function including its own unwrap rules (documented as accepted in the plan's threat model, T-02-03-04)

## Deviations from Plan

None - plan executed exactly as written. One verification-wording note below (not a code deviation).

### Verification Wording Note (not a deviation)

The plan's Task 2 acceptance criteria and `<verification>` item 3 specify: `grep -n "repeat_count >= 3" src/olla/loop.py` precedes `grep -n "decision = check(argv" src/olla/loop.py` in line order. `loop.py` contains **two** occurrences of `decision = check(argv` — one in the `dry_run` single-step preview branch (line 59, unchanged, predates the `for step` loop and has no repetition guard by design) and one in the main loop (line 108, the intended target). `repeat_count >= 3` (line 104) precedes the main-loop occurrence (108) but not the dry_run occurrence (59), since dry_run is a separate early-return code path that the plan's `<action>` explicitly scopes out ("inside the `for step in range(1, max_steps + 1):` loop"). The functional intent — repetition guard ordered before BLOCK/CONFIRM dispatch in the main ReAct loop — is correctly implemented and proven by `test_run_loop_repeated_block_triggers_repetition_guard` and all 4 pre-existing repetition/max-steps tests passing unchanged. A literal `grep -n` of the first match of each pattern would report line 59 < line 104, which could read as a false negative for a naive automated check; documenting here for the verifier's awareness.

## Issues Encountered

None. The local pyenv `python3` (3.14.5 at `/home/nacs/.pyenv/shims/python3`) lacks `ollama`/`pytest-mock`, causing `tests/test_loop.py`, `tests/test_cli.py`, and `tests/test_smoke.py` to fail collection under the bare interpreter (pre-existing environment issue, unrelated to this plan). The project's `.venv` (`/home/nacs/Documents/git/olla/.venv/bin/python3`) has all dependencies installed and was used to run the full suite: `PYTHONPATH=src /home/nacs/Documents/git/olla/.venv/bin/python3 -m pytest tests/ -q` -> 88 passed (up from 77 baseline; +10 from Task 1, +1 from Task 2).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CR-01 blocker from 02-REVIEW.md / 02-VERIFICATION.md is closed: `env`/`find`-wrapped dangerous commands no longer bypass the D-03 blocklist or the CONFIRM gate
- WR-01 (repetition guard ordering) and WR-02 (unspaced fork-bomb) are closed
- ROADMAP Phase 2 Success Criteria #1 (confirm-before-shell, SAFE-04) and #2 (blocklist speed-bump, SAFE-02) now hold for env/find-wrapped argv shapes, restoring them toward VERIFIED
- Full test suite passes (88 tests). No further loop.py changes anticipated for this gap-closure scope.
- Note for the orchestrator/verifier: when running `tests/` for phase 02 going forward, use `/home/nacs/Documents/git/olla/.venv/bin/python3` (has `ollama`/`pytest-mock`) rather than the bare pyenv `python3` to avoid spurious collection errors on test_loop.py/test_cli.py/test_smoke.py.

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-13*
