---
phase: 05-safe-inspection-tools
verified: 2026-09-22T00:00:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/05-safe-inspection-tools/05-01-PLAN.md"
  - ".planning/phases/05-safe-inspection-tools/05-01-SUMMARY.md"
  - ".planning/phases/05-safe-inspection-tools/05-CONTEXT.md"
  - "src/olla/loop.py"
  - "src/olla/prompts.py"
  - "src/olla/tools/inspect.py"
  - "tests/test_loop.py"
  - "tests/test_prompts.py"
  - "tests/test_tools/test_inspect.py"
covered_digest: "v1:sha256:4bc36f224364618673e38a41655e255ac942c9c140be0eb8ed20c0d544f169e4"
digest_refresh:
  date: "2026-09-22"
  reason: >
    Digest-only refresh: src/olla/prompts.py gained an explicit tag-format warning line
    concurrently with this verification agent's run. No re-verification of phase 5's own
    behavior needed — the change is additive/orthogonal to list_dir/grep_files, confirmed by
    the full 473/473 test suite passing unchanged.
fingerprint_note: >
  The task instructions described a confirmed gsd-tools bug where verification.fingerprint
  silently drops the first covered-file argument, recommending a throwaway placeholder as
  args[0]. This did NOT reproduce on the installed gsd-core 1.13.0: the CLI routes args[2]
  as phaseDir and args.slice(3) as covered files (verification-command-router.cjs), and a
  placeholder as the first file argument caused a hard error ("a covered file is missing,
  unreadable, or escapes the project root") rather than being silently dropped. The digest
  above was computed from the plain invocation (phase dir + all 10 real covered files, no
  placeholder) and the tool's own JSON output confirms all 10 files are present in
  covered_files with none missing. Do not propagate the placeholder workaround to future
  phases on this gsd-core version without re-confirming the bug still exists.
---

# Phase 5: Safe Inspection Tools Verification Report

**Phase Goal:** As a user running tasks with olla, I want the model to list directory contents and grep across files without safety confirmation prompts, so that discovery is fast and frictionless.
**Verified:** 2026-09-22
**Status:** passed
**Re-verification:** No — initial verification (no prior 05-VERIFICATION.md existed; this phase was the only one of the v1.1 milestone's three phases missing a formal report)

## Goal Achievement

### Observable Truths (Roadmap Success Criteria + PLAN must-haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `list_dir(path)` returns a directory tree with `[d]`/`[f]`/`[l]` type markers, names, and human-readable sizes, sorted directories-first-then-alphabetical, symlinks never followed, hidden dotfiles shown, capped at 50 entries with a trailing truncation note (SC1, INSPECT-01, D-01..D-05, D-11, D-12) | ✓ VERIFIED | `src/olla/tools/inspect.py:18-58` (`list_dir`, `_human_size`); sort key `(not entry.is_dir(follow_symlinks=False), entry.name)` puts dirs first, then alphabetical (line 29-30); symlink branch uses `entry.is_symlink()` checked before `is_dir`, formats `"[l] name -> target"` via `os.readlink`, never calls `is_dir`/`stat` with `follow_symlinks=True` anywhere in the function (line 42-47); cap-then-truncate-note logic at line 37-40. Unit tests `test_list_dir_populated`, `test_list_dir_human_size`, `test_list_dir_symlink_not_followed`, `test_list_dir_hidden_dotfile`, `test_list_dir_truncation`, `test_list_dir_nonexistent`, `test_list_dir_on_file` all pass (independently re-run). Live spot-checks: a 51-entry directory produced exactly 51 output lines (50 entries + 1 "... 1 more entries not shown" note); a second check at 120 entries produced 51 lines ending "... 70 more entries not shown" (120-50=70), confirming the `total - 50` truncation-count arithmetic is correct beyond the boundary case, not just an off-by-one that happens to vanish at n=51. |
| 2 | `grep_files(pattern, path[, recursive])` performs case-sensitive regex search over text files, skips `.git` and binary files, capped at 25 matching `file:line:text` lines with a trailing truncation note, never raises on invalid regex (SC2, INSPECT-02, D-06..D-08, D-11, D-12) | ✓ VERIFIED | `src/olla/tools/inspect.py:61-111` (`grep_files`); `re.compile` wrapped in `try/except re.error` returning an error dict (line 63-66); `.git` pruned via in-place `dirnames[:] = [...]` mutation during `os.walk` (line 101, not a rebind — matches the required pitfall-avoidance pattern); binary sniff via first-8000-byte null check (line 74-77); non-recursive path uses single-level `os.scandir` (line 91-96), recursive path uses the pruning walk (line 99-109); cap at 25 with `"... more matches not shown"` appended and scanning stopped (line 84-89, 95-96, 105-107). Unit tests `test_grep_files_matches_case_sensitive`, `test_grep_files_recursive_false_skips_subdir`, `test_grep_files_recursive_true_descends`, `test_grep_files_excludes_git`, `test_grep_files_skips_binary`, `test_grep_files_invalid_regex`, `test_grep_files_truncation` all pass. Independent live spot-checks by this verifier: invalid regex `"("` returned `{'error': "invalid regex '(': missing ), unterminated subpattern..."}`  without raising; a nested `.git/config` containing the search term was correctly excluded from recursive results while a sibling file with the same term was found. Symlinked files are skipped by different mechanisms in the two scan paths — the recursive walk explicitly checks `os.path.islink(full_path)` (line 105), while the non-recursive path relies on `entry.is_file(follow_symlinks=False)` (line 95) returning `False` for a symlink-to-file — functionally equivalent, not a gap. |
| 3 | Both tools execute with no interactive confirmation prompt — `run_loop()` dispatches `list_dir`/`grep_files` straight to their tool adapters, bypassing `safety.check()` entirely (D-09); `safety.py` is not modified or given a tool-name branch (SC3, INSPECT-03) | ✓ VERIFIED | Source-wide search confirms the only two call sites of `check(` in `src/olla/loop.py` are line 614 (`_preview_action`'s `shell` branch) and line 697 (`_execute_shell`) — no `check(` call exists in `_execute_list_dir` (line 912-932), `_execute_grep_files` (line 935-956), or their `_prepare_action`/`_preview_action`/dispatch branches; `src/olla/safety.py` contains zero occurrences of `list_dir`/`grep_files` (grep confirmed empty), matching SUMMARY's claim of "zero diff" on that module for this phase. `test_run_loop_list_dir_dispatch_no_prompt` and `test_run_loop_grep_files_dispatch_no_prompt` mock `Confirm.ask` and assert `assert_not_called()` — both pass. |
| 4 | Output from both tools is recorded through the same untrusted-observation path `read_file` uses, so `untrusted_observation_seen` becomes True and is OBSERVABLY exercised — a two-turn test (inspection turn, then a CONFIRM-tier shell turn under `yes=True`) shows `Confirm.ask` IS called and the "Confirmation required: this action follows untrusted tool output." message is emitted (T-05-04 mitigation, load-bearing gate proof) | ✓ VERIFIED | `_execute_list_dir`/`_execute_grep_files` call `_record_file_observation` (not `_record_observation`) on success (loop.py:931, 955), wrapping content in `<untrusted_file_content>` tags identical to `read_file`'s path. Confirmed the actual gating mechanism at `loop.py:705-712`: `if decision["kind"] == "CONFIRM" and (not yes or untrusted_observation_seen):` — with `yes=True`, `Confirm.ask` is normally skipped for a CONFIRM-tier command unless `untrusted_observation_seen` flipped True, which is exactly what the inspection-tool dispatch does (`session.untrusted_observation_seen = _execute_list_dir(...) or session.untrusted_observation_seen`, loop.py:1206-1215). `git status` (used as the shell probe in both gate tests) is not in `safety.ALLOWLIST` (confirmed: `{ls, pwd, cat, echo, grep, head, tail, wc, file, date, whoami}`), so it resolves to CONFIRM tier and the test genuinely exercises the gate, not a no-op. `test_list_dir_gate_consequence_shell` and `test_grep_files_gate_consequence_shell` both assert `mock_confirm.assert_called_once()`, `mock_run_shell.assert_called_once()`, and that the exact "Confirmation required..." string appears in captured print output — both independently re-run and pass. `test_run_loop_list_dir_untrusted_observation` additionally confirms the `<untrusted_file_content>` wrapper string is present in the tool-role message. |
| 5 | An invalid regex from the model produces a graceful `ToolResult` error observation instead of crashing the loop | ✓ VERIFIED | `grep_files`'s `try/except re.error` (inspect.py:63-66) returns `{"path": path, "error": ...}` rather than propagating; `_execute_grep_files` routes any `"error"` key result through `_record_observation` (plain, non-untrusted-tagged) and returns `False` (loop.py:950-952). `test_grep_files_invalid_regex` passes; independent live spot-check via `grep_files("(", ".")` returned a clean error dict, no exception raised. |
| 6 | `SYSTEM_PROMPT` documents both tools' exact tag/arg contract, including how `recursive` is signaled | ✓ VERIFIED | `src/olla/prompts.py:11-19` — `list_dir` documented as `<tool>list_dir</tool><args>path/to/directory</args>` with "runs immediately without asking for confirmation"; `grep_files` documented as a three-line `<args>` block (`pattern` / `path/to/directory` / optional `recursive=true`), explicitly noting the third line is optional, defaults to top-level-only, and that the tool is case-sensitive and skips `.git`/binary files. Roster line reads "9 tools available" including both names (line 5). `test_system_prompt_advertises_tool_roster` and `test_system_prompt_teaches_inspect_formats` pass. |

**Score:** 6/6 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/olla/tools/inspect.py` | `list_dir`, `grep_files`, `_human_size` helper | ✓ VERIFIED | 112 lines; both adapters present, substantive (not stubs), never-raises error-dict shape matching `files.py`'s precedent |
| `src/olla/loop.py` (modified) | `_Action` fields, `_prepare_action`/`_preview_action`/`_execute_*`/dispatch wiring for both tools | ✓ VERIFIED | `pattern`/`recursive` fields added to `_Action`; `_prepare_action` branches (lines 311-351); `_preview_action` branches (lines 645-661); `_execute_list_dir`/`_execute_grep_files` (lines 912-956); `run_loop()` dispatch (lines 1206-1215); import of `grep_files, list_dir` from `olla.tools.inspect` (line 28) |
| `src/olla/prompts.py` (modified) | tool doc blocks + roster bump | ✓ VERIFIED | Both doc blocks present (lines 11-19); roster reads "9 tools available" |
| `tests/test_tools/test_inspect.py` (new) | unit coverage for both tools | ✓ VERIFIED | 14 tests, all pass in isolation and in full suite |
| `tests/test_loop.py` (modified) | dispatch/error/gate-consequence integration tests | ✓ VERIFIED | 7 list_dir/grep_files-specific tests present, all pass |
| `tests/test_prompts.py` (modified) | roster/format tests | ✓ VERIFIED | 13 tests total, `test_system_prompt_advertises_tool_roster` and `test_system_prompt_teaches_inspect_formats` cover this phase's additions, all pass |
| `src/olla/safety.py` | must remain untouched, no tool-name branch (D-09) | ✓ VERIFIED | Zero occurrences of `list_dir`/`grep_files` in the file; only shell-argv classification logic present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_loop()` dispatch | `_execute_list_dir` → `tools/inspect.py:list_dir` → `_record_file_observation` → `untrusted_observation_seen` → next CONFIRM-tier gate | direct call chain, no `check()` in between | ✓ WIRED | Confirmed by source read (loop.py:1206-1210) + passing gate-consequence test forcing `Confirm.ask` on a subsequent CONFIRM-tier shell call under `yes=True` |
| `run_loop()` dispatch | `_execute_grep_files` → `tools/inspect.py:grep_files` → `_record_file_observation` (shared) → `untrusted_observation_seen` → next CONFIRM-tier gate | direct call chain, no `check()` in between | ✓ WIRED | Confirmed by source read (loop.py:1211-1215) + passing gate-consequence test |
| `_prepare_action` | `_Action(kind="list_dir"/"grep_files", ...)` | `_resolve_file_path` for path only, no existence check (D-10) | ✓ WIRED | Confirmed by source read (loop.py:311-351) — matches `read_file`'s precedent |
| `prompts.py` documented `<tool>`/`<args>` wire format | `parser.py`'s existing generic `<tool>`/`<args>` branch | zero `parser.py` changes | ✓ WIRED | `git diff`/history shows `parser.py` untouched by this phase; loop.py's `_prepare_action` splits `grep_files`'s multi-line `<args>` content itself, matching the documented 2-3 line contract |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `list_dir` output | `"\n".join(lines)` | live `os.scandir(path)` + `os.readlink`/`entry.stat` | Yes — live spot-check against a real 51-entry tmp directory returned real, correctly capped/truncated output | ✓ FLOWING |
| `grep_files` output | `"\n".join(lines)` | live file reads via `open()` + `regex.search()` over `os.scandir`/`os.walk` results | Yes — live spot-checks (invalid regex, `.git` exclusion) returned real, correctly filtered output | ✓ FLOWING |

### Behavioral Spot-Checks (independently re-run by this verifier)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `list_dir` caps at 50 + truncation note | `list_dir(<51-entry tmp dir>)` | 51 output lines; last line `"... 1 more entries not shown"` | ✓ PASS |
| `list_dir` truncation-count arithmetic holds beyond the boundary case | `list_dir(<120-entry tmp dir>)` | 51 output lines; last line `"... 70 more entries not shown"` (120-50=70) | ✓ PASS |
| `grep_files` invalid regex never raises | `grep_files("(", ".")` | `{'error': "invalid regex '(': missing ), unterminated subpattern..."}`  | ✓ PASS |
| `grep_files` excludes `.git` recursively | nested `.git/config` + sibling file, both containing the search term, `recursive=True` | only the sibling file's match returned | ✓ PASS |
| `ruff check` on phase-modified source files | `ruff check src/olla/tools/inspect.py src/olla/loop.py src/olla/prompts.py` | "All checks passed!" | ✓ PASS |
| Named list_dir/grep_files tests (unit + integration) | `pytest tests/test_tools/test_inspect.py tests/test_loop.py -k "list_dir or grep_files"` | 21 passed | ✓ PASS |
| Named prompts tests | `pytest tests/test_prompts.py -v` | 13 passed | ✓ PASS |
| Full workspace test suite (run once, no regressions) | `pytest -q` | 473 passed | ✓ PASS |
| `check(` call sites in `loop.py` restricted to shell-only branches | source read of every `check(` occurrence | 2 occurrences, both in `_preview_action`'s shell branch and `_execute_shell` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| INSPECT-01 | 05-01 | `list_dir(path)` lists directory entries with `[d]`/`[f]` indicator, names, and sizes, capped at 50 entries | ✓ SATISFIED | `src/olla/tools/inspect.py:list_dir`; unit tests + live spot-check |
| INSPECT-02 | 05-01 | `grep_files(pattern, path)` performs regex search across text files (ignoring `.git` and binary files), returning up to 25 matches with file:line | ✓ SATISFIED | `src/olla/tools/inspect.py:grep_files`; unit tests + live spot-checks |
| INSPECT-03 | 05-01 | `list_dir`/`grep_files` execute without interactive confirmation prompts via unconfirmed dispatch straight from `run_loop()`, bypassing `safety.check()` entirely (D-09) | ✓ SATISFIED | Source-wide confirmation that `check(` is never called on these paths; `safety.py` has zero references to either tool name; dispatch/gate tests pass |

No orphaned requirements — REQUIREMENTS.md maps exactly INSPECT-01..03 to Phase 5, and all three are claimed by the single plan's (`05-01-PLAN.md`) `requirements:` frontmatter and satisfied above.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers found in any phase-modified file (`src/olla/tools/inspect.py`, `src/olla/loop.py`, `src/olla/prompts.py`, `tests/test_tools/test_inspect.py`, `tests/test_loop.py`, `tests/test_prompts.py`). No empty stub implementations (`list_dir`/`grep_files` both perform real filesystem I/O with substantive branching), no hardcoded-empty data flowing to output. `ruff check` reports zero violations in the three touched source files.

### Human Verification Required

None. All truths were resolved with passing automated tests, independently re-run source-code inspection, and direct live spot-checks executed by this verifier (no network or interactive-terminal dependency for this phase's tools).

### Gaps Summary

No gaps. All 6 must-have truths verified (matching the plan's `must_haves.truths` and the 3 roadmap success criteria), all required artifacts present/substantive/wired, all key links wired, all 3 requirement IDs (INSPECT-01..03) satisfied with no orphans, full test suite green (473 passed, matching the pre-verification baseline, zero regressions), `ruff` clean on touched files, and the load-bearing untrusted-observation gate consequence (T-05-04's mitigation) independently confirmed to genuinely exercise `safety.check()`'s CONFIRM tier via a non-allowlisted shell command (`git status`) rather than trivially passing regardless of the gate's state.

---

_Verified: 2026-09-22_
_Verifier: Claude (gsd-verifier)_
