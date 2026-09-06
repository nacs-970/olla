---
phase: 3
slug: file-tools
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-14
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 (already a dev dependency, per `pyproject.toml`) |
| **Config file** | none — pytest auto-discovers `tests/` (existing convention: `tests/test_*.py`, `tests/test_tools/test_*.py`) |
| **Quick run command** | `pytest tests/test_tools/test_files.py tests/test_loop.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~10 seconds (109 existing tests + ~17 new) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_tools/test_files.py tests/test_parser.py tests/test_loop.py -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01 Task 1/2 | 03-01 | 1 | FILE-01 | T-03-01 | `read_file(path)` returns file contents | unit | `pytest tests/test_tools/test_files.py::test_read_file_success -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-01 Task 1/2 | 03-01 | 1 | FILE-01 | T-03-02 | Oversized file content is truncated before reaching model context | unit | `pytest tests/test_loop.py::test_run_loop_read_file_truncates_large_output -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-01 Task 1/2 | 03-01 | 1 | FILE-01 | T-03-03 | `read_file` on missing/unreadable file returns an error Observation, not an exception | unit | `pytest tests/test_tools/test_files.py::test_read_file_not_found -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | T-03-04 | `write_file(path, content)` writes content to disk only after confirm approval | unit/integration | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_approved -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | T-03-04, T-03-05 | `write_file` confirm prompt shows the resolved path (SC2) | unit | `pytest tests/test_loop.py::test_run_loop_write_file_shows_resolved_path -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | T-03-04 | Declining the `write_file` confirm prompt performs no write | unit | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_declined -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | T-03-04 | `--yes` skips the `write_file` confirm prompt | unit | `pytest tests/test_loop.py::test_run_loop_write_file_yes_skips_prompt -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | — | `write_file` content survives parser round-trip (interior fences preserved) — Pitfall 1 fix | unit | `pytest tests/test_parser.py::test_write_file_args_preserve_interior_fences -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | — | `write_file` content survives parser round-trip (trailing newline preserved) — Pitfall 1 fix | unit | `pytest tests/test_parser.py::test_write_file_args_preserve_trailing_newline -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-01, FILE-02 | — | A `read_file` then `write_file` sequence completes via `run_loop` (end-to-end, SC3) | integration | `pytest tests/test_loop.py::test_run_loop_read_then_write_end_to_end -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-01 Task 1/2 | 03-01 | 1 | FILE-01 | — | `--dry-run` previews `read_file` instead of "unknown tool" (Pitfall 2 regression) | unit | `pytest tests/test_loop.py::test_dry_run_previews_read_file -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | — | `--dry-run` previews `write_file` instead of "unknown tool" (Pitfall 2 regression) | unit | `pytest tests/test_loop.py::test_dry_run_previews_write_file -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-01 Task 1/2 | 03-01 | 1 | FILE-01 | — | Repeated identical `read_file` calls trigger the 3x repetition guard (Pitfall 3 generalization) | unit | `pytest tests/test_loop.py::test_run_loop_repetition_guard_covers_read_file -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | FILE-02 | — | Repeated identical `write_file` calls trigger the 3x repetition guard (Pitfall 3 generalization) | unit | `pytest tests/test_loop.py::test_run_loop_repetition_guard_covers_write_file -x` | Created in Task 1 (RED), implemented in Task 2 (GREEN) | ⬜ pending |
| 03-02 Task 1/2 | 03-02 | 2 | — | — | `<tool>browse</tool>` (repurposed from `write_file`) still returns "unknown tool" Observation once `write_file` is recognized | unit | `pytest tests/test_loop.py::test_run_loop_unknown_tool_returns_observation -x` | Existing test, repurposed in Task 1, must pass after Task 2 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Reconciled with the actual plan structure: each plan's **Task 1 is the Wave-0-equivalent test-creation step** (RED), and Task 2 is the implementation step (GREEN) within the same plan/wave. There is no separate Wave 0 plan — test scaffolding and implementation are paired per vertical slice (per MVP_MODE).

- [x] `tests/test_tools/test_files.py` — new file, created in 03-01 Task 1 (read_file tests) and extended in 03-02 Task 1 (write_file tests), mirroring `tests/test_tools/test_shell.py`'s flat-function/`tmp_path` style
- [x] Extend `tests/test_parser.py` — Pitfall 1 fix cases (interior fence preservation, trailing-newline preservation) added in 03-02 Task 1
- [x] Extend `tests/test_loop.py` — read_file dispatch/dry-run/repetition-guard tests added in 03-01 Task 1; write_file confirm-gate/dry-run/repetition-guard/SC3 tests added in 03-02 Task 1; `test_run_loop_unknown_tool_returns_observation` repurposed (browse) in 03-02 Task 1

*No new fixtures/conftest needed — `tmp_path` (pytest builtin) and `mocker` (`pytest-mock`, already a dev dependency) cover all new test needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Literal `</args>` substring in `write_file` content causes generation-time truncation (Pitfall 5 / T-03-08) | FILE-02 | `</args>` is the stop-sequence passed to `ollama.chat`; mocked `chat` responses bypass the stop-sequence mechanism entirely, so no automated test can reproduce this. It is a documented limitation, not a tested behavior. | Verify `SYSTEM_PROMPT` (src/olla/prompts.py) documents that `write_file` content must not contain the literal string `</args>`. Do not write a regression test for the truncation itself. Covered by 03-02 Task 2 step 7. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an `<automated>` pytest command)
- [x] Wave 0 covers all MISSING references (reconciled above — paired RED/GREEN per plan, no orphaned references)
- [x] No watch-mode flags
- [x] Feedback latency < 10s (full suite ~10s for ~126 tests)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready for execution
</content>
