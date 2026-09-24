---
phase: quick-260924-nbw
plan: 01
subsystem: loop
tags: [react-loop, token-overhead, streaming, debug]
status: complete
requires: []
provides:
  - "tag-free prose accepted as final in _prepare_action"
  - "single in-step retry of an empty model stream (_stream_once helper)"
  - "canonical assistant history envelope; empty assistant turns never recorded"
  - "debug_log writes to stderr"
affects: [src/olla/loop.py, src/olla/debug.py]
tech-stack:
  added: []
  patterns:
    - "History rebuilt from parsed _Action fields, not raw model text"
key-files:
  created: []
  modified:
    - src/olla/debug.py
    - src/olla/loop.py
    - tests/test_debug.py
    - tests/test_loop.py
decisions:
  - "Non-empty prose with no protocol tag (any case, open or close) is a final answer; any tag or empty content keeps the nudge path"
  - "Empty stream (no content and no reasoning) is retried exactly once inside _stream_model_turn; the trim check and the mocked early-return run once"
  - "Assistant history is <tool>NAME</tool><args>ARGS</args> or <final>TEXT</final>, rebuilt from the parsed action"
  - "debug_log output goes to stderr so it can be redirected away from the answer stream"
metrics:
  duration: ~15min
  completed: 2026-09-24
commits: 2
plan_head_before: 80ac33bc72a4bf72090c3805fc63f5c2b54e4616
actuals:
  tokens: 3560
  tasks: 2
  commits: 2
---

# Phase quick-260924-nbw Plan 01: Cut wasted round-trips Summary

Tag-free prose now ends the turn as a final answer. An empty HTTP-200 stream is retried once in the same step. Assistant history is always a canonical `<tool>..</tool><args>..</args>` or `<final>..</final>` envelope, and an empty assistant message is never recorded. `debug_log` writes to stderr. Together, these remove the two extra full-context round-trips seen in the live OpenRouter run.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Debug output to stderr + canonical assistant history (fixes 3, 4) | 97c4352 | src/olla/debug.py, src/olla/loop.py, tests/test_debug.py, tests/test_loop.py |
| 2 | Tag-free prose becomes final + retry empty stream once (fixes 1, 2) | 0499c9f | src/olla/loop.py, tests/test_loop.py |

## What Changed

- **Fix 3 (debug.py):** All three `print` calls in `debug_log` use `file=sys.stderr`. The debug tests now assert on `.err`. The disabled test checks that both `.out` and `.err` are empty. The run_loop debug test checks that `[DEBUG]` is not in `.out`.
- **Fix 4 (run_loop):** `history_content` is `truncate_output(content)` for `none`, `<final>{text}</final>` for `final`, and `<tool>{tool}</tool><args>{args_raw}</args>` for all other kinds. `args_raw` is not re-stripped, so `write_file`/`remember` payloads round-trip byte for byte.
- **Fix 1 (_prepare_action):** Imports the six protocol regexes from `olla.parser` into `_PROTOCOL_TAG_RES`. In the `none` branch, stripped prose that is non-empty and contains no tag returns `_Action("final", "final", None, text=prose)`. Otherwise the original `none` action is returned unchanged.
- **Fix 2 (_stream_model_turn / run_loop):** The per-attempt stream body moved into the module-level helper `_stream_once(provider, messages) -> (content, thought_text)`. When content and reasoning are both blank, `debug_log("Empty model stream; retrying once")` runs and the helper is called one more time, inside the same `try`. The reasoning fallback and all except clauses are unchanged. `run_loop` skips the assistant append when `action.kind == "none"` and `content` is blank. The nudge is still appended.

## Tests

- Retargeted the 4 existing nudge-path tests at malformed tag text, as the plan specified: `<tool>shell`, `"<tool>" + "x"*N`, and `<tool>shell without args`.
- New tests: canonical shell history ending with `</args>`, write_file history round-trip, 2 prose-is-final `_prepare_action` cases, 5 stays-`none` cases, a run_loop prose test (1 call, no nudge, `<final>` history), empty-then-final (2 `stream_chat` calls, `* ok` once), and double-empty (no blank assistant message, exactly 1 nudge, 3 `stream_chat` calls).
- Final: `.venv/bin/python -m pytest -q` shows **496 passed**. `.venv/bin/ruff check src tests` shows **All checks passed!**
- `git diff --stat HEAD~2 -- src/olla/parser.py src/olla/smoke.py scripts/` is empty.

## Deviations from Plan

None. The plan was executed as written. The optional write_file round-trip test was included.

## Known Stubs

None.

## Threat Flags

None. No new surface beyond the plan's threat model. A prose final is display-only through `_display`, and any protocol tag keeps the nudge path.

## Self-Check: PASSED

- FOUND: src/olla/debug.py, src/olla/loop.py, tests/test_debug.py, tests/test_loop.py
- FOUND: 97c4352, 0499c9f on main

## Orchestrator follow-up

- `8ec2ccd`: the executor flagged that an unclosed `<think>` survives `_strip_thinking` and would be accepted as a prose final answer. The orchestrator added `</?think>` to `_PROTOCOL_TAG_RES`, plus the regression test `test_unclosed_think_is_not_accepted_as_prose_final`. The suite now has 497 passing tests and ruff is clean.
