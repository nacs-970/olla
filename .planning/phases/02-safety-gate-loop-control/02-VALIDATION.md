---
phase: 02
slug: safety-gate-loop-control
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 with pytest-mock (`mocker` fixture) — already in use, see `tests/test_loop.py`, `tests/test_cli.py` |
| **Config file** | none — `pyproject.toml` has no `[tool.pytest.ini_options]`; default discovery via `test_*.py` |
| **Quick run command** | `python3 -m pytest tests/test_safety.py tests/test_loop.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (small unit-test suite, all mocked — no real subprocess/model calls) |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_safety.py tests/test_loop.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

> Task ID / Plan / Wave columns are TBD — populate once `/gsd:plan-phase` generates PLAN.md files and assigns task IDs to these requirements.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SAFE-04 | T-02-02 | CONFIRM-tier command prompts via `Confirm.ask`; `--yes` skips prompt; declined command produces observation+continue (D-04) | unit | `python3 -m pytest tests/test_loop.py -k confirm -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SAFE-04 | T-02-03 | `Confirm.ask` raising `EOFError` (non-TTY stdin) is treated as decline, not a crash | unit | `python3 -m pytest tests/test_loop.py -k eof -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SAFE-02 | T-02-01 | Each D-03 blocklist rule blocks its example command; non-matching commands pass through | unit | `python3 -m pytest tests/test_safety.py -x` | ❌ W0 (new file) | ⬜ pending |
| TBD | TBD | TBD | SAFE-02 | T-02-01 | D-04: blocked command produces `"blocked by safety policy: <reason>"` observation regardless of `--yes` | unit | `python3 -m pytest tests/test_loop.py -k block -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SAFE-01 | — | `--dry-run` makes exactly one model call, prints `"Step 1 would run: <argv> -- <verdict>"`, never calls `run_shell` | unit | `python3 -m pytest tests/test_loop.py -k dry_run -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SAFE-01 | — | `--dry-run` with `<final>` first response prints `"Model would answer directly: ..."` and stops | unit | `python3 -m pytest tests/test_loop.py -k dry_run_final -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | LOOP-04 | T-02-04 | 3 identical `(tool, resolved-argv)` calls in a row abort with the D-07 diagnostic, distinct from max-steps message | unit | `python3 -m pytest tests/test_loop.py -k repetition -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SAFE-03 | — | `--max-steps` regression — still produces its own distinct message | unit | `python3 -m pytest tests/test_loop.py -k max_steps -x` | ✅ existing (`test_run_loop_max_steps_no_final`) | ⬜ pending |
| TBD | TBD | TBD | D-01/D-02 | T-02-02 | `argv[0]` in read-only allowlist → ALLOW decision, no prompt | unit | `python3 -m pytest tests/test_safety.py -k allowlist -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | (regression) | — | `test_dry_run_flag_prints_inert_notice` / `test_yes_flag_prints_inert_notice` rewritten to assert real enforcement (placeholder strings removed) | unit | `python3 -m pytest tests/test_cli.py -x` | ⚠️ EXISTS, must be REWRITTEN | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_safety.py` — new file, covers SAFE-02 blocklist rule table + D-01/D-02 allowlist + `check()` decision ordering (BLOCK > ALLOW > CONFIRM)
- [ ] `tests/test_loop.py` — additions: confirm-gate (mock `Confirm.ask`), EOFError handling, repetition guard (LOOP-04), `--dry-run` single-step preview (SAFE-01), blocked-command observation (D-04)
- [ ] `tests/test_cli.py` — REWRITE `test_dry_run_flag_prints_inert_notice` and `test_yes_flag_prints_inert_notice` to assert real enforcement (Pitfall 2); update any tests asserting exact `run_loop(...)` call signatures if new `yes`/`dry_run` params are added

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
