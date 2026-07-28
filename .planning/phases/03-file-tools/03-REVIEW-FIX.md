---
phase: 03-file-tools
fixed_at: 2026-07-28T22:24:35Z
review_path: .planning/phases/03-file-tools/03-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-07-28T22:24:35Z
**Source review:** `.planning/phases/03-file-tools/03-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 9
- Fixed: 9
- Skipped: 0

## Fixed Issues

### CR-01: Text-mode reads silently normalize newline bytes

**Files modified:** `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_tools/test_files.py`, `tests/test_loop.py`
**Commit:** 9a4edfa
**Status:** fixed
**Applied fix:** Reads now use one binary descriptor and explicit UTF-8 decoding, preserving CRLF, lone CR, and missing-final-newline bytes. Writes encode exactly once before touching the destination.

### CR-02: A failed write can truncate or partially replace the destination

**Files modified:** `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_tools/test_files.py`, `tests/test_loop.py`
**Commit:** 9a4edfa
**Status:** fixed
**Applied fix:** Payloads are written to uniquely created same-directory temporary files, flushed and fsynced, then atomically published. Failures clean temporary files and preserve the original destination and its mode.

### CR-03: Content-only snapshots accept deletion and recreation as the same file

**Files modified:** `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_tools/test_files.py`, `tests/test_loop.py`
**Commit:** 9a4edfa
**Status:** fixed: requires human verification
**Applied fix:** Read authorization now carries device, inode, nanosecond modification/creation times, size, and mode captured from the same descriptor. Recreated identical-content files invalidate authorization.

### CR-04: Final validation and mutation are separated by exploitable TOCTOU windows

**Files modified:** `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_tools/test_files.py`, `tests/test_loop.py`
**Commit:** 9a4edfa
**Status:** fixed: requires human verification
**Applied fix:** The loop passes its expected descriptor snapshot into one safe-write primitive. Existing targets are opened without following symlinks, locked, and revalidated immediately before atomic replacement; new targets use exclusive temporary creation plus no-overwrite atomic publication.

### CR-05: Untrusted preview text can control the terminal immediately before approval

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 227265a
**Status:** fixed
**Applied fix:** All model, file, tool, path, and final-answer display text now passes through one renderer that preserves line feeds while visibly escaping C0/C1 controls and surrogates. Shell and file confirmations use the fixed trusted prompt `Proceed?`.

### CR-06: The parser can pair a tool with an unrelated args block

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** b5a1949
**Status:** fixed: requires human verification
**Applied fix:** Parsing now requires exactly one ordered tool/args structure and rejects args-before-tool, duplicate, nested, ambiguous, and unmatched structures while preserving special tool payloads.

### WR-01: Repetition protection skips malformed and unknown responses and retains stale state

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 2d6b88f
**Status:** fixed: requires human verification
**Applied fix:** Every non-final response is normalized and counted before handler dispatch. Malformed, unknown, and tagless responses have stable signatures, intervening responses reset consecutive state, and file signatures use resolved paths plus structured content.

### WR-02: Fixed shared `/tmp` paths make tests environment-dependent

**Files modified:** `tests/test_loop.py`
**Commit:** 71cd89f
**Status:** fixed
**Applied fix:** Every filesystem-sensitive write/dry-run/repetition/end-to-end test now builds read and write targets beneath pytest's isolated `tmp_path` fixture.

### WR-03: The loop duplicates dispatch and policy across a 359-line state machine

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 2d6b88f
**Status:** fixed: requires human verification
**Applied fix:** Responses are parsed once into typed normalized actions. Repetition remains in the outer loop, dry-run and live paths share action preparation/validation, and shell, read, write, and memory execution live in dedicated handlers.

## Verification

- Scoped phase suite: 155 passed.
- Full repository suite: 258 passed.
- Ruff: all nine reviewed production/test files passed.
- Cumulative `git diff --check`: passed.
- Worktree status after commits: clean before this uncommitted report was created.

---

_Fixed: 2026-07-28T22:24:35Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
