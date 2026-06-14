---
phase: 02-safety-gate-loop-control
verified: 2026-06-14T01:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: "5/5 must-haves verified (on Python >=3.11); 0/5 on declared minimum Python 3.10 due to CR-01"
  gaps_closed:
    - "CR-01 (typing.NotRequired / Python 3.10 import incompatibility): src/olla/safety.py line 7 now reads 'from typing import Literal, TypedDict' (NotRequired removed entirely); Decision is now 'class Decision(TypedDict, total=False):' with reason: str. import olla.safety -> olla.loop -> olla.cli chain contains zero Python-3.11-only typing symbols anywhere in src/olla/ (verified by whole-package scan, not just safety.py). check() classification and reason strings are byte-identical to pre-fix (confirmed: ls->ALLOW, rm -rf /->BLOCK with reason, git status->CONFIRM, sudo ls yes=True->BLOCK with reason). 127/127 tests pass, zero regressions."
  gaps_remaining: []
  regressions: []
deferred: []
---

# Phase 02: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.

**Verified:** 2026-06-14T01:00:00Z
**Status:** passed
**Re-verification:** Yes — round 6, after 02-08 closed the sole round-5 blocker (CR-01: `typing.NotRequired` / Python 3.10 import incompatibility).

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 0 | `import olla.safety` (and therefore `import olla`, and `olla <task>` CLI startup) succeeds on the project's declared minimum Python version (>=3.10) — a precondition for all 5 truths below | VERIFIED | `src/olla/safety.py:7` now reads `from typing import Literal, TypedDict` — `NotRequired` removed entirely (`grep -c NotRequired src/olla/safety.py` = 0, `grep -c "Required\[" src/olla/safety.py` = 0). `Decision` is `class Decision(TypedDict, total=False):` (both `TypedDict` and `total=False` available since Python 3.8). **Whole-chain scan** (not just safety.py, per advisor guidance — round 5's masked-symbol risk): grepped every `from typing import` / `import` line across all of `src/olla/` (`cli.py`, `loop.py`, `parser.py`, `prompts.py`, `safety.py`, `smoke.py`, `tools/base.py`, `tools/shell.py`, `tools/__init__.py`, `__init__.py`) — only two `typing` imports in the entire package: `safety.py:7` (`Literal, TypedDict`) and `tools/base.py:3` (`TypedDict`), both 3.10-safe. A separate scan for `NotRequired\|Required[\|Self\|assert_type\|assert_never\|LiteralString\|TypeVarTuple\|Unpack\|dataclass_transform\|tomllib\|StrEnum\|except*\|reveal_type\|ExceptionGroup\|TaskGroup` across `src/olla/` returns zero matches. `str \| None` (PEP 604) and `list[str]` (PEP 585) used in safety.py are both valid on Python >=3.10. The entire `cli.py -> loop.py -> {parser, safety, tools.shell -> tools.base}` import chain contains no Python-3.11-only symbols anywhere. |
| 1 | `--dry-run` previews next tool call without executing it or any side effects (SAFE-01) | VERIFIED | `loop.py` unmodified since 02-04 (`git log --oneline -- src/olla/loop.py` shows last commit `6ebaa52`, predating rounds 5/6). Structurally isolated early-return branch, no `run_shell`/`Confirm.ask` in dry-run path. 127/127 tests pass. |
| 2 | Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02) | VERIFIED | `_blocklist_match` (lines 158-248) unchanged from round 5 (02-08's diff touches only lines 7 and 10-15, the import and `Decision` class). All round-4 dot-segment fixes (rule 7) and prior rule coverage remain intact. WR-01 (rule-4 `rm -rf /.`-family residual) carried forward unchanged, accepted in round 5, not re-litigated here. |
| 3 | `--max-steps` cap (default 15) prevents infinite loops (SAFE-03) | VERIFIED | `loop.py` unchanged — `for step in range(1, max_steps + 1)`, distinct "Reached max steps" diagnostic, `cli.py` `--max-steps` default 15. 127/127 tests pass. |
| 4 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`, does not permit destructive actions to run unattended (SAFE-04) | VERIFIED | `loop.py` dispatch (lines 60-65, 110-123) unchanged and correct per D-04. `decision["kind"]` and `decision["reason"]` accesses (lines 60, 62, 65, 110, 111, 116) all function correctly under the now-`total=False` `Decision` TypedDict — `TypedDict` performs zero runtime key enforcement either way, and `check()` sets `kind` on every one of its 4 return paths and `reason` on both BLOCK paths (confirmed by direct inspection of `check()` lines 251-267). Empirically confirmed: `check(['sudo','ls'], True)` -> `{'kind': 'BLOCK', 'reason': "'sudo' is blocked outright (no safe invocation)"}`. |
| 5 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3x in a row (LOOP-04) | VERIFIED | `loop.py` repetition-guard logic unchanged: `sig = ("shell", tuple(argv))`, `repeat_count >= 3` triggers "same shell call repeated 3x" + `return`. 127/127 tests pass. |

**Score:** 5/5 truths verified. Truth 0 (the precondition gating all others, and the sole round-5 blocker CR-01) is now VERIFIED via static analysis of the complete import chain — not just the single file round 5 flagged. Per advisor framing: a pure import-compatibility question ("does this symbol exist in Python 3.10's stdlib typing module") is conclusively settled by static source inspection; the absence of a literal 3.10/3.11 interpreter on this dev machine does not make this UNCERTAIN, just as round 5 treated the same class of static fact as sufficient to call FAILED. With Truth 0 now VERIFIED and Truths 1-5 unchanged from round 5's VERIFIED status (loop.py untouched since 02-04), all 5 phase truths pass.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | Pure `check(argv, yes) -> Decision` blocklist/allowlist gate, D-01..D-04, importable on declared Python floor | VERIFIED | Line 7: `from typing import Literal, TypedDict` (no `NotRequired`). Lines 10-15: `class Decision(TypedDict, total=False):` with `reason: str` and updated comment (comment text deliberately avoids the literal strings `NotRequired`/`Required[` so it doesn't trip the new regression test — confirmed by reading the comment, lines 12-15). `_blocklist_match` and `check()` (lines 18-267) byte-identical to round 5's verified state except the 2-line header change. 127/127 tests pass. |
| `src/olla/loop.py` | Dispatch BLOCK/CONFIRM/ALLOW correctly, repetition guard, max-steps, dry-run | VERIFIED | Unmodified since 02-04 (`git log --oneline -- src/olla/loop.py` shows last commit `6ebaa52`, predating rounds 5/6). `from olla.safety import check` (line 9) now succeeds on the declared floor — see Truth 0. |
| `src/olla/tools/shell.py` | `run_shell(argv: list[str], timeout=30)`, pre-parsed argv, no internal re-parse | VERIFIED | Unmodified since round 4/5. `from olla.tools.base import ToolResult` (line 5); `tools/base.py` imports only `from typing import TypedDict` (3.10-safe). |
| `src/olla/cli.py` | Entry point; imports `run_loop` from `loop`, which imports `check` from `safety` | VERIFIED | `cli.py:5 from olla.loop import run_loop` -> `loop.py:9 from olla.safety import check` -> `safety.py:7 from typing import Literal, TypedDict`. Full chain confirmed free of 3.11-only symbols. |
| `tests/test_safety.py` | Coverage of blocklist/allowlist rules including 02-07 dot-segment hardening, plus CR-01 regression coverage | VERIFIED | 127 tests total (up from 125), all passing on Python 3.14. Two new tests added by 02-08: `test_safety_module_has_no_python311_only_typing_symbols` (static source-grep for `NotRequired`/`Required[`) and `test_decision_is_importable`. `from olla.safety import ALLOWLIST, Decision, check` (line 5) confirms `Decision` remains exported. |
| `tests/test_loop.py` | End-to-end `--yes` BLOCK regressions | VERIFIED | Unmodified, still passing as part of the 127-test suite. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cli.py` | `loop.py` | `from olla.loop import run_loop` (line 5) | WIRED | Confirmed via grep. No longer broken by transitive ImportError (CR-01 closed). |
| `loop.py` | `safety.py` | `from olla.safety import check` (line 9) | WIRED | Confirmed via grep. `safety.py` now imports cleanly on Python >=3.10 — this line no longer propagates an ImportError. |
| `loop.py` main loop | `safety.check()` | `decision = check(argv, yes=yes)` | WIRED | Correct call, correct pre-parsed argv. Unchanged since round 4. |
| `safety.check()` decision | `loop.py` dispatch | BLOCK -> never executes; CONFIRM+not yes -> `Confirm.ask`; CONFIRM+yes -> execute; ALLOW -> execute | WIRED | Dispatch logic correct per D-04, unchanged. `decision["kind"]`/`decision["reason"]` access patterns verified safe under `total=False` (see Truth 4). |
| `tests/test_safety.py` new regression test | `src/olla/safety.py` source text | `inspect.getsourcefile(check)` + `open(source_path).read()` | WIRED (with a portability caveat — see Anti-Patterns WR-02) | The static regression test correctly locates and reads `safety.py`'s source and asserts absence of `NotRequired`/`Required[`. Confirmed passing on this system (UTF-8 default locale). |

### Data-Flow Trace (Level 4)

Not applicable in the conventional UI/dynamic-data sense (same as round 5) — this phase's artifacts are a pure decision function (`safety.check`) and a CLI dispatch loop, not data-rendering components. The relevant "data flow" for this round is the import-chain trace (Truth 0), which is a static-analysis question, fully addressed above.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-01 fix: NotRequired removed | `grep -c NotRequired src/olla/safety.py` | `0` | PASS |
| CR-01 fix: Required[ absent | `grep -c "Required\[" src/olla/safety.py` | `0` | PASS |
| CR-01 fix: Decision class declaration | `grep -n "class Decision" src/olla/safety.py` | `10:class Decision(TypedDict, total=False):` | PASS |
| CR-01 fix: import line | `grep -n "^from typing" src/olla/safety.py` | `7:from typing import Literal, TypedDict` | PASS |
| Whole-chain scan: no 3.11-only typing imports anywhere in src/olla | `grep -rn "^from typing\|^import typing" src/olla/*.py src/olla/**/*.py` | Only `safety.py:7` (`Literal, TypedDict`) and `tools/base.py:3` (`TypedDict`) — both 3.10-safe | PASS |
| Whole-chain scan: no PEP-655/3.11+ symbols anywhere in src/olla | `grep -rn "NotRequired\|Required\[\|Self\|assert_type\|assert_never\|LiteralString\|TypeVarTuple\|Unpack\|dataclass_transform\|tomllib\|StrEnum\|except\*\|reveal_type\|ExceptionGroup\|TaskGroup" src/olla/` | No matches (exit 1) | PASS |
| `check()` behavioral equivalence | `check(['ls'],False)`, `check(['rm','-rf','/'],False)`, `check(['git','status'],False)`, `check(['sudo','ls'],True)` | `{'kind': 'ALLOW'}`, `{'kind': 'BLOCK', 'reason': "'rm' targeting '/' is a dangerous deletion target"}`, `{'kind': 'CONFIRM'}`, `{'kind': 'BLOCK', 'reason': "'sudo' is blocked outright (no safe invocation)"}` | PASS — byte-identical to pre-fix |
| `Decision.__required_keys__` / `__optional_keys__` | `Decision.__required_keys__`, `Decision.__optional_keys__` | `frozenset()` / `frozenset({'reason', 'kind'})` | Confirms WR-01 (total=False widens both keys to optional) — no runtime impact, see Anti-Patterns |
| Full test suite | `PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q` | `127 passed in 1.73s` | PASS — 125 prior + 2 new (02-08), zero regressions |
| pyproject.toml/CLAUDE.md untouched by 02-08 | `grep requires-python pyproject.toml` | `requires-python = ">=3.10"` (unchanged) | PASS — Option 3 (drop NotRequired, no typing_extensions) executed as planned |
| WR-02 reproduction: new regression test's `open()` lacks encoding | `LC_ALL=C PYTHONUTF8=0 python3 -c "open(inspect.getsourcefile(check)).read()"` | `UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 579` (safety.py contains 8 em-dash U+2014 chars) | Confirms WR-02 from round-6 code review is real and reproducible — see Anti-Patterns |

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository, and neither PLAN nor SUMMARY for this phase declares probe-based verification. Step 7c: SKIPPED (no declared or conventional probes).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-04 | 02-01/02-02 | Repetition guard aborts loop after 2-3x identical tool+args | SATISFIED | `loop.py` repetition guard unchanged, now reachable on declared Python >=3.10 floor (CR-01 closed). 127/127 tests pass. |
| SAFE-01 | 02-01/02-02 | `--dry-run` previews next call, no side effects | SATISFIED | `loop.py` dry-run branch unchanged, now reachable on Python >=3.10. |
| SAFE-02 | 02-02/02-04/02-05/02-06/02-07 | Shell command blocklist (rm -rf /, sudo, dd, etc.) as speed-bump layer | SATISFIED | `_blocklist_match` unchanged from round 5 (verified comprehensive for rule 7's equivalent-form class), now reachable on Python >=3.10. WR-01 (rule-4 `rm`/`/.` asymmetry) remains an accepted residual from round 5, not re-opened. |
| SAFE-03 | 02-01/02-02 | `--max-steps` cap (default 15) prevents infinite loops | SATISFIED | `loop.py` max-steps loop unchanged, now reachable on Python >=3.10. |
| SAFE-04 | 02-01/02-02/02-04/02-05/02-06/02-07 | Confirm prompt before shell/write_file, overridable with `--yes` | SATISFIED | `loop.py` dispatch unchanged and confirmed safe under `total=False` Decision, now reachable on Python >=3.10. |

All 5 requirement IDs declared across 02-01 through 02-08 PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability rows exactly. 02-08's SUMMARY claims `requirements-completed: [LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04]` for "all requirements now reachable on the declared floor" — this claim is now substantiated: the CR-01 blocker that made all 5 requirements unreachable on Python 3.10 is closed, and all 5 were already behaviorally VERIFIED on Python >=3.11 in round 5. No orphaned requirements (cross-referenced against `.planning/REQUIREMENTS.md` Phase 2 rows: LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04 — all 5 present in plan frontmatter, all 5 present in REQUIREMENTS.md, no extras either direction).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 10-15 | `class Decision(TypedDict, total=False):` widens BOTH `kind` and `reason` to optional at the type-checker level (confirmed: `Decision.__required_keys__` == `frozenset()`), where only `reason` needs to be optional. A narrower 3.10-compatible alternative exists (`class _DecisionBase(TypedDict): kind: ...` + `class Decision(_DecisionBase, total=False): reason: str`) that would preserve "kind always required" at the type-checker level. | WARNING (WR-01, from round-6 code review) | Zero runtime impact today — `TypedDict` performs no runtime enforcement either way, and `check()` sets `kind` on all 4 return paths (confirmed). This is, however, exactly the fix the plan specified (`must_haves.artifacts[0].contains: "class Decision(TypedDict, total=False):"`) — not a deviation. Removes a type-checker safety net for hypothetical future code that forgets to set `kind`, but the project ships no type checker (no mypy/pyright in dev deps). Recommend the base-class split as a future low-cost hardening, not phase-blocking. |
| `tests/test_safety.py` | ~363-366 | `test_safety_module_has_no_python311_only_typing_symbols` calls `open(source_path).read()` with no `encoding=` argument. `safety.py` contains 8 occurrences of U+2014 (em-dash) in comments. Empirically reproduced: under `LC_ALL=C PYTHONUTF8=0`, this raises `UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 579`. | WARNING (WR-02, from round-6 code review, independently reproduced in this round) | The CR-01 portability regression test can itself fail with an unrelated `UnicodeDecodeError` on minimal/locale-restricted systems (exactly the kind of environment "Python 3.10 portability" testing should be robust against), masking the actual `NotRequired`/`Required[` check. Does not affect CR-01's core fix (safety.py imports cleanly regardless) or any of the 5 phase truths — this is a fragility in the new regression *guard* itself; on this dev machine (UTF-8 default locale) the test passes (confirmed: 127/127 pass). Recommend `open(source_path, encoding="utf-8")` as a follow-up, not phase-blocking. |
| `tests/test_safety.py` | ~369-373 | `test_decision_is_importable` asserts `Decision is not None` — `Decision` is imported at module scope (line 5), so a failed import would fail collection before this test runs; the assertion is structurally unable to fail independently. | INFO (IN-01, from round-6 code review) | Harmless documentation-style sanity check, no impact. |
| `tests/test_safety.py` | ~363 | Test name `test_safety_module_has_no_python311_only_typing_symbols` implies general 3.11+ coverage but only checks `NotRequired`/`Required[` (the two symbols relevant to this specific incident). Other 3.11+-only symbols (`Self`, `assert_type`, etc.) would not be caught by this test, though this round's independent whole-chain scan confirms none are currently present. | INFO (IN-02, from round-6 code review) | Scope-naming clarity issue only; the broader scan performed in this verification round (Truth 0) covers what the test name implies but the test itself does not. Recommend renaming or broadening in a follow-up, not phase-blocking. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers found in `src/olla/safety.py` or `tests/test_safety.py` (`grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` -> no matches in either file).

### Human Verification Required

None. All findings in this report are reproducible programmatically: static grep of import statements and `Decision` class declaration, `Decision.__required_keys__`/`__optional_keys__` introspection, direct `safety.check()` calls confirming byte-identical classification, whole-package scan for 3.11-only typing symbols, and empirical reproduction of the WR-02 `UnicodeDecodeError` under `LC_ALL=C PYTHONUTF8=0`. Per advisor framing (consistent with round 5's treatment of the same class of fact as FAILED rather than UNCERTAIN): "does symbol X exist in Python 3.10's stdlib typing module" is a static, conclusively-determinable fact, not a matter requiring a literal 3.10/3.11 interpreter or human judgment. No UI, real-time, or external-service behavior is involved in this phase's deliverables.

### Gaps Summary

**CR-01 (typing.NotRequired / Python 3.10 incompatibility): CLOSED.** Plan 02-08 (commits `222363e` test-RED, `cf6d16a` fix-GREEN) removed `NotRequired` from `src/olla/safety.py`'s import line (now `from typing import Literal, TypedDict`) and changed `Decision` to `class Decision(TypedDict, total=False):` with `reason: str`. This round independently extended round 5's single-file finding to a **whole-package import-chain scan**: every `src/olla/*.py` and `src/olla/tools/*.py` file was grepped for `typing` imports (only `safety.py` and `tools/base.py` import from `typing`, both using only `Literal`/`TypedDict`, both 3.10-safe) and for a broader list of Python-3.11+-only stdlib/typing symbols (`NotRequired`, `Required[`, `Self`, `assert_type`, `assert_never`, `LiteralString`, `TypeVarTuple`, `Unpack`, `dataclass_transform`, `tomllib`, `StrEnum`, `except*`, `reveal_type`, `ExceptionGroup`, `TaskGroup`) — zero matches anywhere in `src/olla/`. This addresses the advisor's specific concern from round 5: that safety.py's import failure could have masked a *second* 3.11-only symbol in `loop.py`, `cli.py`, or elsewhere in the chain, which would only surface after safety.py's own fix. No such symbol exists.

`check()`'s classification behavior is confirmed byte-identical to pre-fix for all spot-checked cases (`ls`->ALLOW, `rm -rf /`->BLOCK with reason, `git status`->CONFIRM, `sudo ls` yes=True->BLOCK with reason). `loop.py`'s `decision["kind"]`/`decision["reason"]` access patterns (lines 60, 62, 65, 110, 111, 116) are all safe under the now-fully-optional `Decision` TypedDict, since `TypedDict` performs zero runtime key enforcement and `check()` sets both keys on every relevant path. 127/127 tests pass (125 prior + 2 new from 02-08), zero regressions. `pyproject.toml`'s `requires-python = ">=3.10"` and CLAUDE.md's stated Python floor are unchanged, as specified by the plan's Option 3.

**WR-01 and WR-02 (round-6 code review findings): both confirmed real, both correctly classified as WARNING, neither phase-blocking.** WR-01 (`total=False` widens `kind` to optional too) is the literal approach the plan specified and has zero runtime impact (confirmed via `Decision.__required_keys__` == `frozenset()` and trace of all `decision["kind"]`/`decision["reason"]` accesses). WR-02 (new regression test's `open()` lacks `encoding="utf-8"`, reproducibly raises `UnicodeDecodeError` under `LC_ALL=C`) is a fragility in the new safeguard itself, not in CR-01's core fix — on this dev machine's default UTF-8 locale, all 127 tests pass. Both are recommended as low-cost follow-up hardening but do not gate this phase.

**All prior accepted residuals carried forward unchanged, not re-litigated:** WR-01 from round 5 (rule-4 `rm -rf /.`-family vs rule-7 `chmod/chown` asymmetry — `_blocklist_match` lines 158-248 untouched by 02-08), `env -S` wrap-and-recurse (T-02-07-05), shell-chained `-c` bypass of rule 6b (T-02-06-05/T-02-07-04), recursion-depth limit on `_blocklist_match` (INFO-level).

**Overall status:** `passed`. All 5 phase truths (SAFE-01..04, LOOP-04) are VERIFIED. The sole round-5 blocker (CR-01) is closed and independently re-verified at the whole-package-import-chain level (broader than round 5's single-file finding, per advisor guidance). The phase goal — "A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call" — is achieved on the project's actual declared minimum platform (Python >=3.10), not just on the dev machine's Python 3.14.

---

_Verified: 2026-06-14T01:00:00Z_
_Verifier: Claude (gsd-verifier)_
