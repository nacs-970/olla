---
phase: quick-260924-mml
plan: quick-260924-mml
subsystem: loop, parser
tags: [reasoning, parser, retry-nudge, openrouter, streaming]
requires: []
provides:
  - "_stream_model_turn returns only non-thought content, with a guarded empty-content reasoning fallback"
  - "Retry nudge labeled as an automated harness message, with no literal protocol tags"
  - "Parser args payload spans anchored to the first real tool envelope"
key-files:
  created: []
  modified: [src/olla/loop.py, src/olla/parser.py, tests/test_loop.py, tests/test_parser.py]
key-decisions:
  - "The nudge stays role user, because mid-conversation system messages break some chat templates (e.g. Gemma); it carries an explicit [olla harness: ...] label instead"
  - "Args spans open from the first tool envelope onward, not only at envelope-preceded openers, so test_final_inside_additional_args_block_is_not_an_outer_answer still holds (new spans are a strict subset of old ones)"
  - "The reasoning fallback fires only when content is whitespace-only and the reasoning alone parses to a non-none action; reasoning-sourced tool calls still go through the safety check and confirm gate"
requirements-completed: [QUICK-260924-mml]
duration: 10min
completed: 2026-09-24
status: complete
---

# Quick Task 260924-mml: Reasoning-Merge Parse Loop Fix

**Reasoning text no longer reaches the parser or chat history. The retry nudge no longer looks like the user. A quoted `<args>` in prose no longer masks the real tags after it.**

## Bug

This was reported on the REPL against an OpenRouter reasoning model. `pwd` ran, and then every turn got "No <tool> or <final> tag found" while the model kept replying "the user keeps saying…". The loop ended with a garbage answer that started with `* tag found. Respond using …`.

## Root causes and fixes

| # | Cause | Fix | File |
|---|-------|-----|------|
| A | `_stream_model_turn` appended thought chunks to the parsed content (present since 7b5c413). When the reasoning mentioned `<final>` in prose, the parser saw more than one outer final and returned `none`, which caused the loop. The reasoning was also stored in history, which wastes tokens. | Only non-thought chunks go into the content. Thought text is collected separately and still printed dimmed. | loop.py |
| B | The retry nudge was a plain `role: "user"` message containing literal `<tool>/<args>`, so the model argued with "the user" and quoted the tags back. | The nudge now reads `[olla harness: automated format check, not a message from the user] …` and contains no protocol tags. | loop.py |
| C | Any `<args>` opened a payload span, and because `</args>` is the stop sequence it ran to the end of the content. The quoted `<args>` therefore masked the real `<final>/home/nacs</final>`, and a prose `<final>` became the answer. | Spans now open only from the first `<tool>NAME[</tool>]<args>` envelope onward. | parser.py |
| D | When a reasoning model puts everything in the reasoning channel, the content is empty. | If the content is whitespace-only and the reasoning alone parses to a non-`none` action, the reasoning is used as the content and a `debug_log` line is written. | loop.py |

## Commits

- `e8bd2ab`: fix(quick-260924-mml): anchor args payload spans to tool envelope
- `a319f87`: fix(quick-260924-mml): keep reasoning out of parsed content; label retry nudge

## Deviations

- **Fix C scope narrowed (Rule 1).** Under the planned rule (an `<args>` opens a span only when an envelope directly precedes it), `test_final_inside_additional_args_block_is_not_an_outer_answer` failed. Spans now start at the first tool envelope, and every `<args>` after it still opens a span, as before. Only `<args>` openers that come before any real tool call behave differently, which is exactly the bug.
- `test_stream_model_turn_dimmed_thinking` was updated to expect `"<final>Hello world</final>"`. The old assertion locked in the merge bug.
- The executor stopped before committing because GSD's protected-branch check fired on `main`. The user chose to commit on main, matching the repo history, and the orchestrator made both commits. The orchestrator also fixed a whitespace glitch (`OUTER_FENCE_OPEN_RE =re.compile`).

## Verification

- `.venv/bin/python -m pytest -q`: 484 passed
- `.venv/bin/ruff check src tests`: all checks passed
- The new end-to-end test `test_run_loop_reasoning_mentioning_final_tag_does_not_loop` reproduced the loop before the fix. After the fix it answers `/home/nacs` in one model call.
- It has not been re-run live against OpenRouter yet. That is recommended: `OLLA_DEBUG=1 olla` with the same model and a `pwd` prompt.
