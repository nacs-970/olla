---
phase: 02-safety-gate-loop-control
verified: 2026-06-12T00:00:00Z
status: gaps_found
score: 3/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "A blocklisted command (rm -rf /, sudo, dd, etc.) is caught as a speed-bump before the confirm prompt (SAFE-02 / ROADMAP SC #2)"
    status: failed
    reason: "ALLOWLIST contains 'env' and 'find', both classified ALLOW by argv[0] alone with no inspection of their arguments. 'env' and 'find -exec' execute arbitrary subcommands, so a model emitting `env rm -rf /`, `env sudo ls`, `env dd if=/dev/zero of=/dev/sda`, or `find . -exec rm -rf {} \\;` gets check()==ALLOW and runs with ZERO gating — the entire D-03 blocklist (sudo/su/shutdown/rm-dangerous-targets/dd-on-device/chmod -R /) is bypassed via this path. Confirmed empirically: `check(['env','rm','-rf','/'], yes=False)` -> `{'kind': 'ALLOW'}`."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "ALLOWLIST (lines 14-28) includes 'env' and 'find'; _blocklist_match() (lines 71-100) never special-cases these binaries' arguments, so check() returns ALLOW for argv[0] in {'env','find'} regardless of what command they wrap or exec."
    missing:
      - "Remove 'env' and 'find' from ALLOWLIST (fall through to CONFIRM), OR add _blocklist_match rules that demote 'env <non-KEY=VALUE arg>' and 'find ... -exec/-execdir/-ok/-okdir ...' to CONFIRM/BLOCK so the wrapped command is gated."
      - "Add regression tests proving `check(['env','rm','-rf','/'], yes=False)` and `check(['find','.','-exec','rm','-rf','{}',';'], yes=False)` are NOT 'ALLOW' (currently tests/test_safety.py asserts the opposite — these tests encode the bypass and must be rewritten alongside the fix)."
  - truth: "Confirm prompt (rich.Confirm.ask) before shell/write_file execution, overridable with --yes (SAFE-04 / ROADMAP SC #1)"
    status: failed
    reason: "Same root cause as SAFE-02: 'env <cmd>' and 'find ... -exec <cmd>' resolve to ALLOW, so run_loop's gate dispatch never reaches the Confirm.ask branch for these commands — the user never sees a confirm prompt for a command that executes 'sudo', 'rm -rf /', 'dd', etc. via env/find. The confirm-gate is real and correctly wired for every OTHER command shape (verified by code reading of src/olla/loop.py lines 97-125 and the 02-01 test additions), but is bypassed entirely for this class of input."
    artifacts:
      - path: "src/olla/safety.py"
        issue: "Same as above — check() returns ALLOW for env/find-wrapped dangerous commands, so loop.py's CONFIRM branch (lines 105-112) is never entered for them."
    missing:
      - "Same fix as SAFE-02 gap — once env/find fall through to CONFIRM (or BLOCK for their dangerous forms), the existing Confirm.ask wiring in loop.py will correctly gate them with no further loop.py changes needed."
deferred: []
human_verification: []
---

# Phase 2: Safety Gate + Loop Control Verification Report

**Phase Goal:** A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.
**Verified:** 2026-06-12T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth (ROADMAP SC) | Status | Evidence |
|---|---------|--------|----------|
| 1 | Before any shell execution, the user sees the fully-resolved command string in a confirm prompt and can decline, with `--yes` skipping confirmation | ✗ FAILED | True for the vast majority of commands (verified in `src/olla/loop.py:97-112` — `check()` -> CONFIRM -> `Confirm.ask(f"Run \`{' '.join(argv)}\`?", default=False)`, EOFError-safe, `--yes` skips it). BUT `env <cmd>` and `find ... -exec <cmd>` are classified ALLOW (see CR-01) and never reach this branch — the user sees **no prompt at all** before a wrapped `sudo`/`rm -rf /`/`dd` executes. |
| 2 | A blocklisted command (`rm -rf /`, `sudo`, `dd`, etc.) is caught as a speed-bump before the confirm prompt | ✗ FAILED | The D-03 blocklist rules themselves are correctly implemented and unit-tested for direct invocation (`check(['rm','-rf','/'], yes=False)` -> BLOCK, `check(['sudo','ls'],...)` -> BLOCK, `check(['dd','if=/dev/zero','of=/dev/sda'],...)` -> BLOCK — all verified, 17/17 tests in `tests/test_safety.py` pass). BUT these same commands wrapped as `env rm -rf /`, `env sudo ls`, `env dd if=/dev/zero of=/dev/sda`, or `find . -exec rm -rf {} \;` bypass the blocklist entirely and resolve to ALLOW. Confirmed empirically (see gap detail). |
| 3 | `--dry-run` shows the next planned tool call and stops without executing it or causing any side effect | ✓ VERIFIED | `src/olla/loop.py:37-68` — `if dry_run:` block makes exactly one `call_model`/`parse_response` call, dispatches on all 4 `parsed["type"]` shapes (final/none/unknown-tool/shell), reuses `check(argv, yes=yes)` for the shell verdict, returns before any `run_shell`/`Confirm.ask`. Structurally cannot execute. Note: because it reuses the same flawed `check()`, `--dry-run` on `env rm -rf /` would print `"...— auto-approved (read-only allowlist)"`, an inaccurate-but-non-executing preview — this is a downstream symptom of CR-01, not a separate dry-run defect. The dry-run mechanism itself (truth #3) holds. |
| 4 | The loop aborts with a diagnostic when it hits `--max-steps` (default 15) or when the same tool+args is called 2-3 times in a row | ✓ VERIFIED | `src/olla/loop.py:70-123` — `prev_sig`/`repeat_count` tracks `("shell", tuple(argv))`; 3rd consecutive identical signature prints `"olla stopped: same shell call repeated 3x — model likely stuck"` and returns before the 3rd `run_shell`. `"Reached max steps (N) without a <final> answer."` (line 146) is unchanged and reachable for varied calls (SAFE-03 regression test per 02-02-SUMMARY). Both diagnostic strings are present and textually distinct (`grep` confirmed). **Caveat (WARNING, not blocking):** per code review WR-01, the repetition counter is only updated on the path that has already passed the BLOCK/CONFIRM-decline `continue`s (loop.py line 114 is after lines 99-103 and 105-112's continues) — a model repeating the same BLOCKED or declined command 15x runs unguarded to max-steps instead of tripping the 3x guard. The truth as literally worded ("same tool+args called 2-3 times in a row" aborts) holds for the executed-call case but not for blocked/declined repeats. |

**Score:** 2/4 ROADMAP success criteria fully verified (SC #3, #4); 2/4 FAILED (SC #1, #2) due to CR-01.

### Must-Haves Cross-Reference (PLAN frontmatter, mechanical truths)

| # | Truth (from PLAN frontmatter) | Status | Evidence |
|---|---------|--------|----------|
| 1 | `check(argv, yes)` returns BLOCK for D-03 patterns, ALLOW for D-01 allowlist, CONFIRM otherwise | ✓ VERIFIED (mechanically) | `src/olla/safety.py` implements exactly this; 17/17 `tests/test_safety.py` tests pass. **However**, this mechanical correctness is precisely what CR-01 exploits — `env`/`find` are D-01-allowlisted-by-argv[0], so `check()` is "correct per its own narrow spec" while the spec itself has a hole that defeats the BLOCK rules for wrapped commands. |
| 2 | BLOCK takes precedence over ALLOW | ✓ VERIFIED | For direct invocations (`rm -rf /` is never in ALLOWLIST, so no conflict arises) this holds and is tested. Not violated in the literal sense, but moot for the env/find bypass since `_blocklist_match` never even considers the wrapped command. |
| 3 | `check()` performs no I/O | ✓ VERIFIED | `src/olla/safety.py` imports only `fnmatch` and `typing`; no `rich`/`subprocess`/project imports (grep confirmed). |
| 4 | BLOCK commands never reach `run_shell`; CONFIRM shows `Confirm.ask`; ALLOW runs without prompt; EOFError declines safely; `--yes` skips CONFIRM but not BLOCK | ✓ VERIFIED (for commands `check()` actually classifies BLOCK/CONFIRM) | `src/olla/loop.py:97-125` implements this dispatch correctly and 02-01/02-02 added matching tests per both SUMMARYs. The dispatch logic itself is sound — the gap is upstream, in which commands `check()` puts in which bucket. |
| 5 | `--dry-run` makes exactly one model call and never calls `run_shell`/`Confirm.ask` | ✓ VERIFIED | `src/olla/loop.py:37-68`, structurally separate early-return branch, confirmed by code reading. |
| 6 | Repetition guard aborts before 3rd identical call; 2x-then-different and gate-interrupted sequences proceed; max-steps message unshadowed | ✓ VERIFIED (with WR-01 caveat above) | `src/olla/loop.py:70,114-123`; both diagnostic strings present and distinct. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/safety.py` | ALLOWLIST, blocklist rule table, `check(argv, yes) -> Decision` pure function | ⚠️ EXISTS BUT FLAWED | Exists, exports `Decision`/`ALLOWLIST`/`check` per contract, zero I/O. The D-01 allowlist design contains `env` and `find`, which are NOT side-effect-free as claimed in the module's own comment ("read-only, side-effect-free commands") — see CR-01. |
| `tests/test_safety.py` | Unit tests for D-01/D-03 + BLOCK>ALLOW>CONFIRM ordering | ⚠️ EXISTS, 17/17 PASS, BUT ENCODES THE BUG | All 17 tests pass (`PYTHONPATH=src python3 -m pytest tests/test_safety.py -q` -> "17 passed"). However, the plan's own Task-1 behavior bullet (`02-01-PLAN.md` line 192) asserts `check(["find", ...], yes=False)["kind"] == "ALLOW"` and `check(["env", ...], yes=False)["kind"] == "ALLOW"` as PASSING test cases — these tests pass because they assert the vulnerable behavior, not because the vulnerability is absent. Green tests here are not evidence of safety. |
| `src/olla/loop.py` | `run_loop(..., yes, dry_run)` with safety-gate dispatch wrapping `run_shell`, EOFError-safe confirm | ✓ VERIFIED (wiring) | Confirmed by direct code read: imports `Confirm` and `check`, signature matches, dispatch order matches plan, repetition guard present, dry-run branch present. |
| `src/olla/cli.py` | `--yes`/`--dry-run` wired into `run_loop(...)`; inert notices removed | ✓ VERIFIED | `run_loop(task=task, model=model, max_steps=max_steps, system_prompt=SYSTEM_PROMPT, yes=yes, dry_run=dry_run)` (line 30); `grep` for "is not yet enforced" returns nothing in `cli.py`. |
| `pyproject.toml` | `rich>=13` added to dependencies | ✓ VERIFIED | `pyproject.toml:12` — `"rich>=13",` present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/olla/loop.py` | `src/olla/safety.py` | `check(argv, yes=yes)` | ✓ WIRED | Called at line 97 (main loop gate dispatch) and line 59 (dry-run verdict) — 2 occurrences, as 02-02 verification expected. |
| `src/olla/cli.py` | `src/olla/loop.py` | `run_loop(..., yes=yes, dry_run=dry_run)` | ✓ WIRED | Confirmed line 30. |
| `tests/test_safety.py` | `src/olla/safety.py` | `from olla.safety import check, ALLOWLIST` | ✓ WIRED | 17/17 tests pass. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `check()` blocks direct `rm -rf /` | `check(['rm','-rf','/'], yes=False)` | `{'kind': 'BLOCK', 'reason': "'rm' targeting '/' is a dangerous deletion target"}` | ✓ PASS |
| `check()` allows `env rm -rf /` (CR-01 bypass) | `check(['env','rm','-rf','/'], yes=False)` | `{'kind': 'ALLOW'}` | ✗ FAIL — confirms CR-01 |
| `check()` allows `env sudo ls` (CR-01 bypass) | `check(['env','sudo','ls'], yes=False)` | `{'kind': 'ALLOW'}` | ✗ FAIL — confirms CR-01 |
| `check()` allows `find . -exec rm -rf {} ;` (CR-01 bypass) | `check(['find','.','-exec','rm','-rf','{}',';'], yes=False)` | `{'kind': 'ALLOW'}` | ✗ FAIL — confirms CR-01 |
| `check()` allows `env dd if=/dev/zero of=/dev/sda` (CR-01 bypass) | `check(['env','dd','if=/dev/zero','of=/dev/sda'], yes=False)` | `{'kind': 'ALLOW'}` | ✗ FAIL — confirms CR-01 |
| `tests/test_safety.py` test suite | `PYTHONPATH=src python3 -m pytest tests/test_safety.py -q` | "17 passed" | ✓ PASS (but see artifact note — passing tests encode the vulnerability) |
| Full test suite (`tests/test_loop.py`, `tests/test_cli.py`) | `PYTHONPATH=src python3 -m pytest tests/ -q` | `ModuleNotFoundError: No module named 'ollama'` | ? SKIP — environment lacks `ollama`/`rich` (no project venv reachable in this session; SUMMARY claims 77/77 in the executor's venv, which this verifier cannot access). loop.py/cli.py wiring was instead verified by direct code reading (see Key Link and Artifact tables above), which is sufficient to confirm the dispatch structure matches the plan. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SAFE-02 | 02-01 | Shell command blocklist as a speed-bump layer | ✗ BLOCKED | Blocklist is implemented and unit-tested for direct invocation, but bypassed entirely via `env`/`find` (CR-01). The blocklist does not function as a safety boundary for the documented threat model — see gap above. |
| SAFE-04 | 02-01 | Confirm prompt before shell execution, overridable with `--yes` | ✗ BLOCKED | Confirm-gate dispatch is correctly wired in `loop.py`, but `env`/`find`-wrapped commands never reach it (CR-01) — the user gets zero prompt for a class of dangerous commands. |
| SAFE-01 | 02-02 | `--dry-run` previews next tool call without side effects | ✓ SATISFIED (mechanism); ⚠️ inherits CR-01's inaccuracy | The dry-run mechanism itself is sound (one model call, no execution, returns before run_shell/Confirm.ask). It reuses `check()`, so a dry-run preview of `env rm -rf /` would print "auto-approved (read-only allowlist)" — an inaccurate-but-harmless preview (D-09's "honest preview" intent is undermined for this command class, but `--dry-run`'s own no-side-effects guarantee is not violated). |
| SAFE-03 | 02-02 | `--max-steps` cap prevents infinite loops, with diagnostic distinct from repetition message | ✓ SATISFIED | `"Reached max steps (N)..."` message present and unchanged; SAFE-03 regression test (`test_run_loop_max_steps_with_varied_shell_calls` per 02-02-SUMMARY) asserts both messages don't co-occur for varied calls. Verified by code reading (line 146) and grep. |
| LOOP-04 | 02-02 | Repetition guard aborts on 2-3x identical tool+args | ✓ SATISFIED (with WARNING) | `prev_sig`/`repeat_count` mechanism present, distinct diagnostic confirmed. WR-01 caveat: doesn't cover BLOCK/declined-CONFIRM repeats (warning, not blocking — guard works for the primary executed-call case). |

All 5 requirement IDs from PLAN frontmatter (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04) match REQUIREMENTS.md's Phase 2 traceability row exactly — no orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/olla/safety.py` | 14-28 | `ALLOWLIST` includes `env`/`find` — argv[0]-only matching insufficient for these two binaries since both can execute arbitrary subcommands as arguments | 🛑 BLOCKER | Defeats the entire D-03 blocklist and the CONFIRM gate for any command wrapped in `env` or `find -exec`; directly contradicts the project's non-negotiable safety constraint (blocklist + confirm-gating). This is CR-01 from `02-REVIEW.md`, confirmed empirically. |
| `src/olla/loop.py` | 114 | Repetition signature (`prev_sig`/`repeat_count`) only updated on the path past BLOCK/CONFIRM-decline `continue`s | ⚠️ WARNING | A model repeating the same BLOCKED or declined command does not trip the 3x repetition guard and runs to max-steps instead. Does not change phase status but should be addressed alongside CR-01 fix (WR-01 from `02-REVIEW.md`). |
| `src/olla/safety.py` | 55-56, 92-94 | Fork-bomb rule (`_FORK_BOMB_TOKENS`) uses exact 3-element list equality; an unspaced variant `:(){:|:&};:` (single shlex token) is not caught by this rule and falls through to CONFIRM instead of BLOCK | ℹ️ INFO | WR-02 from `02-REVIEW.md` — lower severity since CONFIRM still requires human approval (or `--yes`); not a silent-execution bypass like CR-01. |

## Human Verification Required

None — CR-01 was confirmed programmatically by direct execution of `check()`, and the gap is unambiguous (code-level, not UX/visual/timing-dependent).

## Gaps Summary

Phase 2's goal — "a user can trust olla with shell execution because every dangerous action is gated... blocklisted patterns are caught" — is **not achieved** due to a single root-cause defect (CR-01, flagged in the just-completed `02-REVIEW.md` and confirmed here by direct execution):

`ALLOWLIST` in `src/olla/safety.py` includes `env` and `find`. `check()` classifies argv based solely on `argv[0]` membership in `ALLOWLIST` (D-01/D-02 design). But `env <cmd> [args...]` runs `<cmd>` directly, and `find ... -exec <cmd> ...` runs `<cmd>` for every matched path — neither is "read-only, side-effect-free" as the code comment claims. As a result:

- `check(['env','rm','-rf','/'], yes=False)` -> `{'kind': 'ALLOW'}` (should be BLOCK — matches the existing `rm`-dangerous-target rule if `env` were stripped)
- `check(['env','sudo','ls'], yes=False)` -> `{'kind': 'ALLOW'}` (should be BLOCK — `sudo` is hard-blocked)
- `check(['env','dd','if=/dev/zero','of=/dev/sda'], yes=False)` -> `{'kind': 'ALLOW'}` (should be BLOCK — raw device write)
- `check(['find','.','-exec','rm','-rf','{}',';'], yes=False)` -> `{'kind': 'ALLOW'}` (should be at minimum CONFIRM, arguably BLOCK)

This breaks **ROADMAP Phase 2 Success Criteria #1 and #2** (the contract) directly: the user receives NO confirm prompt and the blocklist NEVER runs for this entire class of commands. It maps to **SAFE-02 (blocklist as speed-bump)** and **SAFE-04 (confirm-gate)** — both BLOCKED. It also taints **SAFE-01 (--dry-run)** indirectly, since dry-run's verdict is derived from the same flawed `check()` and would print a falsely-reassuring "auto-approved" for these commands (though dry-run's own no-execution guarantee holds).

The 17/17 passing `tests/test_safety.py` tests are not exonerating — `02-01-PLAN.md`'s own Task-1 behavior spec (line 192) explicitly asserts `check(["find",...])["kind"] == "ALLOW"` and `check(["env",...])["kind"] == "ALLOW"` as the expected/passing behavior. The tests encode the vulnerability rather than guard against it.

SAFE-03 (max-steps + distinct diagnostic) and LOOP-04 (repetition guard) ARE correctly implemented and verified by code reading (their tests could not be executed in this session due to a missing `ollama`/`rich` environment — an infrastructure issue unrelated to the phase's code). One non-blocking warning (WR-01) was carried forward: the repetition guard doesn't cover repeated BLOCK/declined calls.

**Recommended fix** (per `02-REVIEW.md`'s own suggestion, which a closure plan should implement): remove `env` and `find` from `ALLOWLIST` (falling through to CONFIRM), or add targeted `_blocklist_match` rules that demote `env <non-KEY=VALUE arg>` and `find ... -exec/-execdir/-ok/-okdir ...` to CONFIRM/BLOCK. Update `tests/test_safety.py` to assert the corrected (non-ALLOW) behavior for these argv shapes.

---

_Verified: 2026-06-12T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
