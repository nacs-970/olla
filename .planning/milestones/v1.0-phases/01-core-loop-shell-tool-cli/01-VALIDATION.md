---
phase: 01
slug: core-loop-shell-tool-cli
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-11
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed retroactively (State B — no VALIDATION.md existed; built from PLAN/SUMMARY artifacts).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (declared `pytest>=8`) |
| **Config file** | `pyproject.toml` (no `[tool.pytest.ini_options]` — pytest defaults) |
| **Quick run command** | `python -m pytest tests/test_<module>.py -v` |
| **Full suite command** | `cd /home/nacs/Documents/git/olla && .venv/bin/python -m pytest tests/ -v` |
| **Estimated runtime** | ~1.6s (41 tests) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_<module>.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | CLI-03 | — | N/A (package skeleton) | structural | `find src tests -name "*.py" \| sort \| grep -c '\.py$'` (==10) | ✅ | ✅ green |
| 01-01-02 | 01 | 1 | CLI-03 | T-01-SC | Supply-chain spot-check before install | manual (blocking-human) | `grep -E '<5 deps>' pyproject.toml \| wc -l` (==5) | ✅ | ✅ approved |
| 01-01-03 | 01 | 1 | LOOP-01 | — | Tolerant `<tool>/<args>/<final>` parsing (fences/prose/unclosed) | unit | `pytest tests/test_parser.py -v` | ✅ | ✅ green (7/7) |
| 01-01-04 | 01 | 1 | SHELL-01 | T-01-01, T-01-02 | `shlex.split`+`subprocess.run(shell=False)`, timeout, missing-cmd | unit | `pytest tests/test_tools/test_shell.py -v` | ✅ | ✅ green (8/8) |
| 01-01-05 | 01 | 1 | LOOP-02, LOOP-03, LOOP-05 | T-01-03 | stop-sequences, `num_ctx=8192`, identical truncation, Step N output | unit | `pytest tests/test_loop.py -v` | ✅ | ✅ green (8/8) |
| 01-01-06 | 01 | 1 | CLI-01, CLI-02 | — | `--model` required (no default), one-shot run wiring | unit | `pytest tests/test_cli.py -v` | ✅ | ✅ green |
| 01-01-07 | 01 | 1 | CLI-01, CLI-02, LOOP-01 | T-01-04 | Real `ollama.chat()` e2e (final + tool path), `--model` fail-fast | manual (blocking) + partial-auto | `olla "do something" 2>&1 \| grep -i -- "--model"` | ✅ | ✅ approved |
| 01-02-01 | 02 | 2 | LOOP-01 | T-01-06 | 3-way response classifier; `call_model` `think` param backward-compat | unit | `pytest tests/test_smoke.py tests/test_loop.py -v` | ✅ | ✅ green (8/8 + 8/8) |
| 01-02-02 | 02 | 2 | LOOP-01 | T-01-06 | `--smoke-test` CLI flag wiring, fail-fast w/o `--model` | unit | `pytest tests/ -v` | ✅ | ✅ green (41/41) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Full suite at audit time:** 41/41 passing (`tests/test_cli.py` 9, `tests/test_loop.py` 8, `tests/test_parser.py` 7, `tests/test_smoke.py` 8, `tests/test_tools/test_shell.py` 8) — additional edge-case tests beyond original PLAN behaviors come from `01-REVIEW-FIX.md` (CR-02, WR-01/02/03).

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test scaffolding needed — pytest + `.venv` already wired, all 41 tests collect and pass.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Supply-chain spot-check of 5 declared PyPI deps (`ollama`, `click`, `pytest`, `pytest-mock`, `ruff`) before `pip install -e ".[dev]"` | CLI-03 | Automated package-legitimacy scan (slopcheck) unavailable this session (T-01-SC); requires human visiting pypi.org | Visit `pypi.org/project/{ollama,click}`, confirm maintainer/description match, no typosquat. **DONE — approved (01-01-SUMMARY)**. |
| Real `ollama.chat()` e2e run: no-tool `<final>` path, tool-calling path, `--model`-required fail-fast | CLI-01, CLI-02, LOOP-01 | Requires a live local Ollama server + pulled model; `test_loop.py`/`test_cli.py` mock `ollama.chat`/`run_loop` | `olla "what is 1+1" --model <name>` → clean `<final>2`; `olla "list files in current directory" --model <name>` → `Step 1: running [...]` + final; `olla "do something"` (no `--model`) → UsageError mentioning `--model`. **DONE — approved against `tripolskypetr/gemma4-uncensored-aggressive:latest` (01-01-SUMMARY)**. |
| Roadmap Success Criterion 6 — `--smoke-test` tag-compliance table across 5 target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive) | LOOP-01 | Requires live Ollama + 5 specific local models pulled; the *classifier/runner mechanism* is unit-tested (8/8 green in `test_smoke.py`), but the cross-model empirical compliance run is a one-time research activity, not CI-suitable | For each target model: `olla --smoke-test --model <name>`; record think=False/True compliance %, reverted-to-native-format count, non-compliant count, and any sub-80% D-08 WARNING. **PENDING — not yet run** (tracked as Phase 1 blocker in `.planning/STATE.md`; tooling is built and unit-tested, only the empirical multi-model run is outstanding). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are documented manual-only with rationale
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — infra pre-existing)
- [x] No watch-mode flags
- [x] Feedback latency < 5s (~1.6s full suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-11 (retroactive reconstruction)

**Outstanding (non-blocking for Nyquist compliance):** Roadmap Success Criterion 6 multi-model empirical `--smoke-test` run — see Manual-Only table above. Recommended before declaring Phase 1 fully "done" per `01-RESEARCH.md` "NEEDS RESEARCH-PHASE" flag, but does not represent a missing automated-test gap.
