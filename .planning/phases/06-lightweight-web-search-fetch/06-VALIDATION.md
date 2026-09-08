---
phase: "06"
slug: "lightweight-web-search-fetch"
# status lifecycle: draft (seeded by plan-phase) -> validated (set by validate-phase §6)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-09"
validated: "2026-09-09"
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
| Task 1 | 06-01 | 1 | WEB-02, WEB-04 | T-06-03, T-06-04 | `fetch_url` end-to-end: strips script/style/nav/header/footer, byte-capped streaming read (`_read_capped`), wraps success in `<untrusted_web_content>` via `_record_web_observation`, revokes `--yes` for the next CONFIRM-tier action | integration/unit | `pytest tests/test_tools/test_web.py -k fetch_url -x` / `pytest tests/test_loop.py -k fetch_url -x` | ✅ | ✅ green |
| Task 2 | 06-01 | 1 | WEB-03 | T-06-04 | Sentence-boundary truncation edge cases (hard-cut fallback, multi-byte/emoji code-point cap), byte-cap stream-stop, error path stays untagged, `--dry-run` preview | unit/integration | `pytest tests/test_tools/test_web.py -x` / `pytest tests/test_loop.py -k fetch_url -x` / `pytest` | ✅ | ✅ green |
| Task 1 | 06-02 | 2 | WEB-01, WEB-04 | T-06-03, T-06-05, T-06-06 | `search_web` parses DDG Lite HTML into 3-5 cards, excludes `<tr class="result-sponsored">` rows, decodes `uddg` redirect URLs, sends browser UA, wraps success in `<untrusted_web_content>` | integration/unit | `pytest tests/test_tools/test_web.py -k search_web -x` / `pytest tests/test_loop.py -k search_web -x` | ✅ | ✅ green |
| Task 2 | 06-02 | 2 | WEB-03 | T-06-04, T-06-05 | `search_web` truncation/error-path (timeout/transport/bot-challenge) coverage, `--dry-run` preview, roster bump to "9 tools available" | unit/integration | `pytest tests/test_tools/test_web.py -x` / `pytest tests/test_prompts.py -x` / `pytest` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_tools/test_web.py` — created (26 tests, inline DDG Lite HTML fixtures)
- [x] `tests/test_loop.py` — `search_web`/`fetch_url` cases added to the untrusted-observation suite
- [x] No new framework/conftest needed — mocked via `mocker.patch("olla.tools.web.httpx.Client", ...)` following the existing pattern

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-09

---

## Validation Audit 2026-09-09

| Metric | Count |
|--------|-------|
| Requirements audited | 4 (WEB-01, WEB-02, WEB-03, WEB-04) |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 7 automated commands in the Per-Task Verification Map re-run against the actual
implementation and confirmed green (431 tests total, 0 failures). No `gsd-nyquist-auditor`
spawn was needed — every requirement was already COVERED.
