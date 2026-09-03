---
phase: 03-file-tools
reviewed: 2026-07-30T12:35:25Z
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
  critical: 4
  warning: 4
  info: 0
  total: 8
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-30T12:35:25Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 03 is not safe to ship. The scoped and full test suites pass, but deterministic probes reproduced three write-boundary defects: an external replacement can be clobbered after the final identity check, a previously read file that disappears is silently recreated, and a post-publication cleanup error can report failure or raise after the target has already been created. The confirmation renderer also leaves Unicode bidi controls active, allowing a path or proposed payload to visually spoof the approval context. Four additional correctness and portability defects affect protocol-looking file content, non-POSIX imports, repetition detection, and valid long filenames.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Existing-file replacement has a final check-to-replace clobber window

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:157-173`
**Issue:** `write_file()` validates the locked descriptor and current directory entry at lines 157-167, then performs a separate unconditional `os.replace()` at lines 168-173. `flock()` is advisory and protects the opened inode, not the pathname. Another process can replace the pathname after the validation; `os.replace()` then destroys that unapproved replacement. A deterministic probe swapped in `EXTERNAL` from inside the `os.replace` call; `write_file()` returned success and the target contained `MODEL`.
**Fix:** Use a commit primitive whose mutation is conditional on the destination still being the authorized object, or fail closed on platforms without one. If portable conditional replacement is unavailable, write through the already-open verified descriptor with explicit rollback/error handling rather than unconditionally replacing a pathname. Add a regression that swaps the directory entry immediately after the last validation and asserts the external object is never overwritten.

### CR-02: A previously observed file can disappear and be silently recreated

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:487-512`
**Issue:** `_execute_write_file()` derives overwrite intent only from `resolved.exists()`. If a file was successfully read and is then deleted before line 487, `target_existed` becomes false, the retained `_FileReadSnapshot` is ignored, and the write is sent as an unrestricted creation with `expected_snapshot=None`. The probe read `ORIGINAL`, deleted the target, and the loop recreated it as `MODEL` while reporting success. A disappeared observed target is stale and must require another read.
**Fix:** Derive the policy from whether a snapshot exists, not only from current existence. When `read_snapshots` contains the path, always validate and pass its identity so a missing target produces a stale refusal. Reserve `expected_snapshot=None` for paths that had no successful same-run read.

```python
snapshot = read_snapshots.get(resolved)
if snapshot is not None:
    if not snapshot.fully_observed or snapshot.identity is None:
        refuse_write()
    expected_snapshot = snapshot.identity
else:
    expected_snapshot = None  # genuine create-only request
```

### CR-03: Cleanup failure can occur after publication but be reported as failure or escape

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:141-189`
**Issue:** The create branch publishes the target with `os.link()` and then unlinks the temporary name. If that unlink fails, the outer `except` returns an error even though the target already contains the payload. If cleanup fails again in `finally`, only `FileNotFoundError` is caught, so the function raises `OSError` and leaves both names despite its “Never raises” contract. The deterministic persistent-failure probe produced exactly that state: the target existed, a temp file remained, and `write_file()` raised.
**Fix:** Track publication as the commit point and keep cleanup failures separate from write success. Prefer a no-replace publish primitive that does not require post-publication unlinking. If hard-link publication remains, never convert an already committed write into a failure result, catch cleanup errors in `finally`, and return/report a cleanup warning consistent with the target's actual state. Add one-shot and persistent-unlink-failure tests.

### CR-04: Unicode bidi controls can spoof the write confirmation display

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:26-39`
**Issue:** `_terminal_safe()` escapes C0/C1 bytes and surrogates but passes Unicode formatting controls such as U+202E RIGHT-TO-LEFT OVERRIDE through unchanged. These characters can reorder the displayed resolved path or proposed content immediately before the fixed `Proceed?` prompt, undermining the user's ability to identify what they are approving. A direct probe showed `_terminal_safe("safe\u202egnp.exe")` still contained the live U+202E character.
**Fix:** Preserve newline deliberately, but visibly escape all other non-printable/format characters before display, including bidi embeddings, overrides, isolates, and line/paragraph separators.

```python
if character == "\n":
    rendered.append(character)
elif not character.isprintable():
    width = 4 if codepoint <= 0xFFFF else 8
    rendered.append(f"\\u{codepoint:0{width}x}")
else:
    rendered.append(character)
```

## Warnings

### WR-01: Special-tool payloads still reject protocol-looking file content

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:46-61`
**Issue:** The parser docstring says `write_file`, `remember`, and `recall` payloads may contain protocol-looking text, but the global counts for `<tool>`, `</tool>`, and `<args>` include occurrences inside the payload. A valid write whose content contains `literal <tool>x</tool>` therefore returns `{"type": "none"}` instead of preserving the bytes. The existing tests cover fences and a literal `<final>`, but not the other protocol tags.
**Fix:** Parse the one outer tool/args envelope statefully. Once a special tool and its outer `<args>` opening are identified, treat its payload as opaque until the outer `</args>` (or end of response) rather than counting nested-looking tag text as structure. Add round-trip cases containing literal `<tool>`, `</tool>`, `<args>`, and `<final>` strings.

### WR-02: The file backend introduces an undeclared POSIX-only runtime dependency

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:3`
**Issue:** `fcntl` is imported unconditionally, and the implementation depends on directory file descriptors, `O_DIRECTORY`/`O_NOFOLLOW`, and `dir_fd` forms of `os.link`, `os.replace`, and `os.unlink`. The package metadata declares only Python `>=3.10`, so on Windows importing `olla.loop` fails before the CLI can start. Other platforms can raise `NotImplementedError` for unsupported `dir_fd` operations, which is not handled by the current error path.
**Fix:** Either declare and enforce POSIX-only support with an actionable startup error, or isolate this backend behind capability checks and provide a safe Windows implementation. Do not silently replace missing anti-symlink flags with zero when the associated guarantee cannot be maintained.

### WR-03: Malformed and valid writes can share a repetition signature

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:215-236`
**Issue:** A write with no content line uses `("write_file", path, "missing-content-line")`. A valid write to the same absolute path whose literal content is `missing-content-line` produces the identical tuple. The direct probe confirmed equality, so alternating two semantically different actions can increment the consecutive-repeat counter and stop the loop as if the same call occurred three times.
**Fix:** Include an explicit status discriminator in every write signature, for example `("write_file", "invalid", path, "missing-content-line")` versus `("write_file", "valid", normalized_path, file_content)`, and add a collision regression.

### WR-04: Valid long target names fail because the temp name embeds the full basename

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:39-47`
**Issue:** `_create_temp_file()` constructs `.{name}.{token}.tmp`. A target basename can be valid near the filesystem's `NAME_MAX` while the derived temp basename exceeds it. On the current filesystem, a valid 250-byte target name failed with `ENAMETOOLONG` because the temporary name added 22 bytes. Both creation and overwrite paths are affected.
**Fix:** Use a short fixed temporary prefix independent of the target basename, such as `.olla.<token>.tmp`, and add a test using a valid basename close to `os.pathconf(directory, "PC_NAME_MAX")`.

## Validation

- Scoped phase suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_loop.py tests/test_parser.py tests/test_prompts.py tests/test_tools/test_files.py` — `155 passed`.
- Full repository suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q` — `258 passed`.
- Ruff across all nine scoped files with `--no-cache` — passed.
- `git diff --check` for the scoped diff — passed.
- Deterministic probes reproduced CR-01, CR-02, CR-03, WR-01, WR-03, and WR-04; a direct renderer probe confirmed CR-04.
- No source files were modified.

---

_Reviewed: 2026-07-30T12:35:25Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
