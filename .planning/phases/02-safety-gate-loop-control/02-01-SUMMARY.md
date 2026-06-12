---
phase: 02-safety-gate-loop-control
plan: 01
subsystem: safety
tags: [safety-gate, blocklist, allowlist, confirm-prompt, rich, ReAct-loop]

# Dependency graph
requires:
  - phase: 01-core-loop-shell-tool-cli
    provides: run_loop's shell-tool dispatch branch (argv = shlex.split(...), run_shell, truncate_output, "Step N: running..." display pattern)
provides:
  - "src/olla/safety.py: pure check(argv, yes) -> Decision (ALLOW/CONFIRM/BLOCK) with D-01 ALLOWLIST and D-03 blocklist rule table"
  - "run_loop safety-gate dispatch: BLOCK short-circuits before run_shell, CONFIRM shows rich.prompt.Confirm.ask (EOFError-safe), ALLOW/--yes bypass the prompt"
  - "--yes wired end-to-end from cli.py through run_loop to the CONFIRM gate"
  - "rich>=13 added as a declared runtime dependency"
affects: [02-02-dry-run-repetition-guard]

# Tech tracking
tech-stack:
  added: ["rich>=13 (rich.prompt.Confirm)"]
  patterns:
    - "Decision TypedDict (kind: ALLOW|CONFIRM|BLOCK, reason: NotRequired[str]) as the safety-gate contract, consumed by loop.py and reusable by 02-02's dry-run preview"
    - "Pure decision module (safety.py) with zero I/O, callable from both the real execution path and a future dry-run preview path"
    - "Denial-as-observation: BLOCK and declined-CONFIRM both append a truthful Observation: message so the model sees the real outcome"

key-files:
  created:
    - src/olla/safety.py
    - tests/test_safety.py
  modified:
    - src/olla/loop.py
    - tests/test_loop.py
    - src/olla/cli.py
    - tests/test_cli.py
    - pyproject.toml

key-decisions:
  - "dd/mkfs* device-path matching strips a 'key=' prefix (e.g. dd's of=/dev/sda) before fnmatch against /dev/* and the sd/nvme/hd device-name prefixes - naive fnmatch on the raw arg fails for dd's if=/of= syntax"
  - "Print of 'Step N: running <argv>...' happens exactly once, only on the path that proceeds to run_shell (restructured so BLOCK and CONFIRM-declined continue before that print)"

patterns-established:
  - "Pure decision/check functions (no I/O) live in dedicated modules and are imported into loop.py for dispatch - keeps safety logic independently testable and reusable for preview/dry-run paths"

requirements-completed: [SAFE-02, SAFE-04]

# Metrics
duration: 35min
completed: 2026-06-12
---

# Phase 02 Plan 01: Safety Gate Confirm Dispatch Summary

**Pure `safety.check(argv, yes) -> Decision` module (D-01 allowlist + D-03 blocklist) wired into `run_loop` as a real BLOCK/CONFIRM/ALLOW gate using `rich.prompt.Confirm.ask`, with `--yes` threaded end-to-end and `rich>=13` added as a dependency.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- `src/olla/safety.py` exports `Decision`, `ALLOWLIST`, and `check(argv, yes) -> Decision` — a pure, side-effect-free classifier covering D-01 (13-binary read-only allowlist) and D-03 (hard-blocked binaries, dangerous `rm` targets, `dd`/`mkfs*` on raw block devices, fork-bomb pattern, `chmod`/`chown -R /`)
- `run_loop` now gates every shell command through `check()` before `run_shell` is ever called: BLOCK short-circuits with a truthful "blocked by safety policy: <reason>" observation, CONFIRM shows a `rich.prompt.Confirm.ask` prompt with the resolved argv (EOFError treated as a safe decline), ALLOW and `--yes` (for CONFIRM only) proceed without prompting
- `--yes` is wired from `cli.py` through `run_loop(..., yes=yes, dry_run=dry_run)`; the inert "--yes is not yet enforced" notice is removed
- `rich>=13` added to `pyproject.toml` dependencies (installed in the dev venv: rich 13.9.4)
- First user-observable change in Phase 2: a user running `olla "task"` now sees olla refuse blocklisted commands and prompt before anything else

## Task Commits

Each task was committed atomically:

1. **Task 1: Write safety.py decision module (ALLOWLIST, blocklist rule table, check())** - `17204c9` (feat)
2. **Task 2: Wire safety-gate dispatch (BLOCK/CONFIRM/ALLOW) into run_loop with EOFError-safe confirm** - `c680646` (feat)
3. **Task 3: Wire --yes into cli.py, add rich dependency, update test_cli.py** - `c2d4b48` (feat)

## Files Created/Modified
- `src/olla/safety.py` - New pure decision module: `Decision` TypedDict, `ALLOWLIST`, `_HARD_BLOCKED_BINARIES`, `_RM_DANGEROUS_TARGETS`, `_DEVICE_GLOB`/`_DEVICE_PREFIXES`, `_FORK_BOMB_TOKENS`, `_blocklist_match()`, `check(argv, yes) -> Decision`
- `tests/test_safety.py` - 17 tests covering every D-01/D-03 rule, empty-argv, yes-invariance, and BLOCK-precedence
- `src/olla/loop.py` - Added `Confirm` (rich) and `check` (olla.safety) imports; `run_loop` signature gains `yes: bool = False, dry_run: bool = False`; shell-tool branch now dispatches on `check(argv, yes=yes)` before calling `run_shell`
- `tests/test_loop.py` - Fixed `test_run_loop_tool_result_real_no_output_success` (now uses `cat /dev/null`, ALLOW-tier, instead of `touch foo`); added 7 new tests for ALLOW/BLOCK/CONFIRM-approved/CONFIRM-declined/yes-bypass/EOFError-decline/BLOCK+yes
- `src/olla/cli.py` - Removed inert "--yes is not yet enforced" notice; `run_loop(...)` call now passes `yes=yes, dry_run=dry_run`
- `tests/test_cli.py` - Updated default/max-steps/dry-run tests to assert the full `run_loop` signature including `yes=`/`dry_run=`; replaced `test_yes_flag_prints_inert_notice` with `test_yes_flag_threaded_through`
- `pyproject.toml` - Added `"rich>=13"` to `dependencies`

## Decisions Made
- **dd/mkfs* device matching**: The plan's literal `fnmatch.fnmatch(arg, "/dev/*")` over raw args fails for `dd`'s `of=/dev/sda` syntax (the token starts with `of=`, not `/dev/`). Implemented `_is_dangerous_device_arg()` which strips a `key=` prefix (via `arg.split("=")[-1]`) before the `/dev/*` glob match and the `sd`/`nvme`/`hd` device-name prefix check. This satisfies all four plan test cases: `dd if=/dev/zero of=/dev/sda` (BLOCK), `mkfs.ext4 /dev/nvme0n1` (BLOCK, bare path also handled since splitting on `=` with no `=` returns the original string), `dd if=/dev/zero of=/tmp/test.img` (CONFIRM). Caught via advisor review before implementation — would otherwise have left a test asserting BLOCK on a rule that never fires.
- **Single print-site for "Step N: running..."**: Restructured the shell-tool branch so the step-display print happens exactly once, only on the path that reaches `run_shell` (after BLOCK and CONFIRM-declined/EOF paths have already `continue`d), per the plan's explicit non-duplication requirement.

## Deviations from Plan

None - plan executed as written, with the dd/mkfs `key=` prefix-stripping refinement (identified during advisor review, before writing code) implementing the spirit of D-03's "dd/mkfs* targeting /dev/sd*|nvme*|hd*" rule for both `dd`'s `if=`/`of=` argument syntax and `mkfs*`'s bare-path syntax — this is the concrete pattern-implementation detail the plan explicitly deferred to "Claude's Discretion" (02-CONTEXT.md), not a deviation from a specified behavior.

## Issues Encountered

- Test execution required `PYTHONPATH=src` with the shared `.venv` at the main repo root, since the venv's editable `olla` install points at the main repo's `src/olla`, not this worktree's copy. `rich>=13` was also installed into that shared venv (rich 13.9.4) to satisfy the new `from rich.prompt import Confirm` import for test runs. This is a test-environment detail only — `pyproject.toml`'s `dependencies` list is the source of truth and was updated in Task 3.

## Next Phase Readiness

- `safety.py`'s `Decision`/`check(argv, yes)` contract is locked and ready for 02-02's `--dry-run` preview to call directly (zero side effects, verdict strings can be derived from `decision["kind"]`/`decision["reason"]`)
- `run_loop`'s signature already accepts `dry_run: bool = False` (currently unused) so 02-02 does not need a second signature-touching edit to the `def run_loop(...)` line
- Full test suite: 66/66 passing (`pytest tests/` — includes the 17 new/updated tests from this plan plus all prior-phase tests, no regressions)
- No blockers for 02-02

---
*Phase: 02-safety-gate-loop-control*
*Completed: 2026-06-12*
