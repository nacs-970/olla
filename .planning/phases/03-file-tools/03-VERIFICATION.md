---
phase: 03-file-tools
verified: 2026-06-15T07:30:00Z
status: gaps_found
score: 13/13 must-haves truths verified, 1 BLOCKER anti-pattern (CR-03) and 1 real-but-exotic BLOCKER-class defect (CR-01) found via code review
overrides_applied: 0
gaps:
  - truth: "write_file never silently destroys file content without disclosure (confirm-gate integrity)"
    status: failed
    reason: >
      CR-03 (03-REVIEW.md): when a model emits <tool>write_file</tool><args>/path/to/file</args>
      with NO newline after the path (e.g. generation stops right after the path because
      </args> is a stop-sequence before any content line is emitted), parsed["args_raw"]
      has no "\n". loop.py's partition("\n") yields file_content="". The confirm prompt
      f"Write to `{resolved}`?" is IDENTICAL to a normal non-empty write -- it gives no
      indication the write will be empty. If approved (or --yes is set), write_file(path, "")
      is called and silently truncates an existing file to 0 bytes. Verified via REPL:
      writing "IMPORTANT DATA" to a file then write_file(p, "") returns
      {'path': p, 'bytes_written': 0} and the file becomes empty. This directly undermines
      CLAUDE.md's "confirm-gating ... non-negotiable" constraint -- the user approves a
      prompt that does not disclose the operation is destructive.
    artifacts:
      - path: "src/olla/loop.py"
        issue: "lines 181-187 (confirm-gate, normal loop) and lines 71-75 (dry-run preview) do not detect or surface the no-newline/empty-content case before showing the write confirmation prompt"
    missing:
      - "Detect parsed[\"args_raw\"].partition(\"\\n\") returning sep=='' (no newline present) BEFORE the confirm prompt; either refuse the write with an Observation explaining no content was provided, or change the prompt to explicitly say 'Write EMPTY content to `{resolved}` (existing content will be erased)?' when file_content == \"\""
      - "Apply the equivalent guard in the dry-run preview branch (lines 71-75) so dry-run also surfaces this case"
      - "Add a regression test: write_file dispatched with args_raw containing no newline must not silently call write_file(path, \"\") without explicit disclosure"

  - truth: "read_file and write_file honor their documented 'Never raises' contract for all path inputs"
    status: failed
    reason: >
      CR-01 (03-REVIEW.md): both read_file (files.py:8-23) and write_file (files.py:26-40)
      docstrings explicitly state "Never raises", but neither except-clause includes
      ValueError. Path(...).read_text()/write_text() raise ValueError: embedded null byte
      for any path string containing \x00 -- not a subclass of OSError, so not caught by
      `except (UnicodeDecodeError, OSError)` (read_file) or `except OSError` (write_file).
      Verified via REPL for both functions AND verified the crash propagates all the way
      through run_loop() uncaught -- a model response of
      <tool>read_file</tool><args>some\x00path</args> prints "Step 1: reading some\x00path..."
      then crashes the entire olla process with an uncaught ValueError, not an error
      Observation the model could recover from. This is a real violation of the documented
      never-raise contract and a process-availability issue, though the triggering input
      (a literal NUL byte) is an exotic/unlikely token for an LLM to emit in decoded text --
      it is a defensive-programming gap rather than a routinely-reachable path in normal use.
    artifacts:
      - path: "src/olla/tools/files.py"
        issue: "lines 22 (read_file except tuple) and 39 (write_file except clause) do not catch ValueError, contradicting both functions' 'Never raises' docstrings"
    missing:
      - "Add ValueError to read_file's except tuple: except (UnicodeDecodeError, OSError, ValueError) as e:"
      - "Add ValueError to write_file's except clause: except (OSError, ValueError) as e:"
      - "Add a regression test for both tools covering a path containing '\\x00'"
deferred: []
---

# Phase 3: File Tools Verification Report

**Phase Goal:** Add file I/O tools (read_file, write_file) to the ReAct loop, completing the v1 tool surface — model can read and write files through the existing dispatch/dry-run/repetition-guard/confirm-gate machinery, with write_file gated by a resolved-path confirm prompt.
**Verified:** 2026-06-15T07:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All 13 must-have truths from 03-01-PLAN.md (5) and 03-02-PLAN.md (8) were checked against the
actual implementation, the actual test suite (146/146 passing), and two reproducible Critical
findings from 03-REVIEW.md (CR-01, CR-03) that surface as defects NOT covered by any of these
literal truths but which are BLOCKER-severity anti-patterns (Step 7) that gate overall status.
CR-02 (the third Critical finding) was independently re-investigated and found to be Pitfall 5
(an explicitly-accepted, documentation-only deviation, T-03-08) rather than a violation of
the Pitfall-1 "round-trip unmodified" truth — see Anti-Patterns table for detail.

| #   | Truth (source) | Status     | Evidence       |
| --- | --------------- | ---------- | -------------- |
| 1   | Model calls read_file and receives file contents as Observation (03-01) | VERIFIED | `src/olla/loop.py:144-168` read_file branch calls `read_file(parsed["args_raw"])`, prints `Step N: reading ...`, appends `Observation: {preview}`. `tests/test_loop.py::test_run_loop_read_file_dispatch_no_prompt` passes. |
| 2   | Large file reads truncated head+tail like shell (03-01) | VERIFIED | `loop.py:163` applies `truncate_output(combined)` (same helper used for shell, `MAX_OBSERVATION_CHARS=2000`, head+tail). `test_run_loop_read_file_truncates_large_output` passes. |
| 3   | Reading a missing file produces an error Observation, not a crash (03-01) | VERIFIED (with caveat) | `files.py:18-19` catches `FileNotFoundError` -> `{"error": "file not found: ..."}`; `loop.py:158-160` routes `"error" in result` to the Observation. `test_run_loop_read_file_error_observation` passes. **Caveat:** this truth is specifically about a *missing* file and IS correctly handled. A separate, unlisted input class (null-byte path, CR-01) crashes the process instead of producing an Observation — tracked as a gap below, not a failure of THIS truth. |
| 4   | `--dry-run` on read_file previews instead of "unknown tool" (03-01) | VERIFIED | `loop.py` dry-run if/elif/else has explicit `elif parsed["tool"] == "read_file":` branch printing `Step 1 would read: {path}`. `test_dry_run_previews_read_file` passes. |
| 5   | Repeating read_file 3x triggers repetition guard (03-01) | VERIFIED | `loop.py:144-150` computes `sig = ("read_file", parsed["args_raw"])`, generalized guard fires `olla stopped: same read_file call repeated 3x — model likely stuck`. `test_run_loop_repetition_guard_covers_read_file` passes. |
| 6   | write_file(path, content) writes to disk only after user confirms (03-02 / SC2) | VERIFIED | `loop.py:185-189` calls `Confirm.ask(...)` (unless `yes=True`); `write_file()` only called on `approved`/`yes`. `test_run_loop_write_file_confirm_approved`-style tests pass. |
| 7   | Confirm prompt shows fully resolved path (SC2) (03-02) | VERIFIED | `loop.py:184` `resolved = Path(path).resolve()`; prompt is `f"Write to \`{resolved}\`?"` — an absolute, resolved path. Confirmed via code read and passing tests. |
| 8   | Declining write_file confirm performs no write (03-02) | VERIFIED | `loop.py:189-191`: if `not approved`, appends `"Observation: declined by user"` and `continue`s — `write_file()` is never called on this path. `test_run_loop_write_file_confirm_declined` asserts `write_file` not called. |
| 9   | `--yes` skips the write_file confirm prompt (03-02) | VERIFIED | `loop.py:185` `if not yes:` guards the entire `Confirm.ask` block; when `yes=True` the block is skipped entirely and `write_file()` is called directly. `test_run_loop_write_file_yes_skips_prompt` passes. |
| 10  | write_file content survives parser round-trip unmodified — interior fences/trailing newlines preserved (Pitfall 1 fixed) (03-02) | VERIFIED | `parser.py:21-32` tool-conditional write_file branch matches `TOOL_RE`/`ARGS_RE` against ORIGINAL (pre-fence-strip) content and returns `args_raw` VERBATIM (no `.strip()`, no fence-stripping). `tests/test_parser.py::test_write_file_args_preserve_interior_fences` and `::test_write_file_args_preserve_trailing_newline` both pass — confirmed these are the literal test names and assertions for "Pitfall 1." **Note:** Pitfall 5 (literal `</args>` substring inside content) is a DIFFERENT, separately-tracked issue (T-03-08, documentation-only) — see CR-02 in Anti-Patterns table; it does not invalidate THIS truth, which concerns fence/whitespace corruption only. |
| 11  | A read-then-write task completes end-to-end (SC3) (03-02) | VERIFIED | `tests/test_loop.py::test_run_loop_read_then_write_end_to_end` (read at lines 784-803) drives `ollama.chat` side_effects through read_file -> write_file -> `<final>done</final>`, asserts both tools called once, `"done"` printed, `mock_chat.call_count == 3`. Passes. |
| 12  | `--dry-run` on write_file previews instead of "unknown tool" (03-02) | VERIFIED | `loop.py:71-75` dry-run `elif parsed["tool"] == "write_file":` prints `Step 1 would write to {resolved} — would prompt for confirmation` and returns without calling `Confirm.ask` or `write_file`. `test_dry_run_previews_write_file` passes. |
| 13  | Repeating write_file 3x triggers repetition guard (03-02) | VERIFIED | `loop.py:169-175` computes `sig = ("write_file", parsed["args_raw"])` BEFORE the confirm-gate; same `prev_sig`/`repeat_count >= 3` mechanism as read_file/shell. `test_run_loop_repetition_guard_covers_write_file` passes. |

**Score:** 13/13 truths verified as literally stated. Status is `gaps_found` NOT because a
listed truth failed, but because two BLOCKER-severity anti-patterns (CR-01, CR-03 — see
below) represent real defects in the delivered tool surface that contradict the project's
own documented contracts ("Never raises" docstrings; CLAUDE.md's "confirm-gating ...
non-negotiable" constraint). Per Step 9 of the verification process, a blocker
anti-pattern alone is sufficient to set `status: gaps_found` regardless of truth score.

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `src/olla/tools/files.py` | `read_file(path) -> ToolResult`, `write_file(path, content) -> ToolResult`, both never-raise | EXISTS, SUBSTANTIVE, WIRED — but VIOLATES "Never raises" contract for null-byte paths (CR-01) | 41 lines, both functions implemented with try/except error-as-dict pattern; missing `ValueError` in except clauses (lines 22, 39) |
| `src/olla/tools/base.py` | `ToolResult` with `content`, `bytes_written`, `path` fields | VERIFIED | `total=False` TypedDict extended additively per plan |
| `src/olla/parser.py` | tool-conditional write_file branch preserving `<args>` verbatim via `partition`-friendly split | VERIFIED for Pitfall 1 scope; Pitfall 5 (literal `</args>` in content) unmitigated in code but unreachable via real `ollama.chat()` (see CR-02) | `ARGS_RE.search(content)` on original content for write_file; `partition("\n")` happens downstream in loop.py |
| `src/olla/loop.py` | dispatch (dry-run + normal-loop) for read_file/write_file with repetition guard + confirm-gate | EXISTS, SUBSTANTIVE, WIRED — confirm-gate does not disclose empty-content writes (CR-03) | if/elif/else over shell/read_file/write_file/unknown in both dry-run and normal loop; `Path.resolve()` used for confirm prompt |
| `src/olla/prompts.py` | SYSTEM_PROMPT documents all 3 tools incl. write_file path/content encoding + `</args>` caveat | VERIFIED | 46-line SYSTEM_PROMPT includes explicit `write_file` example and the line "Never include a literal `</args>` sequence inside file content — it will cut off your output early." |
| `tests/test_tools/test_files.py` | unit tests for read_file/write_file success and error cases | VERIFIED | `test_read_file_success`, `test_read_file_not_found`, write_file success + missing-parent-dir tests all present and passing |
| `tests/test_parser.py` | parser tests incl. fence/newline preservation for write_file | VERIFIED for Pitfall 1; no test for literal `</args>` inside content (Pitfall 5/CR-02 — by design, given stop-sequence makes it unreachable via real model calls) | 3 new write_file tests + 7 pre-existing all pass |
| `tests/test_loop.py` | dispatch/dry-run/confirm-gate/repetition-guard/SC3 tests for both tools | VERIFIED | 8 new write_file tests + 6 new read_file tests (03-01) all pass; `test_run_loop_unknown_tool_returns_observation` repurposed to `browse` |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `src/olla/loop.py` | `src/olla/tools/files.py` | `from olla.tools.files import read_file, write_file` | WIRED | Both imports present at top of loop.py |
| `src/olla/loop.py` | `truncate_output` | read_file Observation reuses truncation helper | WIRED | `loop.py:163` `preview = truncate_output(combined)` for read_file |
| `src/olla/prompts.py` | model output contract | SYSTEM_PROMPT documents read_file/write_file tag shapes | WIRED | Both tools documented with examples in SYSTEM_PROMPT |
| `src/olla/loop.py` | `rich.prompt.Confirm` | write_file confirm-gate shows resolved path before write | WIRED (but see CR-03) | `Confirm.ask(f"Write to \`{resolved}\`?", default=False)` — wired and functional, but does not disclose empty-content case |
| `src/olla/parser.py` | `src/olla/loop.py` | write_file dispatch splits `args_raw` via `partition("\n")` into path + content | WIRED (but see CR-03) | `loop.py:181` `path, _, file_content = parsed["args_raw"].partition("\n")` — wired and functional, but `sep==""` case (no newline) is not detected before the confirm prompt |
| `src/olla/loop.py` (call_model) | `ollama.chat` | `options={"stop": ["</args>", "Observation:"], ...}` | WIRED — CONFIRMS CR-02 is unreachable in production | `loop.py:28`: `</args>` is a hard stop-sequence on the real model call. A model CANNOT emit a literal `</args>` substring past the first occurrence in real generation — confirms Pitfall 5/CR-02 is a parser-only edge case not reachable through `run_loop()`'s actual model-call path, consistent with the plan's T-03-08 documentation-only acceptance. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite passes | `python -m pytest` (via `.venv`) | 146 passed | PASS |
| CR-01: null-byte path crashes read_file/write_file despite "Never raises" | REPL: `read_file("a\x00b")`, `write_file("/tmp/x\x00y", "c")` | Both raise uncaught `ValueError: embedded null byte` | FAIL (confirms CR-01) |
| CR-01: crash propagates through `run_loop()` | mocked `ollama.chat` -> `<tool>read_file</tool><args>some\x00path</args>`, called `run_loop(...)` | Prints `Step 1: reading some\x00path...` then uncaught `ValueError: embedded null byte` — entire process crashes | FAIL (confirms CR-01 is a process-crash, not just a tool-level bug) |
| CR-02: parser truncates write_file content at first literal `</args>` | `parse_response()` on content containing nested `<tool>...</args>` example | `args_raw` truncated at first `</args>` | Reproduced at parser level, but **unreachable via real `ollama.chat()`** due to `</args>` stop-sequence (verified `loop.py:28`) — confirms this is the accepted Pitfall 5 (T-03-08), not a live defect |
| CR-03: write_file with no-newline args silently empties existing file | REPL: file contains "IMPORTANT DATA"; `write_file(p, "")` | Returns `{'path': p, 'bytes_written': 0}`; file content becomes `""` | FAIL (confirms CR-03 — silent data loss with no prompt disclosure) |

### Probe Execution

SKIPPED — no `scripts/*/tests/probe-*.sh` files found in the repository, and neither PLAN nor
SUMMARY for this phase declares probe-based verification. All verification for this phase is
via `pytest` (executed above) and direct REPL reproduction of review findings.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| FILE-01 | 03-01-PLAN.md | read_file tool added to ReAct loop with dispatch/dry-run/repetition-guard | SATISFIED with a known defect (CR-01: null-byte path violates "Never raises" contract, process-crash risk) | Truths 1-5 all VERIFIED; CR-01 is a real but exotic-input defect not covered by the listed truths |
| FILE-02 | 03-02-PLAN.md | write_file tool added with confirm-gated, resolved-path-displaying writes; parser preserves content verbatim; SC2/SC3 satisfied | SATISFIED with a known defect (CR-03: confirm-gate does not disclose empty-content writes, enabling silent data loss) | Truths 6-13 all VERIFIED; CR-03 is a real, reachable defect undermining the confirm-gate's disclosure guarantee |

No orphaned requirements: REQUIREMENTS.md maps only FILE-01 and FILE-02 to Phase 3, both
accounted for above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `src/olla/tools/files.py` | 22 (read_file), 39 (write_file) | `except (UnicodeDecodeError, OSError)` / `except OSError` do not catch `ValueError` raised by `Path.read_text()`/`write_text()` on null-byte paths (CR-01) | BLOCKER | Violates documented "Never raises" contract; a malformed model-emitted path containing `\x00` crashes the entire `olla` CLI process with no recovery Observation. Real-but-exotic trigger (LLM text essentially never contains literal NUL), but the contract violation itself is unconditional and undefended. |
| `src/olla/loop.py` | 181-187 (normal loop), 71-75 (dry-run) | No detection of `parsed["args_raw"].partition("\n")` returning empty `sep` (no newline = no content) before showing the write confirm prompt (CR-03) | BLOCKER | Confirm prompt `f"Write to \`{resolved}\`?"` is indistinguishable from a normal write when the actual operation is "truncate this file to 0 bytes." Approving (or `--yes`) silently destroys existing file content with no disclosure — directly undermines CLAUDE.md's "confirm-gating ... non-negotiable" safety constraint. Reachable: model emits write_file with path only, generation halts at `</args>` stop-sequence before any content line. |
| `src/olla/parser.py` | 7 (`ARGS_RE`), 21-32 (write_file branch) | Non-greedy `ARGS_RE.search()` truncates write_file `args_raw` at the FIRST literal `</args>` substring inside file content (CR-02 / Pitfall 5) | WARNING (accepted deviation, T-03-08) | Confirmed code-level reproducible, BUT confirmed UNREACHABLE via the real `ollama.chat()` path because `</args>` is a hard stop-sequence (`loop.py:28`) — the model physically cannot generate text past the first `</args>`. The plan (03-02-PLAN.md) explicitly accepts this as documentation-only (SYSTEM_PROMPT warns against literal `</args>` in content). This looks intentional — see override suggestion below. |
| `src/olla/parser.py` | 21-32 vs 34-38 | write_file branch returns unconditionally before the `<final>` check, inconsistent with `test_final_wins_over_tool` precedent for shell (WR-01 in 03-REVIEW.md) | WARNING | A model response containing both a completed write_file call and a `<final>` tag has its final answer silently discarded. Untested edge case, not a regression. |
| `src/olla/loop.py` | 71-75, 181-184 | Empty/whitespace write_file path resolves to CWD via `Path("").resolve()`, producing a misleading confirm/dry-run prompt showing the project's own directory (WR-02 in 03-REVIEW.md) | WARNING | No data loss currently (subsequent `write_file("", ...)` errors with `IsADirectoryError` caught as `OSError`), but confusing UX — untested edge case. |
| `src/olla/loop.py` | 162-164 | read_file applies a `"(no output)"` fallback for empty file content, contradicting 03-01-PLAN.md's explicit spec ("no `(no output)` fallback needed — empty file content is valid and meaningful") (WR-03 in 03-REVIEW.md) | WARNING | Reading a genuine 0-byte file produces an Observation identical to an empty shell command, potentially misleading a small model into thinking the read failed. Untested deviation from documented spec. |
| `src/olla/loop.py` | 181-198 vs `src/olla/tools/files.py:34-35` | Confirm prompt shown before `write_file()`'s own `p.parent.exists()` check can fail (IN-01 in 03-REVIEW.md) | INFO | Minor UX rough edge — user approves a write that's guaranteed to fail with "parent directory does not exist". No data loss, no contract violation. |

**No `TBD`/`FIXME`/`XXX` debt markers found** in any of the 8 files modified by this phase
(checked via grep across `src/olla/tools/base.py`, `src/olla/tools/files.py`,
`src/olla/parser.py`, `src/olla/loop.py`, `src/olla/prompts.py`, and the 3 test files).

**This looks intentional (CR-02 / WR-01).** To accept CR-02 as a documented deviation
(Pitfall 5 / T-03-08, confirmed unreachable via the real `ollama.chat()` stop-sequence),
add to this VERIFICATION.md frontmatter:

```yaml
overrides:
  - must_have: "write_file content survives the parser round-trip unmodified — interior code fences and trailing newlines are preserved (Pitfall 1 fixed)"
    reason: "CR-02 (literal </args> truncation) is Pitfall 5, not Pitfall 1 — a separate, explicitly-accepted documentation-only deviation (T-03-08). Confirmed unreachable via the real ollama.chat() path because </args> is a hard stop-sequence (loop.py:28); the model cannot generate text past the first </args> in production. SYSTEM_PROMPT documents the caveat."
    accepted_by: "{maintainer}"
    accepted_at: "{ISO timestamp}"
```

This override was NOT applied automatically (no entry existed at verification time), so
CR-02 is recorded as a WARNING-severity anti-pattern rather than a gap. It does not
contribute to the `gaps_found` status — CR-01 and CR-03 are the drivers of that status.

### Human Verification Required

None. All findings in this report (CR-01, CR-02, CR-03, WR-01/02/03, IN-01) were
independently reproduced programmatically via direct code reads, REPL execution against the
actual `read_file`/`write_file`/`parse_response`/`run_loop` functions, and the existing
146-test pytest suite. No visual, real-time, or external-service behavior is involved in
this phase's scope.

### Gaps Summary

Phase 3's stated goal — read_file and write_file fully wired into the ReAct loop's
dispatch/dry-run/repetition-guard/confirm-gate machinery — is **structurally achieved**.
All 13 must-have truths from 03-01-PLAN.md and 03-02-PLAN.md are literally true: the model
can read files (truncated, error-handled, dry-run-previewed, repetition-guarded), and write
files through a confirm-gate that shows the resolved path, respects `--yes`, declines
correctly, and completes a full read-then-write (SC3) end-to-end. The parser fix for
Pitfall 1 (fence/whitespace corruption) is real and tested. 146/146 tests pass.

However, two BLOCKER-severity defects from 03-REVIEW.md survive independent reproduction
and represent real violations of this project's own non-negotiable safety contracts:

1. **CR-03 (anchor blocker):** The write_file confirm-gate — the mechanism CLAUDE.md calls
   "non-negotiable" — can be approved by a user without any indication that the operation
   will silently truncate an existing file to zero bytes. This happens whenever the model
   emits a write_file call with only a path and no content line (a realistic failure mode:
   generation stops at the `</args>` stop-sequence immediately after the path, before any
   content is produced). This is a genuine confirm-gate integrity gap, independent of any
   "exotic input" caveat — it's a normal malformed-response shape.

2. **CR-01 (real but exotic):** Both `read_file` and `write_file` violate their own
   "Never raises" docstrings for null-byte paths, crashing the entire CLI process. The
   triggering input (`\x00` in a path) is unlikely from real LLM output but the contract
   violation is unconditional and the failure mode (full process crash with no recovery
   Observation) is severe relative to the documented guarantee.

CR-02, initially flagged as a third blocker, was **re-investigated and reclassified**: it
maps to Pitfall 5 (not Pitfall 1, which IS fixed and tested), and is confirmed unreachable
through the real `ollama.chat()` call because `</args>` is a hard stop-sequence
(`loop.py:28`) — the model cannot generate past the first `</args>` in production. This
matches the plan's explicit T-03-08 acceptance (documentation-only, SYSTEM_PROMPT warns
against it). It is recorded as a WARNING with a suggested override, not a gap.

**Recommendation:** Both CR-01 and CR-03 have small, well-scoped fixes documented in
03-REVIEW.md (add `ValueError` to except tuples; detect the no-newline/empty-content case
before the confirm prompt and either refuse or make the emptiness explicit). These should
be closed via a small gap-closure plan before Phase 4 begins, given CR-03's direct conflict
with CLAUDE.md's confirm-gating safety constraint.

---

_Verified: 2026-06-15T07:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Depth: standard_
