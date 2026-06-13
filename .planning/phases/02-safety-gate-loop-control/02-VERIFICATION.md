---
phase: 02-safety-gate-loop-control
verified: 2026-06-14T00:00:00Z
status: gaps_found
score: 3/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Round-3 CR-01: bash/sh/zsh with combined short flags containing 'c' (-lc, -ic, -xc, etc.) now matched via a next()-based scan for any '-'-prefixed, non-'--', 'c'-containing token, not just the exact '-c' token. check(['bash','-lc','sudo rm -rf /'], yes=True/False) -> BLOCK with reason mentioning 'sudo'. Confirmed live across bash -lc, sh -ic, zsh -xc."
    - "Round-3 CR-02: rule (7) (chmod/chown -R on '/') now applies the renamed _normalize_slash_target helper (shared with rule 4) to its '/' target check. check(['chmod','-R','777','//'], yes=True) and check(['chown','-R','user','//'], yes=True) -> BLOCK with reason \"'{binary} -R' targeting '/' is destructive\". chmod --recursive 777 // and chmod -R 777 /// also confirmed BLOCK."
    - "Round-3 CR-03: _is_dangerous_device_arg now collapses a leading run of 2+ slashes (non-end-anchored regex re.sub(r'^/{2,}', '/', path)) before the /dev/* fnmatch/removeprefix checks. check(['dd','if=/dev/zero','of=//dev/sda'], yes=True) and check(['mkfs.ext4','//dev/sda'], yes=True) -> BLOCK with reason mentioning 'raw block device'."
    - "T-02-06-04: end-to-end run_loop(--yes=True) test for 'bash -lc \"sudo rm -rf /\"' confirms BLOCK propagates through loop.py's existing dispatch with zero loop.py code changes (test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks PASSES)."
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02)"
    status: failed
    reason: "Rule (7)'s slash normalization (_normalize_slash_target, added in 02-06 to close round-3 CR-02) only collapses argv tokens that consist ENTIRELY of 2+ slashes (regex ^/{2,}$). It does not handle the dot-segment equivalent-form '/.', '//.' , or '/./, all of which os.path.normpath()/the kernel resolve to the same path as '/' (or '//' which Linux treats identically to '/'). chmod -R 777 /. and chown -R user /. are therefore classified CONFIRM, not BLOCK, even though they recursively chmod/chown the entire root filesystem — exactly the action rule (7) exists to block, and chmod/chown have NO --preserve-root default (unlike GNU rm). This is the SAME bypass class (equivalent-form variant of a rule explicitly fixed in this same phase) that rounds 2 and 3 both found and fixed for // and -lc/-Rf forms respectively — '/.'-family is a sibling equivalent-form of '/' that the current _normalize_slash_target regex does not cover."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "_normalize_slash_target (line 90): 're.sub(r\"^/{2,}$\", \"/\", arg)' is fully end-anchored and matches only strings composed entirely of 2+ slash characters. '/., '//.', '/./' contain a non-slash '.' segment and do not match this regex, so rule (7)'s 'any(_normalize_slash_target(a) == \"/\" for a in argv[1:])' check (line 232) is False for these forms and rule (7) never fires."
    missing:
      - "Extend rule (7)'s root-target detection to also recognize dot-segment equivalent forms of '/' (e.g. '/.', '//.' , '/./', '/.//.', etc.) — for example by additionally checking os.path.normpath(arg).rstrip('/') in ('', '/') or '/' for each argv element, or by adding a second normalization step that strips trailing '/.' / './' segments before the existing _normalize_slash_target comparison. Add regression tests: check(['chmod','-R','777','/.'], yes=True) -> BLOCK, check(['chown','-R','user','/.'], yes=True) -> BLOCK, check(['chmod','-R','777','//.'], yes=True) -> BLOCK, check(['chmod','--recursive','777','/./'], yes=True) -> BLOCK."
  - truth: "Confirm prompt before shell execution, overridable with --yes, does not permit destructive actions to run unattended (SAFE-04)"
    status: failed
    reason: "Because chmod/chown -R '/.'-family targets are misclassified CONFIRM (see SAFE-02 gap above), loop.py's existing CONFIRM+yes=True dispatch (lines 116-123, unchanged) executes 'chmod -R 777 /.' / 'chown -R user /.' unattended under --yes with zero pause — a recursive permission/ownership change across the entire root filesystem, which is precisely the unattended-destructive-action scenario SAFE-04 and the phase goal exist to prevent."
    artifacts:
      - path: "src/olla/loop.py"
        issue: "Lines 116-123 dispatch logic itself is correct per D-04 (CONFIRM+yes=True legitimately skips the prompt for genuinely CONFIRM-tier commands). The defect is entirely upstream in safety.py's rule (7) classification, as in the SAFE-02 gap above."
    missing:
      - "Fix the safety.py rule (7) gap above so '/.'-family chmod/chown -R targets return BLOCK; no loop.py change is needed once classification is correct."
deferred: []
---

# Phase 02: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.

**Verified:** 2026-06-14T00:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — round 4, after 02-06 closed the round-3 (CR-01/CR-02/CR-03 equivalent-form) gaps; this round independently re-derives equivalent-form probes for the same three rules and finds ONE NEW sibling equivalent-form bypass of rule (7) ('/.'-family dot-segment targets) that 02-06's fix does not cover.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `--dry-run` previews next tool call without executing it or any side effects (SAFE-01) | VERIFIED | `loop.py` unchanged since prior verification (02-06's `key-files` only modified `safety.py`, `test_safety.py`, `test_loop.py`, confirmed via `git diff HEAD~3 HEAD --stat`); structurally separate early-return branch, single `call_model`, no `run_shell`/`Confirm.ask` call anywhere in the dry-run path. Regression-confirmed: 121/121 tests pass. |
| 2 | Blocklisted dangerous patterns (rm -rf /, sudo, dd, etc.) are caught — no dangerous action escapes the gate (SAFE-02) | FAILED | All three round-3 forms (`bash -lc "sudo rm -rf /"`, `chmod -R 777 //`/`chown -R user //`, `dd of=//dev/sda`/`mkfs.ext4 //dev/sda`) are now correctly BLOCK — confirmed live against current `src/olla/safety.py`. However, a sibling equivalent-form variant of rule (7) — `chmod -R 777 /.` / `chown -R user /.` / `chmod -R 777 //.` / `chmod --recursive 777 /./` — all return CONFIRM, not BLOCK, despite `os.path.normpath()` resolving `/.` to `/` and the kernel treating `chmod -R / .` and `chmod -R /` identically (no `--preserve-root` default for chmod/chown). |
| 3 | `--max-steps` cap (default 15) prevents infinite loops (SAFE-03) | VERIFIED | `loop.py` unchanged since prior verification — `for step in range(1, max_steps + 1)`, distinct "Reached max steps" diagnostic, `cli.py` exposes `--max-steps` default 15. Regression-confirmed via 121/121 passing tests. |
| 4 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`, does not permit destructive actions to run unattended (SAFE-04) | FAILED | `loop.py` lines 116-123 dispatch is unchanged and correct per D-04 for true CONFIRM-tier commands, and the three round-3 misclassifications are now fixed (confirmed live, plus a new e2e test `test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks` PASSES). But the new `/.'-family chmod/chown -R rule (7) gap above means `chmod -R 777 /.` lands in CONFIRM and executes unattended under `--yes` with zero pause — a recursive permission change across the entire root filesystem. |
| 5 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3x in a row (LOOP-04) | VERIFIED | `loop.py` lines 97-106 unchanged: `sig = ("shell", tuple(argv))`, `repeat_count >= 3` triggers distinct "same shell call repeated 3x" message and `return`. Regression-confirmed via 121/121 passing tests. |

**Score:** 3/5 truths fully verified (Truths 1, 3, 5). Truths 2 and 4 each show the three round-3 forms now fixed, but FAIL overall due to a newly-identified sibling equivalent-form bypass of rule (7).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | Pure `check(argv, yes) -> Decision` blocklist/allowlist gate, D-01..D-04 | PARTIAL | Exists, substantive, wired. All three round-3 fixes (rules 5, 6b, 7 — slash normalization, combined-short-flag scan, doubled-slash device normalization) verified working live. `_normalize_rm_target` fully renamed to `_normalize_slash_target` (zero stale references, grep confirmed) and now shared between rules 4 and 7 as claimed. However, rule (7)'s normalization regex (`^/{2,}$`, fully end-anchored) does not cover the dot-segment equivalent forms of `/` (`/.`, `//.`, `/./`), leaving a sibling gap in the SAME rule that 02-06 just hardened. |
| `src/olla/loop.py` | Dispatch BLOCK/CONFIRM/ALLOW correctly, repetition guard, max-steps, dry-run | VERIFIED | Unmodified since prior (VERIFIED) round — confirmed via `git diff HEAD~3 HEAD --stat` (loop.py not in the changed-files list). All dispatch logic correct and matches D-04 intent. |
| `src/olla/tools/shell.py` | `run_shell(argv: list[str], timeout=30)`, pre-parsed argv, no internal re-parse | VERIFIED | Unmodified since prior (VERIFIED) round. |
| `tests/test_safety.py` | Coverage of blocklist/allowlist rules including 02-06 hardening | PARTIAL | 58 tests (up from 47), all passing — covers all 12 of 02-06's `must_haves.truths` (bash -lc/-ic/-xc combined flags, chmod/chown -R //, dd/mkfs* of=//dev/sda, plus D-04 yes=True variants and no-over-blocking regressions). No test exercises `chmod/chown -R /.`, `//.` , or `/./` — this newly-found gap is entirely untested. |
| `tests/test_loop.py` | End-to-end --yes BLOCK regressions | VERIFIED (for its declared scope) | 121 tests total including the new 02-06 end-to-end `--yes` BLOCK regression `test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks`, which mirrors and passes alongside the round-2 precedent `test_run_loop_bash_dash_c_sudo_with_yes_still_blocks`. No equivalent end-to-end test exists for the new `/.'-family gap (not part of 02-06's declared scope). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `loop.py` main loop | `safety.check()` | `decision = check(argv, yes=yes)` (line ~108) | WIRED | Correct call, correct argv (pre-parsed via single `shlex.split`). Unchanged since prior round. |
| `safety.check()` decision | `loop.py` dispatch | BLOCK -> never executes; CONFIRM+not yes -> `Confirm.ask`; CONFIRM+yes -> execute; ALLOW -> execute | WIRED | Dispatch logic itself is correct per D-04. The new defect is in what `check()` *returns* for `/.'-family chmod/chown inputs, not in how `loop.py` consumes the result. |
| `safety._blocklist_match` rule (6b) (bash/sh/zsh -c, combined short flags) | `safety._blocklist_match` (recursive call) | `next((i for i, a in enumerate(argv) if a.startswith("-") and not a.startswith("--") and "c" in a), None)` | WIRED | `check(['bash','-lc','sudo rm -rf /'], yes=True)` -> BLOCK, `check(['sh','-ic','sudo ls'], yes=False)` -> BLOCK, `check(['zsh','-xc','sudo ls'], yes=False)` -> BLOCK. All confirmed live. `check(['bash','-lc'], yes=False)` (no trailing command) -> CONFIRM, no IndexError. |
| `safety._normalize_slash_target` | rule (4) (`rm`) | `_normalize_slash_target(arg) in _RM_DANGEROUS_TARGETS` | WIRED | `check(['rm','-rf','//'], yes=False)` -> BLOCK (confirmed, unchanged from round 3). |
| `safety._normalize_slash_target` | rule (7) (`chmod`/`chown -R` on `/` and `//`/`///`) | `any(_normalize_slash_target(a) == "/" for a in argv[1:])` | WIRED for all-slash forms (`/`, `//`, `///`), NOT_WIRED for dot-segment forms (`/.`, `//.`, `/./`) | `check(['chmod','-R','777','//'], yes=True)` -> BLOCK (round-3 CR-02, now fixed, confirmed). `check(['chmod','-R','777','/.'], yes=True)` -> CONFIRM (new finding — `_normalize_slash_target`'s `^/{2,}$` regex does not match `/.` since it contains a non-slash character). |
| Slash-normalization (non-anchored `^/{2,}`) | `safety._is_dangerous_device_arg` (rule 5, `dd`/`mkfs*`) | `path = re.sub(r"^/{2,}", "/", path)` before `fnmatch(path, "/dev/*")` | WIRED | `check(['dd','if=/dev/zero','of=//dev/sda'], yes=True)` -> BLOCK (round-3 CR-03, now fixed, confirmed). `check(['mkfs.ext4','//dev/sda'], yes=True)` -> BLOCK (confirmed). |

### Data-Flow Trace (Level 4)

Not applicable in the conventional sense (no UI/dynamic-data rendering) — the equivalent trace here is the decision-to-execution path, covered under Key Link Verification above. The trace confirms: a CONFIRM decision for a destructive command flows unmodified into `run_shell` execution when `--yes` is set, with no secondary check. This was true in prior rounds and remains true for the newly-found `/.'-family gap — `chmod -R 777 /.` classified CONFIRM flows straight to `run_shell(['chmod','-R','777','/.'])` under `--yes`.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Round-3 CR-01 fix: `bash -lc "sudo rm -rf /"` (combined short flags), both `yes` values | `check(['bash','-lc','sudo rm -rf /'], yes=False)` / `yes=True` | Both `{'kind': 'BLOCK', 'reason': "'bash -c' wraps a blocked command: 'sudo' is blocked outright (no safe invocation)"}` | PASS (round-3 fix confirmed live) |
| Round-3 CR-01 fix spans all 3 shells: `sh -ic`, `zsh -xc` | `check(['sh','-ic','sudo ls'], yes=False)`, `check(['zsh','-xc','sudo ls'], yes=False)` | Both BLOCK, `"sudo"` in reason | PASS (round-3 fix confirmed live) |
| Round-3 CR-01 guard: `bash -lc` with no trailing command | `check(['bash','-lc'], yes=False)` | `{'kind': 'CONFIRM'}`, no exception | PASS — guard preserved, no IndexError regression |
| Round-3 CR-02 fix: `chmod -R 777 //` and `chown -R user //` | `check(['chmod','-R','777','//'], yes=True)` / `check(['chown','-R','user','//'], yes=True)` | Both `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` / `"'chown -R' ..."` | PASS (round-3 fix confirmed live) |
| Round-3 CR-02 fix (long flag + `//`): `chmod --recursive 777 //`, `chmod -R 777 ///` | `check(['chmod','--recursive','777','//'], yes=True)` / `check(['chmod','-R','777','///'], yes=True)` | Both BLOCK | PASS (round-3 fix confirmed live) |
| Round-3 CR-03 fix: `dd if=/dev/zero of=//dev/sda` and `mkfs.ext4 //dev/sda` | `check(['dd','if=/dev/zero','of=//dev/sda'], yes=True)` / `check(['mkfs.ext4','//dev/sda'], yes=True)` | Both `{'kind': 'BLOCK', 'reason': "'dd'/'mkfs.ext4' targeting raw block device ... is destructive"}` | PASS (round-3 fix confirmed live) |
| **NEW round-4 finding**: `chmod -R 777 /.` and `chown -R user /.` | `check(['chmod','-R','777','/.'], yes=True)` / `check(['chown','-R','user','/.'], yes=True)` | Both `{'kind': 'CONFIRM'}` | **FAIL — should BLOCK** (rule 7's intent is to block recursive chmod/chown of `/`; `/.` resolves to `/`) |
| **NEW round-4 finding**: `chmod -R 777 //.` and `chmod --recursive 777 /./` | `check(['chmod','-R','777','//.'], yes=True)` / `check(['chmod','--recursive','777','/./'], yes=True)` | Both `{'kind': 'CONFIRM'}` | **FAIL — should BLOCK** (same class, doubled-slash + dot-segment combination) |
| Control: literal `/` and `//` still correctly BLOCK rule (7) | `check(['chmod','-R','777','/'], yes=True)` | `{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}` | PASS (control — confirms rule 7 itself fires, only the `/.'-family normalization is missing) |
| Lower-severity sibling: `rm -rf /.` (rm has GNU `--preserve-root` default in most distros, unlike chmod/chown) | `check(['rm','-rf','/.'], yes=True)` | `{'kind': 'CONFIRM'}` | Noted but not separately gapped — anchored on chmod/chown per the no-default-protection reasoning above; same underlying `_normalize_slash_target` limitation |
| Full test suite | `PYTHONPATH=src .venv/bin/python3 -m pytest tests/ -q` | `121 passed in 1.70s` | PASS — no regressions; matches SUMMARY's claim exactly; the new `/.'-family gap is entirely untested |

All commands run via `PYTHONPATH=src .venv/bin/python3 -c "from olla.safety import check; ..."` directly against the live `src/olla/safety.py` (post-`02-06`, commits `dd85f58`/`ec33508`/`7b7faf4`) — no test mocks, no SUMMARY narration relied upon.

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository, and neither PLAN nor SUMMARY for this phase declares probe-based verification. Step 7c: SKIPPED (no declared or conventional probes).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-04 | 02-01/02-02 | Repetition guard aborts loop after 2-3x identical tool+args | SATISFIED | `loop.py` lines 97-106, unchanged, distinct diagnostic confirmed. Regression-confirmed via 121/121 passing tests. |
| SAFE-01 | 02-01/02-02 | `--dry-run` previews next call, no side effects | SATISFIED | `loop.py` unchanged, structurally isolated branch, confirmed no execution path. |
| SAFE-02 | 02-02/02-04/02-05/02-06 | Shell command blocklist (rm -rf /, sudo, dd, etc.) as speed-bump layer | BLOCKED | Round-3 forms (`bash -lc`, `chmod/chown -R //`, `dd/mkfs* of=//dev/sda`) are now correctly BLOCK — 02-06's fixes confirmed working. But a sibling equivalent-form variant of rule (7) — `chmod -R 777 /.` / `chown -R user /.` / `//.` / `/./` — empirically returns CONFIRM, not BLOCK, despite resolving to the exact same root-filesystem target that rule (7) exists to block (and that the literal `/` and `//` forms correctly block). SAFE-02 names recursive destructive filesystem operations as an exemplar; `chmod -R 777 /.` is a full-root permission change reachable through a two-character path suffix. |
| SAFE-03 | 02-01/02-02 | `--max-steps` cap (default 15) prevents infinite loops | SATISFIED | `loop.py` unchanged, `cli.py` default 15, confirmed. |
| SAFE-04 | 02-01/02-02/02-04/02-05/02-06 | Confirm prompt before shell/write_file, overridable with `--yes` | BLOCKED | Dispatch logic in `loop.py` (lines 116-123) is correct per D-04, and 02-06's e2e test for the round-3 `-lc` form PASSES. But because the `/.'-family chmod/chown -R targets above are misclassified CONFIRM instead of BLOCK, `--yes` causes `chmod -R 777 /.` (full-root recursive permission change) to execute with zero confirmation — the same "destructive action runs unattended" scenario the phase goal and SAFE-04 exist to prevent. |

All 6 requirement IDs declared across 02-01 through 02-06 PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability rows exactly (all currently marked "Pending" in REQUIREMENTS.md — none have been marked done, which is consistent with this report). No orphaned requirements.

02-06's SUMMARY claims `requirements-completed: [SAFE-02, SAFE-04]` for its own (round-3) scope — that claim is accurate for the three CR-01/02/03 forms it targeted (confirmed fixed above, all 12 of its `must_haves.truths` verified). The newly-found `/.'-family gap was outside 02-06's declared scope (its `must_haves.truths` did not enumerate dot-segment forms). SAFE-02/SAFE-04 as overall phase requirements remain BLOCKED due to this sibling gap in the same rule (7) that 02-06 just hardened.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 90, 232 | `_normalize_slash_target`'s regex (`^/{2,}$`, fully end-anchored) only collapses all-slash strings; rule (7)'s `/`-target check (`any(_normalize_slash_target(a) == "/" for a in argv[1:])`) therefore misses dot-segment equivalent forms of `/` (`/.`, `//.`, `/./`) that `os.path.normpath`/the kernel resolve identically to `/` | BLOCKER | `chmod -R 777 /.` / `chown -R user /.` / `chmod -R 777 //.` / `chmod --recursive 777 /./` all bypass rule (7) and execute a full-root recursive permission/ownership change unattended under `--yes` — same severity class as the round-2/round-3 findings this phase already fixed twice for sibling equivalent forms (`//`, `-lc`) |
| `src/olla/loop.py` | 24-27 | `call_model` accesses `response["message"]["content"]` unconditionally; raises uncaught `KeyError` if `think=True` and model returns only `thinking` | INFO (WR-01, not reachable from `run_loop`; only from `run_smoke_test`) | Not a phase-blocking gap — carried forward unchanged from prior rounds |
| `src/olla/loop.py` | 60-67 | Dry-run preview says "would prompt for confirmation" for CONFIRM decisions even when `--yes` would skip the prompt | INFO (WR-02, cosmetic/diagnostic-text-only) | Does not affect actual execution safety — carried forward unchanged |
| `src/olla/safety.py` | 75, 110-132 | `env -S "<command>"` remains CONFIRM by design — same wrap-and-recurse class as CR-01, documented as accepted residual (T-02-06-06) in 02-06's threat_model | WARNING | Same root issue as CR-01 but via `env -S` rather than `bash -c`/`-lc`; explicitly accepted as out-of-scope residual, carried forward unchanged |
| `src/olla/safety.py` | rule 6b recursion | T-02-06-05 (documented accepted residual): `bash -c "true; sudo rm -rf /"` (shell-chained `-c` strings via `&&`/`;`/`\|`) — `shlex.split` produces `["true;", "sudo", ...]`, `argv[0]` is `"true;"` (not a recognized binary), so the chained `sudo` is not detected | WARNING | Same equivalent-form class as round-3 findings but explicitly named and accepted as out-of-scope per 02-06's threat_model, carried forward unchanged |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers found in `src/olla/safety.py`, `tests/test_safety.py`, or `tests/test_loop.py` (`grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` -> no matches).

### Human Verification Required

None. All findings in this report are reproducible programmatically via direct `safety.check()` calls (shown above) — no UI, real-time, or external-service behavior is involved.

### Gaps Summary

**Closed since round 3:** 02-06 successfully closed all three round-3 gaps:

1. **Round-3 CR-01** (`bash`/`sh`/`zsh` combined short-flags `-lc`/`-ic`/`-xc` etc.): rule (6b) now scans for any `-`-prefixed, non-`--`, `c`-containing token via `next(...)`, not just the exact `-c` token. Confirmed BLOCK across bash, sh, and zsh, both `yes` values, with no IndexError on truncated `bash -lc` (no trailing command).
2. **Round-3 CR-02** (`chmod`/`chown -R //`, `///`, `--recursive ... //`): rule (7) now applies `_normalize_slash_target` (renamed from `_normalize_rm_target`, now shared with rule 4) to its `/`-target check. Confirmed BLOCK for all tested doubled/tripled-slash + long-flag forms.
3. **Round-3 CR-03** (`dd`/`mkfs* of=//dev/sda`): `_is_dangerous_device_arg` now collapses a leading run of 2+ slashes (non-anchored `^/{2,}` regex) before the `/dev/*` fnmatch. Confirmed BLOCK for `dd of=//dev/sda` and `mkfs.ext4 //dev/sda`.
4. **T-02-06-04**: a new e2e test (`test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks`) confirms the CR-01 fix propagates through `loop.py`'s unchanged dispatch under `--yes`. PASSES.

All four are empirically confirmed fixed via direct `check()` calls against the live `src/olla/safety.py`, plus the full 121-test suite (109 prior + 11 new unit tests + 1 new e2e test) passes with zero regressions. `loop.py`, `tools/shell.py`, SAFE-01, SAFE-03, and LOOP-04 are unchanged and remain VERIFIED.

**New in round 4:** Independently probing for "any NEW equivalent-form bypass classes the [round-3] fix might have missed" (per this verification's mandate) surfaced one sibling gap in rule (7), the SAME rule 02-06 just hardened for round-3 CR-02:

- **`chmod -R 777 /.`**, **`chown -R user /.`**, **`chmod -R 777 //.`**, **`chmod --recursive 777 /./`** all return CONFIRM, not BLOCK.
- `os.path.normpath("/.")` -> `/`, and on Linux `chmod -R` on `/.` recursively touches the entire root filesystem exactly as `chmod -R /` does — chmod/chown have no `--preserve-root` default (unlike GNU `rm`, which does in most distros).
- The control case `chmod -R 777 /` correctly BLOCKs (`{'kind': 'BLOCK', 'reason': "'chmod -R' targeting '/' is destructive"}`), confirming rule (7) itself is intact — only its target-normalization (`_normalize_slash_target`, regex `^/{2,}$`, fully end-anchored, all-slash-only) fails to recognize `/.`-family as equivalent to `/`.
- This is the SAME bypass *class* (equivalent-form variant of an enumerated target in a rule already fixed once this phase) that rounds 2 and 3 both identified and fixed for `//` and `-lc`/`-Rf` respectively. Per the explicit precedent set by round 3's gaps summary ("equivalent-form variants of rules ... explicitly fixed ... [do not get the] 'speed-bump, not primary boundary' excuse"), this is not dismissible as an accepted residual.
- Other probed forms were checked and found NOT reachable or NOT a new gap: `bash --command=...` is not a valid bash flag (unreachable under `shell=False`); `chmod -R 777 /*` / `rm -rf //*` do not glob-expand under `shell=False` (literal `*`, doesn't reach `/`); `dd of=//dev/sda==` strips to an empty/invalid path via `split("=")[-1]` (not a real device). `rm -rf /.` shows the same underlying `_normalize_slash_target` limitation but is lower severity (rm's `--preserve-root` default mitigates it in most distros) and is noted in the spot-check table but not separately gapped.

**On overrides:** No override exists in this VERIFICATION.md's frontmatter for this finding, and none is suggested as accepted — per the verification-overrides reference, "implementation is simply incomplete, fix it instead" is explicitly excluded from override eligibility, and this is a one-line-scale fix to the SAME helper 02-06 just touched (extend `_normalize_slash_target` or add a parallel dot-segment normalization, consistent with how round-3 itself was closed). The `env -S` residual (T-02-06-06) and shell-chained `-c` strings (T-02-06-05) remain pre-existing, separately-named, explicitly-accepted residuals from 02-06's threat_model and are unchanged WARNING-level findings — they are NOT being conflated with the new BLOCKER above.

**Step 9b (deferral check):** Loaded `gsd-sdk query roadmap.analyze` equivalent — no later phase (Phase 3: File Tools, Phase 4: Memory Tool) addresses shell-blocklist hardening or chmod/chown target normalization. Deferral does not apply, consistent with all prior rounds' findings.

---

_Verified: 2026-06-14T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
