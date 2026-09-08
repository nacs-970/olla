---
phase: 06-lightweight-web-search-fetch
verified: 2026-09-09T00:00:00Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
covered_files:
  - .planning/REQUIREMENTS.md
  - .planning/phases/06-lightweight-web-search-fetch/06-01-PLAN.md
  - .planning/phases/06-lightweight-web-search-fetch/06-01-SUMMARY.md
  - .planning/phases/06-lightweight-web-search-fetch/06-02-PLAN.md
  - .planning/phases/06-lightweight-web-search-fetch/06-02-SUMMARY.md
  - .planning/phases/06-lightweight-web-search-fetch/06-CONTEXT.md
  - .planning/phases/06-lightweight-web-search-fetch/06-REVIEW.md
  - src/olla/loop.py
  - src/olla/prompts.py
  - src/olla/tools/web.py
  - tests/test_loop.py
  - tests/test_prompts.py
  - tests/test_tools/test_web.py
covered_digest: "v1:sha256:f11c73bf165d4bc129c7891b2d2dfdbf6b01ccbe41ccd481cd34fe05f4be7df2"
---

# Phase 6: Lightweight Web Search & Fetch Verification Report

**Phase Goal:** As a user running tasks requiring online information, I want olla to query DuckDuckGo and fetch webpage text using curl/httpx, so that the model can research topics without heavy browser dependencies.
**Verified:** 2026-09-09
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria + PLAN must-haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `search_web(query)` returns top 3-5 snippet cards (title, URL, summary) parsed from DuckDuckGo Lite (SC1/WEB-01) | ✓ VERIFIED | `src/olla/tools/web.py:156-186` (`search_web`, `_DDGResultParser`, `_format_ddg_cards`, `_DDG_MAX_RESULTS=5`); unit tests `test_search_web_excludes_sponsored_rows_and_decodes_uddg`, `test_search_web_discriminator_is_tr_class_not_anchor_class` pass; **live network probe** (`search_web("python html.parser")` against the real `lite.duckduckgo.com`) returned exactly 5 numbered cards with real (non-DDG-redirect) decoded URLs — proves the parser works against current live markup, not just the fixture |
| 2 | `fetch_url(url)` retrieves webpage content and extracts cleaned text with HTML markup stripped (SC2/WEB-02) | ✓ VERIFIED | `src/olla/tools/web.py:189-215` (`fetch_url`, `_TextExtractor`); unit tests `test_fetch_url_small_page_returns_cleaned_content`, `test_text_extractor_drops_script_style_nav_header_footer`, `test_text_extractor_keeps_aside_content` pass; **live network probe** (`fetch_url("https://example.com")`) returned clean extracted text with no markup — proves the real stream→decode→extract path executes correctly end to end, not only under mocked `httpx.Client` |
| 3 | Web observation outputs are strictly hard-truncated to 3,000 characters (code points, not bytes) before appending to context (SC3/WEB-03) | ✓ VERIFIED | `_truncate_to_sentence(text, limit=3000)` (`web.py:59-70`) operates on `len(text)`; tests `test_truncate_to_sentence_noop_under_limit`, `test_truncate_to_sentence_hard_cuts_at_limit_when_no_punctuation`, `test_truncate_to_sentence_counts_code_points_not_utf8_bytes` (multi-byte/emoji case), `test_search_web_truncates_long_formatted_output` all pass. Note: the recorded string can reach ~3,054 chars once the truncation note is appended (D-04's cap-note convention, same shape as Phase 5's D-11) — this is the intended "hard-cap-then-note" behavior, not an unbounded overflow. |
| 4 | Web observations tag turn state as `untrusted`, revoking `--yes` auto-bypass on subsequent destructive actions (SC4/WEB-04) | ✓ VERIFIED | `_record_web_observation` (`loop.py:469-480`) wraps content in `<untrusted_web_content>` and returns `True` from `_execute_fetch_url`/`_execute_search_web`, which sets `untrusted_observation_seen`; end-to-end integration tests `test_fetch_url_wraps_untrusted_content_and_forces_reconfirmation` and `test_search_web_wraps_untrusted_content_and_forces_reconfirmation` prove `Confirm.ask` is invoked for a subsequent `shell` call even under `yes=True`; negative counterparts (`test_fetch_url_error_does_not_force_reconfirmation`, `test_search_web_error_does_not_force_reconfirmation`) prove an error path does neither |
| 5 | `fetch_url`/`search_web` dispatch with no interactive confirmation prompt — `run_loop()` routes straight to their adapters, bypassing `safety.check()` entirely (D-01) | ✓ VERIFIED | `loop.py:1144-1153` dispatch branches call `_execute_fetch_url`/`_execute_search_web` directly with no `check()`/`safety.check()` call anywhere in either function or the dispatch branch (confirmed by direct code reading of `loop.py:923-961`); `src/olla/safety.py` was not modified in this phase's commits |
| 6 | `fetch_url("")`/`search_web("")` (and whitespace-only) return `{"error": ...}` without making any HTTP call | ✓ VERIFIED | `test_fetch_url_empty_returns_error_without_http_call`, `test_fetch_url_whitespace_only_returns_error_without_http_call`, `test_search_web_empty_returns_error_without_http_call`, `test_search_web_whitespace_only_returns_error_without_http_call` all assert `mock_client_cls.assert_not_called()` and pass |
| 7 | A page whose extracted text is empty after boilerplate-stripping returns a non-blank placeholder, never a blank observation | ✓ VERIFIED | `test_fetch_url_all_boilerplate_returns_placeholder` asserts `{"content": "(no readable text extracted)"}`, passes |
| 8 | A genuine zero-result search and a DuckDuckGo bot-challenge page are distinguishable — the former returns legible `{"content": "no results found"}`, the latter `{"error": ...}` | ✓ VERIFIED | `test_search_web_genuine_zero_results_returns_content_message` and `test_search_web_bot_challenge_returns_error` both pass against distinct fixtures; detector uses literal substring `"anomaly-modal"` (not the bare word `"anomaly"`) per the plan's deliberate false-positive avoidance |
| 9 | The response byte-cap (`_read_capped`, 5,000,000 bytes) applies to both `fetch_url` and `search_web` via the same shared streaming helper, stopping before draining an oversized stream | ✓ VERIFIED | `_read_capped` (`web.py:145-153`) is called by both `fetch_url` (line 198) and `search_web` (line 165-167) — no separate/duplicated implementation; `test_fetch_url_stops_reading_once_byte_cap_exceeded` asserts the mocked iterator is not fully drained, passes |
| 10 | `fetch_url`/`search_web` never raise for empty input, timeout, transport error, HTTP error, or a malformed/invalid URL — every path returns a dict | ✓ VERIFIED | Both functions catch `(httpx.TimeoutException, httpx.TransportError, httpx.HTTPError, httpx.InvalidURL)`; `httpx.InvalidURL` handling (CR-01 fix, commit `fb7de05`) independently reproduced live: `fetch_url("http://example.com\nX-Injected: true")` returns `{"error": "fetch_url request failed: Invalid non-printable ASCII character in URL, ...")}` instead of raising |
| 11 | `--dry-run` on `fetch_url`/`search_web` shows a "Step 1 would fetch/search:" preview instead of the unknown-tool fallback | ✓ VERIFIED | `loop.py:630-633` preview branches; `test_fetch_url_dry_run_shows_fetch_preview`, `test_search_web_dry_run_shows_search_preview` pass |
| 12 | System prompt documents both tools' `<tool>`/`<args>` contracts with the "runs immediately without confirmation" phrase, and the roster line correctly reads "9 tools available" with both tools added, without breaking the pre-existing `Example:` count assertion | ✓ VERIFIED | `src/olla/prompts.py:5,21-27` — roster line reads "9 tools available" with all 9 names; fetch_url/search_web doc blocks present with the exact confirmation phrase; `test_system_prompt_advertises_tool_roster`, `test_system_prompt_teaches_fetch_url_format`, `test_system_prompt_teaches_search_web_format` pass; `test_system_prompt_preserves_shell_file_guidance`'s `SYSTEM_PROMPT.count("Example:") == 4` assertion still passes (4 `Example:` blocks present, unchanged) |

**Score:** 12/12 truths verified (0 present-but-behavior-unverified)

### Prohibitions (must_haves.prohibitions, verification: test)

| # | Prohibition | Requirement | Enforcement Evidence | Status |
|---|-------------|-------------|----------------------|--------|
| 1 | MUST NOT record search_web/fetch_url success output through `_record_observation`/`_record_file_observation` — only `_record_web_observation` may record successful web content | WEB-04 | `_execute_fetch_url`/`_execute_search_web` (`loop.py:923-961`) each contain exactly one success-path recording call, `_record_web_observation(...)`, with no alternate call to `_record_observation`/`_record_file_observation` on the success branch (source-read confirmed); `test_fetch_url_wraps_untrusted_content_and_forces_reconfirmation`/`test_search_web_wraps_untrusted_content_and_forces_reconfirmation` positively assert the `<untrusted_web_content>` tag is present. Enforcement is source-inspection + tag-presence assertion; no test explicitly asserts the *absence* of a duplicate untagged recording, but the source has no such second call path. | resolved |
| 2 | MUST NOT surface a DuckDuckGo bot-challenge/CAPTCHA response as if it were genuine search results | WEB-01 | `test_search_web_bot_challenge_returns_error` — wired, passing | resolved |
| 3 | MUST NOT include DuckDuckGo Lite sponsored/ad rows in numbered results, indistinguishable from organic results | WEB-01 | `test_search_web_excludes_sponsored_rows_and_decodes_uddg` + `test_search_web_discriminator_is_tr_class_not_anchor_class` — wired, passing | resolved |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/tools/web.py` | `fetch_url`, `search_web`, shared helpers | ✓ VERIFIED | 216 lines; exports `fetch_url`, `search_web`, `_TextExtractor`, `_truncate_to_sentence`, `_read_capped`, `_DDGResultParser`, `_decode_ddg_href`, `_format_ddg_cards` — all present and substantive, not stubs |
| `src/olla/loop.py` (modified) | dispatch/preview/execute/record wiring | ✓ VERIFIED | `fetch_url`/`search_web` import (line 35); `_prepare_action` branches (335-349); `_preview_action` branches (630-633); `_record_web_observation` (469-480); `_execute_fetch_url`/`_execute_search_web` (923-961); `run_loop()` dispatch (1144-1153) |
| `src/olla/prompts.py` (modified) | tool doc blocks + roster bump | ✓ VERIFIED | Both doc blocks present; roster reads "9 tools available" |
| `tests/test_tools/test_web.py` (new) | unit test coverage | ✓ VERIFIED | 26 tests collected, all pass in isolation and in full suite |
| `tests/test_loop.py` (modified) | integration tests | ✓ VERIFIED | 6 fetch_url/search_web-specific tests collected, all pass |
| `tests/test_prompts.py` (modified) | roster/format tests | ✓ VERIFIED | 13 tests collected (2 new), all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_loop()` dispatch | `_execute_fetch_url` → `tools/web.py:fetch_url` → `_record_web_observation` → `untrusted_observation_seen` → next CONFIRM-tier gate | direct call chain | ✓ WIRED | Confirmed by source read + passing integration test forcing `Confirm.ask` on the next shell call |
| `run_loop()` dispatch | `_execute_search_web` → `tools/web.py:search_web` → `_record_web_observation` (shared) → `untrusted_observation_seen` → next CONFIRM-tier gate | direct call chain | ✓ WIRED | Confirmed by source read + passing integration test |
| `_prepare_action`/`_preview_action` | `_Action(kind="fetch_url"/"search_web", args_raw=<input>)` | no new `_Action` fields, no `_resolve_file_path` call | ✓ WIRED | Confirmed by source read (lines 335-349) — matches memory-branch shape exactly |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `fetch_url` content | `extracted_text` / `_truncate_to_sentence(...)` | live `httpx.Client` streaming GET, decoded + parsed by `_TextExtractor` | Yes — live probe against `https://example.com` returned real cleaned text | ✓ FLOWING |
| `search_web` content | `_format_ddg_cards(parser.results)` | live `httpx.Client` streaming GET to `lite.duckduckgo.com/lite/`, parsed by `_DDGResultParser` | Yes — live probe against real DuckDuckGo Lite returned 5 real, decoded-URL cards | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `fetch_url` real end-to-end HTTP fetch + extraction | `fetch_url("https://example.com")` (live network) | `{'content': 'Example DomainExample DomainThis domain is for use in documentation examples without needing permission. Avoid use in operations.Learn more'}` | ✓ PASS |
| `search_web` real end-to-end HTTP query + DDG Lite parse | `search_web("python html.parser")` (live network) | 5 numbered cards, all real (non-redirect) decoded URLs, no sponsored rows, no bot-challenge markup | ✓ PASS |
| `fetch_url` handles a malformed/injected URL without crashing (CR-01 regression check) | `fetch_url("http://example.com\nX-Injected: true")` | `{'error': "fetch_url request failed: Invalid non-printable ASCII character in URL, '\\n' at position 18."}` | ✓ PASS |
| Full test suite regression | `.venv/bin/python -m pytest -q` | `431 passed in 5.80s` | ✓ PASS |
| Named fetch_url/search_web loop tests | `.venv/bin/python -m pytest tests/test_loop.py -k "fetch_url or search_web" -v` | `6 passed` | ✓ PASS |
| Named prompts tests | `.venv/bin/python -m pytest tests/test_prompts.py -v` | `13 passed` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| WEB-01 | 06-02 | `search_web(query)` queries DuckDuckGo Lite via httpx, returning top 3-5 snippet cards without extra pip dependencies | ✓ SATISFIED | Live probe returned 5 cards; no new dependency added (`httpx` already existing); unit + integration tests pass |
| WEB-02 | 06-01 | `fetch_url(url)` fetches webpage content via httpx, extracting readable text and stripping HTML markup | ✓ SATISFIED | Live probe returned cleaned text; `_TextExtractor` unit tests pass |
| WEB-03 | 06-01, 06-02 | Hard output truncation limits web tool observations to <= 3,000 characters before appending to context | ✓ SATISFIED | `_truncate_to_sentence` code-point-based cap tests pass (see truth #3 note on the ~54-char truncation-note tail, an intended part of the D-04 cap-note convention) |
| WEB-04 | 06-01, 06-02 | Observations from web tools tag state as untrusted, revoking `--yes` auto-bypass on subsequent destructive actions | ✓ SATISFIED | Integration tests prove `Confirm.ask` invoked post-fetch/search even under `--yes=True` |

No orphaned requirements — REQUIREMENTS.md maps exactly WEB-01..04 to Phase 6, and all four are claimed by the two plans' `requirements:` frontmatter and satisfied above.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers in any phase-modified file. (`_NO_TEXT_PLACEHOLDER` is a legitimate constant name for a user-facing fallback string, not a debt marker.) No empty stub implementations, no hardcoded-empty data flowing to output.

### Threat Model / Accepted-Risk Findings (not gaps)

The phase's own code review (`06-REVIEW.md`) raised three critical findings. Per the phase's locked context decisions, only one was a genuine defect; the other two are the deliberate, user-confirmed consequence of D-01/D-02 and are recorded here for traceability, not as gaps:

| ID | Finding | Disposition |
|----|---------|-------------|
| CR-01 | `fetch_url` could raise uncaught `httpx.InvalidURL` on a malformed URL, crashing the loop | **Fixed** in commit `fb7de05` — independently reproduced and confirmed fixed above (spot-check) |
| CR-02 | `fetch_url`/`search_web` bypass the `untrusted_observation_seen` reconfirmation gate on their *own* dispatch (i.e. a preceding untrusted observation does not gate the fetch/search call itself) | **Accepted, not a gap** — direct, intended consequence of D-01 ("unconfirmed dispatch... same tier as list_dir/grep_files"); matches Phase 5's INSPECT-03/D-09 precedent. T-06-03 in the threat register documents this as `accept`-adjacent (mitigated only on the *output* side via WEB-04, not the *input* side) |
| CR-03 | No SSRF/destination restriction on `fetch_url` | **Accepted, not a gap** — D-02 explicitly declines host/scheme restrictions after the user was shown the SSRF exposure and reconfirmed "no restrictions." T-06-01/T-06-02 in the threat register record this as `accept` |

Warnings WR-01 (web observations not truncated to `MAX_OBSERVATION_CHARS` like other tools), WR-02 (HTTP status code never checked), WR-03 (inconsistent substring-vs-equality class matching in the DDG parser — live probe today shows no practical impact, but is a legitimate forward-looking fragility), WR-04 (no wall-clock ceiling on streaming reads), and IN-01 (naive sentence-boundary heuristic) do not map to any ROADMAP success criterion or PLAN must-have, so none is scored as a gap. They are legitimate hardening opportunities for a future phase/backlog item, not phase-06 blockers.

### Human Verification Required

None. All truths were resolved with either passing automated tests or a direct live-network spot-check (network was available in this environment, so this did not need to be deferred to a human).

### Gaps Summary

No gaps. All 12 must-have truths verified, all 3 prohibitions enforced, all 4 roadmap success criteria satisfied, all 4 requirement IDs (WEB-01..04) satisfied with no orphans, full test suite green (431 passed, 0 regressions), and both `fetch_url` and `search_web` independently confirmed working end-to-end against live services (not just mocks) during this verification pass.

---

_Verified: 2026-09-09_
_Verifier: Claude (gsd-verifier)_
