---
phase: 07-interactive-repl-mode
plan: 02
subsystem: cli
tags: [repl, prompt_toolkit, slash-commands, session-lifecycle]

# Dependency graph
requires:
  - phase: 07-interactive-repl-mode
    provides: "07-01's SessionState-injectable run_loop() and minimal main_loop() REPL entry point, including the current_model seam"
provides:
  - "FileHistory-backed persistent REPL input history and explicit multiline PromptSession config (REPL-01)"
  - "patch_stdout()-wrapped turn processing so step-progress prints don't corrupt the active prompt (D-14)"
  - "Single-Ctrl+C-continues / double-Ctrl+C-within-1.5s-exits semantics at both the idle-prompt and mid-turn interrupt sites (D-12)"
  - "/model, /exit, /quit, /clear slash-command dispatcher scoped to raw terminal input only (D-06/D-15/D-16/D-17, T-07-01 mitigation)"
affects: [07-03-rolling-context-trim]

# Actuals (#2632)
actuals:
  tokens: 3750
  tasks: 3
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Closure-based double-tap timestamp check (_is_double_tap, time.monotonic) reachable from both Ctrl+C sites, instead of a custom prompt_toolkit KeyBindings/event.app.exit registration — simpler because run_loop() blocks the main thread outside prompt_toolkit's async event loop, so the idle-prompt and mid-turn interrupts need the same decision logic, not two different mechanisms"
    - "Slash-command dispatch checks only the raw session.prompt() return value, before any run_loop() call — never scans session_state.messages/tool-observation text (T-07-01 mitigation)"

key-files:
  created: []
  modified:
    - src/olla/repl.py
    - tests/test_repl.py

key-decisions:
  - "Double-Ctrl+C exit implemented as a closure (_is_double_tap) checked from a try/except KeyboardInterrupt at both the session_prompt.prompt() call and the run_loop() call, instead of the plan's literal custom KeyBindings bound to c-c. prompt_toolkit's key-binding/event-loop machinery is not active while run_loop() blocks synchronously mid-turn, so a KeyBindings-only approach cannot cover the mid-turn interrupt site required by Task 3's concurrency test; the closure approach covers both sites with one code path and is directly testable via mocked session.prompt() side effects and a mocked time.monotonic() clock, which the plan's own test guidance names as an acceptable alternative."
  - "/model with no argument (bare '/model') prints a one-line usage message and re-prompts instead of raising IndexError from an unguarded text.split()[1] — not specified in the plan's <action> text, added as a Rule 2 (missing critical) fix since the alternative is an unhandled crash on obviously-reachable user input."

requirements-completed: [REPL-01, REPL-02]

coverage:
  - id: D1
    description: "PromptSession is constructed with a FileHistory-backed history= kwarg and an explicit multiline kwarg"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_session_construction_uses_file_history_and_multiline"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single Ctrl+C (at the idle prompt or mid-turn) continues the session; double Ctrl+C within 1.5s exits; a pause past the threshold does not exit"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_exit_semantics_single_ctrl_c_continues"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_exit_semantics_double_ctrl_c_exits"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_ctrl_c_during_turn_leaves_state_unchanged_before_next_turn"
        status: pass
    human_judgment: false
  - id: D3
    description: "/model <name> validates via get_provider() and reassigns current_model so the very next run_loop() call uses the switched-to model, without touching scratchpad/read_snapshots/untrusted_observation_seen"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_model_switch_preserves_state"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_model_switch_changes_model_used_by_next_run_loop_call"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_repeated_model_switch_is_idempotent"
        status: pass
    human_judgment: false
  - id: D4
    description: "/clear resets messages, scratchpad, read_snapshots, and untrusted_observation_seen to fresh-session defaults"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_clear_resets_all_state"
        status: pass
    human_judgment: false
  - id: D5
    description: "/exit and /quit end the loop without calling run_loop(); an unresolved slash command never crashes the REPL"
    requirement: "REPL-01"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_exit_and_quit_slash_commands_end_loop_without_run_loop"
        status: pass
      - kind: unit
        ref: "tests/test_repl.py#test_model_switch_without_argument_prints_usage"
        status: pass
    human_judgment: false
  - id: D6
    description: "Slash-command dispatch only ever inspects raw terminal input, never messages/tool-observation text — a '/model attacker' string injected via a simulated tool observation cannot spoof a provider switch"
    requirement: "REPL-02"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_slash_command_in_tool_observation_does_not_dispatch"
        status: pass
    human_judgment: false
  - id: D7
    description: "The REPL actually launches, accepts /clear and /model, and exits cleanly against a real (network-unreachable) Ollama model configuration — end-to-end manual smoke test"
    verification:
      - kind: manual_procedural
        ref: "printf '/clear\\n/model qwen2.5:3b\\n/exit\\n' | uv run olla --model qwen2.5:3b — printed 'Session cleared.' and \"Switched to model 'qwen2.5:3b'\", exited 0"
        status: pass
    human_judgment: true
    rationale: "No live Ollama server was available in this environment (ollama not installed, localhost:11434 unreachable), so the confirm-prompt-during-patch_stdout interaction the plan's <verification> asks to smoke-test (a real model turn hitting the shell/write_file confirm gate) could not be exercised end-to-end with a live model response — only the provider-construction and slash-command paths, which make no network call, were verified this way. A human with a running local Ollama instance should confirm a full multi-turn session including a confirm-gated tool call."

# Metrics
duration: 32min
completed: 2026-09-15
status: complete
---

# Phase 7 Plan 2: REPL UX & Slash-Command Controls Summary

**`src/olla/repl.py` expanded from 07-01's bare `prompt_toolkit` tracer into the full REPL-01/REPL-02 UX: `FileHistory`-backed persistent history, explicit `multiline`, `patch_stdout()`-wrapped turns, single/double-Ctrl+C exit semantics at both the idle-prompt and mid-turn interrupt sites, and a `/model`/`/exit`/`/quit`/`/clear` slash-command dispatcher scoped to raw terminal input only.**

## Performance

- **Duration:** 32 min
- **Started:** 2026-09-14T23:04Z (approx, base commit before this plan's first task)
- **Completed:** 2026-09-15T00:03:50+07:00
- **Tasks:** 3
- **Files modified:** 2 (`src/olla/repl.py`, `tests/test_repl.py`)

## Accomplishments
- `PromptSession` now constructed with `history=FileHistory(Path.home() / ".olla_history")` and `multiline=False`, giving REPL input persistent cross-restart history and explicit multiline config (REPL-01)
- Each turn's `run_loop()` call wrapped in `patch_stdout()` so existing step-progress prints (`_display()`) don't corrupt the active prompt's cursor position (D-14), unchanged print content
- Single Ctrl+C continues the session (re-prompts or re-raises to the prompt); a second Ctrl+C within 1.5s of the first — at either the idle prompt or mid-turn while `run_loop()` runs — exits the session (D-12); a pause past the threshold resets the tap count rather than exiting
- `/model <name>` calls `get_provider()` as a config-level validation gate and, only on success, reassigns the `current_model` local that every subsequent `run_loop(model=current_model, ...)` call reads — proven by asserting the *next* `run_loop` call's `model` kwarg, not just that `get_provider` was invoked; `messages`/`scratchpad`/`read_snapshots`/`untrusted_observation_seen` are untouched (D-06/D-17); repeated `/model x` calls are idempotent
- `/clear` resets `messages`, `scratchpad`, `read_snapshots`, and `untrusted_observation_seen` to fresh-session defaults (D-16)
- `/exit`/`/quit` end the loop without calling `run_loop()`; unrecognized `/`-prefixed input prints a message and re-prompts instead of being sent to the model
- Slash-command dispatch is provably scoped to the raw `session.prompt()` return value only — a `"/model attacker"` string injected into `session_state.messages` (simulating a tool observation) never triggers a provider switch (T-07-01 mitigation)

## Task Commits

Each task was committed atomically via TDD (Tasks 1-2) or direct addition (Task 3):

1. **Task 1: PromptSession UX — FileHistory, multiline, patch_stdout, double-Ctrl+C** — TDD cycle:
   - RED: `62b87e3` (test) — `test_session_construction_uses_file_history_and_multiline`, `test_exit_semantics_single_ctrl_c_continues`, `test_exit_semantics_double_ctrl_c_exits` fail (`KeyError: 'history'`)
   - GREEN: `9838245` (feat) — `pytest tests/test_repl.py -k "session_construction or exit_semantics" -x` passes (3 passed); full `tests/test_repl.py` (5 passed)
   - REFACTOR: none needed — `ruff check` clean after GREEN
2. **Task 2: Slash-command dispatch — /model, /exit, /quit, /clear** — TDD cycle:
   - RED: `b2c8be6` (test) — 6 new tests fail (`/model`/`/clear` currently forwarded to `run_loop()` as ordinary tasks)
   - GREEN: `ede8829` (feat) — `pytest tests/test_repl.py -k "model_switch or clear_resets or slash or exit_and_quit" -x` passes (6 passed); full `tests/test_repl.py` (11 passed)
   - REFACTOR: none needed — `ruff check` clean after GREEN
3. **Task 3: Idempotency/concurrency edge coverage + full regression** — `623e666` (test) — `test_repeated_model_switch_is_idempotent`, `test_ctrl_c_during_turn_leaves_state_unchanged_before_next_turn`; full `tests/test_repl.py` (13 passed, no test weakened)

**Plan metadata:** (this commit, once written)

## Files Created/Modified
- `src/olla/repl.py` - `FileHistory`/`multiline` `PromptSession` construction, `patch_stdout()`-wrapped turns, `_is_double_tap()` closure handling both Ctrl+C sites, `/model`/`/exit`/`/quit`/`/clear` slash dispatcher
- `tests/test_repl.py` - 11 new tests covering session construction, exit semantics, all four slash commands, the injection-scoping guard, idempotency, and the mid-turn Ctrl+C concurrency edge

## Decisions Made
- Double-Ctrl+C exit implemented as a shared closure checked from `try/except KeyboardInterrupt` at both interrupt sites (idle prompt and mid-turn `run_loop()`), rather than the plan's literal custom `KeyBindings`/`event.app.exit` approach — see key-decisions above for rationale.
- `/model` with no argument prints a usage line and re-prompts rather than crashing (Rule 2).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, design substitution] Double-Ctrl+C via closure instead of custom `KeyBindings`**
- **Found during:** Task 1 (PromptSession UX)
- **Issue:** The plan's `<action>` specifies a custom `KeyBindings()` bound to `c-c` calling `event.app.exit(exception=KeyboardInterrupt)`. `prompt_toolkit`'s key-binding/event-loop machinery is only active while `PromptSession.prompt()` itself is running; it is not active while `run_loop()` blocks the main thread synchronously mid-turn (Task 3's `test_ctrl_c_during_turn_leaves_state_unchanged_before_next_turn` requires exactly this mid-turn interrupt to be handled). A `KeyBindings`-only implementation would cover only the idle-prompt site, not the mid-turn site the plan itself requires tested in Task 3.
- **Fix:** Implemented a `_is_double_tap()` closure tracking `time.monotonic()` timestamps, checked from `try/except KeyboardInterrupt` at both the `session_prompt.prompt()` call and the `run_loop()` call. One decision path covers both sites.
- **Files modified:** src/olla/repl.py
- **Verification:** `pytest tests/test_repl.py -k "exit_semantics" -x` (2 passed) plus Task 3's `test_ctrl_c_during_turn_leaves_state_unchanged_before_next_turn` (mid-turn site).
- **Committed in:** `9838245` (Task 1 GREEN commit)

**2. [Rule 2 - Missing Critical] `/model` with no argument no longer crashes**
- **Found during:** Task 2 (slash-command dispatch)
- **Issue:** The plan's dispatch shape (`command, *rest = text.split(maxsplit=1)`, `<name>` taken from `rest`) has no guidance for a bare `/model` with no name — an unguarded `rest[0]` would raise `IndexError` and crash the whole REPL session on directly-reachable user input.
- **Fix:** `argument = rest[0].strip() if rest else ""`; empty `argument` prints `"Usage: /model <name>"` and re-prompts without calling `get_provider()`.
- **Files modified:** src/olla/repl.py
- **Verification:** `test_model_switch_without_argument_prints_usage` passes; `mock_run_loop.assert_not_called()`.
- **Committed in:** `ede8829` (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 bug/design-substitution, 1 missing-critical)
**Impact on plan:** Both changes were necessary for the plan's own acceptance criteria (Task 3's mid-turn interrupt test) and for basic crash-safety on ordinary user input. No scope creep — neither touches REPL-03/context-trim territory.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the mechanical `gsd_run check tdd-red-evidence` gate was not invoked. RED/GREEN discipline was followed manually for Tasks 1-2:
- **Task 1 RED** (`62b87e3`, `test(07-02): ...`): new tests committed before implementation existed; `pytest tests/test_repl.py -k "session_construction or exit_semantics" -x` failed with `KeyError: 'history'` (genuine RED — the kwarg didn't exist yet).
- **Task 1 GREEN** (`9838245`, `feat(07-02): ...`): implemented `FileHistory`/`multiline`/`patch_stdout`/double-Ctrl+C; same filter now passes (3 passed); full `tests/test_repl.py` (5 passed).
- **Task 2 RED** (`b2c8be6`, `test(07-02): ...`): 6 new tests committed before dispatch existed; `pytest tests/test_repl.py -k "model_switch or clear_resets or slash or exit_and_quit" -x` failed (`/model`/`/clear` sent straight to `run_loop()` as ordinary tasks — `assert 2 == 1` on call count).
- **Task 2 GREEN** (`ede8829`, `feat(07-02): ...`): implemented the slash dispatcher; same filter passes (6 passed); full `tests/test_repl.py` (11 passed).
- **Task 3** (`623e666`, `test(07-02): ...`): test-only addition per plan (no `tdd="true"` on this task); both new tests passed on first run against the existing Task 1-2 implementation — no separate RED phase applicable.
- **REFACTOR**: not needed for either TDD task — `ruff check src/olla/repl.py tests/test_repl.py` was clean after each GREEN commit.

## Issues Encountered
None beyond the two auto-fixed deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REPL-01 and REPL-02 are fully delivered: multiline editing, persistent history, correct Ctrl+C/Ctrl+D/double-Ctrl+C exit semantics, and the full `/model`/`/exit`/`/quit`/`/clear` slash-command surface (D-06/D-12 through D-17).
- `session_state`/`current_model` remain the exact seams 07-03 needs for rolling context trimming (`turn_start_index`, captured unused in 07-01, is still available in `run_loop()`).
- No blockers. One caveat carried to a human: the `--yes`-gated confirm-prompt-inside-`patch_stdout()` interaction (advisor-flagged) was not exercised against a live model this session — no local Ollama server was reachable in this environment. A human with a running Ollama instance should manually confirm a full REPL session including a confirm-gated shell/`write_file` call renders correctly under `patch_stdout()`.
- Only REPL-03 (context trimming, 07-03) remains in this phase.

---
*Phase: 07-interactive-repl-mode*
*Completed: 2026-09-15*

## Self-Check: PASSED

All key files present on disk (`src/olla/repl.py`, `tests/test_repl.py`, this SUMMARY.md). All five commit hashes (`62b87e3`, `9838245`, `b2c8be6`, `ede8829`, `623e666`) found in `git log --oneline --all`. Task-level `<acceptance_criteria>` re-verified: `pytest tests/test_repl.py -k "session_construction or exit_semantics" -x` (3 passed), `pytest tests/test_repl.py -k "model_switch or clear_resets or slash or exit_and_quit" -x` (6 passed), `pytest tests/test_repl.py -x` (13 passed, no fewer than the file defines, no existing test weakened). Plan-level `<verification>` re-run: `pytest tests/test_repl.py -x` (13 passed) and full suite `pytest -q` (448 passed, no regressions vs. the 437-test pre-plan baseline); manual smoke test (`printf '/clear\n/model qwen2.5:3b\n/exit\n' | uv run olla --model qwen2.5:3b`) printed `Session cleared.` and `Switched to model 'qwen2.5:3b'`, exited 0.
