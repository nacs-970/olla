---
phase: 02-safety-gate-loop-control
verified: 2026-06-13T00:00:00Z
status: gaps_found
score: 3/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "env/find ALLOWLIST argv[0] bypass (old CR-01): env -u FOO sudo rm -rf / and find . -exec ... -exec sudo rm -rf / ; now correctly BLOCK via recursive _blocklist_match on _unwrap_env/_unwrap_find_exec"
    - "WR-02 fork-bomb false positive on echo data: echo \"...:(){ :|:& };:...\" now ALLOWs (anchored .match()), canonical bash -c fork-bomb still BLOCKs"
    - "WR-03 chmod/chown -Rf-style combined short flags on / now BLOCK"
    - "IN-01 run_shell double shlex.split removed; argv passed pre-parsed end-to-end"
  gaps_remaining:
    - "SAFE-02/SAFE-04: bash/sh/zsh -c \"<dangerous command>\" only checked against fork-bomb regex, not full D-03 blocklist (new CR-01)"
    - "SAFE-02/SAFE-04: chmod/chown --recursive (long flag) on / not matched by rule (7) (new CR-02)"
    - "SAFE-02/SAFE-04: rm -rf // and /// not in _RM_DANGEROUS_TARGETS (new CR-03)"
  regressions: []
gaps:
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "bash/sh/zsh -c wraps a hard-blocked binary (sudo) or a dangerous rm/chmod target without being recursively checked against the D-03 blocklist — only the fork-bomb regex is applied to the -c argument. check(['bash','-c','sudo rm -rf /'], yes=False) returns CONFIRM, not BLOCK, even though direct check(['sudo','ls'], yes=False) returns BLOCK with reason \"'sudo' is blocked outright (no safe invocation)\". A one-line wrapper defeats the hard-block guarantee the code's own comments describe as having 'no safe invocation'."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Rule (6b) at lines 177-181 only runs _FORK_BOMB_RE.search() against the bash/sh/zsh -c argument; it does not shlex.split() that argument and recurse it through _blocklist_match the way rules (2) and (3) already do for env/find -exec."
    missing:
      - "Extend rule (6b) (or add a new rule) to shlex.split() the bash/sh/zsh -c argument and recursively run _blocklist_match on the resulting argv, in addition to the existing fork-bomb .search() check."
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "chmod/chown rule (7) excludes long-form --recursive via 'not a.startswith(\"--\")', so chmod --recursive 777 / returns CONFIRM instead of BLOCK, even though the short-flag equivalent chmod -R 777 / (and -Rf, -fR, etc.) correctly BLOCKs. The rule's own intent (catch recursive chmod/chown on /) is unambiguous; --recursive is a literal synonym that slips through an incomplete pattern match."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Rule (7) at lines 184-186: 'if any(a.startswith(\"-\") and not a.startswith(\"--\") and \"R\" in a for a in argv[1:])' never matches '--recursive'."
    missing:
      - "Add a check for a == '--recursive' (or 'a in (\"-R\", \"--recursive\") or (a.startswith(\"-\") and not a.startswith(\"--\") and \"R\" in a)') in rule (7)."
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "_RM_DANGEROUS_TARGETS contains '/' but not '//' or '///'. Linux collapses repeated leading slashes to a single '/', so rm -rf // and rm -rf /// are functionally identical to rm -rf / but check(['rm','-rf','//'], yes=False) returns CONFIRM instead of BLOCK. The rule's intent (block rm -rf / and equivalents) is unambiguous; // is an untreated alias of an already-blocked target."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "_RM_DANGEROUS_TARGETS set at lines 45-51 = {'/', '~', '/*', '$HOME', '.'} — no entry for '//' or '///', and no normalization of repeated leading slashes before the membership check in rule (4)."
    missing:
      - "Normalize repeated leading slashes (e.g. re.sub(r'^/{2,}$', '/', arg)) before the _RM_DANGEROUS_TARGETS membership check in rule (4), or add literal '//' and '///' entries to the set."
  - truth: "Confirm prompt before shell execution, overridable with --yes, does not permit destructive actions to run unattended (SAFE-04)"
    status: failed
    reason: "All three bypasses above (CR-01/CR-02/CR-03) are classified CONFIRM, not BLOCK. loop.py's dispatch (lines 116-123) skips Confirm.ask entirely when yes=True and CONFIRM falls through to run_shell unconditionally. Under --yes, 'bash -c \"sudo rm -rf /\"', 'chmod --recursive 777 /', and 'rm -rf //' all execute with zero pause — exactly the unattended-destructive-action scenario SAFE-04 and the phase goal ('the loop cannot run away ... every dangerous action is gated by a confirm prompt') are meant to prevent."
    artifacts:
      - path: "src/olla/loop.py"
        issue: "Lines 116-123: 'if decision[\"kind\"] == \"CONFIRM\" and not yes:' — CONFIRM + yes=True executes without any gate. This is correct behavior for true CONFIRM-tier commands (D-04 says --yes legitimately skips the prompt for CONFIRM), but CR-01/02/03 are misclassified CONFIRM when they should be BLOCK (which loop.py never executes regardless of --yes)."
    missing:
      - "Fix the three safety.py classification bugs above so CR-01/CR-02/CR-03 return BLOCK; no loop.py change is needed once classification is correct."
---

# Phase 02: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.

**Verified:** 2026-06-13T00:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — after 02-04 gap closure (env/find ALLOWLIST bypass)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `--dry-run` previews next tool call without executing it or any side effects (SAFE-01) | VERIFIED | `loop.py` lines 37-68: structurally separate early-return branch, single `call_model`, no `run_shell`/`Confirm.ask` call anywhere in the dry-run path. |
| 2 | Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02) | FAILED | `bash -c "sudo rm -rf /"`, `chmod --recursive 777 /`, and `rm -rf //` all return CONFIRM (not BLOCK) from `safety.check()`, despite their direct/short-flag equivalents (`sudo ls`, `chmod -R 777 /`, `rm -rf /`) correctly BLOCKing. Empirically reproduced against live `src/olla/safety.py` (CR-01/CR-02/CR-03, see below). |
| 3 | `--max-steps` cap (default 15) prevents infinite loops (SAFE-03) | VERIFIED | `loop.py` line 73 `for step in range(1, max_steps + 1)`, line 146 distinct "Reached max steps" diagnostic, separate from repetition-guard message. `cli.py` exposes `--max-steps` default 15. |
| 4 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`, does not permit destructive actions to run unattended (SAFE-04) | FAILED | `loop.py` lines 116-123 correctly skip `Confirm.ask` on CONFIRM+`--yes` (per D-04, this is by-design for true CONFIRM-tier commands) — but the three SAFE-02 misclassifications above (CR-01/02/03) mean genuinely destructive commands land in CONFIRM and execute unattended under `--yes` with zero pause. |
| 5 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3x in a row (LOOP-04) | VERIFIED | `loop.py` lines 97-106: `sig = ("shell", tuple(argv))`, `repeat_count >= 3` triggers distinct "same shell call repeated 3x" message and `return`. (WR-04 from 02-REVIEW.md notes non-`shell`/unparseable-arg repeats aren't tracked — info-level, not a phase-blocking gap for LOOP-04's stated scope of "same tool+args".) |

**Score:** 3/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | Pure `check(argv, yes) -> Decision` blocklist/allowlist gate, D-01..D-04 | PARTIAL | Exists, substantive, wired, and 02-04's targeted fixes (env/find unwrap, fork-bomb anchor, chmod -Rf) verified working — but three additional D-03 pattern-matching gaps (bash -c wrap, chmod --recursive, rm -rf //) remain live, contradicting the "blocklisted dangerous patterns are caught" guarantee. |
| `src/olla/loop.py` | Dispatch BLOCK/CONFIRM/ALLOW correctly, repetition guard, max-steps, dry-run | VERIFIED | All dispatch logic correct and matches D-04 intent. The CONFIRM+yes=True passthrough is correct *given* a correct `check()` classification — the gap is upstream in `safety.py`'s classification, not in `loop.py`'s dispatch. |
| `src/olla/tools/shell.py` | `run_shell(argv: list[str], timeout=30)`, pre-parsed argv, no internal re-parse | VERIFIED | 02-04's IN-01 fix confirmed: signature takes `argv: list[str]`, no `shlex` import/re-parse. |
| `tests/test_safety.py` | Coverage of blocklist/allowlist rules including 02-04 hardening | PARTIAL | 35 tests, all passing — but no test exercises `bash -c "sudo ..."`, `bash -c "rm -rf /..."`, `chmod --recursive ... /`, or `rm -rf //`/`///`. The new CR-01/CR-02/CR-03 vectors are entirely untested, which is why 96/96 green tests do not indicate these are fixed. |
| `tests/test_loop.py` | End-to-end --yes BLOCK regressions | VERIFIED (for its declared scope) | 31 tests including the 2 new 02-04 end-to-end `--yes` BLOCK regressions for env/find wrapping — correct for the old CR-01 class. No equivalent end-to-end test exists for the new bash-c/--recursive/`//` vectors. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `loop.py` main loop | `safety.check()` | `decision = check(argv, yes=yes)` (line 108) | WIRED | Correct call, correct argv (pre-parsed via single `shlex.split`). |
| `safety.check()` decision | `loop.py` dispatch | BLOCK -> never executes; CONFIRM+not yes -> `Confirm.ask`; CONFIRM+yes -> execute; ALLOW -> execute | WIRED | Dispatch logic itself is correct per D-04. Wiring is sound — the defect is in what `check()` *returns* for CR-01/02/03 inputs, not in how `loop.py` consumes the result. |
| `safety._blocklist_match` rule (2)/(3) (env/find wrap-and-recurse) | `safety._blocklist_match` (recursive call) | Direct recursion | WIRED & VERIFIED | `check(['env','-u','FOO','sudo','rm','-rf','/'], yes=False)` -> BLOCK (`'env' wraps a blocked command: 'sudo' is blocked outright...'`). `check(['find','.','-exec','true',';','-exec','sudo','rm','-rf','/',';'], yes=False)` -> BLOCK. Both confirmed live. |
| `safety._blocklist_match` rule (6b) (bash/sh/zsh -c) | `safety._blocklist_match` (recursive call) | MISSING — only `_FORK_BOMB_RE.search()`, no recursion | NOT_WIRED | The exact wrap-and-recurse pattern proven correct for `env`/`find` (rules 2/3) is NOT applied to `bash/sh/zsh -c`. This is the root cause of CR-01. |

### Data-Flow Trace (Level 4)

Not applicable in the conventional sense (no UI/dynamic-data rendering) — the equivalent trace here is the decision-to-execution path, covered under Key Link Verification above. The trace confirms: a CONFIRM decision for a destructive command flows unmodified into `run_shell` execution when `--yes` is set, with no secondary check.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Direct `sudo` is hard-blocked | `check(['sudo','ls'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'sudo' is blocked outright (no safe invocation)"}` | PASS (control) |
| Direct `rm -rf /` is blocked | `check(['rm','-rf','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'rm' targeting '/' is a dangerous deletion target"}` | PASS (control) |
| Direct `chmod -R 777 /` is blocked | `check(['chmod','-R','777','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` | PASS (control) |
| `chmod -Rf 777 /` (02-04 combined-flag fix) is blocked | `check(['chmod','-Rf','777','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` | PASS (02-04 regression confirmed) |
| `sudo rm -rf /` wrapped in `bash -c` (CR-01) | `check(['bash','-c','sudo rm -rf /'], yes=False)` and `yes=True` | `{'kind': 'CONFIRM'}` (both) | FAIL — should BLOCK |
| `chmod --recursive 777 /` (CR-02) | `check(['chmod','--recursive','777','/'], yes=False)` | `{'kind': 'CONFIRM'}` | FAIL — should BLOCK |
| `rm -rf //` and `rm -rf ///` (CR-03) | `check(['rm','-rf','//'], yes=False)` / `check(['rm','-rf','///'], yes=False)` | `{'kind': 'CONFIRM'}` (both) | FAIL — should BLOCK |
| `env -u FOO sudo rm -rf /` (old CR-01, 02-04 fix) | `check(['env','-u','FOO','sudo','rm','-rf','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'env' wraps a blocked command: 'sudo' is blocked outright (no safe invocation)"}` | PASS (02-04 fix confirmed live) |
| Chained `find -exec ... -exec sudo rm -rf / ;` (old CR-01, 02-04 fix) | `check(['find','.','-exec','true',';','-exec','sudo','rm','-rf','/',';'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'find' -exec wraps a blocked command: 'sudo' is blocked outright (no safe invocation)"}` | PASS (02-04 fix confirmed live) |

All commands run via `PYTHONPATH=src python3 -c "from olla.safety import check; ..."` directly against the live `src/olla/safety.py` — no test mocks, no SUMMARY narration relied upon.

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository, and neither PLAN nor SUMMARY for this phase declares probe-based verification. Step 7c: SKIPPED (no declared or conventional probes). Test suite was not re-run in full (existing 96-test green status from 02-04-SUMMARY is consistent with the spot-checks above — green because the new CR-01/02/03 vectors are untested, not because they're fixed).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-04 | 02-01/02-02 | Repetition guard aborts loop after 2-3x identical tool+args | SATISFIED | `loop.py` lines 97-106, distinct diagnostic confirmed. WR-04 (non-shell/unparseable repeats untracked) is an info-level caveat on scope, not a failure of the stated requirement. |
| SAFE-01 | 02-01/02-02 | `--dry-run` previews next call, no side effects | SATISFIED | `loop.py` lines 37-68, structurally isolated branch, confirmed no execution path. |
| SAFE-02 | 02-02/02-04 | Shell command blocklist (rm -rf /, sudo, dd, etc.) as speed-bump layer | BLOCKED | CR-01 (`bash -c "sudo rm -rf /"`), CR-02 (`chmod --recursive 777 /`), CR-03 (`rm -rf //`) all empirically return CONFIRM, not BLOCK, despite their direct/canonical-flag equivalents correctly BLOCKing. The requirement explicitly names "rm -rf /" and "sudo" as exemplar targets — both are reachable via these one-line wrappers. |
| SAFE-03 | 02-01/02-02 | `--max-steps` cap (default 15) prevents infinite loops | SATISFIED | `loop.py` line 73/146, `cli.py` default 15, confirmed. |
| SAFE-04 | 02-01/02-02/02-04 | Confirm prompt before shell/write_file, overridable with `--yes` | BLOCKED | Dispatch logic in `loop.py` (lines 116-123) is correct per D-04 — but because CR-01/02/03 are misclassified CONFIRM instead of BLOCK, `--yes` causes them to execute with zero confirmation, the exact "destructive action runs unattended" scenario SAFE-04 (and the phase goal) exist to prevent. |

All 5 requirement IDs declared across 02-01/02-02/02-04 PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability rows exactly. No orphaned requirements.

02-04's SUMMARY claims `requirements-completed: [SAFE-02, SAFE-04]` for its own (narrower) scope — that claim is accurate for the env/find ALLOWLIST bypass class it targeted (confirmed fixed above), but does not extend to the new CR-01/CR-02/CR-03 bypass class discovered in the subsequent `02-REVIEW.md` pass. SAFE-02/SAFE-04 as overall phase requirements remain BLOCKED.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 177-181 | Incomplete wrap-and-recurse: rule (6b) checks only fork-bomb regex against `bash/sh/zsh -c` argument, not the full D-03 blocklist (unlike rules 2/3 for `env`/`find`) | BLOCKER | CR-01 — hard-blocked binaries (`sudo`, etc.) and other D-03 rules are bypassable via `bash -c "..."` |
| `src/olla/safety.py` | 184-186 | Incomplete pattern match: `not a.startswith("--")` excludes `--recursive` from chmod/chown `-R` detection | BLOCKER | CR-02 — `chmod --recursive 777 /` bypasses an otherwise-correct rule |
| `src/olla/safety.py` | 45-51 | Incomplete set membership: `_RM_DANGEROUS_TARGETS` lacks `//`/`///` (filesystem-equivalent to `/`) | BLOCKER | CR-03 — `rm -rf //` bypasses an otherwise-correct rule |
| `src/olla/loop.py` | 25-27 | `call_model` accesses `response["message"]["content"]` unconditionally; raises uncaught `KeyError` if `think=True` and model returns only `thinking` | INFO (WR-01, not reachable from `run_loop` which always passes `think=False`; reachable only from `run_smoke_test`) | Not a phase-blocking gap — informational per 02-REVIEW.md |
| `src/olla/loop.py` | 60-67 | Dry-run preview says "would prompt for confirmation" for CONFIRM decisions even when `--yes` would skip the prompt | INFO (WR-02 in 02-REVIEW.md, cosmetic/diagnostic-text-only) | Does not affect actual execution safety — preview text inaccuracy only |
| `src/olla/safety.py` | 96-98 (docstring), `_ENV_FLAGS_WITH_ARG` | `env -S "<command>"` remains CONFIRM by design — documented residual of the same bypass class as CR-01 | WARNING (WR-03 in fresh review, pre-existing documented limitation from 02-04) | Same root issue as CR-01 but in `env -S` rather than `bash -c`; both should likely be fixed together |

No `TBD`/`FIXME`/`XXX` debt markers found in `src/olla/safety.py` or `src/olla/loop.py`.

### Human Verification Required

None. All findings in this report are reproducible programmatically via direct `safety.check()` calls (shown above) — no UI, real-time, or external-service behavior is involved.

### Gaps Summary

02-04 successfully closed its declared scope: the env/find ALLOWLIST argv[0] bypass (old CR-01), the WR-02 fork-bomb false-positive on `echo` data, the WR-03 chmod/chown combined-short-flag detection, and IN-01's double-parse. All four are empirically confirmed fixed and regression-tested (96/96 tests pass, plus independent spot-checks above).

However, a subsequent fresh code review (`02-REVIEW.md`, committed `088cf31`, produced AFTER 02-04 merged) identified three NEW, independently-reproducible bypasses of the SAME phase requirements (SAFE-02/SAFE-04) via a DIFFERENT vector class — incomplete pattern matching rather than missing recursion:

1. **CR-01**: `bash/sh/zsh -c "<command>"` is checked only against the fork-bomb regex, not the full D-03 blocklist. `bash -c "sudo rm -rf /"` -> CONFIRM (should BLOCK, since direct `sudo` is hard-blocked with "no safe invocation").
2. **CR-02**: `chmod --recursive 777 /` -> CONFIRM (should BLOCK; `chmod -R 777 /` and `-Rf` etc. already correctly BLOCK).
3. **CR-03**: `rm -rf //` and `rm -rf ///` -> CONFIRM (should BLOCK; `rm -rf /` already correctly BLOCKs, and `//`/`///` are filesystem-equivalent to `/`).

All three: (a) are reproducible against the live, current `src/olla/safety.py`; (b) return CONFIRM (not BLOCK), which under `--yes` (SAFE-04's documented override) executes the destructive command with zero pause; (c) represent incomplete-pattern-match fixes with one-line solutions already proposed in `02-REVIEW.md`; (d) are untested by the current 96-test suite (no test exercises any of these three exact inputs).

Per the phase goal ("every dangerous action is gated... blocklisted patterns are caught"), and per SAFE-02's explicit text naming "rm -rf /" and "sudo" as exemplar targets, these three reproducible bypasses constitute a real, unaddressed violation of SAFE-02 and SAFE-04 — independent of whether 02-04's own (narrower) must_haves were satisfied. 02-04 fixed a different bypass class (env/find wrap-and-recurse); CR-01/02/03 are a sibling bypass class (incomplete D-03 pattern coverage) discovered afterward.

No override exists in this VERIFICATION.md's frontmatter for these findings, and none is suggested — per the verification-overrides reference, "implementation is simply incomplete, fix it instead" is explicitly excluded from override eligibility, and all three findings have known, small, proposed fixes (extend rule 6b to recurse like rules 2/3; add `--recursive` to rule 7's flag check; normalize/extend `_RM_DANGEROUS_TARGETS` for `//`/`///`).

No later phase (Phase 3: File Tools, Phase 4: Memory Tool) addresses shell-blocklist hardening — Step 9b deferral does not apply.

---

_Verified: 2026-06-13T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
