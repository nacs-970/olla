---
phase: 06-lightweight-web-search-fetch
plan: 02
subsystem: tools
tags: [httpx, html-parser, react-loop, prompt-injection, tool-calling, duckduckgo]

requires:
  - phase: 06-lightweight-web-search-fetch
    plan: 01
    provides: "_read_capped shared byte-cap helper, _record_web_observation untrusted-tagging path, _truncate_to_sentence, _HEADERS/_TIMEOUT constants — all reused directly by search_web"
provides:
  - "search_web(query) tool: DuckDuckGo Lite HTML parsing (sponsored-row exclusion, uddg redirect decode, bot-challenge detection) via a shared byte-capped streaming read"
  - "Full run_loop() wiring for search_web: unconfirmed dispatch, dry-run preview, untrusted-tagged observation recording"
  - "9-tool system prompt roster (final tool-roster state for phase 06)"
affects: []

actuals:
  tokens: 5216
  tasks: 2
  commits: 2
plan_head_before: ff9ef8877c320f8fc532f4dda9603e8be241c84c

tech-stack:
  added: []
  patterns:
    - "_DDGResultParser (HTMLParser subclass) discriminates sponsored vs organic results on the <tr> class, never the anchor class, using a depth counter identical in shape to _TextExtractor's drop-tag counter"
    - "search_web reuses the exact _read_capped/_truncate_to_sentence/_record_web_observation chokepoints established by fetch_url in plan 06-01 — no new shared helper needed"

key-files:
  created: []
  modified:
    - src/olla/tools/web.py
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_tools/test_web.py
    - tests/test_loop.py
    - tests/test_prompts.py

key-decisions:
  - "Bot-challenge detection uses the literal substring \"anomaly-modal\", not the bare word \"anomaly\" — avoids false-positiving on a genuine zero-result page whose echoed query text happens to discuss that topic"
  - "search_web's HTTP call routes through the same _read_capped streaming helper as fetch_url (never a plain buffering client.get()), so both web tools respect the same 5MB byte ceiling on the same RAM-constrained host (T-06-04)"
  - "Discriminator for sponsored-row exclusion is the <tr class=\"result-sponsored\"> ancestor, tracked via a depth counter — never the anchor's class=\"result-link\", which both sponsored and organic anchors share"

patterns-established: []

requirements-completed: [WEB-01, WEB-03, WEB-04]

coverage:
  - id: D1
    description: "search_web(query) queries DuckDuckGo Lite, excludes sponsored rows (discriminated on <tr> class), and decodes the uddg= redirect to the real target URL for every returned card"
    requirement: "WEB-01"
    verification:
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_excludes_sponsored_rows_and_decodes_uddg"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_discriminator_is_tr_class_not_anchor_class"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_sends_browser_user_agent_and_follows_redirects"
        status: pass
    human_judgment: false
  - id: D2
    description: "A bot-challenge response and a genuine zero-result response are distinguishable: the former is {\"error\": ...}, the latter is {\"content\": \"no results found\"}"
    requirement: "WEB-01"
    verification:
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_bot_challenge_returns_error"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_genuine_zero_results_returns_content_message"
        status: pass
    human_judgment: false
  - id: D3
    description: "search_web's output is capped via the shared _truncate_to_sentence, and empty-query input never makes an HTTP call"
    requirement: "WEB-03"
    verification:
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_truncates_long_formatted_output"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_empty_returns_error_without_http_call"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_whitespace_only_returns_error_without_http_call"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_timeout_returns_error"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_transport_error_returns_error"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_stream_timeout_returns_error"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_search_web_stream_transport_error_returns_error"
        status: pass
    human_judgment: false
  - id: D4
    description: "A successful search_web observation is wrapped in <untrusted_web_content> and forces re-confirmation on the next CONFIRM-tier shell/write_file action even under --yes; an error does not; dry-run shows a search preview instead of falling through to the unknown-tool branch"
    requirement: "WEB-04"
    verification:
      - kind: integration
        ref: "tests/test_loop.py::test_search_web_wraps_untrusted_content_and_forces_reconfirmation"
        status: pass
      - kind: integration
        ref: "tests/test_loop.py::test_search_web_error_does_not_force_reconfirmation"
        status: pass
      - kind: integration
        ref: "tests/test_loop.py::test_search_web_dry_run_shows_search_preview"
        status: pass
      - kind: unit
        ref: "tests/test_prompts.py::test_system_prompt_advertises_tool_roster"
        status: pass
      - kind: unit
        ref: "tests/test_prompts.py::test_system_prompt_teaches_search_web_format"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-09
status: complete
---

# Phase 06 Plan 02: search_web end-to-end Summary

**`search_web(query)` delivered end-to-end: DuckDuckGo Lite HTML parsing with sponsored-row exclusion and uddg-redirect decoding, wired into `run_loop()` with unconfirmed dispatch and untrusted-tagged observation recording, plus the phase's final system-prompt roster bump to "9 tools available".**

## Performance

- **Duration:** ~6min
- **Started:** 2026-09-09T01:51:23+07:00 (prior commit)
- **Completed:** 2026-09-09T01:57:21+07:00
- **Tasks:** 2/2 completed
- **Files modified:** 6 (0 created, 6 modified)

## Accomplishments

- `src/olla/tools/web.py`: added `_DDG_URL`, `_DDG_BOT_CHALLENGE_MARKER` ("anomaly-modal"), `_DDG_NO_RESULTS_CONTENT`, `_DDG_BOT_CHALLENGE_ERROR`, `_DDG_MAX_RESULTS` constants; `_DDGResultParser` (an `HTMLParser` subclass tracking `_sponsored_depth` per `<tr class="result-sponsored">`, gating `<a class="result-link">`/`<td class="result-snippet">` collection on that depth); `_decode_ddg_href` (recovers the real URL from the `uddg=` query param via `parse_qs(urlsplit(href).query)`, falling back to the raw href); `_format_ddg_cards` (numbered 3-line cards, capped at 5); `search_web(query)` itself, routing through the shared `_read_capped`/`_truncate_to_sentence` chokepoints built in plan 06-01.
- `run_loop()` fully wired: `_prepare_action`/`_preview_action` branches for `search_web`, a new `_execute_search_web` mirroring `_execute_fetch_url` exactly (unconfirmed dispatch, no `safety.check()` call), and a `run_loop()` dispatch branch.
- `prompts.py` documents the `search_web` `<tool>`/`<args>` contract and bumps the tool-roster line from "7 tools available" to "9 tools available", adding `search_web`/`fetch_url` to the backtick set — the only place in the phase this line changes.
- End-to-end tracer test proves a successful `search_web` call forces re-confirmation on a subsequent `shell` call even under `--yes=True`; companion tests prove a bot-challenge error path does neither, and dry-run shows a "Step 1 would search:" preview.
- Edge-case hardening: `httpx.Client` constructor and `httpx.Client.stream` timeout/transport-error paths both tested, discriminator-is-`<tr>`-class-not-anchor-class test, sentence-boundary truncation of an oversized snippet field.
- Full `pytest` suite: 431 passed, 0 regressions (baseline was 426 after Task 1, 415 before this plan).

## Task Commits

Each task was committed atomically:

1. **Task 1: search_web end-to-end — DDG Lite parser, full loop.py wiring, prompt doc** - `e2ee7e2` (feat)
2. **Task 2: search_web edge-case hardening + phase-final prompt roster bump** - `4130f27` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP/REQUIREMENTS update)

_Note: both tasks carried `tdd="true"`; `workflow.tdd_mode` is `false` in this project's config, so the strict RED/GREEN/REFACTOR gate enforcement does not apply. Tests and implementation were authored together and verified green before each commit, matching this project's existing single-commit-per-task convention._

## Files Created/Modified
- `src/olla/tools/web.py` - `_DDG_URL`/`_DDG_BOT_CHALLENGE_MARKER`/`_DDG_NO_RESULTS_CONTENT`/`_DDG_BOT_CHALLENGE_ERROR`/`_DDG_MAX_RESULTS` constants; `_DDGResultParser`; `_decode_ddg_href`; `_format_ddg_cards`; `search_web`
- `src/olla/loop.py` - `search_web` import; `_prepare_action`/`_preview_action` branches; `_execute_search_web`; `run_loop()` dispatch branch
- `src/olla/prompts.py` - new `search_web` doc block after `fetch_url`; roster line bumped to "9 tools available"
- `tests/test_tools/test_web.py` - DDG-Lite-shaped fixtures (sponsored + organic rows, anchor-class-only decoy, no-match, bot-challenge, long-snippet); unit tests for empty/whitespace input, sponsored exclusion, uddg decode, discriminator correctness, zero-results vs bot-challenge, User-Agent, timeout/transport errors (both constructor- and stream-level), truncation
- `tests/test_loop.py` - end-to-end untrusted-tagging test, error-path counterpart, dry-run preview test
- `tests/test_prompts.py` - `test_system_prompt_advertises_tool_roster` updated to the 9-tool set; new `test_system_prompt_teaches_search_web_format`

## Decisions Made

- Bot-challenge detection checks for the literal substring `"anomaly-modal"`, not the bare word `"anomaly"` — the plan explicitly called out that a bare-word check would false-positive on a genuine zero-result page whose echoed query text discusses that topic.
- `search_web`'s HTTP call goes through the exact same `_read_capped` byte-capped streaming helper as `fetch_url`, never a plain buffering `client.get()`/`.get()` call — both tools share the same RAM-constrained host (T-06-04), so neither bypasses the byte ceiling.
- The sponsored/organic discriminator is the `<tr class="result-sponsored">` ancestor (tracked via a depth counter mirroring `_TextExtractor`'s drop-tag counter shape), never the anchor's `class="result-link"` — verified by a dedicated test using an anchor with a decoy `sponsored`-lookalike attribute that a naive anchor-class filter would wrongly exclude.

## Deviations from Plan

None — plan executed exactly as written. Two of the Task 2-specified edge-case tests (long-snippet truncation, and the `httpx.Client`-constructor-level timeout/transport-error tests) were written alongside Task 1's initial test batch rather than strictly deferred to Task 2's commit; Task 2 then added the additional `httpx.Client.stream`-level mocks the plan specifically called for (mocking the actual streaming entry point `_read_capped` calls, not just the `Client()` constructor) plus the dry-run/error-path loop tests and the roster bump. This is a minor test-authoring-order deviation with no functional impact — all required coverage exists and both tasks' commits are internally coherent and independently green.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 06 (Lightweight Web Search & Fetch) is complete: both `fetch_url` (plan 06-01) and `search_web` (this plan) are fully wired, tested, and documented in the system prompt with the correct 9-tool roster.
- Full test suite is green (431 passed) with no regressions.
- No further plans are scoped for phase 06.

---
*Phase: 06-lightweight-web-search-fetch*
*Completed: 2026-09-09*

## Self-Check: PASSED

All modified files and both task commits verified present on disk / in git log.
