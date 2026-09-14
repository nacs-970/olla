---
phase: 07-interactive-repl-mode
plan: 01
subsystem: cli
tags: [repl, prompt_toolkit, tiktoken, session-state, react-loop]

# Dependency graph
requires:
  - phase: 06-web-tools
    provides: fetch_url/search_web untrusted-content tagging that SessionState now carries across REPL turns unchanged
provides:
  - "SessionState dataclass (messages, scratchpad, read_snapshots, untrusted_observation_seen) threaded through run_loop() via an optional trailing `session` parameter"
  - "src/olla/repl.py — minimal prompt_toolkit REPL entry point (main_loop()) driving run_loop() once per turn over one shared SessionState"
  - "olla with no TASK argument and a resolvable --model launches the REPL instead of raising UsageError"
  - "current_model seam in repl.main_loop() that 07-02's /model handler will reassign"
affects: [07-02-repl-ux-and-controls, 07-03-rolling-context-trim]

# Actuals (#2632)
actuals:
  tokens: 5100
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: [prompt_toolkit>=3.0,<4, tiktoken>=0.11,<1]
  patterns:
    - "Outer session loop (repl.py) / inner bounded step loop (run_loop()) separation — run_loop() accepts an optional externally-owned SessionState instead of always constructing its own"
    - "session = session or SessionState(...) resolution at the top of run_loop(), before the dry_run branch, so the system-prompt-seeding invariant (session.messages[0] is always the system prompt) holds for both one-shot and multi-turn callers"

key-files:
  created:
    - src/olla/repl.py
    - tests/test_repl.py
  modified:
    - src/olla/loop.py
    - src/olla/cli.py
    - src/olla/tools/memory.py
    - pyproject.toml
    - uv.lock
    - tests/test_loop.py
    - tests/test_cli.py

key-decisions:
  - "SessionState placed immediately after the existing _FileReadSnapshot dataclass (not literally 'before _terminal_safe' as PLAN.md's prose suggested) — the type hint references _FileReadSnapshot, which does not exist yet at that earlier point in the file; NameError would result. Still lands in the first ~110 lines of the module, satisfying the 'near the top' intent."
  - "repl.py's own get_provider() call at launch discards its return value — run_loop() re-resolves the provider internally on every turn regardless, so the launch-time call exists solely to fail fast on a bad --model before entering the input loop, matching the existing smoke.py/run_loop() try/except/print/return shape."

requirements-completed: [REPL-01, REPL-02]

coverage:
  - id: D1
    description: "olla with no TASK argument and a resolvable --model launches repl.main_loop() instead of raising click.UsageError"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_no_task_launches_repl_when_model_given"
        status: pass
      - kind: unit
        ref: "tests/test_cli.py#test_no_task_no_model_raises_usage_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two sequential REPL turns (via run_loop() called twice with the same injected SessionState) share one Scratchpad instance end-to-end — remember in turn 1, recall in turn 2"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_session_state_persists_scratchpad_across_calls"
        status: pass
    human_judgment: false
  - id: D3
    description: "The one-shot CLI path's run_loop() call remains byte-for-byte unchanged in its kwargs (no session= leak into the task-given branch)"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_cli.py#test_task_and_model_call_run_loop_with_defaults"
        status: pass
    human_judgment: false
  - id: D4
    description: "read_snapshots persistence across REPL turn boundaries does not silently defeat the existing read-before-overwrite staleness check — a genuinely fresh snapshot from turn 1 still satisfies a turn-2 write with no re-read"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_read_snapshot_persists_across_turns"
        status: pass
    human_judgment: false
  - id: D5
    description: "untrusted_observation_seen set during turn 1 (via a read_file tool call) is still True at the start of, and after, turn 2 — driven directly against two run_loop() calls, not only REPL-side sentinels (T-07-05 mitigation coverage)"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_untrusted_observation_seen_persists_across_calls"
        status: pass
    human_judgment: false
  - id: D6
    description: "prompt_toolkit and tiktoken were installed only after explicit human sign-off on package legitimacy"
    verification:
      - kind: other
        ref: "checkpoint:human-verify Task 1 (gate=blocking-human), resumed with human response 'approved'"
        status: pass
    human_judgment: false

# Metrics
duration: 17min
completed: 2026-09-14
status: complete
---

# Phase 7 Plan 1: Session-Injectable run_loop() + Minimal prompt_toolkit REPL Summary

**`run_loop()` refactored to accept an optional externally-owned `SessionState` (messages/scratchpad/read_snapshots/untrusted_observation_seen); a new `src/olla/repl.py` drives it once per turn from a bare `prompt_toolkit` `PromptSession`, wired end-to-end from `olla` with no TASK argument through to a persisted Scratchpad across two consecutive REPL turns.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-09-14T15:45:00Z (resumed after Task 1 checkpoint approval)
- **Completed:** 2026-09-14T16:01:53Z
- **Tasks:** 3 (Task 1 checkpoint approved in a prior session with no commits; Task 2 + Task 3 executed and committed this session)
- **Files modified:** 8 (pyproject.toml, uv.lock, src/olla/loop.py, src/olla/repl.py [new], src/olla/cli.py, src/olla/tools/memory.py, tests/test_repl.py [new], tests/test_loop.py, tests/test_cli.py)

## Accomplishments
- `prompt_toolkit>=3.0,<4` and `tiktoken>=0.11,<1` added as vetted runtime dependencies after human sign-off on package legitimacy (Task 1 checkpoint)
- `SessionState` dataclass + session-injectable `run_loop()` — one-shot CLI path unchanged (session=None still builds a fresh Scratchpad/messages/read_snapshots exactly as before); state construction moved to the top of `run_loop()` (before the `dry_run` branch), fixing the sequencing hazard so the system-prompt-seeding invariant holds for both call shapes
- `src/olla/repl.py` — minimal REPL entry point (`main_loop()`): bare `PromptSession` loop, single Ctrl+C continues / Ctrl+D exits, blank-input skip, `current_model` seam for 07-02's `/model` switch, one `SessionState` shared across every turn
- `olla` (no TASK, resolvable `--model`) now launches the REPL instead of raising `click.UsageError`; the one-shot task-given path's `run_loop()` call is byte-for-byte unchanged
- `Scratchpad` module/class docstrings updated to the dual one-shot (per-invocation)/REPL (per-session, reset by `/clear`) lifetime contract (D-01/D-05)

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify prompt_toolkit and tiktoken package legitimacy before install** — checkpoint approved in a prior executor run (no commit; human responded "approved")
2. **Task 2: Add prompt_toolkit and tiktoken dependencies** - `d5322ac` (feat)
3. **Task 3: End-to-end "REPL session" — SessionState refactor + minimal prompt_toolkit loop** — TDD cycle:
   - RED: `9e12c4a` (test) — new/modified tests fail to collect (`olla.repl` doesn't exist, `SessionState` not exported, `olla.cli.run_repl` undefined), confirmed via `pytest tests/test_repl.py tests/test_loop.py tests/test_cli.py -x`
   - GREEN: `4cabac1` (feat) — `pytest tests/test_repl.py tests/test_loop.py tests/test_cli.py -x` passes (163 passed); full suite 437 passed
   - REFACTOR: none needed — implementation was already `ruff check`-clean after the GREEN commit; no separate refactor commit

**Plan metadata:** (this commit, once written)

## Files Created/Modified
- `pyproject.toml` - added `prompt_toolkit>=3.0,<4` and `tiktoken>=0.11,<1` to `dependencies`
- `uv.lock` - regenerated via `uv sync` (+ `uv sync --extra dev` to restore dev tooling, see Deviations)
- `src/olla/loop.py` - `SessionState` dataclass; `run_loop(..., session=None)`; all internal `messages`/`scratchpad`/`read_snapshots`/`untrusted_observation_seen` references now route through `session.*`
- `src/olla/repl.py` (new) - `main_loop()`: provider init, `SessionState` construction, bare `PromptSession` loop calling `run_loop()` once per turn
- `src/olla/cli.py` - imports `repl.main_loop as run_repl`; no-TASK branch launches the REPL when `--model` is given, raises `UsageError` mentioning `--model` otherwise
- `src/olla/tools/memory.py` - `Scratchpad` module/class docstrings updated to the dual lifetime contract
- `tests/test_repl.py` (new) - `main_loop` dispatches two turns through one shared `SessionState`; provider-init failure prints and returns without calling `run_loop`
- `tests/test_loop.py` - three new session-persistence tests (Scratchpad, read_snapshots, untrusted_observation_seen across two separate `run_loop()` calls)
- `tests/test_cli.py` - `test_missing_task_raises_usage_error` rewritten into `test_no_task_launches_repl_when_model_given`; added `test_no_task_no_model_raises_usage_error`

## Decisions Made
- `SessionState`'s exact placement in `loop.py` deviated from PLAN.md's literal "before `_terminal_safe`" instruction (would raise `NameError` on the `_FileReadSnapshot` type reference); placed immediately after `_FileReadSnapshot` instead, still near the top of the module.
- `repl.py`'s launch-time `get_provider()` call discards its return value — `run_loop()` already re-resolves the provider internally on every turn (unchanged existing behavior), so the launch-time call exists purely as a fail-fast gate on a bad `--model` before the input loop starts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv sync` (Task 2's specified command) dropped dev dependencies**
- **Found during:** Task 2 (Add prompt_toolkit and tiktoken dependencies)
- **Issue:** Running plain `uv sync` (as Task 2's `<action>` specifies) resolved and installed only the base `dependencies` list, uninstalling `pytest`, `pytest-mock`, and `ruff` — all declared under `[project.optional-dependencies].dev`, which `uv sync` does not install by default without `--extra dev`/`--all-extras`. The project's venv had those dev tools installed prior to this session (used for the pre-task baseline `pytest` run), so this was a real regression, not a pre-existing gap.
- **Fix:** Ran `uv sync --extra dev` immediately after, restoring `pytest`, `pytest-mock`, `ruff`, and their transitive deps (`iniconfig`, `packaging`, `pluggy`).
- **Files modified:** uv.lock (already modified by the first `uv sync`; the second sync only changed the installed venv, not the lockfile)
- **Verification:** `uv run pytest --version` reports `pytest 9.1.1`; `uv run pytest -q` passes the full 431-test pre-task baseline before Task 3 begins.
- **Committed in:** d5322ac (Task 2 commit — uv.lock as committed already reflects the full dependency set including dev extras' resolution metadata)

**2. [Rule 1 - Bug] `turn_start_index` triggers ruff F841 (assigned but never used)**
- **Found during:** Task 3, post-implementation lint check
- **Issue:** PLAN.md explicitly specifies `turn_start_index` is "unused beyond the capture in this plan" (consumed by 07-03), which `ruff check` correctly flags as an unused local variable.
- **Fix:** Added `# noqa: F841` on the assignment line with the existing explanatory comment, keeping `ruff check` clean without removing the intentionally-forward-looking capture.
- **Files modified:** src/olla/loop.py
- **Verification:** `ruff check src/olla/loop.py src/olla/repl.py src/olla/cli.py src/olla/tools/memory.py` → "All checks passed!"
- **Committed in:** 4cabac1 (Task 3 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug/polish)
**Impact on plan:** Both fixes necessary for a correct, lint-clean dev/test environment. No scope creep — neither touched REPL-01/REPL-02 behavior.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the mechanical `gsd_run check tdd-red-evidence` gate was not invoked. RED/GREEN discipline was still followed manually for Task 3:
- **RED** (`9e12c4a`, `test(07-01): ...`): committed the new/modified test files before any source implementation existed. `pytest tests/test_repl.py tests/test_loop.py tests/test_cli.py -x` failed at collection (`ModuleNotFoundError: No module named 'olla.repl'`) — a genuine RED caused by the new API surface not existing yet, not a fixture crash or unrelated failure.
- **GREEN** (`4cabac1`, `feat(07-01): ...`): implemented `SessionState`, the `run_loop()` refactor, `repl.py`, the `cli.py` branch, and the `memory.py` docstring updates. Same three test files now pass (163 passed); full suite 437 passed, no regressions vs. the 431-test baseline.
- **REFACTOR**: not needed — no `refactor(07-01): ...` commit; `ruff check` was already clean after GREEN (once the intentional `turn_start_index` noqa was added).

## Issues Encountered
None beyond the two auto-fixed deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `SessionState` and the `current_model` seam in `repl.py` are ready for 07-02 (`/model`, `/exit`, `/quit`, `/clear` slash commands, `FileHistory`, `multiline`, `patch_stdout`, double-Ctrl+C) and 07-03 (rolling context trim consuming `turn_start_index`) to build on directly.
- No blockers. Manual smoke test (`olla --model qwen2.5:3b < /dev/null`) confirms the REPL launches a `> ` prompt and exits cleanly (exit code 0) on EOF without requiring a live Ollama server (provider construction is lazy).

---
*Phase: 07-interactive-repl-mode*
*Completed: 2026-09-14*

## Self-Check: PASSED

All key files present on disk (`src/olla/repl.py`, `tests/test_repl.py`, `src/olla/loop.py`, `src/olla/cli.py`, `src/olla/tools/memory.py`, this SUMMARY.md). All three commit hashes (`d5322ac`, `9e12c4a`, `4cabac1`) found in `git log --oneline --all`. Task-level `<acceptance_criteria>` re-verified: `pytest tests/test_repl.py -x` (2 passed), `pytest tests/test_loop.py -k "session_state or read_snapshot or untrusted_observation_seen" -x` (3 passed), `pytest tests/test_cli.py -x` (15 passed), full suite `pytest -q` (437 passed, no regressions vs. the 431-test pre-task baseline). Plan-level `<verification>` re-run: full suite passes; `git diff pyproject.toml uv.lock` (against `a42d39a`) shows both new dependencies; manual smoke test (`olla --model qwen2.5:3b < /dev/null`) exits cleanly (code 0) after printing a `> ` prompt.
