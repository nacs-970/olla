---
phase: 03-file-tools
fixed_at: 2026-07-30T14:23:03Z
review_path: /home/nacs/Documents/git/olla/.planning/phases/03-file-tools/03-REVIEW.md
iteration: 3
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-07-30T14:23:03Z
**Source review:** `/home/nacs/Documents/git/olla/.planning/phases/03-file-tools/03-REVIEW.md`
**Iteration:** 3

**Summary:**

- Findings in scope: 8
- Fixed: 8
- Skipped: 0

## Fixed Issues

### CR-01: New files bypass the process umask and are published world-writable

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** c357be6
**Status:** fixed
**Applied fix:** Creation staging now starts at mode `0600`, remains restrictive while payload bytes are written, and restores only the kernel-derived effective creation mode before publication. A subprocess regression sets umask `077`, preserves the staging link for inspection, and proves both names remain mode `0600`.

### CR-02: A concurrent in-place edit is discarded because post-exchange validation checks only inode identity

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** d8c1358
**Status:** fixed: requires human verification
**Applied fix:** Post-exchange validation now checks the displaced destination's complete identity and data metadata, normalizing only the ctime transition caused by the exchange syscall itself. A deterministic exchange-hook regression mutates the same inode and proves the external bytes are restored with a stale result.

### CR-03: Rollback failure deletes the displaced file and leaves unapproved model content published

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** 79d2932
**Status:** fixed: requires human verification
**Applied fix:** The exchange state now explicitly protects the displaced name from generic cleanup. If rollback fails, the result reports the published replacement as commit-uncertain, returns the recovery pathname, and preserves the displaced inode instead of unlinking it. The forced-failure regression verifies both objects remain recoverable.

### CR-04: The closed staging pathname can be replaced before publication

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** 0f4cfc4
**Status:** fixed: requires human verification
**Applied fix:** The staging descriptor remains open through publication. Full descriptor/name snapshots are checked immediately before commit and again at the published destination; substitution causes create cleanup or overwrite rollback without deleting the displaced destination. Create and overwrite regressions replace the staging name at the commit boundary.

### CR-05: An ancestor-directory swap can redirect a confirmed write to another location

**Files modified:** `src/olla/tools/files.py`, `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 3d154ab
**Status:** fixed: requires human verification
**Applied fix:** Parent directories are opened component-by-component with `O_NOFOLLOW`, retained across confirmation, checked against their full snapshot after approval, and passed by descriptor into the write primitive. The ancestor-swap regression proves a late symlink replacement cannot redirect bytes into the attacker-selected directory.

### CR-06: Shell output bypasses the untrusted-observation confirmation gate

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commits:** 0805ff4, e8ac4b2
**Status:** fixed: requires human verification
**Applied fix:** Shell stdout, stderr, and execution errors now enter model history with the `tool` role inside an explicit untrusted-shell-output envelope. Executed shell output permanently enables the confirmation gate, so `--yes` cannot approve a later CONFIRM-tier command or write without user confirmation. Adversarial output and legacy observation regressions cover the policy.

### CR-07: Model-controlled file content can forge the final confirmation context

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 473e50e
**Status:** fixed
**Applied fix:** Create and overwrite previews now have trusted start/end markers, while the actual Rich `Text` confirmation prompt contains the authoritative resolved path and UTF-8 byte count with markup disabled. Forged metadata and `Proceed?` lines in both create and overwrite payloads cannot replace the real prompt context.

### CR-08: New-file creation is acknowledged without syncing the directory entry

**Files modified:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
**Commit:** 118fcdc
**Status:** fixed
**Applied fix:** Creation now fsyncs staged payload metadata and the parent directory after publication and temporary-name cleanup. Directory-sync failure returns a successful published result with an explicit durability warning. Regressions prove both file and directory descriptors are synced and exercise the warning path.

## Verification

- Scoped Phase 3 suite: 187 passed.
- Full repository suite: 290 passed.
- Ruff: all nine reviewed production/test files passed.
- Cumulative `git diff --check`: passed.
- Isolated fix worktree status after all source commits: clean.

---

_Fixed: 2026-07-30T14:23:03Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
