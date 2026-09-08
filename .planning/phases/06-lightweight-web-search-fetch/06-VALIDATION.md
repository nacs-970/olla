---
phase: "06"
slug: "lightweight-web-search-fetch"
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

- **After every task commit:** Run `python -m pytest tests/test_tools/test_web.py tests/test_loop.py -k web`
- **After every plan wave:** Run `python -m pytest tests`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | WEB-01 | V5 | Parses DDG Lite HTML into 3-5 cards, skips sponsored rows, decodes `uddg` redirect URLs, sends browser UA | unit | `pytest tests/test_tools/test_web.py -k search_web` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 0 | WEB-02 | — | Strips script/style/nav/header/footer, keeps readable text | unit | `pytest tests/test_tools/test_web.py -k fetch_url_extraction` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 0 | WEB-03 | — | Output ≤3,000 chars, sentence-boundary truncation (D-04) | unit | `pytest tests/test_tools/test_web.py -k truncat` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 0 | WEB-04 | Tampering/EoP | Web observation tagged untrusted, revokes `--yes` for subsequent destructive action | integration | `pytest tests/test_loop.py -k untrusted_web` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 0 | WEB-04 | Tampering/EoP | `--yes` revoked check follows existing `test_untrusted_file_instruction_cannot_use_yes_for_shell_or_write` template | integration | `pytest tests/test_loop.py -k web_cannot_use_yes` | ❌ W0 | ⬜ pending |

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
