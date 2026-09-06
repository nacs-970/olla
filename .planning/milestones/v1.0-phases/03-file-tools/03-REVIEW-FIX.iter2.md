---
phase: 03-file-tools
fixed_at: 2026-07-30T12:57:49Z
review_path: /home/nacs/Documents/git/olla/.planning/phases/03-file-tools/03-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-07-30T12:57:49Z
**Source review:** `/home/nacs/Documents/git/olla/.planning/phases/03-file-tools/03-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 8
- Fixed: 8
- Skipped: 0

## Fixed Issues

### CR-01: Existing-file replacement has a final check-to-replace clobber window

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** ecd4f66
**Status:** fixed: requires human verification
**Applied fix:** Existing files are now updated through the already-open, identity-verified descriptor. Failed writes restore the original bytes, and a final directory-entry check reports a stale result without overwriting an external replacement.

### CR-02: A previously observed file can disappear and be silently recreated

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 21761a1
**Status:** fixed: requires human verification
**Applied fix:** Write policy now follows the retained read snapshot rather than current path existence. A deleted observed target fails the fresh read check and cannot fall through to create-only publication.

### CR-03: Cleanup failure can occur after publication but be reported as failure or escape

**Files modified:** `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_tools/test_files.py`, `tests/test_loop.py`
**Commit:** fb167e0
**Status:** fixed: requires human verification
**Applied fix:** Creation records hard-link publication as the commit point, retries temporary cleanup, catches persistent cleanup errors, and returns a successful write with a user-visible cleanup warning when a temporary name remains.

### CR-04: Unicode bidi controls can spoof the write confirmation display

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 98008f1
**Status:** fixed
**Applied fix:** The terminal renderer preserves line feeds but visibly escapes every other non-printable Unicode character, including bidi overrides, isolates, and line or paragraph separators.

### WR-01: Special-tool payloads still reject protocol-looking file content

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** 0fc4514
**Status:** fixed: requires human verification
**Applied fix:** Special tools are recognized from their outer pre-payload envelope. Their args payload is then treated as opaque, preserving literal tool, args, and final tags without weakening ordinary-tool ambiguity checks.

### WR-02: The file backend introduces an undeclared POSIX-only runtime dependency

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`, `pyproject.toml`
**Commit:** 16a9c3a
**Status:** fixed
**Applied fix:** Package metadata now declares POSIX support, and startup validates `fcntl`, anti-symlink flags, directory descriptors, and follow-symlink capabilities with an actionable platform error instead of silent zero-valued fallbacks.

### WR-03: Malformed and valid writes can share a repetition signature

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 22a2271
**Status:** fixed: requires human verification
**Applied fix:** Every write repetition signature now includes an explicit `valid` or `invalid` discriminator, preventing the missing-content sentinel from colliding with literal valid file content.

### WR-04: Valid long target names fail because the temp name embeds the full basename

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** cfe9de9
**Status:** fixed
**Applied fix:** Temporary files now use the fixed-length `.olla.<token>.tmp` pattern independent of the target basename, with regression coverage one byte below the filesystem's `NAME_MAX`.

## Verification

- Scoped phase suite: 167 passed.
- Full repository suite: 270 passed.
- Ruff: all nine reviewed production/test files passed.
- Cumulative `git diff --check`: passed.
- Isolated fix worktree status: clean before this uncommitted report was written.

---

_Fixed: 2026-07-30T12:57:49Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
