---
phase: 02-safety-gate-loop-control
verified: 2026-06-14T00:00:00Z
status: gaps_found
score: 5/5 must-haves verified (on Python >=3.11); 0/5 on declared minimum Python 3.10 due to CR-01
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Round-4 rule (7) dot-segment bypass: chmod/chown -R on '/.', '//.' , '/./', and bonus '/..' , '/foo/..' all now BLOCK via the new os.path.normpath(a).rstrip('/') == '' disjunct added in 02-07 (commit 6ff02cc). Confirmed live across all 6 documented variants plus the no-over-block control (chmod -R 755 /tmp/x stays CONFIRM). 125/125 tests pass (121 prior + 4 new), zero regressions."
  gaps_remaining: []
  regressions:
    - "NEW (not a regression of 02-07's change, but newly surfaced by this round's independent code review): src/olla/safety.py:7 imports typing.NotRequired, which requires Python >=3.11 (PEP 655). pyproject.toml declares requires-python = '>=3.10' with no typing_extensions fallback. On a genuine Python 3.10 interpreter, 'import olla.safety' raises ImportError at module load, which propagates through 'from olla.safety import check' in loop.py and 'from olla.loop import run_loop' in cli.py -- the entire CLI fails to start. This defect predates 02-07 (present since 02-01) but was not caught by any prior verification round because .venv runs Python 3.14."
gaps:
  - truth: "The safety module (and therefore the whole olla CLI) imports and runs successfully on the project's declared minimum supported Python version, so that SAFE-01 through SAFE-04 and LOOP-04 are actually reachable (all five truths depend on `import olla.safety` succeeding)"
    status: failed
    reason: "src/olla/safety.py line 7 is 'from typing import Literal, NotRequired, TypedDict'. typing.NotRequired was added to the stdlib typing module in Python 3.11 (PEP 655) -- it does not exist in Python 3.10's typing module. pyproject.toml declares 'requires-python = \">=3.10\"' (matching CLAUDE.md's stated Python >=3.10 floor) and lists no typing_extensions dependency as a fallback. On a genuine Python 3.10 interpreter this import raises 'ImportError: cannot import name \\'NotRequired\\' from \\'typing\\''. Because loop.py does 'from olla.safety import check' and cli.py does 'from olla.loop import run_loop', this ImportError propagates to CLI startup -- 'import olla' / 'olla <task>' fails before any code runs. Every one of SAFE-01..04 and LOOP-04 is therefore unreachable on Python 3.10, a platform the project explicitly declares supported. This was not caught locally because .venv runs Python 3.14 (where NotRequired exists in stdlib typing)."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Line 7: 'from typing import Literal, NotRequired, TypedDict'; line 12: 'reason: NotRequired[str]'. NotRequired is the only symbol in this file requiring Python >=3.11 -- Literal, TypedDict, list[str], str.removeprefix, X|Y unions are all available on 3.10."
      - path: "pyproject.toml"
        issue: "Line 'requires-python = \">=3.10\"' with dependencies = [\"ollama>=0.6.2\", \"click>=8.1,<9\", \"rich>=13\"] -- no typing_extensions fallback for pre-3.11 NotRequired."
    missing:
      - "Pick one of three fixes (all viable, pick based on project's actual Python-version targeting intent): (1) bump pyproject.toml's requires-python to '>=3.11' and update CLAUDE.md's stated '>=3.10' constraint to match; (2) keep '>=3.10' and add a conditional typing_extensions dependency ('typing_extensions>=4.0; python_version < \"3.11\"') with 'from typing_extensions import NotRequired' (or try/except ImportError fallback) in safety.py; (3) drop NotRequired entirely and use 'class Decision(TypedDict, total=False):' with a comment noting reason is the only optional key (cheapest, slightly weakens the type-checker guarantee that kind is always present)."
      - "Add a regression check (e.g. a tox/CI matrix entry, or at minimum a documented manual verification) that runs 'python -m pytest' (or at least 'python -c \"import olla.safety\"') under the actual declared minimum Python version, so a future re-introduction of a too-new typing/stdlib symbol is caught before merge."
deferred: []
---

# Phase 02: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.

**Verified:** 2026-06-14T00:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — round 5, after 02-07 closed the round-4 rule (7) dot-segment gap (chmod/chown -R on `/.`, `//.`, `/./`). This round confirms that fix is complete and comprehensive, then independently re-derives the SAME equivalent-form-bypass class against rule (4) (`rm`) per WR-01 from the round-5 code review, AND evaluates a separate, newly-surfaced, higher-severity defect (CR-01: `typing.NotRequired` import incompatible with the declared Python >=3.10 floor) that blocks the entire module from importing on the project's own declared minimum platform.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 0 | `import olla.safety` (and therefore `import olla`, and `olla <task>` CLI startup) succeeds on the project's declared minimum Python version (>=3.10) — a precondition for all 5 truths below | FAILED | `src/olla/safety.py:7` imports `NotRequired` from `typing`, which requires Python >=3.11 (PEP 655). `pyproject.toml` declares `requires-python = ">=3.10"`, no `typing_extensions` fallback. On 3.10, `ImportError: cannot import name 'NotRequired' from 'typing'` at module load — propagates through `loop.py` -> `cli.py` to CLI startup. See gap below. |
| 1 | `--dry-run` previews next tool call without executing it or any side effects (SAFE-01) | VERIFIED (on Python >=3.11) | `loop.py` unchanged since round 4 (02-07's `key-files.modified` is only `src/olla/safety.py`, `tests/test_safety.py`; confirmed via SUMMARY). Structurally isolated early-return branch, no `run_shell`/`Confirm.ask` in dry-run path. 125/125 tests pass on this system's Python 3.14. |
| 2 | Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02) | VERIFIED (on Python >=3.11) | Round-4 gap (rule 7 dot-segment bypass) is fully closed — see Behavioral Spot-Checks below for all 6 variants now correctly BLOCK. Rule (4) (`rm`) lacks the same normpath disjunct (`rm -rf /.`, `/..`, `/foo/..` all CONFIRM, not BLOCK) — empirically confirmed, but treated as an accepted residual (not a new gap) per the data-flow finding below: GNU coreutils `rm`'s own `.`/`..`-final-component refusal independently prevents these from executing destructively even under CONFIRM+`--yes`. |
| 3 | `--max-steps` cap (default 15) prevents infinite loops (SAFE-03) | VERIFIED (on Python >=3.11) | `loop.py` unchanged since round 4 — `for step in range(1, max_steps + 1)`, distinct "Reached max steps" diagnostic, `cli.py` `--max-steps` default 15. 125/125 tests pass. |
| 4 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`, does not permit destructive actions to run unattended (SAFE-04) | VERIFIED (on Python >=3.11) | `loop.py` dispatch (lines 116-123) unchanged, correct per D-04. The round-4 `chmod/chown -R /.`-family gap (the prior round's SAFE-04 failure) is closed — these now correctly BLOCK, never reach the CONFIRM+`--yes` unattended-execution path. The `rm -rf /.`-family CONFIRM classification does reach the `--yes` dispatch unattended, but GNU `rm`'s own `.`/`..`-component refusal prevents the destructive side effect (see data-flow trace) — not the same "runs unattended and destroys" scenario as the round-2/3/4 chmod findings. |
| 5 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3x in a row (LOOP-04) | VERIFIED (on Python >=3.11) | `loop.py` lines 97-106 unchanged: `sig = ("shell", tuple(argv))`, `repeat_count >= 3` triggers "same shell call repeated 3x" + `return`. 125/125 tests pass. |

**Score:** 5/5 behavioral truths verified on Python >=3.11 (the interpreter this repo's `.venv` and test suite actually run on). However, Truth 0 — the precondition that `import olla.safety` succeeds on the project's own declared minimum Python version (`>=3.10`, per `pyproject.toml` and `CLAUDE.md`) — FAILS. Per the decision tree (Step 9), one FAILED must-have forces `status: gaps_found` regardless of how many other truths pass. The phase goal ("a user can trust olla with shell execution") is not achievable for any user on a genuine Python 3.10 interpreter, because the CLI does not start.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | Pure `check(argv, yes) -> Decision` blocklist/allowlist gate, D-01..D-04, importable on declared Python floor | PARTIAL | Exists, substantive, wired, and behaviorally correct on Python 3.11+ (confirmed live). Round-4 rule (7) dot-segment fix verified comprehensive (6/6 variants). However, line 7's `from typing import ... NotRequired ...` is incompatible with the declared `requires-python = ">=3.10"` (NotRequired requires 3.11, PEP 655) — fails to import on 3.10. |
| `src/olla/loop.py` | Dispatch BLOCK/CONFIRM/ALLOW correctly, repetition guard, max-steps, dry-run | VERIFIED | Unmodified since round 4 (02-07's `key-files.modified` is `src/olla/safety.py`, `tests/test_safety.py` only). All dispatch logic correct. Imports `from olla.safety import check` — inherits safety.py's import failure on 3.10. |
| `src/olla/tools/shell.py` | `run_shell(argv: list[str], timeout=30)`, pre-parsed argv, no internal re-parse | VERIFIED | Unmodified since round 4. |
| `src/olla/cli.py` | Entry point; imports `run_loop` from `loop`, which imports `check` from `safety` | VERIFIED (existence/wiring) but inherits CR-01 | `cli.py:5 'from olla.loop import run_loop'` -> `loop.py:9 'from olla.safety import check'` -> `safety.py:7 'from typing import ... NotRequired'`. Confirmed via direct grep of all three files. This is the exact propagation path for CR-01's ImportError to CLI startup. |
| `tests/test_safety.py` | Coverage of blocklist/allowlist rules including 02-07 dot-segment hardening | VERIFIED for declared scope | 125 tests total (up from 121), all passing on Python 3.14. Includes the 4 new round-4 regression tests (`test_chmod_recursive_dot_segment_target_blocks`, `test_chown_recursive_dot_segment_target_blocks`, `test_chmod_recursive_double_slash_dot_target_blocks`, `test_chmod_recursive_long_flag_dot_slash_target_blocks`). No test exercises `rm -rf /.`-family (consistent with 02-07's explicit out-of-scope declaration for rule 4), and no test runs the suite under Python 3.10/3.11 to catch CR-01. |
| `tests/test_loop.py` | End-to-end `--yes` BLOCK regressions | VERIFIED for declared scope | Unmodified since round 4, still passing as part of the 125-test suite. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cli.py` | `loop.py` | `from olla.loop import run_loop` (line 5) | WIRED | Confirmed via grep. |
| `loop.py` | `safety.py` | `from olla.safety import check` (line 9) | WIRED, but this is the propagation path for CR-01's ImportError | Confirmed via grep. On Python 3.10, this line itself raises ImportError (transitively, via safety.py's own failed import of `NotRequired`), which aborts `loop.py`'s module load, which aborts `cli.py`'s module load, which aborts `olla` CLI startup entirely. |
| `loop.py` main loop | `safety.check()` | `decision = check(argv, yes=yes)` | WIRED (on Python >=3.11) | Correct call, correct pre-parsed argv. Unchanged since round 4. |
| `safety.check()` decision | `loop.py` dispatch | BLOCK -> never executes; CONFIRM+not yes -> `Confirm.ask`; CONFIRM+yes -> execute; ALLOW -> execute | WIRED (on Python >=3.11) | Dispatch logic correct per D-04, unchanged. |
| `safety._blocklist_match` rule (7) (`chmod`/`chown -R` root-equivalent forms) | `os.path.normpath(a).rstrip("/") == ""` disjunct (new in 02-07) | `any(_normalize_slash_target(a) == "/" or os.path.normpath(a).rstrip("/") == "" for a in argv[1:])` | WIRED | All 6 round-4 dot-segment/doubled-slash-dot variants confirmed BLOCK live (see Behavioral Spot-Checks). Control case (`chmod -R 755 /tmp/x`) confirmed still CONFIRM — no over-blocking. |
| `safety._blocklist_match` rule (4) (`rm` dangerous targets) | `_normalize_slash_target(arg) in _RM_DANGEROUS_TARGETS` (NOT extended with the rule-7 normpath disjunct) | `if _normalize_slash_target(arg) in _RM_DANGEROUS_TARGETS: return ...` | NOT_WIRED for dot-segment forms (by design, per 02-07 plan's explicit out-of-scope declaration) | `check(['rm','-rf','/.'], yes=True)`, `check(['rm','-rf','/..'], yes=True)`, `check(['rm','-rf','/foo/..'], yes=True)` all return `{'kind': 'CONFIRM'}`, not BLOCK. Asymmetric with rule (7) (`chmod -R 777 /.` -> BLOCK). See Data-Flow Trace below for why this is treated as an accepted residual rather than a new gap. |

### Data-Flow Trace (Level 4)

Not applicable in the conventional UI/dynamic-data sense — the equivalent trace is the decision-to-execution path for the `rm -rf /.`-family CONFIRM classification (rule 4), since this is the one place where Levels 1-3 pass (artifact exists, substantive, wired) but a downstream system property determines whether the wiring gap is actually exploitable.

**Trace:** `check(["rm","-rf","/."], yes=True)` returns `{'kind': 'CONFIRM'}` -> `loop.py`'s CONFIRM+`yes=True` branch dispatches to `run_shell(["rm","-rf","/."], ...)` with zero pause -> `subprocess.run(["rm","-rf","/."], shell=False, ...)`.

**Verified empirically on this system (GNU coreutils 9.11, the project's actual dev/target environment)**:
- `rm -rf /.` -> `rm: refusing to remove '.' or '..' directory: skipping '/.'`, exit 0. Nothing deleted.
- `rm -rf /..` -> `rm: refusing to remove '.' or '..' directory: skipping '/..'`, exit 1. Nothing deleted.
- `rm -rf //` -> `rm: it is dangerous to operate recursively on '//' (same as '/')...`, exit 1. Nothing deleted.
- `rm -rfv foo/..` (relative, run in a dir containing `foo/`) -> `rm: refusing to remove '.' or '..' directory: skipping 'foo/..'`, exit 0. `foo` NOT deleted.
- `rm -rf /foo/..` (absolute, `/foo` does not exist) -> exit 0, no protective message printed — but this is because `rm` errors on the nonexistent `/foo` path component before ever reaching the `..`-component check, NOT because `..` is treated permissively. No deletion occurs in this case either, for an unrelated reason (the path doesn't exist).

**Conclusion:** GNU `rm` itself refuses to act on ANY argument whose final path component is literally `.` or `..`, independent of `safety.py`'s classification. This is `rm`'s own hardcoded safety behavior (distinct from, and broader than, the `--preserve-root`-for-`/`-specifically default cited in 02-07's T-02-07-03 rationale — the actual backstop here is the `.`/`..`-final-component skip, which `--preserve-root` does not control). So while `check(["rm","-rf","/."], yes=True)` returns CONFIRM rather than BLOCK (an asymmetry with rule 7's now-stricter `chmod`/`chown` handling), the data-flow trace shows the destructive side effect does NOT actually occur on this system when this CONFIRM is auto-approved under `--yes` — unlike the round-2/3/4 `chmod -R /.`-family findings, where `chmod` has no equivalent self-protection and the recursive permission change DID actually execute. **STATUS: ⚠️ accepted residual (WR-01), not promoted to a gap** — see Anti-Patterns and Gaps Summary for the precision caveat on `T-02-07-03`'s stated rationale.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Round-4 gap CLOSED: `chmod -R 777 /.` | `check(['chmod','-R','777','/.'], yes=True)` | `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` | PASS |
| Round-4 gap CLOSED: `chown -R user /.` | `check(['chown','-R','user','/.'], yes=True)` | `{'kind': 'BLOCK', 'reason': "'chown -R' targeting '/' is destructive"}` | PASS |
| Round-4 gap CLOSED: `chmod -R 777 //.` | `check(['chmod','-R','777','//.'], yes=True)` | `{'kind': 'BLOCK', ...}` | PASS |
| Round-4 gap CLOSED: `chmod --recursive 777 /./` | `check(['chmod','--recursive','777','/./'], yes=True)` | `{'kind': 'BLOCK', ...}` | PASS |
| Bonus dot-segment variants now also covered by normpath disjunct: `chmod -R 777 /..`, `chmod -R 777 /foo/..` | `check(['chmod','-R','777','/..'], yes=True)` / `check(['chmod','-R','777','/foo/..'], yes=True)` | Both `{'kind': 'BLOCK', ...}` | PASS — confirms the round-4 fix is principled (covers the whole "normalizes to /" class), not a narrow whack-a-mole patch |
| No-over-block control | `check(['chmod','-R','755','/tmp/x'], yes=True)` | `{'kind': 'CONFIRM'}` | PASS — fix does not over-block legitimate targets |
| WR-01: `rm -rf /.`, `rm -rf /..`, `rm -rf /foo/..` | `check(['rm','-rf','/.'], yes=True)` etc. | All `{'kind': 'CONFIRM'}` | Confirmed asymmetric with chmod/chown (rule 7), but see Data-Flow Trace — `rm`'s own `.`/`..` refusal independently prevents the destructive effect. Accepted residual, not a new gap. |
| CR-01: static import check | `grep -n "NotRequired" src/olla/safety.py` | Line 7: `from typing import Literal, NotRequired, TypedDict`; line 12: `reason: NotRequired[str]` | FAIL (on declared Python >=3.10 floor) |
| CR-01: import chain to CLI | `grep -n "^from\|^import" src/olla/cli.py src/olla/loop.py` | `cli.py:5 from olla.loop import run_loop`; `loop.py:9 from olla.safety import check` | Confirms ImportError on safety.py propagates to `loop.py` and `cli.py` module load |
| CR-01: NotRequired availability | `grep NotRequired /usr/lib/python3.14/typing.py` -> found (3.14 has it) | PEP 655 (NotRequired) landed in Python 3.11; absent from 3.10's stdlib typing | No 3.10/3.11 interpreter available on this system to directly reproduce the ImportError (`which python3.10 python3.11` -> none found), but the PEP-655/Python-3.11 fact is well-established and the code's unconditional import + lack of typing_extensions fallback is directly observable |
| Full test suite | `.venv/bin/python -m pytest tests/ -q` | `125 passed in 1.86s` | PASS on Python 3.14 — confirms zero regressions from 02-07, but does not (and cannot, on this system) exercise the declared Python 3.10 floor |

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository, and neither PLAN nor SUMMARY for this phase declares probe-based verification. Step 7c: SKIPPED (no declared or conventional probes).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-04 | 02-01/02-02 | Repetition guard aborts loop after 2-3x identical tool+args | SATISFIED (on Python >=3.11); BLOCKED on declared Python >=3.10 due to CR-01 | `loop.py` lines 97-106 unchanged, distinct diagnostic confirmed, 125/125 tests pass. But `loop.py` imports `safety`, which fails to import on 3.10 — `run_loop` is unreachable on the declared minimum platform. |
| SAFE-01 | 02-01/02-02 | `--dry-run` previews next call, no side effects | SATISFIED (on Python >=3.11); BLOCKED on declared Python >=3.10 due to CR-01 | Same as above. |
| SAFE-02 | 02-02/02-04/02-05/02-06/02-07 | Shell command blocklist (rm -rf /, sudo, dd, etc.) as speed-bump layer | SATISFIED (on Python >=3.11); BLOCKED on declared Python >=3.10 due to CR-01 | Round-4 rule-7 dot-segment gap fully closed (6/6 variants BLOCK, confirmed live). `rm -rf /.`-family asymmetry (rule 4) confirmed but accepted as residual per data-flow trace. But `safety.py` itself fails to import on 3.10, so the entire blocklist is unreachable on the declared minimum platform. |
| SAFE-03 | 02-01/02-02 | `--max-steps` cap (default 15) prevents infinite loops | SATISFIED (on Python >=3.11); BLOCKED on declared Python >=3.10 due to CR-01 | `loop.py` unchanged, `cli.py` default 15, confirmed. Same CR-01 unreachability. |
| SAFE-04 | 02-01/02-02/02-04/02-05/02-06/02-07 | Confirm prompt before shell/write_file, overridable with `--yes` | SATISFIED (on Python >=3.11); BLOCKED on declared Python >=3.10 due to CR-01 | `loop.py` dispatch correct per D-04; round-4 chmod/chown `/.`-family gap (the prior SAFE-04 failure) is closed. Same CR-01 unreachability. |

All 5 requirement IDs declared across 02-01 through 02-07 PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability rows exactly (all marked "Pending" in REQUIREMENTS.md). No orphaned requirements.

02-07's SUMMARY claims `requirements-completed: [SAFE-02, SAFE-04]` for its own (round-4 dot-segment) scope — that claim is accurate and confirmed for the 6 chmod/chown variants it targeted. However, all 5 requirements as overall phase deliverables are now gated on CR-01: a defect that predates 02-07 (present since 02-01, in `safety.py`'s original `Decision` TypedDict definition) but was not caught by rounds 1-4's verification because none of them ran (or could run, given `.venv`'s Python 3.14) the test suite under the project's declared Python >=3.10 floor.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 7, 12 | `from typing import Literal, NotRequired, TypedDict` / `reason: NotRequired[str]` — `NotRequired` (PEP 655) requires Python >=3.11; `pyproject.toml` declares `requires-python = ">=3.10"` with no `typing_extensions` fallback | BLOCKER | `import olla.safety` raises `ImportError` on Python 3.10, which propagates through `loop.py` and `cli.py` to CLI startup — the entire `olla` CLI fails to start on the project's own declared minimum supported Python version. This is strictly more severe than any single blocklist-rule bypass, because it prevents ALL of SAFE-01..04 and LOOP-04 from being reachable at all on that platform. |
| `src/olla/safety.py` | 47-53, 183-186 | `_RM_DANGEROUS_TARGETS` / rule (4) (`rm`) was not extended with the `os.path.normpath(a).rstrip("/") == ""` disjunct that rule (7) (`chmod`/`chown`) gained in 02-07 — `rm -rf /.`, `/..`, `/foo/..` remain CONFIRM while the equivalent `chmod -R /.`-family now correctly BLOCKs | WARNING (accepted residual, WR-01) | Asymmetric coverage between rule 4 and rule 7 for the same equivalent-form class. However, the data-flow trace shows GNU `rm`'s own `.`/`..`-final-component refusal independently prevents the destructive effect on this system — so the asymmetry is a coverage inconsistency, not a live unattended-destruction path, unlike the chmod/chown findings rounds 2-4 fixed. T-02-07-03's stated rationale ("`--preserve-root` default") is imprecise (the actual backstop is the `.`/`..`-component skip, a different `rm` behavior than `--preserve-root`) but the protective conclusion holds. Recommend tightening for defense-in-depth and to remove the asymmetry, but not phase-blocking. |
| `src/olla/safety.py` | 75, 110-132 | `env -S "<command>"` remains CONFIRM by design — same wrap-and-recurse class as the bash-`-c` fix, documented as accepted residual (T-02-07-05) | WARNING | Pre-existing, explicitly accepted residual, carried forward unchanged from round 4. Not re-reported as a new gap per round-5 instructions. |
| `src/olla/safety.py` | rule 6b recursion | Shell-chained `-c` strings (`bash -c "true; sudo rm -rf /"`) bypass rule 6b's single-command recursion — `argv[0]` of the shlex-split result is `"true;"`, not `"sudo"` — documented accepted residual (T-02-06-05 / T-02-07-04) | WARNING | Pre-existing, explicitly accepted residual, carried forward unchanged from round 4. Not re-reported as a new gap per round-5 instructions. |
| `src/olla/safety.py` | `_blocklist_match` recursion (env/find -exec/bash -c) | No explicit recursion-depth limit | INFO | Low-probability input shape for small local models; carried forward unchanged, not phase-blocking. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers found in `src/olla/safety.py` or `tests/test_safety.py` (`grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` -> no matches in either file).

### Human Verification Required

None. All findings in this report are reproducible programmatically via direct `safety.check()` calls, static grep of import statements, and the documented PEP-655/Python-version-history fact for `typing.NotRequired` (no UI, real-time, or external-service behavior is involved). A definitive empirical reproduction of CR-01's `ImportError` would require a genuine Python 3.10 or 3.11 interpreter, which is not available on this system (`which python3.10 python3.11 python3.12 python3.13` -> none found; `.venv` runs 3.14, where `NotRequired` exists). This does not block the finding's classification as FAILED — the import statement and the PEP-655 version requirement are both directly observable facts, not matters of opinion or UI judgment.

### Gaps Summary

**Round-4 gap CLOSED, comprehensively:** 02-07 (commits `be792e9` test-RED, `6ff02cc` feat-GREEN) added `os.path.normpath(a).rstrip("/") == ""` as a second disjunct to rule (7)'s root-target detection. This closes not just the 3 originally-identified dot-segment forms (`/.`, `//.`, `/./`) but the entire "normalizes to `/` or `//`" class — confirmed live for `/..` and `/foo/..` as well, which were not explicitly enumerated in 02-07's plan but pass correctly because `os.path.normpath` resolves them the same way. The no-over-block control (`chmod -R 755 /tmp/x` -> CONFIRM) still holds. 125/125 tests pass (4 new + 121 prior), zero regressions. This gap is fully and correctly closed.

**WR-01 (rule-4/rm dot-segment asymmetry): assessed independently, NOT promoted to a new gap.** The empirical claim is true — `rm -rf /.`, `/..`, `/foo/..` are CONFIRM while the equivalent `chmod -R .../.`-family is now BLOCK, an asymmetry within the same "equivalent-form root target" class this phase has hardened 3 times (rounds 2, 3, 4) for other rules/binaries. However, the data-flow trace (Level 4) to actual execution shows this asymmetry does not translate into a live unattended-destruction path on this system: GNU coreutils `rm` itself refuses to operate on any argument whose final path component is literally `.` or `..` (verified empirically: `rm -rf /.`, `/..`, and relative `foo/..` all print `refusing to remove '.' or '..' directory` and exit without deleting anything). This is `rm`'s own independent safety behavior — distinct from (and broader than) the `--preserve-root`-for-bare-`/` default that 02-07's T-02-07-03 rationale cites, but the protective conclusion (no destructive side effect occurs) holds. Combined with PROJECT.md's explicit "speed-bump, not the primary boundary" framing for the blocklist and the already-documented acceptance of T-02-07-03, this is recorded as a WARNING-level coverage inconsistency (worth fixing for defense-in-depth and consistency) rather than a phase-blocking gap. Recommend tightening rule (4) with the same `os.path.normpath` disjunct in a future round regardless, both for consistency and because the protective backstop is a property of the *target system's* `rm`, not of `safety.py` itself.

**CR-01 (typing.NotRequired / Python 3.10 incompatibility): NEW BLOCKER.** `src/olla/safety.py:7` imports `NotRequired` from `typing` — a symbol added in Python 3.11 (PEP 655) — while `pyproject.toml` declares `requires-python = ">=3.10"` (matching CLAUDE.md's stated floor) with no `typing_extensions` fallback. On a genuine Python 3.10 interpreter, `import olla.safety` raises `ImportError` at module load. Because `loop.py` does `from olla.safety import check` and `cli.py` does `from olla.loop import run_loop`, this ImportError propagates to CLI startup — `olla` does not run at all on Python 3.10. This defect predates 02-07 (present since 02-01's original `Decision` TypedDict definition) but was not caught by rounds 1-4's verification because `.venv` runs Python 3.14, where `NotRequired` is available in stdlib `typing`.

This is judged in-scope for this phase's must-haves: every one of LOOP-04, SAFE-01, SAFE-02, SAFE-03, and SAFE-04 is implemented in/reached through `safety.py` and `loop.py`, both of which fail to import on the declared minimum platform. "A user can trust olla with shell execution" (the phase goal) cannot be evaluated at all for a user on Python 3.10 — the CLI never starts. This is a single isolated import-line defect (one symbol), trivially fixable via any of three documented options (bump floor to 3.11, add typing_extensions fallback, or use `TypedDict, total=False`), but it is observably FAILED, not UNCERTAIN — the import statement and PEP-655's version requirement are both directly verifiable facts, independent of which fix the team chooses.

**Step 9b (deferral check):** No later phase (Phase 3: File Tools, Phase 4: Memory Tool, per the milestone roadmap) addresses Python-version-compatibility of the safety module or rule-4/rm target normalization. Deferral does not apply.

**Overall status:** `gaps_found`, with CR-01 as the sole blocker. Once CR-01 is fixed (any of the three documented options), all 5 behavioral truths are already VERIFIED (confirmed on Python 3.14, and the fix options for CR-01 do not touch any of the blocklist logic itself) — re-verification after a CR-01 fix should be a fast confirmation pass, not a full re-derivation.

---

_Verified: 2026-06-14T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
