---
phase: 02
slug: safety-gate-loop-control
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-12
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 with pytest-mock (`mocker` fixture) — see `tests/test_loop.py`, `tests/test_cli.py`, `tests/test_safety.py` |
| **Config file** | none — `pyproject.toml` has no `[tool.pytest.ini_options]`; default discovery via `test_*.py` |
| **Quick run command** | `PYTHONPATH=src python3 -m pytest tests/test_safety.py tests/test_loop.py -x -q` |
| **Full suite command** | `PYTHONPATH=src python3 -m pytest tests/ -q` |
| **Estimated runtime** | ~2 seconds (127 tests, 1.69s observed — all mocked, no real subprocess/model calls) |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH=src python3 -m pytest tests/test_safety.py tests/test_loop.py -x -q`
- **After every plan wave:** Run `PYTHONPATH=src python3 -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SAFE-02 | 02-SECURITY.md | `check(argv, yes)` classifies BLOCK/ALLOW/CONFIRM per D-01/D-03 rule table | unit | `pytest tests/test_safety.py -v` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | SAFE-02, SAFE-04 | 02-SECURITY.md | BLOCK/CONFIRM/ALLOW dispatch wired into `run_loop`; EOFError-safe confirm prompt | unit | `pytest tests/test_loop.py -v` | ✅ | ✅ green |
| 02-01-03 | 01 | 1 | SAFE-04 | 02-SECURITY.md | `--yes` threaded cli -> run_loop; inert "not yet enforced" notice removed | unit | `pytest tests/test_cli.py -v` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | SAFE-01 | 02-SECURITY.md | `--dry-run` single-call preview reuses `safety.check()` for an honest verdict, no execution | unit | `pytest tests/test_loop.py -v -k "dry_run or tool_then_final or max_steps_no_final"` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | LOOP-04, SAFE-03 | 02-SECURITY.md | 3x-repeat repetition guard with diagnostic distinct from max-steps; `--dry-run` cli wiring; max-steps regression | unit | `pytest tests/test_loop.py tests/test_cli.py -v` | ✅ | ✅ green |
| 02-03-01 | 03 | 1 | SAFE-02 | 02-SECURITY.md | env/find ALLOWLIST-bypass closed (CR-01 r1); fork-bomb unspaced-variant detection (WR-02) | unit | `PYTHONPATH=src pytest tests/test_safety.py -v` | ✅ | ✅ green |
| 02-03-02 | 03 | 1 | LOOP-04 | 02-SECURITY.md | repetition guard covers BLOCK and declined-CONFIRM repeats (WR-01) | unit | `PYTHONPATH=src pytest tests/test_loop.py -v -k "repetition or repeated or block_interrupted or max_steps_with_varied"` | ✅ | ✅ green |
| 02-04-01 | 04 | 1 | SAFE-02 | 02-SECURITY.md | narrower env/find unwrap under `--yes` (CR-01 r2); fork-bomb data-arg false-positive fix (WR-02 r2); chmod/chown -Rf bypass (WR-03) | unit | `PYTHONPATH=src pytest tests/test_safety.py -v` | ✅ | ✅ green |
| 02-04-02 | 04 | 1 | SAFE-02, SAFE-04 | 02-SECURITY.md | `run_shell` accepts pre-parsed argv (IN-01); loop-level `--yes` regression for CR-01 | unit | `PYTHONPATH=src pytest tests/ -q` | ✅ | ✅ green |
| 02-05-01 | 05 | 1 | SAFE-02 | 02-SECURITY.md | bash/sh/zsh -c wrap-and-recurse closed (CR-01 r3); chmod/chown -R `//` (CR-02); dd/mkfs `//dev/*` (CR-03) | unit | `PYTHONPATH=src pytest tests/test_safety.py -v` | ✅ | ✅ green |
| 02-05-02 | 05 | 1 | SAFE-02, SAFE-04 | 02-SECURITY.md | end-to-end `--yes` regression for CR-01 r3 | unit | `PYTHONPATH=src pytest tests/ -q` | ✅ | ✅ green |
| 02-06-01 | 06 | 1 | SAFE-02 | 02-SECURITY.md | combined short-flag `bash -lc`/`sh -ic`/`zsh -xc` (CR-01 r4); chmod/chown -R `//` target (CR-02 r4); `dd`/`mkfs of=//dev/sda` (CR-03 r4) | unit | `PYTHONPATH=src pytest tests/test_safety.py -q` | ✅ | ✅ green |
| 02-06-02 | 06 | 1 | SAFE-02, SAFE-04 | 02-SECURITY.md | e2e `--yes` regression for combined-flag `bash -lc` bypass | unit | `PYTHONPATH=src pytest tests/ -q` | ✅ | ✅ green |
| 02-07-01 | 07 | 1 | SAFE-02 | 02-SECURITY.md | dot-segment equivalent root-target forms on rule 7 — `/.`, `//.`, `/./` (CR-02 r5) | unit | `PYTHONPATH=src pytest tests/ -q` | ✅ | ✅ green |
| 02-08-01 | 08 | 1 | LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04 | 02-SECURITY.md | drop `NotRequired` (PEP 655, py3.11+) -> `TypedDict(total=False)` for `>=3.10` import compat (CR-01 r6, final); static regression test against future PEP-655 reintroduction | unit | `PYTHONPATH=src pytest tests/ -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — `tests/test_safety.py`, `tests/test_loop.py`, `tests/test_cli.py` and the pytest/pytest-mock setup were established in 02-01 and extended in-place by every subsequent gap-closure plan; no separate Wave 0 bootstrap was needed.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-06-14

---

## Validation Audit 2026-06-14

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 15 tasks across 8 plans (02-01 through 02-08) carry `<automated>` pytest verify commands. Full suite `PYTHONPATH=src python3 -m pytest tests/ -q` confirms 127/127 passing at audit time (06-14), matching 02-VERIFICATION.md round 6 (`status: passed`). No COVERED→PARTIAL/MISSING regressions found; reconstructed from PLAN+SUMMARY artifacts (State B reconstruction performed despite an existing pre-execution draft VALIDATION.md, since the draft's Per-Task Map was entirely `TBD`/placeholder).
