---
phase: 07-interactive-repl-mode
plan: 03
subsystem: cli
tags: [repl, tiktoken, context-trim, prompt-injection-mitigation, react-loop]

# Dependency graph
requires:
  - phase: 07-interactive-repl-mode
    provides: "07-01's SessionState-injectable run_loop() and turn_start_index capture; 07-02's full REPL UX these turns run inside"
provides:
  - "src/olla/context_trim.py — tiktoken-based token counting with a graceful char-count fallback, a proactive trim decision, and an untrusted-tagged summarization digest (REPL-03)"
  - "A single trim-check chokepoint inside _stream_model_turn() covering every REPL-turn model call: the step-loop call, the dry_run branch call, and the legacy call_model() path"
  - "turn_start_index recomputed from the real session.messages length delta after every step-loop call, so a second trim later in the same turn slices against the correctly-shrunk boundary, not a stale one"
  - "repl.py warms the tiktoken encoder once at startup with a visible message"
affects: []

# Actuals (#2632)
actuals:
  tokens: 6258
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single chokepoint inside _stream_model_turn() (not at three separate call sites) — provider.get_context_length() and context_trim.should_trim()/summarize_and_trim() run once, before every model call this function makes, regardless of which of the three call paths reaches it"
    - "Length-delta recompute (turn_start_index -= _len_before - len(session.messages)) around the step-loop call site, so a mutable local boundary stays valid across multiple trims within one run_loop() call without needing a mutable session-state field"

key-files:
  created:
    - src/olla/context_trim.py
    - tests/test_context_trim.py
  modified:
    - src/olla/loop.py
    - src/olla/repl.py
    - tests/test_loop.py
    - tests/test_repl.py
    - tests/test_debug.py

key-decisions:
  - "summarize_and_trim()'s no-op guard checks slice emptiness directly (`if not messages[1:protected_from_index]: return`) rather than comparing protected_from_index to a threshold — this covers both 'nothing eligible' cases (protected_from_index<=1 for the one-shot path, and an oversized in-progress turn with no prior history) with one guard, and avoids a subtle bug where messages[1:1] = [digest] would silently *insert* rather than no-op (an empty-slice assignment grows the list) had the guard been index-based instead of emptiness-based."
  - "Three pre-existing tests (not just the two the plan named in tests/test_loop.py) needed a real get_context_length() return value added to their Mock/MagicMock providers — tests/test_debug.py::test_run_loop_logs_in_debug_mode hit the identical TypeError (`'>=' not supported between instances of 'int' and 'MagicMock'`) and was fixed the same way, tracked as a deviation since it falls outside this plan's declared files_modified list."

requirements-completed: [REPL-03]

coverage:
  - id: D1
    description: "count_tokens_or_fallback() counts real tiktoken tokens when the encoder loads, and falls back to a char-count proxy (printing one warning) when tiktoken.get_encoding() raises requests.exceptions.RequestException — the failure is cached so it is not retried per call"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_context_trim.py#test_count_tokens_or_fallback_uses_real_encoder"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_count_tokens_or_fallback_falls_back_to_char_proxy_on_request_exception"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_get_encoder_caches_failure_and_does_not_retry"
        status: pass
    human_judgment: false
  - id: D2
    description: "should_trim() returns True only once history is at or beyond threshold_ratio of provider.get_context_length()'s budget, and False for empty history"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_context_trim.py#test_should_trim_true_at_or_above_threshold"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_should_trim_false_below_threshold"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_should_trim_false_for_empty_messages"
        status: pass
    human_judgment: false
  - id: D3
    description: "summarize_and_trim() replaces the trimmable middle slice with one digest message always wrapped in <untrusted_summary_digest>, leaving the system prompt and the in-progress-turn tail byte-for-byte unchanged; falls back to a placeholder digest (not a raise, not a silent skip) when the summarization provider.chat() call itself fails"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_context_trim.py#test_summarize_and_trim_replaces_middle_slice_and_protects_head_and_tail"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_summarize_and_trim_provider_failure_falls_back_to_placeholder_digest"
        status: pass
      - kind: unit
        ref: "tests/test_context_trim.py#test_summarize_and_trim_noop_when_in_progress_turn_is_entire_trimmable_range"
        status: pass
    human_judgment: false
  - id: D4
    description: "The trim-check chokepoint inside _stream_model_turn() fires before the model call, driven through the real run_loop() step loop (not only context_trim's own unit tests), and never includes the system prompt in the summarized slice"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_trim_check_fires_before_model_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "turn_start_index is recomputed from the session.messages length delta after every step-loop call, so a second trim later in the same turn slices against the correctly-shrunk boundary rather than a stale one that could clip into the in-progress turn — proven with two real trim events in one run_loop() call"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_trim_check_protects_in_progress_turn_across_multiple_trims"
        status: pass
    human_judgment: false
  - id: D6
    description: "The one-shot CLI path (run_loop(session=None)) still runs the chokepoint unconditionally, but protected_from_index=1 makes the summarized slice empty, so there is no observable behavior change vs. pre-phase one-shot mode"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop.py#test_run_loop_one_shot_trim_check_is_effectively_a_noop"
        status: pass
    human_judgment: false
  - id: D7
    description: "repl.py's main_loop() warms the tiktoken encoder once at startup, before the first prompt, printing a visible message"
    requirement: "REPL-03"
    verification:
      - kind: unit
        ref: "tests/test_repl.py#test_main_loop_warms_encoder_at_startup"
        status: pass
      - kind: manual_procedural
        ref: "uv run olla --model qwen2.5:3b < /dev/null — printed 'preparing token counter...' exactly once before the REPL exited on EOF"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-09-15
status: complete
---

# Phase 7 Plan 3: Rolling Context Trim (REPL-03) Summary

**New `src/olla/context_trim.py` adds `tiktoken`-based proactive rolling-context trimming — sourced from the previously-dead-code `provider.get_context_length()` — wired into a single chokepoint inside `_stream_model_turn()`, with dropped turns replaced by an LLM-generated digest that is always wrapped in `<untrusted_summary_digest>` so summarized content never re-enters context as unmarked trusted text.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-14T17:04Z (approx, base commit before this plan's first task)
- **Completed:** 2026-09-14T17:19:53Z
- **Tasks:** 3
- **Files modified:** 7 (`src/olla/context_trim.py` [new], `tests/test_context_trim.py` [new], `src/olla/loop.py`, `src/olla/repl.py`, `tests/test_loop.py`, `tests/test_repl.py`, `tests/test_debug.py`)

## Accomplishments
- `src/olla/context_trim.py` — `get_encoder()`/`count_tokens_or_fallback()` count history tokens against a cached `tiktoken` encoder, falling back to a char-count proxy (and printing one warning line) when the encoder's first-use network fetch raises `requests.exceptions.RequestException`, with the failure cached so it isn't retried per call (Pitfall 1/2 mitigation)
- `should_trim()` compares history size against `provider.get_context_length()` — the already-implemented, previously-unused per-provider budget source — at an 85% threshold ratio, never a second hardcoded `num_ctx` constant
- `summarize_and_trim()` replaces the trimmable middle slice with one digest message, always wrapped in `<untrusted_summary_digest>`, protecting the system prompt and the current in-progress turn byte-for-byte; falls back to a placeholder digest (not a crash, not a silent skip) when the summarization `provider.chat()` call itself fails (T-07-02 mitigation, the plan's single highest-severity risk item)
- `_stream_model_turn()` gained a `protected_from_index` parameter and now runs the trim-check unconditionally at its top — the single chokepoint covering the step-loop call, the `dry_run` branch call, and the legacy `call_model()`/`_call_model_for_loop()` path (only ever reached from inside this same function)
- `run_loop()`'s step-loop call site recomputes `turn_start_index` from the real `session.messages` length delta immediately after every `_stream_model_turn()` call, so a second trim later in the same turn slices against the correctly-shrunk boundary rather than a stale (too-large) one that could clip into the in-progress turn — proven with two real trim events driven through the actual step loop, not just a single-trim smoke test
- `repl.py`'s `main_loop()` warms the `tiktoken` encoder once at startup (before the input loop), printing "preparing token counter..." so the ~3.5s cold-fetch cost is explained rather than landing unexplained mid-conversation

## Task Commits

Each task was committed atomically:

1. **Task 1: context_trim.py — tiktoken counting, trim decision, summarization + untrusted-tagged digest** — TDD cycle:
   - RED: `676b084` (test) — `pytest tests/test_context_trim.py -x` fails at collection (`olla.context_trim` doesn't exist)
   - GREEN: `8cba811` (feat) — `pytest tests/test_context_trim.py -x` passes (13 passed); full suite 461 passed
   - REFACTOR: none needed — `ruff check` was already clean after GREEN
2. **Task 2: Wire the trim-check chokepoint into _stream_model_turn() and warm the encoder at REPL startup** — `344ba5d` (feat)
3. **Task 3: Extend tests/test_loop.py — trim-check fires inside the real step loop, protects in-progress turn** — `12286fa` (test)

**Plan metadata:** (this commit, once written)

## Files Created/Modified
- `src/olla/context_trim.py` (new) - `DEFAULT_ENCODING`/`TRIM_THRESHOLD_RATIO`/`FALLBACK_CHARS_PER_TOKEN`/`SUMMARY_PROMPT` constants; `get_encoder()`, `count_tokens_or_fallback()`, `should_trim()`, `summarize_and_trim()`, `warm_encoder()`
- `tests/test_context_trim.py` (new) - 13 tests covering every behavior in the plan's `<behavior>` spec
- `src/olla/loop.py` - `_stream_model_turn(..., protected_from_index=1)` runs the trim-check chokepoint before every model call; both `run_loop()` call sites pass `protected_from_index=turn_start_index`; the step-loop call site recomputes `turn_start_index` from the length delta after every call
- `src/olla/repl.py` - `main_loop()` calls `context_trim.warm_encoder()` once at startup, before the input loop
- `tests/test_loop.py` - `import itertools`, `from olla import context_trim`; 3 new tests (`test_run_loop_trim_check_fires_before_model_call`, `test_run_loop_trim_check_protects_in_progress_turn_across_multiple_trims`, `test_run_loop_one_shot_trim_check_is_effectively_a_noop`); `get_context_length.return_value = 8192` added to two pre-existing MagicMock providers
- `tests/test_repl.py` - `test_main_loop_warms_encoder_at_startup`
- `tests/test_debug.py` - `get_context_length.return_value = 8192` added to `test_run_loop_logs_in_debug_mode`'s MagicMock provider (deviation, see below)

## Decisions Made
- `summarize_and_trim()`'s no-op guard checks slice emptiness (`if not messages[1:protected_from_index]: return`) rather than an index comparison against `protected_from_index` — a cleaner single guard that also sidesteps a subtle bug: `messages[1:1] = [digest]` is a slice *insert*, not a no-op, so an index-based guard that missed the `protected_from_index<=1` case would have silently grown the message list by one on every one-shot-path trim check.
- Kept the unused `model` parameter on `summarize_and_trim(messages, protected_from_index, provider, model)` exactly as the plan's signature specifies (`provider.chat()` doesn't take a `model` argument since the provider is already bound to a model) — no lint violation since `ruff`'s default rule set doesn't flag unused function arguments.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] A third pre-existing test (outside the plan's declared files) needed the same MagicMock provider fix**
- **Found during:** Task 2 (Wire the trim-check chokepoint), full-suite regression pass
- **Issue:** The plan's `<action>` named `tests/test_loop.py` as the file to grep for unconfigured `Mock`/`MagicMock` providers. Running the *full* `pytest` suite (not just `tests/test_loop.py`) surfaced an identical failure in `tests/test_debug.py::test_run_loop_logs_in_debug_mode`, whose `MagicMock()` provider also lacked a `get_context_length` return value — `should_trim()`'s `count >= budget * threshold_ratio` compared an `int` to a `MagicMock`, raising `TypeError`.
- **Fix:** Added `mock_provider.get_context_length.return_value = 8192` to `tests/test_debug.py`'s fixture, identical to the two fixes already applied in `tests/test_loop.py`.
- **Files modified:** `tests/test_debug.py`
- **Verification:** Full suite `pytest -q` — 462 passed (post-Task-2), no regressions.
- **Committed in:** `344ba5d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to keep the full pre-existing suite green after adding the chokepoint; the plan's own `<verify>` for Task 2 only names `tests/test_loop.py` and `tests/test_repl.py -k warm`, but the full suite is also run per the plan-level `<verification>` block, which is where this surfaced. No scope creep — the fix is mechanically identical to the two the plan explicitly anticipated.

## TDD Gate Compliance

`workflow.tdd_mode` is `false` in `.planning/config.json`, so the mechanical `gsd_run check tdd-red-evidence` gate was not invoked. RED/GREEN discipline was followed manually for Task 1 (the only `tdd="true"` task in this plan):
- **RED** (`676b084`, `test(07-03): ...`): `tests/test_context_trim.py` committed before `src/olla/context_trim.py` existed. `pytest tests/test_context_trim.py -x` failed at collection (`ImportError: cannot import name 'context_trim' from 'olla'`) — a genuine RED caused by the new module not existing yet, not a fixture crash or unrelated failure.
- **GREEN** (`8cba811`, `feat(07-03): ...`): implemented `context_trim.py` per the behavior spec. Same test file now passes (13 passed); full suite 461 passed, no regressions vs. the 448-test pre-plan baseline.
- **REFACTOR**: not needed — `ruff check src/olla/context_trim.py tests/test_context_trim.py` was already clean after GREEN.

Tasks 2 and 3 are `type="auto"` (no `tdd="true"`), executed directly per their `<action>`/`<acceptance_criteria>` with the standard commit-per-task discipline.

## Issues Encountered
None beyond the one auto-fixed deviation documented above.

## User Setup Required
None - no external service configuration required. No new dependencies were added this plan (`prompt_toolkit`/`tiktoken` were already added and vetted in 07-01).

## Next Phase Readiness
- REPL-01, REPL-02, and REPL-03 are all fully delivered — Phase 7 (Interactive REPL Mode) is complete.
- One documented note (not a blocker, per advisor review): `run_loop()` re-resolves the provider fresh on every turn (07-01's design), so `OpenAICompatProvider._context_length` is cold each turn — the new `get_context_length()` call adds one `/models` HTTP fetch (5s timeout) per turn on the remote OpenAI-compatible path. This is expected given 07-01's per-turn provider-resolution design (caching the provider across turns would be a separate architectural change, out of scope here) and does not affect the local Ollama path (`OllamaProvider.get_context_length()` is a pure in-memory return, no network call).
- No blockers. Manual smoke test (`uv run olla --model qwen2.5:3b < /dev/null`) confirms "preparing token counter..." prints exactly once at startup before the REPL exits cleanly on EOF, with no live Ollama server required (provider construction and encoder warming are both network-independent for the local path; `tiktoken`'s own BPE-file cache was already warm on this host from an earlier session).

---
*Phase: 07-interactive-repl-mode*
*Completed: 2026-09-15*

## Self-Check: PASSED

All key files present on disk (`src/olla/context_trim.py`, `tests/test_context_trim.py`, `src/olla/loop.py`, `src/olla/repl.py`, this SUMMARY.md). All four commit hashes (`676b084`, `8cba811`, `344ba5d`, `12286fa`) found in `git log --oneline --all`. Task-level `<acceptance_criteria>` re-verified: `pytest tests/test_context_trim.py -x` (13 passed), `pytest tests/test_loop.py -x && pytest tests/test_repl.py -k warm -x` (146 passed + 1 passed), `pytest tests/test_loop.py -k "trim_check" -x` (3 passed). Plan-level `<verification>` re-run: `pytest tests/test_context_trim.py tests/test_loop.py -x` (162 passed) and full suite `pytest -q` (465 passed, no regressions vs. the 448-test pre-plan baseline); manual smoke test (`uv run olla --model qwen2.5:3b < /dev/null`) printed "preparing token counter..." exactly once before exiting cleanly (code 0) on EOF.
