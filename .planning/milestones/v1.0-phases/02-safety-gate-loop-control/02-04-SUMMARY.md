---
phase: 02-safety-gate-loop-control
plan: 04
subsystem: safety
tags: [safety-gate, blocklist, shell, regex, tdd]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: safety.check() blocklist/allowlist gate, run_shell tool, ReAct loop --yes handling (02-01..02-03)
provides:
  - "Hardened env/find-exec unwrap closing the CR-01 --yes BLOCK-bypass for env -u/-C wrapped sudo and multi-clause find -exec"
  - "Anchored fork-bomb regex (WR-02): data arguments containing fork-bomb syntax no longer false-positive BLOCK; bash/sh/zsh -c fork-bomb still BLOCKs"
  - "chmod/chown combined-flag detection (-Rf, -fR, etc.) targeting / now BLOCKs (WR-03)"
  - "run_shell(argv: list[str]) — single shlex.split() in loop.py, no double-parse (IN-01)"
affects: [02-REVIEW, safety-gate-loop-control]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_blocklist_match rules stay first-match-wins, numbered (1)-(7); rule (3) now iterates all -exec clauses returned by _unwrap_find_exec"
    - "Fork-bomb detection split into anchored .match() on joined argv (argv[0] is the pattern) plus an explicit bash/sh/zsh -c .search() sub-check (the -c argument is itself the command)"
    - "Pre-parsed argv passed end-to-end: loop.py shlex.split()'s once, passes the resulting argv to both safety.check() and run_shell()"

key-files:
  created: []
  modified:
    - src/olla/safety.py
    - src/olla/tools/shell.py
    - src/olla/loop.py
    - tests/test_safety.py
    - tests/test_tools/test_shell.py
    - tests/test_loop.py

key-decisions:
  - "env -S/--split-string is kept in _ENV_FLAGS_WITH_ARG (skipped, not parsed into) — env -S \"sudo rm -rf /\" remains CONFIRM by design per plan spec; a real residual gap under --yes, documented as a known limitation rather than auto-expanded under Rule 2"
  - "_unwrap_find_exec changed return type to list[list[str]] (all -exec/-execdir/-ok/-okdir clauses, empty clauses skipped) so rule (3) can recursively gate every clause, not just the first"
  - "Fork-bomb rule (6) split into an anchored .match() (argv[0] is fork-bomb syntax) plus a separate bash/sh/zsh -c .search() sub-check, fixing the WR-02 echo-data false positive while preserving the bash -c BLOCK"
  - "chmod/chown rule (7) now matches any short flag combination containing 'R' (e.g. -Rf, -fR) via startswith('-') and not startswith('--'), not just the literal '-R' token"

requirements-completed: [SAFE-02, SAFE-04]

# Metrics
duration: ~25min
completed: 2026-06-13
---

# Phase 02 Plan 04: Safety Gate Gap Closure (CR-01/WR-02/WR-03/IN-01) Summary

**Closed the CR-01 env/find-exec --yes BLOCK-bypass, fixed the WR-02 fork-bomb regex false positive on echo data while preserving bash -c BLOCK, hardened WR-03 chmod/chown -Rf-style detection, and removed run_shell's redundant shlex re-parse (IN-01) by passing a single pre-parsed argv end-to-end.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2
- **Files modified:** 6 (2 source modules in safety/tools/loop, 3 test files)

## Accomplishments

- `_unwrap_env` now index-walks argv, correctly skipping env flags that consume a following argument (`-u`/`--unset`, `-C`/`--chdir`, `-a`/`--argv0`, `-S`/`--split-string`) via new `_ENV_FLAGS_WITH_ARG`, so `env -u FOO sudo rm -rf /` and `env -C /tmp sudo ls` now correctly recurse into the wrapped `sudo` command and BLOCK.
- `_unwrap_find_exec` returns `list[list[str]]` — every `-exec`/`-execdir`/`-ok`/`-okdir ... ;`/`+` clause in a `find` invocation, not just the first. Rule (3) iterates all clauses, so `find . -exec true ; -exec sudo rm -rf / ;` BLOCKs on its second clause.
- Fork-bomb rule (6) is now anchored: `_FORK_BOMB_RE.match()` on the joined argv catches `argv[0]` being fork-bomb syntax (both spaced and unspaced canonical forms still BLOCK, regression-proofed), while `echo "...:(){ :|:& };:..."` (fork-bomb text as *data* to `echo`) now correctly ALLOWs. A separate explicit `bash/sh/zsh -c <cmd>` sub-check (`.search()` on the `-c` argument) preserves BLOCK for `bash -c ':(){ :|:& };:'`.
- chmod/chown rule (7) detects combined short flags (`-Rf`, `-fR`, etc.) containing `R`, not just the literal `-R` token, when targeting `/`.
- `run_shell(argv: list[str], timeout=30)` — `shlex` import and re-parsing removed from `olla.tools.shell`; `olla.loop`'s single call site passes the `argv` already computed via `shlex.split(parsed["args_raw"])`, eliminating the double-parse (IN-01).
- 8 new tests in `tests/test_safety.py` (27 -> 35), 2 new end-to-end `--yes` BLOCK regression tests in `tests/test_loop.py` (29 -> 31), `tests/test_tools/test_shell.py` rewritten for the new signature (8 -> 6). Full suite: 96 passed.

## Task Commits

Each task followed RED -> GREEN (no REFACTOR needed — implementations were clean on first pass):

1. **Task 1: Harden safety.py rules (2) env-unwrap, (3) find-exec-unwrap, (6) fork-bomb, (7) chmod/chown**
   - `8911f5b` test(02-04): add failing tests for safety rule hardening (RED — 6 genuinely new failures)
   - `8e73c5f` feat(02-04): harden env/find-exec unwrap, fork-bomb anchor, chmod/chown -Rf (GREEN — 35/35 pass)
2. **Task 2: IN-01 — run_shell takes pre-parsed argv**
   - `d3f1a17` test(02-04): rewrite shell tool tests for pre-parsed argv signature (RED — 6/6 fail on old `shlex.split(list)` signature)
   - `6ebaa52` feat(02-04): run_shell takes pre-parsed argv, drop double shlex.split (GREEN — 6/6 pass)
   - `8b9b87d` test(02-04): add end-to-end --yes BLOCK regressions for CR-01 bypasses (2 new tests, pass immediately — ride on Task 1's already-committed fix)

**Plan metadata:** committed alongside this SUMMARY (see final commit below).

## Files Created/Modified

- `src/olla/safety.py` - `_ENV_FLAGS_WITH_ARG` constant; rewritten `_unwrap_env` (index-walk, skips flag+arg pairs); rewritten `_unwrap_find_exec` (returns all -exec clauses); rule (3) iterates all clauses; rule (6) anchored fork-bomb match + explicit bash/sh/zsh -c sub-check; rule (7) detects combined -R* flags
- `src/olla/tools/shell.py` - `run_shell(argv: list[str], timeout=30)`, removed `shlex` import and re-parsing
- `src/olla/loop.py` - single `run_shell(argv)` call site (was `run_shell(parsed["args_raw"])`)
- `tests/test_safety.py` - 8 new tests: env `-u`/`-C`/`-S` flag-with-arg handling, find multi-exec clause, fork-bomb-as-echo-data ALLOW, fork-bomb-via-bash-c BLOCK, chmod/chown `-Rf` combined flags
- `tests/test_tools/test_shell.py` - rewritten for `argv: list[str]` signature (8 -> 6 tests; collapsed empty/whitespace cases, dropped unbalanced-quote case now covered at the loop level)
- `tests/test_loop.py` - 2 new end-to-end `--yes` regression tests: `env -u FOO sudo rm -rf /` and chained `find -exec ... -exec sudo rm -rf / ;` both BLOCK and never call `run_shell`

## Decisions Made

- `env -S/--split-string` is included in `_ENV_FLAGS_WITH_ARG` (its string argument is skipped wholesale, not parsed into) — per the plan's exact spec, `env -S "sudo rm -rf /"` remains **CONFIRM**, pinned by `test_env_split_string_flag_wrapping_sudo_confirms`. This is a deliberate scope boundary, not an oversight — see Known Limitations below.
- `_unwrap_find_exec`'s return type changed from `list[str]` to `list[list[str]]`; verified via grep that rule (3) in `_blocklist_match` is its only caller, so the signature change is fully contained.
- Fork-bomb detection split into two checks (anchored `.match()` for argv[0]-is-the-pattern, plus explicit `bash/sh/zsh -c` `.search()` for the `-c` argument) rather than a single `.search()` — this is the minimal change that fixes the WR-02 false positive without losing the bash -c BLOCK.
- chmod/chown rule (7) generalized from `"-R" in argv` to "any non-`--` flag token starting with `-` that contains `R`" — catches `-Rf`, `-fR`, `-Rv`, etc., while leaving long-form `--recursive` (not covered by either old or new code; out of scope per plan).

## Deviations from Plan

None - plan executed exactly as written. All 6 numbered action steps in Task 1 and all 4 numbered action steps in Task 2 were implemented as specified, including the exact `<behavior>` test cases.

## Known Limitations

- `env -S "sudo rm -rf /"` remains CONFIRM (not BLOCK) even under `--yes`. This is an explicit, test-pinned scope boundary from the plan (`-S` consumes its argument as a single string for env to re-split itself; `_unwrap_env` does not parse into that string). A real residual of the same SAFE-02/SAFE-04 bypass class as CR-01, but out of scope for this gap-closure plan — flag for a future hardening pass if `env -S`-wrapped commands are deemed a priority.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 4 findings from `02-REVIEW.md` re-review (CR-01, WR-02, WR-03, IN-01) are addressed; full suite (96 tests) passes.
- Phase 02 (safety-gate-loop-control) gap-closure complete pending orchestrator's STATE.md/ROADMAP.md/REQUIREMENTS.md updates across the wave.
- The `env -S` residual (see Known Limitations) is the only intentionally-deferred item; no other known stubs or threat-surface gaps introduced.

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-13*

## Self-Check: PASSED

- FOUND: 02-04-SUMMARY.md
- FOUND: src/olla/safety.py, src/olla/tools/shell.py, src/olla/loop.py, tests/test_safety.py, tests/test_tools/test_shell.py, tests/test_loop.py
- FOUND commits: 8911f5b, 8e73c5f, d3f1a17, 6ebaa52, 8b9b87d, 8736407
