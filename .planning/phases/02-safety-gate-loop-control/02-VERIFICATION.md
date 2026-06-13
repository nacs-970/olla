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
    - "CR-01 (round 2): bash/sh/zsh -c \"<command>\" with the exact token '-c' is now shlex-split and recursed through the full D-03 blocklist — check(['bash','-c','sudo rm -rf /'], yes=False/True) -> BLOCK with reason mentioning 'sudo'. Confirmed live."
    - "CR-02 (round 2): chmod/chown --recursive (long flag) on '/' now matches rule (7) -> BLOCK. check(['chmod','--recursive','777','/'], yes=False) -> BLOCK. Confirmed live."
    - "CR-03 (round 2): rm -rf // and /// normalized via _normalize_rm_target to '/' and matched in _RM_DANGEROUS_TARGETS -> BLOCK. check(['rm','-rf','//'], yes=False) -> BLOCK. Confirmed live."
    - "T-02-05-06: bash -c / sh -c with no trailing command argument no longer raises IndexError (single outer len(argv) > c_index + 1 guard) — falls through cleanly to CONFIRM."
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "Round 2's fixes for bash/sh/zsh -c wrap-and-recurse used an exact-token match for '-c', which combined short-flag forms (-lc, -ic, -xc, etc.) bypass entirely — the whole rule (6b) block (fork-bomb check AND CR-01 recursion) is skipped. check(['bash','-lc','sudo rm -rf /'], yes=True) -> CONFIRM, while check(['bash','-c','sudo rm -rf /'], yes=True) -> BLOCK. Confirmed across bash, sh, and zsh with -lc/-ic/-xc."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Rule (6b) at line 202: 'if binary in (\"bash\", \"sh\", \"zsh\") and \"-c\" in argv:' is an exact-token membership check. Bash/sh/zsh accept combined single-letter flag bundles (-lc, -ic, -xc, ...) that contain 'c' and behave identically to '-c' for the purposes of executing the following string argument as a command. None of these tokens equal the literal string '-c', so the entire wrap-and-recurse block (fork-bomb + CR-01 blocklist recursion) is skipped for these forms."
    missing:
      - "Replace the exact '-c' membership check with detection of any argv token that starts with '-', does not start with '--', and contains 'c' (e.g. via next((i for i, a in enumerate(argv) if a.startswith(\"-\") and not a.startswith(\"--\") and \"c\" in a), None)). The wrapped command remains the next argv element after that token. Add regression tests for bash -lc, sh -lc, and zsh -ic at minimum."
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "The //-/-/// -> '/' normalization (_normalize_rm_target) introduced in round 2 was wired only into rule (4) (rm). Rule (7) (chmod/chown -R on '/') still does an exact '/' in argv membership check, so chmod -R 777 // and chown -R user // (and chmod --recursive 777 //) remain CONFIRM despite their single-slash equivalents (chmod -R 777 /, chmod --recursive 777 /) correctly BLOCKing. Confirmed live: check(['chmod','-R','777','//'], yes=True) -> CONFIRM; check(['chmod','-R','777','/'], yes=True) -> BLOCK."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Rule (7) at line 219: 'if binary in (\"chmod\", \"chown\") and \"/\" in argv:' does not apply _normalize_rm_target (or equivalent) to argv elements before the '/' membership check, unlike rule (4) which does (line 178)."
    missing:
      - "Apply the same multi-slash normalization used in rule (4) to rule (7)'s '/' check, e.g. 'if binary in (\"chmod\",\"chown\") and any(_normalize_rm_target(a) == \"/\" for a in argv[1:]):'. Consider renaming _normalize_rm_target to a binary-agnostic name (e.g. _normalize_slash_target) since it is no longer rm-specific. Add regression tests for chmod -R 777 // and chown -R user //."
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "_is_dangerous_device_arg requires an exact single-leading-slash '/dev/' prefix via fnmatch(path, '/dev/*') and removeprefix('/dev/'). A doubled-slash path (//dev/sda) does not match this pattern, so the entire dd/mkfs* raw-device rule (5) is skipped for //dev/... paths even though the kernel treats //dev/sda identically to /dev/sda. Confirmed live: check(['dd','if=/dev/zero','of=//dev/sda'], yes=True) -> CONFIRM; check(['mkfs.ext4','//dev/sda'], yes=True) -> CONFIRM; the single-slash equivalents correctly BLOCK."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "_is_dangerous_device_arg at lines 92-101: 'path = arg.split(\"=\")[-1]; if not fnmatch.fnmatch(path, _DEVICE_GLOB): return False' — no normalization of a leading run of 2+ slashes before the fnmatch/removeprefix checks."
    missing:
      - "Normalize a leading run of 2+ slashes to a single '/' in the path portion before the fnmatch/removeprefix checks in _is_dangerous_device_arg (e.g. 'path = re.sub(r\"^/{2,}\", \"/\", path)' — note: only collapse the leading run, not full-string-anchored like _normalize_rm_target, since 'of=//dev/sda' needs '//dev' -> '/dev' regardless of trailing path). Add regression tests for dd ... of=//dev/sda and mkfs.ext4 //dev/sda."
  - truth: "Confirm prompt before shell execution, overridable with --yes, does not permit destructive actions to run unattended (SAFE-04)"
    status: failed
    reason: "All three round-3 bypasses above (bash -lc combined flags, chmod/chown -R //, dd/mkfs //dev) are classified CONFIRM, not BLOCK. loop.py's dispatch (lines 116-123, unchanged since prior verification) skips Confirm.ask entirely when yes=True, and CONFIRM falls through to run_shell(argv) unconditionally. Under --yes, 'bash -lc \"sudo rm -rf /\"', 'chmod -R 777 //', and 'dd if=/dev/zero of=//dev/sda' all execute with zero pause — exactly the unattended-destructive-action scenario SAFE-04 and the phase goal ('the loop cannot run away ... every dangerous action is gated by a confirm prompt') are meant to prevent."
    artifacts:
      - path: "src/olla/loop.py"
        issue: "Lines 116-123: 'if decision[\"kind\"] == \"CONFIRM\" and not yes:' — CONFIRM + yes=True executes via run_shell(argv) without any gate. This dispatch logic is correct for true CONFIRM-tier commands (D-04: --yes legitimately skips the prompt for CONFIRM), but the three safety.py classification bugs above mean genuinely destructive commands are misclassified CONFIRM when they should be BLOCK (which loop.py never executes regardless of --yes)."
    missing:
      - "Fix the three safety.py classification bugs above so the round-3 bypasses return BLOCK; no loop.py change is needed once classification is correct."
---

# Phase 02: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.

**Verified:** 2026-06-13T00:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — round 3, after 02-05 closed the round-2 (CR-01/CR-02/CR-03) gaps; a fresh `02-REVIEW.md` (committed `1f14ef7`, post-wave-3) found a sibling round-3 bypass class (equivalent-form variants of the same three rules) which this verification confirms live against the current `src/olla/safety.py`.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `--dry-run` previews next tool call without executing it or any side effects (SAFE-01) | VERIFIED | `loop.py` unchanged since prior verification (02-05's `key-files` only modified `safety.py`, `test_safety.py`, `test_loop.py`); structurally separate early-return branch, single `call_model`, no `run_shell`/`Confirm.ask` call anywhere in the dry-run path. Regression-confirmed: 109/109 tests pass. |
| 2 | Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02) | FAILED | Round 2's three CR-01/02/03 forms (`bash -c "sudo rm -rf /"`, `chmod --recursive 777 /`, `rm -rf //`) are now correctly BLOCK — confirmed live. But three NEW equivalent-form bypasses remain: `bash -lc "sudo rm -rf /"` (combined short-flag bypasses rule 6b's exact `-c` check), `chmod -R 777 //` / `chown -R user //` (the `//`->`/` normalization wasn't wired into rule 7), and `dd if=/dev/zero of=//dev/sda` / `mkfs.ext4 //dev/sda` (`_is_dangerous_device_arg` doesn't normalize a doubled leading slash). All confirmed CONFIRM (not BLOCK) against live `src/olla/safety.py`. |
| 3 | `--max-steps` cap (default 15) prevents infinite loops (SAFE-03) | VERIFIED | `loop.py` unchanged since prior verification — `for step in range(1, max_steps + 1)`, distinct "Reached max steps" diagnostic, `cli.py` exposes `--max-steps` default 15. Regression-confirmed via 109/109 passing tests. |
| 4 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`, does not permit destructive actions to run unattended (SAFE-04) | FAILED | `loop.py` lines 116-123 dispatch is unchanged and correct per D-04 for true CONFIRM-tier commands — but the three round-3 SAFE-02 misclassifications above mean genuinely destructive commands (recursive chmod on `/`, raw-device writes, `sudo rm -rf /` via `bash -lc`) land in CONFIRM and execute unattended under `--yes` with zero pause. |
| 5 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3x in a row (LOOP-04) | VERIFIED | `loop.py` lines 97-106 unchanged: `sig = ("shell", tuple(argv))`, `repeat_count >= 3` triggers distinct "same shell call repeated 3x" message and `return`. Regression-confirmed via 109/109 passing tests (WR-04's non-shell/unparseable-repeat caveat remains info-level, not phase-blocking for LOOP-04's stated scope). |

**Score:** 3/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | Pure `check(argv, yes) -> Decision` blocklist/allowlist gate, D-01..D-04 | PARTIAL | Exists, substantive, wired, and 02-05's round-2 fixes (bash/sh/zsh `-c` recursion, `chmod/chown --recursive`, `rm -rf //`/`///` normalization) verified working live. But three NEW equivalent-form gaps remain in the same three rules (6b, 7, 5) — round-3 findings from `02-REVIEW.md`, confirmed reproducible. |
| `src/olla/loop.py` | Dispatch BLOCK/CONFIRM/ALLOW correctly, repetition guard, max-steps, dry-run | VERIFIED | Unmodified since prior (VERIFIED) round. All dispatch logic correct and matches D-04 intent. The CONFIRM+yes=True passthrough is correct *given* a correct `check()` classification — the gap is upstream in `safety.py`'s pattern coverage. |
| `src/olla/tools/shell.py` | `run_shell(argv: list[str], timeout=30)`, pre-parsed argv, no internal re-parse | VERIFIED | Unmodified since prior (VERIFIED) round. |
| `tests/test_safety.py` | Coverage of blocklist/allowlist rules including 02-05 hardening | PARTIAL | 47 tests (up from 35), all passing — covers the literal round-2 forms (`bash -c`, `chmod --recursive`, `rm -rf //`) exactly as 02-05's must_haves specified. But no test exercises `bash -lc`/`-ic`/`-xc`, `chmod -R 777 //`/`chown -R user //`, or `dd .../mkfs* of=//dev/...` — the round-3 vectors are entirely untested, which is why 109/109 green tests do not indicate these are fixed. |
| `tests/test_loop.py` | End-to-end --yes BLOCK regressions | PARTIAL (for its declared scope) | 109 tests total including the new 02-05 end-to-end `--yes` BLOCK regression for `bash -c "sudo rm -rf /"`. No equivalent end-to-end test exists for the round-3 vectors (`bash -lc`, `chmod -R //`, `dd of=//dev/...`). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `loop.py` main loop | `safety.check()` | `decision = check(argv, yes=yes)` (line 108) | WIRED | Correct call, correct argv (pre-parsed via single `shlex.split`). Unchanged since prior round. |
| `safety.check()` decision | `loop.py` dispatch | BLOCK -> never executes; CONFIRM+not yes -> `Confirm.ask`; CONFIRM+yes -> execute; ALLOW -> execute | WIRED | Dispatch logic itself is correct per D-04. The defect is in what `check()` *returns* for round-3 inputs, not in how `loop.py` consumes the result. |
| `safety._blocklist_match` rule (6b) (bash/sh/zsh -c, exact token) | `safety._blocklist_match` (recursive call) | `"-c" in argv` exact membership | WIRED for exact `-c`, NOT_WIRED for combined short-flags | `check(['bash','-c','sudo rm -rf /'], yes=True)` -> BLOCK (confirmed). `check(['bash','-lc','sudo rm -rf /'], yes=True)` -> CONFIRM (round-3 CR-01) — the entire rule (6b) block is skipped for `-lc`/`-ic`/`-xc`/etc. because none of these tokens equal the literal `"-c"`. |
| `safety._normalize_rm_target` | rule (4) (`rm`) | `_normalize_rm_target(arg) in _RM_DANGEROUS_TARGETS` | WIRED | `check(['rm','-rf','//'], yes=False)` -> BLOCK (confirmed). |
| `safety._normalize_rm_target` (or equivalent) | rule (7) (`chmod`/`chown -R`) | NOT WIRED — rule (7) still does exact `"/" in argv` | NOT_WIRED | `check(['chmod','-R','777','//'], yes=True)` -> CONFIRM (round-3 CR-02). The normalization helper added for rule (4) was never applied to rule (7)'s `/` check. |
| Slash-normalization | `safety._is_dangerous_device_arg` (rule 5, `dd`/`mkfs*`) | NOT WIRED — `fnmatch(path, "/dev/*")` and `removeprefix("/dev/")` require exact single leading slash | NOT_WIRED | `check(['dd','if=/dev/zero','of=//dev/sda'], yes=True)` -> CONFIRM (round-3 CR-03). No normalization exists for this rule at all. |

### Data-Flow Trace (Level 4)

Not applicable in the conventional sense (no UI/dynamic-data rendering) — the equivalent trace here is the decision-to-execution path, covered under Key Link Verification above. The trace confirms: a CONFIRM decision for a destructive command flows unmodified into `run_shell` execution when `--yes` is set, with no secondary check. This was true in the prior round and remains true — the regression here is entirely in `safety.check()`'s classification, not in the execution path.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Round-2 fix: `bash -c "sudo rm -rf /"` (exact `-c`) is blocked, both `yes` values | `check(['bash','-c','sudo rm -rf /'], yes=False)` / `yes=True` | Both `{'kind': 'BLOCK', 'reason': "'bash -c' wraps a blocked command: 'sudo' is blocked outright (no safe invocation)"}` | PASS (round-2 fix confirmed live) |
| Round-2 fix: `chmod --recursive 777 /` is blocked | `check(['chmod','--recursive','777','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` | PASS (round-2 fix confirmed live) |
| Round-2 fix: `rm -rf //` is blocked | `check(['rm','-rf','//'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'rm' targeting '//' is a dangerous deletion target"}` | PASS (round-2 fix confirmed live) |
| Round-3 CR-01: `bash -lc "sudo rm -rf /"` (combined short flags) | `check(['bash','-lc','sudo rm -rf /'], yes=True)` | `{'kind': 'CONFIRM'}` | FAIL — should BLOCK |
| Round-3 CR-01 spans all 3 shells: `sh -lc`, `zsh -ic`, `sh -xc` (control variants) | `check(['sh','-lc',...], yes=True)`, `check(['zsh','-ic',...], yes=True)`, `check(['sh','-xc',...], yes=True)` | All `{'kind': 'CONFIRM'}` | FAIL — all should BLOCK |
| Round-3 CR-02: `chmod -R 777 //` and `chown -R user //` | `check(['chmod','-R','777','//'], yes=True)` / `check(['chown','-R','user','//'], yes=True)` | Both `{'kind': 'CONFIRM'}` | FAIL — should BLOCK |
| Round-3 CR-02 (long flag + `//`): `chmod --recursive 777 //` | `check(['chmod','--recursive','777','//'], yes=True)` | `{'kind': 'CONFIRM'}` | FAIL — should BLOCK |
| Round-3 CR-03: `dd if=/dev/zero of=//dev/sda` and `mkfs.ext4 //dev/sda` | `check(['dd','if=/dev/zero','of=//dev/sda'], yes=True)` / `check(['mkfs.ext4','//dev/sda'], yes=True)` | Both `{'kind': 'CONFIRM'}` | FAIL — should BLOCK |
| Control: single-slash equivalents of CR-03 correctly block | `check(['dd','if=/dev/zero','of=/dev/sda'], yes=True)` | `{'kind': 'BLOCK', 'reason': "'dd' targeting raw block device 'of=/dev/sda' is destructive"}` | PASS (control) |
| Full test suite | `.venv/bin/python -m pytest tests/ -q` | `109 passed in 1.89s` | PASS — no regressions, but round-3 vectors are entirely untested |

All commands run via `PYTHONPATH=src python3 -c "from olla.safety import check; ..."` directly against the live `src/olla/safety.py` at HEAD (`528472d`) — no test mocks, no SUMMARY narration relied upon.

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository, and neither PLAN nor SUMMARY for this phase declares probe-based verification. Step 7c: SKIPPED (no declared or conventional probes).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-04 | 02-01/02-02 | Repetition guard aborts loop after 2-3x identical tool+args | SATISFIED | `loop.py` lines 97-106, unchanged, distinct diagnostic confirmed. Regression-confirmed via 109/109 passing tests. |
| SAFE-01 | 02-01/02-02 | `--dry-run` previews next call, no side effects | SATISFIED | `loop.py` unchanged, structurally isolated branch, confirmed no execution path. |
| SAFE-02 | 02-02/02-04/02-05 | Shell command blocklist (rm -rf /, sudo, dd, etc.) as speed-bump layer | BLOCKED | Round-2 forms (CR-01/02/03 from prior review) are now correctly BLOCK. But round-3 equivalent-form variants — `bash -lc "sudo rm -rf /"`, `chmod -R 777 //`/`chown -R user //`, `dd of=//dev/sda`/`mkfs.ext4 //dev/sda` — all empirically return CONFIRM, not BLOCK, despite their already-blocked canonical-flag/single-slash equivalents correctly BLOCKing. SAFE-02 explicitly names "rm -rf /" and "sudo" and "dd" as exemplar targets — `sudo` (via `bash -lc`) and a `dd`-class raw-device write (via `//dev/sda`) are both reachable through these one-character/one-token wrappers. "Speed-bump, not primary boundary" does not excuse this: these are equivalent-form variants of rules 02-05 explicitly claimed to fix, with one-line solutions already documented in `02-REVIEW.md`. |
| SAFE-03 | 02-01/02-02 | `--max-steps` cap (default 15) prevents infinite loops | SATISFIED | `loop.py` unchanged, `cli.py` default 15, confirmed. |
| SAFE-04 | 02-01/02-02/02-04/02-05 | Confirm prompt before shell/write_file, overridable with `--yes` | BLOCKED | Dispatch logic in `loop.py` (lines 116-123) is correct per D-04 — but because the three round-3 vectors are misclassified CONFIRM instead of BLOCK, `--yes` causes them to execute with zero confirmation: `bash -lc "sudo rm -rf /"`, `chmod -R 777 //` (full-filesystem permission change), and `dd if=/dev/zero of=//dev/sda` (raw block-device zeroing) all run unattended. This is exactly the "destructive action runs unattended" scenario SAFE-04 and the phase goal exist to prevent. |

All 5 requirement IDs declared across 02-01/02-02/02-03/02-04/02-05 PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability rows exactly (all currently marked "Pending" in REQUIREMENTS.md — none have been marked done, which is consistent with this report). No orphaned requirements.

02-05's SUMMARY claims `requirements-completed: [SAFE-02, SAFE-04]` for its own (narrower, round-2) scope — that claim is accurate for the three CR-01/02/03 forms it targeted (confirmed fixed above), but does not extend to the new round-3 equivalent-form bypass class discovered in the subsequent `02-REVIEW.md` pass (committed `1f14ef7`, post-wave-3). SAFE-02/SAFE-04 as overall phase requirements remain BLOCKED.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 202 | Exact-token check `"-c" in argv` does not match combined short-flag bundles (`-lc`, `-ic`, `-xc`, ...) that bash/sh/zsh treat identically to `-c` | BLOCKER | Round-3 CR-01 — the entire wrap-and-recurse fix added in 02-05 (fork-bomb + full D-03 recursion) is skipped for these forms, re-opening the `sudo`/`rm -rf /` bypass via a one-character flag change |
| `src/olla/safety.py` | 219 | Rule (7) (`chmod`/`chown -R` on `/`) uses exact `"/" in argv`, not normalized via `_normalize_rm_target` (added for rule 4 in 02-05) | BLOCKER | Round-3 CR-02 — `chmod -R 777 //` / `chown -R user //` / `chmod --recursive 777 //` bypass an otherwise-correct rule via the same `//`->`/` equivalence 02-05 already documented and fixed for `rm` |
| `src/olla/safety.py` | 92-101 | `_is_dangerous_device_arg` requires exact single-leading-slash `/dev/` prefix (`fnmatch(path, "/dev/*")`, `removeprefix("/dev/")`); no normalization of doubled leading slash | BLOCKER | Round-3 CR-03 — `dd of=//dev/sda` / `mkfs.ext4 //dev/sda` bypass the raw-device-write rule entirely |
| `src/olla/loop.py` | 24-27 | `call_model` accesses `response["message"]["content"]` unconditionally; raises uncaught `KeyError` if `think=True` and model returns only `thinking` | INFO (WR-01, not reachable from `run_loop`; only from `run_smoke_test`) | Not a phase-blocking gap — carried forward unchanged from prior review |
| `src/olla/loop.py` | 60-67 | Dry-run preview says "would prompt for confirmation" for CONFIRM decisions even when `--yes` would skip the prompt | INFO (WR-02, cosmetic/diagnostic-text-only) | Does not affect actual execution safety — carried forward unchanged |
| `src/olla/safety.py` | 75, 114-126 | `env -S "<command>"` remains CONFIRM by design — same wrap-and-recurse class as CR-01, documented as accepted residual in 02-05 SUMMARY (no `overrides:` entry exists, so this carries no formal weight, but is consistent with prior round's WARNING classification) | WARNING | Same root issue as CR-01 but via `env -S` rather than `bash -c`/`-lc`; candidate for the same fix pass |
| `src/olla/safety.py` | rule 6b recursion | T-02-05-05 (documented residual): `bash -c "true; sudo rm -rf /"` (shell-chained `-c` strings) — `shlex.split` produces `["true;", "sudo", ...]`, `argv[0]` is `"true;"` (not a recognized binary), so the chained `sudo` is not detected | WARNING | Same equivalent-form class as round-3 findings but explicitly out-of-scope per 02-05's threat_model (no override entry exists, so not formally accepted, but consistent with prior round's treatment as a separate, named residual) |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers found in `src/olla/safety.py` or `src/olla/loop.py`.

### Human Verification Required

None. All findings in this report are reproducible programmatically via direct `safety.check()` calls (shown above) — no UI, real-time, or external-service behavior is involved.

### Gaps Summary

**Closed since round 2:** 02-05 successfully closed all three round-2 gaps (CR-01: `bash/sh/zsh -c "<command>"` with the exact `-c` token now shlex-splits and recurses through the full D-03 blocklist; CR-02: `chmod/chown --recursive` on `/` now blocks; CR-03: `rm -rf //`/`///` normalized and blocked), plus an incidental crash fix (T-02-05-06, bare `-c` with no trailing argument no longer raises `IndexError`). All four are empirically confirmed fixed and regression-tested (109/109 tests pass, plus independent spot-checks above). `loop.py`, `tools/shell.py`, SAFE-01, SAFE-03, and LOOP-04 are unchanged and remain VERIFIED (regression-confirmed).

**New in round 3:** A fresh code review (`02-REVIEW.md`, committed `1f14ef7`, produced AFTER 02-05 merged) identified three NEW, independently-reproducible bypasses of the SAME phase requirements (SAFE-02/SAFE-04), each an **equivalent-form variant of a rule 02-05 explicitly fixed**:

1. **Round-3 CR-01**: `bash`/`sh`/`zsh` with combined short flags containing `c` (`-lc`, `-ic`, `-xc`, etc.) — rule (6b)'s exact `"-c" in argv` check does not recognize these, so the entire fork-bomb + recursion block (round-2's fix) is skipped. `bash -lc "sudo rm -rf /"` -> CONFIRM (should BLOCK, same as `bash -c "sudo rm -rf /"`). Confirmed across bash, sh, and zsh.
2. **Round-3 CR-02**: The `//`->`/` normalization 02-05 added (`_normalize_rm_target`, wired into rule 4 for `rm`) was never wired into rule (7) (`chmod`/`chown -R`). `chmod -R 777 //` / `chown -R user //` / `chmod --recursive 777 //` -> CONFIRM (should BLOCK, same as the single-slash forms).
3. **Round-3 CR-03**: `_is_dangerous_device_arg` (rule 5, `dd`/`mkfs*`) requires an exact single-leading-slash `/dev/` prefix with no normalization at all. `dd if=/dev/zero of=//dev/sda` / `mkfs.ext4 //dev/sda` -> CONFIRM (should BLOCK, same as the single-slash `/dev/sda` forms).

All three: (a) are reproducible against the live, current `src/olla/safety.py` at HEAD (`528472d`); (b) return CONFIRM (not BLOCK), which under `--yes` (SAFE-04's documented override) executes the destructive command with zero pause; (c) are equivalent-form variants of rules 02-05 explicitly fixed and claimed complete (`requirements-completed: [SAFE-02, SAFE-04]`), with one-line solutions already proposed in `02-REVIEW.md`; (d) are entirely untested by the current 109-test suite.

Per the phase goal ("every dangerous action is gated... blocklisted patterns are caught"), and per SAFE-02's explicit text naming "rm -rf /", "sudo", and "dd" as exemplar targets, these three reproducible bypasses constitute a real, unaddressed violation of SAFE-02 and SAFE-04 — independent of whether 02-05's own (narrower, literal-form) must_haves were satisfied (they were — see Behavioral Spot-Checks).

**On overrides:** No override exists in this VERIFICATION.md's frontmatter for these findings, and none is suggested. Per the verification-overrides reference, "implementation is simply incomplete, fix it instead" is explicitly excluded from override eligibility. All three findings are bugs in rules that 02-05 claimed to have fixed (not deliberately descoped), with known, small, proposed fixes (generalize rule 6b's `-c` detection to any short-flag bundle containing `c`; apply the existing slash-normalization helper to rule 7; add leading-slash normalization to `_is_dangerous_device_arg` for rule 5). The `env -S` residual (WR-03) and T-02-05-05 (chained `-c` strings) are pre-existing, separately-named residuals from 02-05's threat_model and remain WARNING-level, unchanged from the prior round — they are NOT being conflated with the three new BLOCKERs above.

**Step 9b (deferral check):** No later phase (Phase 3: File Tools, Phase 4: Memory Tool) addresses shell-blocklist hardening — deferral does not apply, consistent with the prior round's finding.

---

_Verified: 2026-06-13T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
