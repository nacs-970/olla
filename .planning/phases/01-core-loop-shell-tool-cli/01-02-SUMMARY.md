---
phase: 01-core-loop-shell-tool-cli
plan: 02
subsystem: testing
tags: [ollama, click, regex, smoke-test, cli, tag-compliance]

# Dependency graph
requires:
  - phase: 01-core-loop-shell-tool-cli
    provides: "call_model(model, messages) -> str, run_loop, SYSTEM_PROMPT, CLI main() with TASK/--model/--dry-run/--max-steps/--yes (Plan 01-01)"
provides:
  - "call_model(model, messages, think=False) -> str — additive, backward-compatible think parameter"
  - "olla.smoke.classify_response(content) -> compliant | reverted_to_native_format | non_compliant"
  - "olla.smoke.run_smoke_test(model) -> None — runs FIXED_PROMPTS under think=False/True, prints compliance + D-08 WARNING"
  - "olla --smoke-test --model <name> CLI flag"
affects: [future phases needing real-model compliance data, any phase touching call_model signature]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Three-way response classifier using ordered regex checks (compliant checked before reverted-to-native, with negative lookahead to disambiguate olla <tool>NAME</tool> from Gemma's native <tool>{...} JSON)"
    - "CLI early-return branch pattern: --smoke-test check runs before the existing TASK-required validation, short-circuiting run_loop"

key-files:
  created:
    - src/olla/smoke.py
    - tests/test_smoke.py
  modified:
    - src/olla/loop.py
    - src/olla/cli.py
    - tests/test_cli.py

key-decisions:
  - "call_model's think parameter defaults to False, preserving Plan 01-01's run_loop behavior and tests unchanged (verified: existing test_call_model and all run_loop tests pass unmodified)"
  - "classify_response checks olla-compliant patterns (<final>, <tool>NAME</tool><args>) before native-format patterns, so a response containing both classifies as compliant"

patterns-established:
  - "Pattern: smoke/validation modules live alongside loop.py and import call_model + SYSTEM_PROMPT directly — no new abstraction layer"

requirements-completed: [LOOP-01]

# Metrics
duration: ~15min
completed: 2026-06-11
---

# Phase 01 Plan 02: Smoke-Test Tag-Compliance Classifier Summary

**Added `olla --smoke-test --model <name>` (D-07): runs two fixed prompts under think=False/True against a model, three-way classifies each response (olla-compliant / reverted-to-native-format / non-compliant) via ordered regex, and flags sub-80% think=False compliance with a D-08 WARNING without building any fallback format.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `call_model` in `src/olla/loop.py` gained an additive `think: bool = False` parameter, replacing the hardcoded `think=False` passed to `ollama.chat()` — Plan 01-01's `run_loop` and its tests required zero changes
- New `src/olla/smoke.py` module: `classify_response()` three-way classifier (compliant / reverted_to_native_format / non_compliant) using `OLLA_FINAL_RE`, `OLLA_TOOL_RE` (with negative lookahead to distinguish olla's `<tool>shell</tool>` from Gemma's native `<tool>{...}` JSON), `NATIVE_QWEN_RE`, `NATIVE_GEMMA_RE`
- `run_smoke_test(model)` runs `FIXED_PROMPTS` (2 static prompts) under both `think=False` and `think=True`, prints per-mode compliance percentages and reverted/non-compliant counts, and prints a D-08 WARNING line when think=False compliance is below 80%
- `olla --smoke-test --model <name>` CLI flag wired into `main()`, checked before the existing TASK-required validation; `olla --smoke-test` without `--model` raises `click.UsageError` mentioning `--model`

## Task Commits

Each task was committed atomically (TDD: test → feat per task):

1. **Task 1: Extend call_model with think param + smoke-test classifier/runner**
   - `dd25f3c` (test) - add failing tests for smoke-test classifier and runner
   - `47dc8d1` (feat) - add think param to call_model and smoke-test classifier/runner
2. **Task 2: Wire --smoke-test flag into CLI**
   - `e4f2358` (test) - add failing tests for --smoke-test CLI flag
   - `f8edddc` (feat) - wire --smoke-test flag into CLI

**Plan metadata:** (this commit)

## Files Created/Modified
- `src/olla/loop.py` - `call_model` signature extended to `call_model(model, messages, think: bool = False)`, passes `think=think` to `ollama.chat()`
- `src/olla/smoke.py` - new: `classify_response`, `run_smoke_test`, `FIXED_PROMPTS`, `NATIVE_QWEN_RE`, `NATIVE_GEMMA_RE`, `OLLA_TOOL_RE`, `OLLA_FINAL_RE`
- `src/olla/cli.py` - imports `run_smoke_test`, adds `--smoke-test` flag, new early-return branch checked before the TASK-required check
- `tests/test_smoke.py` - new: 8 tests covering all 5 classifier cases + 3 run_smoke_test behaviors
- `tests/test_cli.py` - 3 new tests for `--smoke-test` flag behavior

## Decisions Made
- Followed plan exactly: regex definitions, check ordering, FIXED_PROMPTS contents, and CLI branch placement match the plan's `<action>` specification verbatim.
- No fallback delimiter format was built (D-08) — the WARNING is purely informational/flagging.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Test execution environment:** The worktree has no local `.venv`; the main repo's `.venv` has `olla` installed in editable mode pointing at the main repo's `src/`, not the worktree's. Verification was run with `PYTHONPATH=src:$PYTHONPATH /home/nacs/Documents/git/olla/.venv/bin/python -m pytest tests/ -v` from the worktree root, which correctly resolves `olla` to the worktree's `src/olla`. This is an environment-only workaround; no project files were changed to address it.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Full test suite (33 tests) passes: 5 parser + 6 loop + 8 smoke + 7 cli + 5 shell tool tests, all green with no live Ollama server required (smoke/cli tests mock `call_model`/`run_smoke_test`).
- `olla --smoke-test --model <name>` is ready for manual validation against the user's real local models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive) — this empirical run was not performed as part of this plan (requires a live Ollama server) but the tooling is in place.
- No blockers for Phase 01 completion; this was the final plan (2 of 2) for Phase 01.

---
*Phase: 01-core-loop-shell-tool-cli*
*Completed: 2026-06-11*
