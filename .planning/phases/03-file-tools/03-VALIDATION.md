---
phase: 3
slug: file-tools
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Estimated runtime** | ~10 seconds (109 existing tests + ~11 new) |

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
| TBD | TBD | TBD | FILE-01 | — | `read_file(path)` returns file contents | unit | `pytest tests/test_tools/test_files.py::test_read_file_success -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-01 | — | Oversized file content is truncated before reaching model context | unit | `pytest tests/test_loop.py::test_run_loop_read_file_truncates_large_output -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-01 | — | `read_file` on missing/unreadable file returns an error Observation, not an exception | unit | `pytest tests/test_tools/test_files.py::test_read_file_not_found -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-02 | — | `write_file(path, content)` writes content to disk only after confirm approval | unit/integration | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_approved -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-02 | — | `write_file` confirm prompt shows the resolved path (SC2) | unit | `pytest tests/test_loop.py::test_run_loop_write_file_shows_resolved_path -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-02 | — | Declining the `write_file` confirm prompt performs no write | unit | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_declined -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-02 | — | `--yes` skips the `write_file` confirm prompt | unit | `pytest tests/test_loop.py::test_run_loop_write_file_yes_skips_prompt -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | FILE-02 | — | `write_file` content survives parser round-trip (fences, trailing newline) — Pitfall 1 fix | unit | `pytest tests/test_parser.py::test_write_file_args_preserve_fences_and_newline -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SC3 | — | A `read_file` then `write_file` sequence completes via `run_loop` (end-to-end) | integration | `pytest tests/test_loop.py::test_run_loop_read_then_write_end_to_end -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LOOP-04 | — | `--dry-run` previews `read_file`/`write_file` instead of "unknown tool" (Pitfall 2 regression) | unit | `pytest tests/test_loop.py::test_dry_run_previews_read_file` / `test_dry_run_previews_write_file -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LOOP-04 | — | Repeated identical `read_file`/`write_file` calls trigger the 3x repetition guard (Pitfall 3 generalization) | unit | `pytest tests/test_loop.py::test_run_loop_repetition_guard_covers_file_tools -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tools/test_files.py` — new file, covers FILE-01/FILE-02 unit tests for `tools/files.py::read_file`/`write_file` (use `tmp_path` fixture, mirroring `tests/test_tools/test_shell.py`'s style)
- [ ] Extend `tests/test_parser.py` — add cases for `write_file` path/content split, fence preservation, trailing-newline preservation (Pitfall 1)
- [ ] Extend `tests/test_loop.py` — add `read_file`/`write_file` dispatch tests mirroring existing shell CONFIRM-tier tests, plus `--dry-run` and repetition-guard coverage for the new tools

*No new fixtures/conftest needed — `tmp_path` (pytest builtin) and `mocker` (`pytest-mock`, already a dev dependency) cover all new test needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Literal `</args>` substring in `write_file` content causes generation-time truncation (Pitfall 5) | FILE-02 | `</args>` is the stop-sequence passed to `ollama.chat`; mocked `chat` responses bypass the stop-sequence mechanism entirely, so no automated test can reproduce this. It is a documented limitation, not a tested behavior. | Verify `SYSTEM_PROMPT` documents that `write_file` content must not contain the literal string `</args>`. Do not write a regression test for the truncation itself. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
