---
phase: 02-safety-gate-loop-control
plan: 06
subsystem: safety
tags: [python, safety-gate, blocklist, regex, shlex, pytest, security]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: D-03 blocklist rules (_blocklist_match), D-04 yes-never-weakens-classification, prior CR-01/CR-02/CR-03 round-1/round-2 fixes (plans 02-01..02-05)
provides:
  - Renamed _normalize_slash_target helper shared by rule (4) rm and rule (7) chmod/chown
  - Rule (6b) combined-short-flag scan (-lc/-ic/-xc/...) for bash/sh/zsh -c wrap-and-recurse (CR-01 round 3)
  - Rule (7) doubled-leading-slash normalization for chmod/chown -R root targets (CR-02 round 3)
  - _is_dangerous_device_arg doubled-leading-slash normalization for dd/mkfs* device targets (CR-03 round 3)
  - 11 new regression tests in tests/test_safety.py + 1 new e2e test in tests/test_loop.py
affects: [02-safety-gate-loop-control verification, any future safety.py blocklist changes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Equivalent-form normalization before blocklist comparison (slash-collapsing regex applied before set-membership/glob checks, not as a separate pre-pass)"
    - "Combined short-flag detection via next() generator scan instead of exact argv membership test"

key-files:
  created: []
  modified:
    - src/olla/safety.py
    - tests/test_safety.py
    - tests/test_loop.py

key-decisions:
  - "Renamed _normalize_rm_target to _normalize_slash_target since it is now shared by rule (4) (rm) and rule (7) (chmod/chown -R), with docstring updated to describe both call sites"
  - "_is_dangerous_device_arg normalization regex is NOT end-anchored (^/{2,} vs _normalize_slash_target's ^/{2,}$) because the device path retains trailing non-slash content after the doubled prefix (e.g. //dev/sda -> /dev/sda)"
  - "Rule (6b) flag scan matches any '-'-prefixed, non-'--', 'c'-containing token (e.g. -lc, -ic, -xc) via next() with a None default, preserving the existing len(argv) > c_index + 1 guard to avoid IndexError on truncated bash -lc emissions"
  - "Added an extra D-04 regression test (test_bash_dash_lc_sudo_rm_rf_root_blocks_with_yes) beyond the plan's 10 named tests to explicitly cover yes=True for the new -lc bypass path"

requirements-completed: [SAFE-02, SAFE-04]

# Metrics
duration: 25min
completed: 2026-06-13
---

# Phase 02 Plan 06: Round-3 Equivalent-Form Blocklist Bypass Closure Summary

**Closed three round-3 equivalent-form bypasses in src/olla/safety.py (combined short-flags `-lc`/`-ic`/`-xc` for bash/sh/zsh -c, doubled leading slashes `//`/`///` for chmod/chown -R and dd/mkfs* device targets), with 12 new regression/e2e tests, all 121 tests passing.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- CR-01 (round 3): `bash -lc "sudo rm -rf /"`, `sh -ic "sudo ls"`, `zsh -xc "sudo ls"` now BLOCK (previously CONFIRM, exploitable via `--yes`)
- CR-02 (round 3): `chmod -R 777 //`, `chown -R user //` (and `///`) now BLOCK via the renamed `_normalize_slash_target` helper shared with rule (4)
- CR-03 (round 3): `dd of=//dev/sda`, `mkfs.ext4 //dev/sda` now BLOCK via doubled-leading-slash normalization in `_is_dangerous_device_arg`
- End-to-end verification (`run_loop` with `--yes=True`) confirms the CR-01 fix is correctly wired with zero `loop.py` changes (T-02-06-04)

## Task Commits

Each task was committed atomically:

1. **Task 1: Harden safety.py rules (5)/(6b)/(7) + regression tests** - `dd85f58` (fix)
2. **Task 2: e2e verification test for bash -lc sudo with --yes** - `ec33508` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `src/olla/safety.py` - Renamed `_normalize_rm_target` to `_normalize_slash_target` (now shared by rules 4 and 7); added doubled-leading-slash normalization to `_is_dangerous_device_arg`; rewrote rule (6b)'s flag-detection to scan for any `-`-prefixed, non-`--`, `c`-containing token via `next()`; rewrote rule (7)'s target check to use `_normalize_slash_target`
- `tests/test_safety.py` - Added 11 new tests: 5 for CR-01 round 3 (`-lc`/`-ic`/`-xc` combined flags, plus yes=True and bare-flag-no-command guards), 2 for CR-03 round 3 (doubled-slash dd/mkfs device targets), 4 for CR-02 round 3 (doubled/tripled-slash and long-flag chmod/chown root targets)
- `tests/test_loop.py` - Added `test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks`, mirroring the round-2 `-c` precedent with combined `-lc`

## Decisions Made
- Renamed `_normalize_rm_target` -> `_normalize_slash_target` to reflect its now-shared use by rule (4) `rm` and rule (7) `chmod`/`chown -R`; updated docstring to describe both call sites and both target forms (`/` for rule 7, `_RM_DANGEROUS_TARGETS` membership for rule 4)
- Used a non-end-anchored regex (`^/{2,}`) for the `_is_dangerous_device_arg` normalization, distinct from `_normalize_slash_target`'s fully-anchored (`^/{2,}$`) regex, because device paths retain trailing content (`//dev/sda` -> `/dev/sda`, not collapsed to `/`)
- Rule (6b)'s combined-short-flag scan uses `next((... for i, a in enumerate(argv) if a.startswith("-") and not a.startswith("--") and "c" in a), None)` rather than `argv.index("-c")`, preserving the existing `len(argv) > c_index + 1` IndexError guard for truncated emissions like bare `bash -lc`
- Added one extra test beyond the plan's 10 named tests (`test_bash_dash_lc_sudo_rm_rf_root_blocks_with_yes`) to explicitly cover the D-04 `yes=True` case for the new `-lc` bypass, mirroring the existing round-2 `_even_with_yes` precedent

## Deviations from Plan

None - plan executed exactly as written. The plan named 10 new tests for `tests/test_safety.py`; 11 were added (the 10 named tests plus one additional `yes=True` D-04 variant explicitly implied by the plan's `<behavior>` bullets but not given a distinct name). This is additive test coverage only, not a change to production code or scope.

## Issues Encountered

None. All edits matched the plan's `<interfaces>` exactly. The discriminator check (`PYTHONPATH=src <main-repo-venv-python> -c "import olla.safety; print(olla.safety.__file__)"` run from the worktree root) confirmed the worktree's edited `src/olla/safety.py` was the module under test before interpreting any pytest results.

## Verification

- `grep -n "_normalize_rm_target" src/olla/safety.py tests/test_safety.py` -> zero matches (fully renamed, no stale references)
- `PYTHONPATH=src .venv/bin/python3 -m pytest tests/test_safety.py -q` -> 58 passed (47 pre-existing + 11 new)
- `PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q` -> 121 passed (109 pre-existing + 11 + 1 new)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All three round-3 equivalent-form bypasses (CR-01/CR-02/CR-03) identified in `02-VERIFICATION.md` round 3 (`gaps_found`, 3/5) are now closed
- `_normalize_slash_target` is now the single shared helper for slash-equivalent-form normalization across rules 4 and 7; any future rule needing similar normalization should reuse it
- Residual accepted risks documented in the plan's threat model remain open by design: T-02-06-05 (shell-chained `-c` via `&&`/`;`/`|`), T-02-06-06 (`env -S "..."` embedding a wrapped command in a single string)
- Ready for re-verification (round 4) of phase 02 safety gate

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-13*
