---
phase: 02-safety-gate-loop-control
plan: 05
subsystem: safety
tags: [safety-gate, blocklist, shlex, regex, pytest]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: D-01/D-02/D-03/D-04 safety-gate design (ALLOWLIST, _HARD_BLOCKED_BINARIES, _blocklist_match, wrap-and-recurse for env/find -exec) from plans 02-01..02-04
provides:
  - "rm -rf // and /// normalized to / and blocked (CR-03)"
  - "bash/sh/zsh -c \"<command>\" shlex-split and recursed through full D-03 blocklist (CR-01)"
  - "chmod/chown --recursive (long-flag) on / blocked, matching existing -R/-Rf coverage (CR-02)"
  - "bash -c / sh -c with no trailing command falls through to CONFIRM without IndexError (T-02-05-06)"
affects: [02-safety-gate-loop-control-verification, 03-*]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single outer guard (`if ... and \"-c\" in argv: c_index = argv.index(\"-c\"); if len(argv) > c_index + 1:`) wraps both fork-bomb and shlex-split-and-recurse checks for bash/sh/zsh -c, preventing IndexError on truncated/malformed model emissions while keeping the existing wrap-and-recurse shape used for env/find -exec"
    - "_normalize_rm_target: fully-anchored regex (`^/{2,}$`) collapses literal multi-slash rm targets to '/' before D-03 set membership check, without affecting /*, ~, ., $HOME, or paths with non-slash trailing chars"

key-files:
  created: []
  modified:
    - src/olla/safety.py
    - tests/test_safety.py
    - tests/test_loop.py

key-decisions:
  - "Used shlex.split() with try/except ValueError -> [] for bash/sh/zsh -c argument parsing, matching CLAUDE.md's stdlib-only / no-new-dependency constraint"
  - "T-02-05-05 (shell-chained -c strings, e.g. bash -c \"true; sudo rm -rf /\") and env -S (02-04 residual) remain explicitly out of scope per plan's threat_model — not silently promised as solved"

requirements-completed: [SAFE-02, SAFE-04]

# Metrics
duration: 25min
completed: 2026-06-13
---

# Phase 2 Plan 5: Safety-Gate Bypass Closure (CR-01/CR-02/CR-03) Summary

**Closed three reproducible safety-gate bypasses (bash/sh/zsh -c blocklist evasion, chmod/chown --recursive long-flag evasion, rm -rf multi-slash root evasion) plus a crash bug on truncated `bash -c` emissions, raising test_safety.py from 35 to 47 tests and the full suite from 96 to 109.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-06-13T07:25:00Z (approx, from worktree setup)
- **Completed:** 2026-06-13T07:51:10Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- CR-01 closed: `bash -c "sudo rm -rf /"` (and `sh -c`, including via `find -exec sh -c ... ;`) now shlex-splits the `-c` argument and recurses it through the full D-03 `_blocklist_match`, so any blocked command wrapped in a `-c` string is caught — not just literal fork-bomb syntax.
- CR-02 closed: `chmod --recursive` / `chown --recursive` (GNU long-flag form of `-R`) targeting `/` now blocks, matching the existing `-R`/`-Rf` coverage.
- CR-03 closed: `rm -rf //` and `rm -rf ///` (and any run of 2+ leading slashes) are normalized to `/` before D-03 dangerous-target matching, since they are filesystem-equivalent to `rm -rf /` on Linux.
- T-02-05-06 (revision-time crash fix): `bash -c` / `sh -c` with no trailing command argument (`["bash", "-c"]`) no longer raises `IndexError` — falls through cleanly to CONFIRM via a single outer `len(argv) > c_index + 1` guard.
- D-04 invariant preserved and regression-tested: `bash -c "sudo rm -rf /"` is BLOCK regardless of `yes=True`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Harden safety.py rules (4)/(6b)/(7) + add 12 regression tests to test_safety.py** - `528472d` (fix)
2. **Task 2: Add end-to-end --yes regression test to test_loop.py for CR-01** - `55dd1dc` (test)

**Plan metadata:** (this commit, SUMMARY.md)

_Note: Task 1 combines the safety.py hardening fix and its accompanying tests in a single `fix` commit per the plan's task grouping; Task 2 is test-only._

## Files Created/Modified
- `src/olla/safety.py` - Added `import shlex` and `_normalize_rm_target()` helper; rule (4) normalizes `rm` targets before dangerous-target match (CR-03); rule (6b) restructured into a single outer `bash/sh/zsh -c` guard that checks fork-bomb pattern AND shlex-splits + recurses the `-c` string through `_blocklist_match` (CR-01), with `len(argv) > c_index + 1` preventing IndexError on bare `-c` (T-02-05-06); rule (7) extended to also match `--recursive` long-flag on chmod/chown targeting `/` (CR-02)
- `tests/test_safety.py` - Added 12 new tests: 8 for CR-01 (`bash -c`/`sh -c`/`find -exec sh -c` wrapping sudo/rm/dd/fork-bomb, plus `yes=True` D-04 check, plus bare `-c` no-crash CONFIRM cases for bash and sh), 2 for CR-02 (`chmod --recursive` and `chown --recursive` on `/`), 2 for CR-03 (`rm -rf //` and `rm -rf ///`) — 35 -> 47 tests
- `tests/test_loop.py` - Added `test_run_loop_bash_dash_c_sudo_with_yes_still_blocks`: end-to-end loop test confirming `bash -c "sudo rm -rf /"` with `yes=True` is blocked, `run_shell` is never called, and "blocked by safety policy:" + "sudo" appear in output — 96 -> 109 tests (full suite)

## Decisions Made
- Used stdlib `shlex.split()` with `try/except ValueError: wrapped = []` for parsing the `-c` argument string — consistent with CLAUDE.md's no-new-dependency / `shlex.split` conventions already used elsewhere in safety.py (env/find unwrapping).
- Restructured rule (6b) into a single outer guard (rather than two separate `if` blocks each re-deriving `c_index`) so the IndexError fix (T-02-05-06) applies uniformly to both the fork-bomb check and the new blocklist-recursion check, per the plan's prescribed code shape.
- `_normalize_rm_target` uses a fully-anchored regex (`^/{2,}$`) so it only affects literal targets consisting entirely of repeated slashes — `/*`, `~`, `.`, `$HOME`, and multi-slash paths with trailing non-slash characters (e.g. `//etc/foo`) are unaffected.

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria and the plan's 5 manual spot-checks passed on first implementation attempt; no Rule 1-4 deviations were needed.

## Known Limitations (carried-forward residuals, intentionally unfixed)

Per the plan's threat_model and success_criteria, the following gaps remain explicitly out of scope for this plan and are **not** resolved by it:

- **T-02-05-05 (shell-chained `-c` strings):** `bash -c "true; sudo rm -rf /"` — `shlex.split()` on the full `-c` string produces `["true;", "sudo", "rm", "-rf", "/"]`. Because `_blocklist_match` checks `argv[0]` (`"true;"`, not a recognized binary) against rule shapes that expect the dangerous command as `argv[0]`, this compound-command form is not detected by the new rule (6b) recursion and remains CONFIRM rather than BLOCK. A future plan would need to split on shell statement separators (`;`, `&&`, `||`, `|`) before recursing each sub-command.
- **`env -S "..."` (02-04 documented residual):** `env -S` consumes its argument as a single string for `env` itself to re-split; `_unwrap_env` does not parse into that embedded string, so `env -S "sudo rm -rf /"` remains CONFIRM. Unchanged by this plan (`test_env_split_string_flag_wrapping_sudo_confirms` documents this as expected CONFIRM behavior, not a regression).

These residuals are accepted per the plan's threat_model dispositions (T-02-05-02, T-02-05-05: `accept`) and are not silently promised as solved by the CR-01/CR-02/CR-03 closure above.

## Known Stubs

None - no stub patterns introduced.

## Issues Encountered
- Initial pytest run accidentally executed against the main repo's (unmodified) test files due to a `cd` that left the worktree; diagnosed via `grep -c "^def test_"` count mismatch (35 vs 47) and re-run without `cd`, confirming the worktree's modified files (47 tests) were correctly exercised. No code or test content was affected — this was a verification-command issue only, not a plan deviation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- CR-01/CR-02/CR-03 closed; SAFE-02 and SAFE-04 requirements addressed by this plan's hardening.
- Full suite green at 109 tests (47 in test_safety.py, 109 total).
- Residual T-02-05-05 (shell-chained `-c` compound commands) and `env -S` remain open — candidates for a future gap-closure plan if re-verification flags them again.
- Orchestrator should re-run phase 02 verification against this plan's changes before marking SAFE-02/SAFE-04 complete in REQUIREMENTS.md/STATE.md.

## Self-Check: PASSED

- FOUND: src/olla/safety.py (modified, contains _normalize_rm_target, restructured rule 6b, --recursive in rule 7)
- FOUND: tests/test_safety.py (47 tests collected)
- FOUND: tests/test_loop.py (109 tests collected in full suite)
- FOUND: 528472d (fix(02-05): harden safety.py rules 4/6b/7 for CR-03/CR-01/CR-02)
- FOUND: 55dd1dc (test(02-05): add end-to-end --yes regression for CR-01 bash -c sudo)

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-13*
