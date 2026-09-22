---
phase: 06-lightweight-web-search-fetch
plan: 01
subsystem: tools
tags: [httpx, html-parser, react-loop, prompt-injection, tool-calling]

requires:
  - phase: 05-safe-inspection-tools
    provides: unprompted-dispatch precedent (list_dir/grep_files bypass safety.check() entirely, D-09) reused verbatim for fetch_url
provides:
  - "fetch_url(url) tool: byte-capped streaming HTTP fetch + boilerplate-stripping text extraction + sentence-boundary truncation"
  - "_read_capped shared byte-cap helper reusable by plan 06-02's search_web"
  - "_record_web_observation untrusted-tagging path reusable by plan 06-02's search_web"
affects: [06-02-search-web]

actuals:
  tokens: 4328
  tasks: 2
  commits: 2
plan_head_before: b5e2ad62c154b052e3d6c707b20c1eb54c7955b2

tech-stack:
  added: []
  patterns:
    - "Shared byte-capped streaming read (_read_capped) as the single chokepoint both fetch_url and the upcoming search_web must use"
    - "Untrusted-tagged observation recording (_record_web_observation) mirroring the existing _record_shell_observation/_record_file_observation shape"

key-files:
  created:
    - src/olla/tools/web.py
    - tests/test_tools/test_web.py
  modified:
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_loop.py
    - tests/test_prompts.py

key-decisions:
  - "_truncate_to_sentence operates on Python str code points (len()), never UTF-8 byte length, per WEB-02/WEB-03 encoding-edge requirement"
  - "fetch_url's success path records via _record_web_observation only — never through _record_observation/_record_file_observation/truncate_output, since fetch_url's content is already capped at 3,000 chars and re-truncating at MAX_OBSERVATION_CHARS (2,000) would silently shrink it"
  - "_DROP_TAGS intentionally limited to script/style/nav/header/footer; aside/form/iframe/svg/noscript are never added (D-03) — proven by a test asserting aside content survives extraction"

patterns-established:
  - "New unprompted tools dispatch straight from run_loop with no safety.check() call, following the list_dir/grep_files/D-09 precedent"

requirements-completed: [WEB-02, WEB-03, WEB-04]

coverage:
  - id: D1
    description: "fetch_url(url) fetches a webpage via a byte-capped streaming httpx.Client read and returns boilerplate-stripped, sentence-truncated text"
    requirement: "WEB-02"
    verification:
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_fetch_url_small_page_returns_cleaned_content"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_text_extractor_drops_script_style_nav_header_footer"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_text_extractor_keeps_aside_content"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_fetch_url_empty_returns_error_without_http_call"
        status: pass
    human_judgment: false
  - id: D2
    description: "Output is capped at 3,000 code points (not bytes) and trimmed to a sentence boundary, with a truncation note appended when cut"
    requirement: "WEB-03"
    verification:
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_truncate_to_sentence_noop_under_limit"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_truncate_to_sentence_hard_cuts_at_limit_when_no_punctuation"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_truncate_to_sentence_counts_code_points_not_utf8_bytes"
        status: pass
      - kind: unit
        ref: "tests/test_tools/test_web.py::test_fetch_url_stops_reading_once_byte_cap_exceeded"
        status: pass
    human_judgment: false
  - id: D3
    description: "A successful fetch_url observation is wrapped in <untrusted_web_content> and forces re-confirmation on the next CONFIRM-tier shell/write_file action even under --yes; an error does not"
    requirement: "WEB-04"
    verification:
      - kind: integration
        ref: "tests/test_loop.py::test_fetch_url_wraps_untrusted_content_and_forces_reconfirmation"
        status: pass
      - kind: integration
        ref: "tests/test_loop.py::test_fetch_url_error_does_not_force_reconfirmation"
        status: pass
    human_judgment: false
  - id: D4
    description: "fetch_url dispatches with no safety.check() call, has a --dry-run preview, and the system prompt documents its unconfirmed-execution contract"
    verification:
      - kind: integration
        ref: "tests/test_loop.py::test_fetch_url_dry_run_shows_fetch_preview"
        status: pass
      - kind: unit
        ref: "tests/test_prompts.py::test_system_prompt_teaches_fetch_url_format"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-09
status: complete
---

# Phase 06 Plan 01: fetch_url end-to-end Summary

**`fetch_url(url)` delivered end-to-end: a new boilerplate-stripping, byte-capped, sentence-truncating HTTP text reader wired into `run_loop()` with unconfirmed dispatch and untrusted-tagged observation recording that revokes `--yes` on the next destructive action.**

## Performance

- **Duration:** ~15min
- **Started:** 2026-09-09T01:36:43+07:00 (prior commit)
- **Completed:** 2026-09-09T01:48:32+07:00
- **Tasks:** 2/2 completed
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `src/olla/tools/web.py` created with `_TextExtractor` (an `HTMLParser` subclass that drops `script`/`style`/`nav`/`header`/`footer` subtrees via a depth counter, keeping `aside`/`form`/`iframe`/`svg`/`noscript` content per D-03), `_truncate_to_sentence` (a 3,000-code-point sentence-boundary cap with a hard-cut fallback), a shared `_read_capped` byte-capped streaming read (5,000,000-byte ceiling, reusable by plan 06-02's `search_web`), and `fetch_url(url)` itself.
- `run_loop()` fully wired: `_prepare_action`/`_preview_action` branches, unconfirmed dispatch (no `safety.check()` call anywhere in the `fetch_url` path), a new `_record_web_observation` wrapping successful content in `<untrusted_web_content>` and setting `untrusted_observation_seen=True`, and a new `_execute_fetch_url`.
- `prompts.py` documents the `fetch_url` `<tool>`/`<args>` contract with the exact required phrase, without touching the existing 7-tool roster line or the `Example:` count assertion.
- End-to-end tracer test proves a successful `fetch_url` call forces re-confirmation on a subsequent `shell` call even under `--yes=True`; a companion negative test proves an error path does neither.
- Edge-case hardening: hard-cut-at-limit fallback, code-point-vs-byte-count truncation, byte-cap early-stop on an oversized mocked stream, `TimeoutException`/`TransportError` handling, and `--dry-run` preview — all covered by passing tests.
- Full `pytest` suite: 415 passed, 0 regressions (baseline was 397 before this plan).

## Task Commits

Each task was committed atomically:

1. **Task 1: fetch_url end-to-end — web.py adapter, full loop.py wiring, prompt doc** - `1f7cfc2` (feat)
2. **Task 2: fetch_url edge-case hardening — truncation, byte-cap, error-path, dry-run coverage** - `5ee8a33` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP/REQUIREMENTS update)

_Note: both tasks carried `tdd="true"`; `workflow.tdd_mode` is `false` in this project's config, so the strict RED/GREEN/REFACTOR gate enforcement (including `gsd_run check tdd-red-evidence`) does not apply. Tests and implementation were authored together and verified green before each commit, matching this project's existing single-commit-per-task convention (see phase 05's `feat(05): add list_dir and grep_files inspection tools`)._

## Files Created/Modified
- `src/olla/tools/web.py` - `_HEADERS`, `_TIMEOUT`, `_MAX_RESPONSE_BYTES`, `_DROP_TAGS` constants; `_TextExtractor`; `_truncate_to_sentence`; `_read_capped`; `fetch_url`
- `src/olla/loop.py` - `fetch_url` import; `_prepare_action`/`_preview_action` branches; `_record_web_observation`; `_execute_fetch_url`; `run_loop()` dispatch branch
- `src/olla/prompts.py` - new `fetch_url` doc block after the `grep_files` block
- `tests/test_tools/test_web.py` - new file: extraction, truncation, empty-url, byte-cap, timeout/transport-error, happy-path tests
- `tests/test_loop.py` - end-to-end untrusted-tagging test, error-path counterpart, dry-run preview test
- `tests/test_prompts.py` - `test_system_prompt_teaches_fetch_url_format`

## Decisions Made

- `_truncate_to_sentence` measures `len(text)` (code points), never `len(text.encode())`, so multi-byte/emoji content is capped by character count — verified by a test that would fail under a byte-based implementation.
- `fetch_url`'s success path records through `_record_web_observation` only, bypassing `truncate_output()` entirely, since `fetch_url`'s content is already capped at 3,000 chars and `MAX_OBSERVATION_CHARS` (2,000) would otherwise silently re-truncate it with a head/tail marker — this was called out explicitly by the plan's prohibition and confirmed correct by review before implementation.
- `_read_capped` is a standalone module-level function (not a method) specifically so plan 06-02's `search_web` can import and reuse it without duplicating the byte-cap logic.

## Deviations from Plan

None — plan executed exactly as written. One ruff lint fixup (`PLR1730`, replacing an `if`/assignment with `max()`) was applied during Task 1 before the first commit; this is a style-only change with no behavior impact, not a logic deviation.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `_read_capped` and `_record_web_observation`/`_truncate_to_sentence` are ready for plan 06-02's `search_web` to reuse directly, per the plan's stated dependency.
- The `fetch_url` doc block is in place; plan 06-02 will need to update the `"7 tools available"` roster line to `8` once `search_web` also exists (explicitly deferred by this plan, not done here).
- Full test suite is green (415 passed) with no regressions, ready for plan 06-02 to build on.

---
*Phase: 06-lightweight-web-search-fetch*
*Completed: 2026-09-09*

## Self-Check: PASSED

All created files and both task commits verified present on disk / in git log.
