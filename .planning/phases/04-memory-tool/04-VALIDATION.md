---
phase: 04
slug: memory-tool
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-25
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 with pytest-mock 3.15.1 |
| **Config file** | none — commands explicitly scope to `tests/` |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_tools/test_memory.py tests/test_parser.py tests/test_loop.py tests/test_prompts.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests -q` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run the directly affected memory/parser/loop/prompt test file.
- **After every plan wave:** Run `.venv/bin/python -m pytest tests -q`.
- **Before `$gsd-verify-work`:** Full scoped suite, exact stdout/Observation assertions, and the mocked three-turn MEM-01 flow must be green.
- **Max feedback latency:** 5 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MEM-01 | T-04-03 | One invocation stores, explicitly recalls, and uses a note without write-time disclosure or cross-run state | mocked E2E | `.venv/bin/python -m pytest tests/test_loop.py::test_run_loop_remember_recall_then_final tests/test_parser.py tests/test_loop.py -q` | ✅ extend/W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | MEM-01 | T-04-01 / T-04-02 | Bounds validate projected state before mutation; rejected writes preserve prior values and capacity | unit | `.venv/bin/python -m pytest tests/test_tools/test_memory.py -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | MEM-01 | T-04-04 | Parser preserves remember values verbatim and the prompt retains the explicit five-tool contract | contract/unit | `.venv/bin/python -m pytest tests/test_parser.py tests/test_prompts.py -q` | ⚠️ extend/W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | MEM-01 | T-04-03 / T-04-05 / T-04-06 | Dry-run cannot access memory; normal calls do not disclose on write, bypass confirmation, retain repetition control, and isolate runs | integration | `.venv/bin/python -m pytest tests/test_loop.py -q -k 'remember or recall or memory'` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tools/test_memory.py` — adapter contract, boundaries, replacement accounting, whitespace, atomic failure, and isolation.
- [ ] `tests/test_prompts.py` — five-tool advertisement, both formats, exact round-trip transcript, and unchanged shell/file guidance.
- [ ] `tests/test_parser.py` additions — raw `remember` payload preservation and trimmed `recall`.
- [ ] `tests/test_loop.py` additions — dispatch, dry-run no-access spies, no confirmation, repetition, two-run isolation, and remember→recall→final.

No framework installation or test configuration is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Optional live small-model format smoke | MEM-01 | The Ollama daemon is unavailable in the current environment; mocked chat is the deterministic phase gate | Start Ollama, run a one-shot task that stores a fact, performs another step, recalls it, and uses it in `<final>`; confirm exact visible step/observation text |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test references.
- [ ] No watch-mode flags.
- [ ] Feedback latency < 5 seconds.
- [ ] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
