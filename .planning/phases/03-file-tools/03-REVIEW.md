---
phase: 03-file-tools
reviewed: 2026-07-28T21:20:32Z
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

# Phase 03-file-tools: Code Review Report

**Reviewed:** 2026-07-28T21:20:32Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

The Phase 03 file-tool implementation has material data-integrity and safety-boundary defects. In particular, text reads silently normalize line endings, failed writes can destroy the original file, one stale-file transition is misclassified as creation, and the final freshness checks remain vulnerable to check/use races. Model-controlled preview text can also manipulate the terminal, while the parser can pair an `<args>` block with an unrelated later `<tool>` block.

The 125 scoped tests and Ruff check pass, but the adversarial reproductions described below still fail against the implementation. Six blockers and three robustness/maintainability warnings must be addressed before shipping.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Text-mode reads corrupt unrequested line-ending bytes

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:16`
**Issue:** `Path.read_text()` opens with universal-newline translation, so CRLF and bare-CR bytes become `\n` before the snapshot, preview, or model sees them. Writing the apparently unchanged content at line 37 therefore changes unrelated bytes. A file containing `b"one\r\ntwo\rthree\n"` was read as `'one\ntwo\nthree\n'` and rewritten as `b"one\ntwo\nthree\n"`. This directly contradicts the exact-content snapshot and unrequested-byte-preservation claims; the LF-only regression at `tests/test_loop.py:920-945` cannot detect it.

**Fix:** Disable newline translation on both paths and add CRLF, bare-CR, and mixed-ending round-trip tests.

```python
def read_file(path: str) -> ToolResult:
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            return {"path": path, "content": handle.read()}
    # existing error mapping...

# Use newline="" in the guarded/atomic write implementation as well.
```

### CR-02: A failed overwrite can truncate or partially destroy the original file

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:37`
**Issue:** `Path.write_text()` opens an existing target with truncation before encoding/writing completes. The function catches the resulting exception and returns an error, but the old data is already gone. Reproduction: writing the invalid UTF-8 string `'\ud800'` to a file containing `b"original bytes\n"` returned an error dict and left the file at `b""`. Disk-full and other mid-write errors can likewise leave partial content. Returning an error is not sufficient when the operation has already caused data loss.

**Fix:** Encode before touching the destination, write and `fsync` a temporary file in the same directory, and replace the destination only after the complete write succeeds. Preserve required mode/metadata, clean up the temporary file on every failure, and combine the replacement with the guarded freshness operation from CR-04.

```python
payload = content.encode("utf-8")  # fail before opening the target
with tempfile.NamedTemporaryFile(dir=p.parent, delete=False) as handle:
    handle.write(payload)
    handle.flush()
    os.fsync(handle.fileno())
# Revalidate the expected target version, then atomically install the temp file.
```

### CR-03: A file deleted after the model read is silently recreated as a new file

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:416-440`
**Issue:** Snapshot validation runs only when `resolved.exists()` is true at preview time. If a file was read successfully and then deleted before the model's write turn, `target_existed` becomes false, the cached snapshot is ignored, and the code follows the unrestricted creation path. With `yes=True`, the deleted file is recreated without confirmation. This violates Plan 03-05's requirement that disappearance after a read be treated as stale and refused. The current tests cover content changes before preview but not disappearance before preview.

**Fix:** Treat any cached read followed by absence as a stale transition, invalidate it, and require a fresh failed/read observation before creation is allowed.

```python
snapshot = read_snapshots.get(resolved)
target_existed = resolved.exists()
if snapshot is not None and not target_existed:
    read_snapshots.pop(resolved, None)
    _record_observation(messages, _read_again_observation(resolved))
    continue
```

Add a real-filesystem regression for both `yes=False` and `yes=True` that deletes the target between the read and write model turns and asserts that it stays absent.

### CR-04: Freshness and creation-race checks are not atomic with the write

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:482-513`
**Issue:** The final `exists()`/`read_file()` checks finish before the separate `write_file()` call. Another process can create an absent target at line 512, after line 501 reports it absent, and `Path.write_text()` then overwrites that newly appeared file. The same gap allows an existing target to change after the final comparison but before truncation. A reproduction that creates `"external winner\n"` at the `write_file` call boundary ends with `"model content\n"`, despite the claimed absent-to-existing protection. Re-resolving and re-reading “immediately before” is still a classic TOCTOU check, not a guarded write.

**Fix:** Move the expectations into a single storage-layer transaction. Creation must use exclusive creation (`O_CREAT | O_EXCL`) so an appeared path returns a conflict. Existing-file updates should carry expected identity/version information (at least device, inode, and exact bytes), open a stable descriptor without following a new final symlink, lock/revalidate that descriptor, and write atomically or return a stale conflict. `run_loop` must turn that conflict into the existing read-again Observation.

```python
# Creation sketch: this cannot overwrite a path that appeared after validation.
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)

# Overwrite API sketch:
write_file_guarded(
    path,
    proposed,
    expected_content=snapshot.content,
    expected_stat=snapshot.stat,
)
```

### CR-05: Raw model/file text can spoof or erase the confirmation UI

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:61-85,168-171,441-459`
**Issue:** Proposed content, current-file diff text, paths, shell output, and error strings are printed without escaping terminal control characters. A model can put ANSI cursor/clear-screen sequences in proposed content and manipulate the safety preview immediately before confirmation. The resolved model-controlled path is also interpolated into `Confirm.ask()` as a plain string; Rich parses string prompts as markup, so bracket markup in a filename can style or conceal the displayed target. Newlines and control characters in paths can spoof additional preview/prompt lines. This undermines the confirmation gate that the phase treats as its safety boundary.

**Fix:** Create a display-only sanitizer that renders C0/C1 controls (except intentional line breaks) as visible escapes, apply it to every preview/result/path, and pass a `rich.text.Text` prompt built from already-sanitized literal text so Rich never parses model input as markup. Keep the unsanitized content only for the actual write. Add regressions containing ESC, carriage return, newline, and Rich markup-like path text.

```python
def visible_terminal_text(value: str) -> str:
    return "".join(
        ch if ch == "\n" or unicodedata.category(ch) not in {"Cc", "Cf"}
        else ch.encode("unicode_escape").decode("ascii")
        for ch in value
    )

prompt = Text(f"{operation} `{visible_terminal_text(str(resolved))}`?")
approved = Confirm.ask(prompt, default=False)
```

### CR-06: The parser executes unrelated `<tool>` and `<args>` tags as one call

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:22-43,52-58`
**Issue:** `TOOL_RE.search()` and `ARGS_RE.search()` run independently over the entire response, so ordering and association are not enforced. For example, `parse_response('<args>/tmp/wrong.txt\nWRONG</args><tool>write_file</tool>')` returns an executable `write_file` call using the earlier unrelated args, even though the tool has no following args block. The same flaw affects shell and read calls. Small-model malformed output or surrounding examples can therefore execute a different action from the emitted tool block, with `--yes` removing the remaining interactive check.

**Fix:** Parse one ordered tool-call sequence and bind only the `<args>` immediately following that matched `<tool>`; return `none` for reversed or unpaired blocks. Preserve the special raw payload handling after association is established.

```python
tool_match = TOOL_RE.search(content)
if tool_match is not None:
    args_match = ARGS_RE.search(content, tool_match.end())
    if args_match is not None:
        # normalize the tool and handle write_file/remember/recall payloads
        ...
```

Add reversed-tag, stray-args, two-tool, and mixed-prose regressions.

## Warnings

### WR-01: Tests depend on shared `/tmp` paths and are environment-sensitive

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/tests/test_loop.py:403-470,684-699,898-916`
**Issue:** Multiple write tests hard-code `/tmp/x.txt` and `/tmp/out.txt` while `run_loop` calls the real `Path.exists()` before reaching mocked `write_file`. If another process or an earlier failed run leaves either file behind, the implementation classifies it as existing and refuses the write for lack of a snapshot, causing unrelated test failures. The repetition test at lines 799-815 is even weaker: `mock_write_file.call_count <= 2` passes when the file already exists and no writes occur, so it can stop testing the intended dispatch path.

**Fix:** Use a unique `tmp_path` target in every test and assert exact call counts/arguments.

```python
def test_run_loop_write_file_confirm_approved(tmp_path, mocker, capsys):
    target = tmp_path / "x.txt"
    # interpolate target into the scripted model response
    mock_write_file.assert_called_once_with(str(target.resolve()), "new content\n")
```

### WR-02: Repetition protection skips malformed shell and unknown-tool loops

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:306-313,545-547`
**Issue:** A repeated malformed shell call continues before the repetition signature is recorded, and repeated unknown tools never call `_track_repetition`. Weak models can therefore repeat the exact same invalid call until `max_steps`, despite the loop's explicit three-repeat stuck-model policy. File-path and memory errors do use the guard, making behavior inconsistent across tool failures.

**Fix:** Track a raw fallback signature before dispatch for every parsed tool, then replace it with a normalized signature where parsing succeeds. Add regressions proving three identical malformed-shell or unknown-tool calls stop before a full `max_steps` run.

### WR-03: `run_loop` is an oversized duplicated state machine

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:198-556`
**Issue:** The 359-line function duplicates parsing, resolution, and per-tool policy between dry-run and normal execution and nests the write transaction deeply inside the main loop. This makes safety invariants difficult to audit and has already allowed the absent-after-read branch in CR-03 to bypass snapshot validation. Future tools must edit both dispatch trees and manually preserve repetition, Observation, confirmation, and `--yes` semantics.

**Fix:** Extract typed per-tool preparation objects and small handlers. In particular, centralize write parsing/classification into a side-effect-free `prepare_write()` used by dry-run and execution, then place all freshness transitions in a dedicated guarded-write function. Keep `run_loop` responsible only for model turns, repetition accounting, and recording returned Observations.

---

_Reviewed: 2026-07-28T21:20:32Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
