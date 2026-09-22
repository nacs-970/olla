---
phase: "5"
slug: "safe-inspection-tools"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-08"
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8 |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options] testpaths = ["tests"]` |
| **Quick run command** | `pytest tests/test_tools/test_inspect.py tests/test_loop.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_tools/test_inspect.py tests/test_loop.py -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Task 1 | 05-01 | 1 | INSPECT-01 | T-05-03 | `list_dir` returns `[d]`/`[f]`/`[l]` entries, sizes, sorted dirs-first-alpha, capped at 50, `.git` shown | unit | `pytest tests/test_tools/test_inspect.py -k list_dir -x` | ❌ W0 | ⬜ pending |
| Task 2 | 05-01 | 1 | INSPECT-02 | T-05-01, T-05-02, T-05-05 | `grep_files` regex-matches text files, skips `.git`/binary, caps at 25 lines, `file:line` output, `recursive` flag toggles traversal depth | unit | `pytest tests/test_tools/test_inspect.py -k grep_files -x` | ❌ W0 | ⬜ pending |
| Task 1 + Task 2 | 05-01 | 1 | INSPECT-03 | T-05-04 | `list_dir`/`grep_files` dispatch executes without a confirmation prompt (loop-level, not safety.py), and output tagging observably gates the next destructive action via a two-turn test | unit/integration | `pytest tests/test_loop.py -k "list_dir or grep_files" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tools/test_inspect.py` — new file covering both `list_dir()` and `grep_files()` adapter behavior (mirrors `tests/test_tools/test_files.py`'s structure: `tmp_path` fixture, one test per success/error/edge-case scenario)
- [ ] `tests/test_loop.py` additions — new tests for the `_prepare_action`/dispatch branches for `list_dir`/`grep_files`, covering (a) no confirmation prompt is triggered, (b) `untrusted_observation_seen` is set on success
- [ ] `tests/test_prompts.py` additions — assert the new tools' names and the `recursive` parameter appear in `SYSTEM_PROMPT`

*Framework install: none needed — `pytest`/`pytest-mock` are already dev dependencies.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
