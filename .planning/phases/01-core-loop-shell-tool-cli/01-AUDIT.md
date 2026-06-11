---
phase: 01-core-loop-shell-tool-cli
audited: 2026-06-11
scope: phase-01-checkpoint
note: "Milestone v1.0 only 25% complete (1/4 phases). Full v1.0-MILESTONE-AUDIT deferred until phases 2-4 land. This is a phase-01 checkpoint only."
status: tech_debt
scores:
  requirements: 8/8
  success_criteria: 5/6 (1 partial)
  internal_integration: 4/4 flows wired, 0 blockers, 2 warnings
nyquist:
  compliant_phases: [01]
  partial_phases: []
  missing_phases: []
  overall: COMPLIANT
---

# Phase 01 Checkpoint Audit

## Requirements Coverage (3-source cross-check)

| REQ-ID | SUMMARY frontmatter | VALIDATION.md | REQUIREMENTS.md | Status |
|--------|---------------------|----------------|-------------------|--------|
| LOOP-01 | listed | ✅ green (7/7) | Complete | **satisfied** |
| LOOP-02 | listed | ✅ green (8/8) | Complete (updated) | **satisfied** |
| LOOP-03 | listed | ✅ green (8/8) | Complete (updated) | **satisfied** |
| LOOP-05 | listed | ✅ green (8/8) | Complete (updated) | **satisfied** |
| SHELL-01 | listed | ✅ green (8/8) | Complete (updated) | **satisfied** |
| CLI-01 | listed | ✅ green | Complete (updated) | **satisfied** |
| CLI-02 | listed | ✅ green | Complete (updated) | **satisfied** |
| CLI-03 | listed | ✅ approved | Complete (updated) | **satisfied** |

REQUIREMENTS.md traceability table was stale (7 of 8 still showed "Pending" despite SUMMARY/VALIDATION both green) — corrected in this audit.

LOOP-04 not in scope (assigned Phase 2).

## Success Criteria (ROADMAP Phase 1, 6 total)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `olla "task" --model <name>` drives loop, no hardcoded default | ✅ | `--model` required check live-confirmed; CLI tests |
| 2 | Parser tolerant of fences/prose/unclosed tags | ✅ | 7/7 parser tests + CR-01/CR-02 fixes for empty/malformed args |
| 3 | Stop-sequence + truncation (no self-hallucinated observation) | ✅ | `options={'stop':['</args>','Observation:']}`, `truncate_output()` shared |
| 4 | "Step N: running `<cmd>`..." progress output | ✅ | loop tests + live e2e |
| 5 | `pip install` exposes `olla` console-script | ✅ | hatchling src-layout, `.venv/bin/olla` works |
| 6 | `--smoke-test` compliance table across 5 target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive) | ⚠️ **PARTIAL** | Classifier/runner built + unit-tested (8/8); CLI flag wired. **Empirical multi-model run not yet performed** — only `gemma4-uncensored-aggressive` partially exercised (Task 7 single-prompt e2e, not the full `--smoke-test` 2-prompt × 2-think-mode matrix). |

**5/6 fully satisfied.** Criterion 6 — the original "NEEDS RESEARCH-PHASE" empirical bet validation — is the one open item before Phase 1 is fully done per its own roadmap definition.

## Internal Integration (gsd-integration-checker, phase-scoped)

41/41 tests pass. All 4 phase-01 E2E flows (no-tool, tool-call, `--smoke-test`, error-recovery) wired end-to-end, no blockers.

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | WARNING | `loop.py:55-60` ↔ `tools/shell.py:22-28` | WR-01's `"(no output)"` placeholder is dead code on the real success path. `run_shell` always returns `stdout`/`stderr` keys (empty strings) on success, so `loop.py`'s `elif "stdout" in result or "stderr" in result` is always true → `combined = ""` → empty `Observation:` for no-output commands (e.g. `touch file`), instead of the intended `(no output)`. The guarding unit test mocks a `run_shell` return shape (`{"argv":..., "returncode":0}`, no stdout/stderr keys) the real implementation never produces. |
| 2 | WARNING (forward-note) | `loop.py:54` | `parsed["tool"]` (the `<tool>NAME</tool>` value) is parsed but never read — `run_shell` is called unconditionally for any `type=="tool"`. No effect with Phase 1's single tool ("shell"), but Phase 3 (file tools) will need a name-based dispatch layer. |
| 3 | INFO | `loop.py:48` vs `tools/shell.py:17` | Both catch `ValueError` from `shlex.split`, but on the `run_loop` path `loop.py`'s catch fires first — `shell.py`'s catch is only reachable via direct `run_shell` calls, not the loop. Redundant-but-harmless; not a wiring break. |

## Tech Debt (aggregated, carried into backlog)

1. **SC6 empirical smoke-test run** — run `olla --smoke-test --model <name>` against all 5 target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive), record think=False/True compliance %, check for D-08 sub-80% warnings. Tooling is ready; this is a one-time empirical run, not a code change.
2. **Finding 1 (WR-01 gap)** — fix `loop.py`'s combined-output branch so a real no-output success (`stdout=""`, `stderr=""`) actually produces `(no output)` instead of an empty `Observation:`. Likely fix: check `result.get("stdout","") or result.get("stderr","")` truthiness, not key presence.
3. **Finding 2 (tool dispatch)** — before Phase 3 adds a second tool, add a `parsed["tool"]` → handler dispatch in `run_loop` (currently hardcoded to `run_shell`).
4. **IN-01** (01-REVIEW.md) — `smoke.classify_response` checks olla-compliant patterns before native-format patterns; a response containing both is always "compliant". Minor, test-support code only.
5. **IN-02** (01-REVIEW.md) — magic number `80` (D-08 threshold) in `smoke.py` lacks a named constant.

None of these block Phase 2 start. Items 1 and 3 are the most relevant to revisit before declaring v1 fully shipped (item 1 affects model-visible output correctness across all future tools).

## Nyquist

| Phase | VALIDATION.md | Compliant | Action |
|-------|---------------|-----------|--------|
| 01 | exists | true | none — compliant |

## Bottom Line

Phase 01 is solid: all 8 assigned requirements satisfied, 41/41 tests green, 0 open security threats, code review findings (CR-01/02, WR-01/02/03) fixed, internal wiring confirmed with no blockers. One success criterion (SC6, multi-model empirical smoke-test) is partial — tooling done, run not yet executed. Two new minor warnings surfaced (WR-01 dead-code gap, unused tool-name dispatch) for the backlog.

Milestone v1.0 audit (full requirements/integration/flows across all 4 phases) deferred until phases 2-4 are built — running it now would trivially report 12 orphaned requirements for not-yet-started phases.
