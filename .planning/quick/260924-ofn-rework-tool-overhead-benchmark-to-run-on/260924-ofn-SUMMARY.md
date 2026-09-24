---
phase: quick-260924-ofn
plan: 01
subsystem: benchmark
tags: [benchmark, openrouter, token-overhead, tooling]
status: complete
requires: [olla.prompts.SYSTEM_PROMPT, olla.providers.get_provider]
provides: [scripts/benchmark_tool_overhead.py (OpenRouter two-arm), tests/test_benchmark_script.py]
affects: []
tech-stack:
  added: []
  patterns: [derived native prompt via line-level filter, ABBA scheduling, None-aware stats, per-call JSON checkpointing]
key-files:
  created: [tests/test_benchmark_script.py]
  modified: [scripts/benchmark_tool_overhead.py]
decisions:
  - "Native system prompt is derived from SYSTEM_PROMPT by derive_native_prompt (not hand-typed); per-tool behaviour sentences live in the tool-schema descriptions"
  - "require_parameters is sent on the native arm only; the xml arm keeps the production stop sequence and no provider field"
  - "--print-prompts counts the compact tools JSON (as sent on the wire), not the indented display"
metrics:
  duration: 4m
  completed: 2026-09-24
actuals:
  tokens: 10659
  tasks: 2
  commits: 1
plan_head_before: 857e50794d3f3abea1d3f609ca538565ffb1bb00
requirements: [QUICK-260924-ofn]
---

# Phase quick-260924-ofn Plan 01: OpenRouter tool-overhead benchmark Summary

XML-tag vs JSON-function-calling prompt-overhead benchmark on one OpenRouter model: non-streaming, two arms that carry the same policy text (the native prompt is derived by a documented filter), ABBA ordering, None-aware stats, per-call error capture and JSON checkpointing, and 27 offline tests.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Rewrite benchmark for OpenRouter + no-network tests | bbb6116 | scripts/benchmark_tool_overhead.py, tests/test_benchmark_script.py |
| 2 | Full-suite verification + by-eye `--print-prompts` audit | (no commit; no defect found) | none |

## Review findings addressed

- #1: All Ollama code removed (client import, CACHE_CHECK_*, run_cache_check, CHAT_OPTIONS, XML_TRIMMED_SYSTEM_PROMPT, three-arm rotation). `cached_tokens` is recorded separately.
- #2: `post_with_retry` retries 429 and 5xx with delays (2, 4, 8). Other statuses are not retried. Exceptions become records with the error set. The output JSON is rewritten after every call, and each call is also wrapped in its own try/except.
- #3: A missing count stays None. `mean_excluding_none` and `sum_excluding_none` return the excluded count, and the report prints it.
- #4, #5, #8: `NATIVE_SYSTEM_PROMPT = derive_native_prompt(SYSTEM_PROMPT)`. The relocated behaviour sentences appear in the schemas only.
- #6: Completion tokens are reported separately, with the stop caveat.
- #7: Neither arm sends temperature.
- #9: The output parent directory is validated before `get_provider` or any call. `cached_tokens` is in the JSON.
- #10: `build_schedule` uses task-major ABBA (k = task_idx * repeats + repeat).

## Task 2 audit

- Full suite: **524 passed** (497 baseline + 27 new). `ruff check src tests scripts`: **All checks passed!**
- `--print-prompts` ran with `OPENROUTER_API_KEY` unset. No network call, and no key needed.
- The native prompt has **15 non-blank lines**, which match the spec in order. Lines 1-14 are verbatim from SYSTEM_PROMPT, and line 15 is the appended "reply with plain text" line.
- No tag fragment, Example line, Observation-prefixed line, or dangling continuation line ("file content goes here", "value on all remaining lines:", "mode=fast") remains.
- The filter drops these policy-looking SYSTEM_PROMPT lines as tag-format guidance. This matches the 15-line spec:
  - "Never include a literal </args> sequence inside file content or a remembered value — it will cut off your output early." (TAG_RE)
  - "Only output one tag block per turn. Do not explain your reasoning outside the tags." ("tag block" marker)
  - "When you have the final answer for the user, respond with:" + "<final>your answer text here</final>" (marker + TAG_RE). NATIVE_FINAL_LINE replaces these.
  - The "Tags are written exactly..." / "No `=`..." / "`<tool=name</tool>`..." block (TAG_RE)
- The tools JSON has 9 functions. Their descriptions match the plan word for word. `recursive` is a boolean, and `grep_files` requires [pattern, path].
- Character counts (characters, not tokens):
  - xml arm: system = 4225
  - native arm: system = 1251, tools JSON (compact) = 2641, sum = 3892
  - With indented tools JSON, the native figures would be tools = 4039 and sum = 5290.
- `git diff HEAD~1 --stat` shows only the two Task 1 files. `git status --porcelain src/olla` is empty.
- No live OpenRouter run was made.

## Deviations from Plan

**1. [Rule 1 - Accuracy] `--print-prompts` counts the compact tools JSON**
- **Found during:** Task 1 (by-eye review of the output)
- **Issue:** The plan's flow prints `json.dumps(NATIVE_TOOLS, indent=2)` and then "tools-JSON chars". Counting the indented display adds about 1400 characters of whitespace that are never sent (httpx serializes `json=` compactly).
- **Fix:** The tools count now uses `len(json.dumps(NATIVE_TOOLS))` and is labelled "tools JSON (compact)". The indented display is unchanged. Indented: tools = 4039, sum = 5290. Compact: tools = 2641, sum = 3892. To revert, change `tools_chars` back to the indented length.
- **Files modified:** scripts/benchmark_tool_overhead.py
- **Commit:** bbb6116

**2. Additions beyond the spec (no behaviour conflict)**
- A `sum_excluding_none` helper for the None-aware cached and reasoning totals.
- `build_headers(api_key)` and `summarize()` / `print_report()` split out of `main`.
- On a 200 response with a top-level `error`, the parsed data is still returned alongside the error, so any usage present is kept.

## Skipped per orchestrator constraints

- No docs commit, no ROADMAP update, and no requirements mark-complete. Per the orchestrator's instructions, these artifacts are not committed.

## Known Stubs

None.

## Threat Flags

None. The only new surface is the outbound OpenRouter POST and the `--output` file, both covered by T-ofn-01..04. The end-to-end test asserts that the key string is absent from the JSON and the CLI output.

## Self-Check: PASSED

- FOUND: scripts/benchmark_tool_overhead.py
- FOUND: tests/test_benchmark_script.py
- FOUND: commit bbb6116
