---
phase: 03-file-tools
reviewed: 2026-07-28T22:04:46Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/olla/loop.py
  - src/olla/parser.py
  - src/olla/prompts.py
  - src/olla/tools/base.py
  - src/olla/tools/files.py
  - tests/test_loop.py
  - tests/test_parser.py
  - tests/test_prompts.py
  - tests/test_tools/test_files.py
findings:
  critical: 6
  warning: 3
  info: 0
  total: 9
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-28T22:04:46Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

The file-tool implementation is not safe to ship. Six blocker-class defects can corrupt file bytes, destroy an existing file while reporting failure, overwrite a replacement or concurrent update, expose the confirmation UI to terminal-control injection, or dispatch arguments under the wrong tool. Three warnings cover an incomplete repetition guard, environment-dependent tests, and duplicated loop state that is already allowing policy drift.

The scoped suite passes (`125 passed`) and Ruff reports no violations, but isolated adversarial repros trigger the data-integrity, race, parser, and repetition failures below. Passing tests therefore do not establish the safety of the current implementation.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01: Text-mode reads silently normalize newline bytes

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:15-17`
**Issue:** `Path.read_text()` uses universal-newline translation. A file containing `b"a\r\nb\r\n"` is returned to the loop as `"a\nb\n"`; writing the observed content back changes every CRLF sequence to LF even when the model intended no such edit. `Path.write_text()` at lines 37-38 can also perform platform newline translation, and `bytes_written` then describes the encoded input rather than necessarily the bytes placed on disk. The isolated repro rewrote `b'a\r\nb\r\n'` as `b'a\nb\n'`.
**Fix:** Preserve byte-for-byte newline sequences by reading bytes and decoding explicitly, and encode once before the atomic write path. For example:

```python
data = Path(path).read_bytes()
content = data.decode("utf-8")

encoded = content.encode("utf-8")
# Pass `encoded` to the atomic binary writer used for CR-02/CR-04.
```

Add regression coverage for CRLF, lone CR, and a file with no final newline.

#### CR-02: A failed write can truncate or partially replace the destination

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:33-40`
**Issue:** `Path.write_text()` opens the destination with truncating `w` semantics before the full payload has been encoded and written. The exception handler turns a later failure into an error result but cannot restore the original bytes. With an existing file containing `ORIGINAL`, passing an unpaired surrogate produced a Unicode encoding error and left the destination as `b''`. I/O failures such as a full filesystem can likewise expose a partial file.
**Fix:** Encode before touching the destination, write all bytes to a uniquely created temporary file in the same directory, flush and `fsync`, then atomically replace the destination. Clean up the temporary file on every failure and report success only after replacement succeeds. Preserve the existing file's mode where appropriate.

```python
encoded = content.encode("utf-8")  # may fail without touching `path`
fd, temp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
try:
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_name, p)
except Exception:
    Path(temp_name).unlink(missing_ok=True)
    raise
```

The concurrency requirements in CR-04 must be folded into this primitive rather than implemented as separate prechecks.

#### CR-03: Content-only snapshots accept deletion and recreation as the same file

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:37-41`
**Issue:** `_FileReadSnapshot` records only decoded content and a display flag. Both stale checks at lines 428-439 and 490-500 compare only that content. If the observed file is deleted and another file is created at the same path with identical text, the replacement inherits the old file's overwrite authorization. An isolated repro deleted and recreated the target with identical content between `read_file` and `write_file`; the loop accepted it and overwrote the replacement.
**Fix:** Capture identity and version metadata from the same open descriptor used to read the bytes (`st_dev`, `st_ino`, `st_mtime_ns`, `st_size`, and file type), and require it to match at commit time. Clear authorization whenever identity changes, even if content is identical. Keep this identity check inside the atomic/locked write primitive so CR-04 cannot reopen a race after validation.

#### CR-04: Final validation and mutation are separated by exploitable TOCTOU windows

**Classification:** BLOCKER
**Files:** `/home/nacs/Documents/git/olla/src/olla/loop.py:466-513`; `/home/nacs/Documents/git/olla/src/olla/tools/files.py:37`
**Issue:** The loop re-resolves, checks existence, and rereads the target, then calls a separate `write_file()` that reopens the pathname with ordinary truncating semantics. A concurrent writer can update or replace the target after the last check and before the open; a replacement symlink can redirect the write. The create path similarly checks `exists()` and later opens with `w`, so a file created in between is overwritten. An isolated repro inserted an external update immediately after the final read returned; the loop reported success and replaced that update with the model payload.
**Fix:** Replace the split check/use sequence with one capability-style safe-write API. Open the parent by directory descriptor, reject symlinks (`O_NOFOLLOW`/`lstat`), use `O_CREAT | O_EXCL` for new files, and hold a lock or verified descriptor for existing files while committing an atomic same-directory temporary file. The API should accept the expected snapshot identity and return a stale result if it cannot prove that the committed target is the authorized object.

#### CR-05: Untrusted preview text can control the terminal immediately before approval

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:52-85`
**Issue:** Proposed model content, existing file content, tool output, paths, and final text are printed as raw terminal data. In the write flow, the raw diff/content is emitted at lines 441-447 immediately before `Confirm.ask()` at lines 449-459. ANSI/OSC sequences can clear or rewrite the screen, forge an approval-looking prompt, create deceptive hyperlinks, or attempt terminal features such as clipboard control. The preview helper returns `"...\x1b[2JFAKE APPROVED"` unchanged. Unpaired surrogate text can also raise while line 59 calculates UTF-8 bytes, crashing the loop before it can produce an observation.
**Fix:** Route every model-, file-, and tool-controlled display value through one terminal-safe renderer. Preserve intentional line breaks but visibly escape C0/C1 controls (especially ESC), OSC terminators, and unencodable surrogates. Render paths/content as plain `rich.text.Text` rather than markup, and keep the actual confirmation prompt free of untrusted text (display a sanitized preview first, then ask a fixed `Proceed?`).

#### CR-06: The parser can pair a tool with an unrelated args block

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:22-24`
**Issue:** `TOOL_RE.search()` and `ARGS_RE.search()` independently select the first matching tag anywhere in the response; lines 31-43 and 52-59 then combine those unrelated matches. For `<args>echo WRONG</args><tool>shell</tool><args>echo intended</args>`, `parse_response()` returns `shell` with `echo WRONG`. Likewise, `<tool>shell</tool><tool>read_file</tool><args>ls</args>` dispatches `ls` as a shell command even though the args follow `read_file`. With `--yes`, a misassociated state-changing shell command can execute without an additional prompt.
**Fix:** Parse one ordered tool-call structure instead of searching tags independently. Require the selected `<args>` to begin after the corresponding tool tag, reject args-before-tool, extra tool tags, and ambiguous multiple blocks, and preserve payload text only after structural association is proven. Add adversarial tests for reordered, duplicated, nested, and unmatched tags.

### Warnings

#### WR-01: Repetition protection skips malformed and unknown responses and retains stale state

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:306-313`
**Issue:** Shell parsing errors `continue` before updating or resetting repetition state. Unknown tools at lines 544-547 and tagless responses at lines 549-553 also bypass the guard. Consequently, three identical malformed shell calls run to `max_steps` instead of stopping on the third response. Because `prev_sig` is retained across these skipped branches, a later valid call can also be counted as consecutive with a valid call that occurred before an intervening malformed/unknown response. File signatures at lines 357 and 389 use raw args, so trivial path aliases or whitespace changes evade detection.
**Fix:** Centralize repetition accounting for every non-final model response before handler-specific early exits. Give malformed, unknown, and tagless responses stable signatures; either track or explicitly reset them. Normalize file signatures with the resolved path plus structured content, just as memory calls already use normalized signatures.

#### WR-02: Fixed shared `/tmp` paths make tests environment-dependent

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/tests/test_loop.py:403-470`
**Issue:** Multiple tests assume `/tmp/x.txt` does not exist even though `run_loop()` checks the real filesystem before invoking the mocked writer. The same assumption recurs at lines 684-699 and 799-815, while lines 898-917 depend on `/tmp/out.txt` being absent. Another user, process, or concurrent test can create these paths and switch the code into the existing-file refusal branch, causing nondeterministic failures or testing a different path than intended.
**Fix:** Accept `tmp_path` in every filesystem-sensitive test and construct all read/write paths beneath it. Use those generated paths in both model responses and assertions; do not mock away the filesystem condition that selects the branch under test.

#### WR-03: The loop duplicates dispatch and policy across a 359-line state machine

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:198-556`
**Issue:** `run_loop()` handles dry-run and live dispatch in separate branches, duplicates observation recording and shell repetition logic, and embeds preview, authorization, stale-state, confirmation, execution, and reporting policies in one oversized function. The divergent repetition behavior in WR-01 is already a concrete symptom: shell uses an inline counter while other handlers use `_track_repetition`, and several exits bypass both. Future safety changes must be duplicated and can silently drift between dry-run and execution.
**Fix:** Parse each response into a typed action, then dispatch through per-tool handlers that expose shared `validate`, `preview`, and `execute` operations. Keep repetition and observation recording in the outer loop, and make dry-run call the same validation/preview path while omitting only execution.

## Validation

- `.venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_loop.py tests/test_parser.py tests/test_prompts.py tests/test_tools/test_files.py` — 125 passed.
- `.venv/bin/ruff check` across all nine scoped files — passed.
- Isolated temporary-directory repros confirmed newline normalization, destructive failed writes, stale deletion/recreation acceptance, and the post-validation overwrite race.
- Direct parser and loop repros confirmed args/tool misassociation and malformed-call repetition bypass.
- No source files were modified.

---

_Reviewed: 2026-07-28T22:04:46Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
