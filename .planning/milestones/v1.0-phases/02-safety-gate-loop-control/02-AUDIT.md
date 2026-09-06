---
phase: 02-safety-gate-loop-control
audited: 2026-06-14
scope: phase-02-checkpoint
note: "Milestone v1.0 now 50% complete (2/4 phases). Full v1.0-MILESTONE-AUDIT deferred until phases 3-4 land. This is a phase-02 checkpoint only."
status: tech_debt
scores:
  requirements: 5/5
  success_criteria: 4/4
  internal_integration: 8/8 links wired, 8/8 E2E flows complete, 0 blockers, 0 new warnings
nyquist:
  compliant_phases: [01, 02]
  partial_phases: []
  missing_phases: []
  overall: COMPLIANT
---

# Phase 02 Checkpoint Audit

## Requirements Coverage (3-source cross-check)

| REQ-ID | SUMMARY frontmatter | VALIDATION.md | REQUIREMENTS.md | Status |
|--------|---------------------|----------------|-------------------|--------|
| LOOP-04 | listed (02-02/02-03/02-08) | ✅ green | Complete (updated) | **satisfied** |
| SAFE-01 | listed (02-02/02-08) | ✅ green | Complete (updated) | **satisfied** |
| SAFE-02 | listed (02-01/02-03/02-04/02-05/02-06/02-07/02-08) | ✅ green | Complete (updated) | **satisfied** |
| SAFE-03 | listed (02-02/02-08) | ✅ green | Complete (updated) | **satisfied** |
| SAFE-04 | listed (02-01/02-02/02-03/02-04/02-05/02-06/02-07/02-08) | ✅ green | Complete (updated) | **satisfied** |

REQUIREMENTS.md traceability table was stale (all 5 still showed "Pending" despite 02-VERIFICATION.md round 6 `status: passed` and 02-VALIDATION.md `nyquist_compliant: true`) — corrected in this audit.

No orphans: cross-referenced against REQUIREMENTS.md Phase 2 rows (LOOP-04, SAFE-01..04) — exact match, 5/5.

## Success Criteria (ROADMAP Phase 2, 4 total)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Confirm prompt shows fully-resolved command before shell execution; decline supported; `--yes` skips | ✅ | SAFE-04 — `Confirm.ask` dispatch, EOFError-safe decline, `--yes` wired e2e |
| 2 | Blocklisted command (`rm -rf /`, `sudo`, `dd`, etc.) caught as speed-bump before confirm prompt | ✅ | SAFE-02 — `_blocklist_match` covers rules 1-7 incl. all gap-closure rounds 1-5 |
| 3 | `--dry-run` shows next planned tool call, stops, no side effects | ✅ | SAFE-01 — 7 dry-run sub-flows tested (final/none/unknown-tool/ALLOW/CONFIRM/BLOCK/malformed-args) |
| 4 | Loop aborts with diagnostic at `--max-steps` (default 15) or 2-3x identical tool+args repeat | ✅ | SAFE-03 + LOOP-04 — distinct diagnostics, repetition guard fires independent of ALLOW/CONFIRM/BLOCK |

**4/4 fully satisfied.** Unlike Phase 1 (5/6, SC6 empirical smoke-test deferred), Phase 2 closes clean on all stated success criteria.

## Internal Integration (gsd-integration-checker, phase 1+2 scope)

8/8 pipeline links WIRED (CLI -> run_loop -> parser -> safety.check -> dispatch -> run_shell -> observation -> next iteration). 8/8 E2E flows COMPLETE (no-tool/final, tool-then-final, BLOCK, CONFIRM-decline, CONFIRM-accept/`--yes`, dry-run, max-steps, repetition-guard). 0 blockers, 0 new warnings. 127/127 tests pass.

Both findings carried forward from the Phase 1 checkpoint (01-AUDIT.md) are addressed by Phase 2's work on `loop.py`:

| # | Finding | Status |
|---|---------|--------|
| 1 | WR-01 — `loop.py`'s `(no output)` placeholder was dead code on the real `run_shell` return shape | **RESOLVED** — now `combined = result.get("stdout","") + result.get("stderr",""); if not combined: combined = "(no output)"`, tested against the real return shape (`test_run_loop_tool_result_real_no_output_success`) |
| 2 | `parsed["tool"]` parsed but never read; `run_shell` called unconditionally for any `type=="tool"` | **RESOLVED** (defect) — `loop.py:84` now checks `parsed["tool"] != "shell"`, unknown tools rejected with an Observation, `run_shell` not called. Forward-note (real dispatch table needed before Phase 3 adds a 2nd tool) still stands as a Phase 3 design item, not a current gap. |

## Tech Debt (aggregated, carried into backlog)

1. **SC6 empirical smoke-test run** (carried from 01-AUDIT.md, untouched by Phase 2) — still PARTIAL/OPEN. 0.6B-4B Qwen3 range and `gemma4:e2b` remain untested; revisit when smaller models are available.
2. **WR-01 (02-VERIFICATION round 6)** — `Decision(TypedDict, total=False)` widens `kind` to optional too (only `reason` needed it). Zero runtime impact (`check()` sets `kind` on all 4 paths). Recommend base-class split (`_DecisionBase` with required `kind` + `Decision(_DecisionBase, total=False)` with `reason`) as low-cost future hardening.
3. **WR-02 (02-VERIFICATION round 6)** — `test_safety_module_has_no_python311_only_typing_symbols` calls `open(source_path)` without `encoding="utf-8"`; reproducibly raises `UnicodeDecodeError` under `LC_ALL=C PYTHONUTF8=0` (safety.py contains 8 em-dashes). Passes on this dev machine's UTF-8 locale (127/127 green) but is a latent CI/locale fragility in the regression guard itself. Fix: add `encoding="utf-8"`.
4. **IN-01/IN-02 (02-VERIFICATION round 6)** — `test_decision_is_importable` structurally can't fail independently (an import-time failure would fail collection first); `test_safety_module_has_no_python311_only_typing_symbols` name implies broader 3.11+ coverage than it checks. Both cosmetic, no functional impact.
5. **Accepted residuals carried from round 5, not re-litigated** — rule-4 `rm -rf /.`-family vs rule-7 `chmod/chown` asymmetry; `env -S` wrap-and-recurse (T-02-07-05); shell-chained `-c` bypass of rule 6b (T-02-06-05/T-02-07-04); recursion-depth limit on `_blocklist_match` (INFO). All documented in 02-SECURITY.md as accepted residual risk — blocklist is a speed-bump by design (SAFE-02), not the primary safety boundary.
6. **01-REVIEW.md IN-01/IN-02** (carried, not re-verified this round) — `smoke.classify_response` pattern-check ordering; magic number `80` (D-08 threshold) lacks a named constant. Test-support code only.

None of these block Phase 3 start.

## Nyquist

| Phase | VALIDATION.md | Compliant | Action |
|-------|---------------|-----------|--------|
| 01 | exists | true | none — compliant |
| 02 | exists | true | none — compliant |

## Bottom Line

Phase 02 is solid: all 5 assigned requirements satisfied (LOOP-04, SAFE-01..04), all 4 ROADMAP success criteria fully met (the safety gate, confirm-prompt, dry-run, max-steps, and repetition guard all work end-to-end), 127/127 tests green, 8/8 integration links wired with 0 blockers across 6 gap-closure rounds. Both Phase 1 carry-forward integration findings are resolved. Remaining items are accumulated tech debt (Phase 1's SC6 empirical smoke-test still open, plus a handful of WARNING/INFO-level type-checker and test-robustness nits from Phase 2's round-6 review) — none phase-blocking.

Milestone v1.0 audit (full requirements/integration/flows across all 4 phases) deferred until phases 3-4 are built — running it now would trivially report 3 orphaned requirements (FILE-01, FILE-02, MEM-01) for not-yet-started phases.
