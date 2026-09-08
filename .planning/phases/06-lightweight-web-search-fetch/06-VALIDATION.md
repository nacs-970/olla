---
phase: "06"
slug: "lightweight-web-search-fetch"
# status lifecycle: draft (seeded by plan-phase) -> validated (set by validate-phase §6)
# draft/false here is the correct planner-emitted state, matching phase 05's precedent
# (.planning/phases/05-safe-inspection-tools/05-VALIDATION.md remains draft/false even
# post-execution) -- plan-phase does not self-attest to Nyquist compliance or execution
# completion; /gsd-validate-phase owns that flip after the plans are actually run.
# Sign-off boxes below are checked there, not here. The design-time review that produced
# this file DID confirm every automated-verify/sampling/latency criterion holds against
# the finalized 06-01/06-02 two-plan structure (see Per-Task Verification Map) -- what
# remains genuinely false is whether execution has happened, which it has not yet.
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-09"
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8, pytest-mock >=3.14 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `python -m pytest tests/test_tools/test_web.py` |
| **Full suite command** | `python -m pytest tests` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_tools/test_web.py tests/test_loop.py -k "fetch_url or search_web"`
- **After every plan wave:** Run `python -m pytest tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 1 | 06-01 | 1 | WEB-02, WEB-04 | T-06-03, T-06-04 | `fetch_url` end-to-end: strips script/style/nav/header/footer, byte-capped streaming read (`_read_capped`), wraps success in `<untrusted_web_content>` via `_record_web_observation`, revokes `--yes` for the next CONFIRM-tier action | integration/unit | `pytest tests/test_tools/test_web.py -k fetch_url -x` / `pytest tests/test_loop.py -k fetch_url -x` | ❌ W0 | ⬜ pending |
| Task 2 | 06-01 | 1 | WEB-03 | T-06-04 | Sentence-boundary truncation edge cases (hard-cut fallback, multi-byte/emoji code-point cap), byte-cap stream-stop, error path stays untagged, `--dry-run` preview | unit/integration | `pytest tests/test_tools/test_web.py -x` / `pytest tests/test_loop.py -k fetch_url -x` / `pytest` | ❌ W0 | ⬜ pending |
| Task 1 | 06-02 | 2 | WEB-01, WEB-04 | T-06-03, T-06-05, T-06-06 | `search_web` parses DDG Lite HTML into 3-5 cards, excludes `<tr class="result-sponsored">` rows, decodes `uddg` redirect URLs, sends browser UA, wraps success in `<untrusted_web_content>` | integration/unit | `pytest tests/test_tools/test_web.py -k search_web -x` / `pytest tests/test_loop.py -k search_web -x` | ❌ W0 | ⬜ pending |
| Task 2 | 06-02 | 2 | WEB-03 | T-06-04, T-06-05 | `search_web` truncation/error-path (timeout/transport/bot-challenge) coverage, `--dry-run` preview, roster bump to "9 tools available" | unit/integration | `pytest tests/test_tools/test_web.py -x` / `pytest tests/test_prompts.py -x` / `pytest` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tools/test_web.py` — new file; inline a trimmed 2-3-result DDG Lite HTML sample as a string constant (no `tests/fixtures/` dir convention in this repo)
- [ ] `tests/test_loop.py` — add `search_web`/`fetch_url` cases to the existing untrusted-observation suite (template at `tests/test_loop.py:1560`)
- [ ] No new framework/conftest needed — mock via `mocker.patch("olla.tools.web.httpx.Client", ...)` following the existing `mocker.patch("olla.loop.run_shell")` pattern

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
