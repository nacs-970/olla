---
phase: 03-file-tools
reviewed: 2026-07-28T22:45:20Z
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
  critical: 3
  warning: 2
  info: 0
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-28T22:45:20Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 03 remains unsafe to ship. The fixes correctly preserve newline bytes, reject stale delete/recreate identities when the replacement is already present, publish new names without clobbering an appeared destination, sanitize C0/C1 terminal controls, enforce ordered tool/args parsing, count malformed and unknown responses, isolate filesystem-sensitive tests, and centralize loop dispatch. However, three independently reproduced write-boundary defects remain: an existing target can still be replaced after the final identity check, a previously observed target that disappears early enough is downgraded to an authorized creation, and new-file publication can report failure or raise after it already mutated the filesystem. Two warnings cover an undeclared POSIX-only runtime dependency and a repetition-signature collision.

The scoped suite passes (`155 passed`), the full suite passes (`258 passed`), and Ruff is clean. Those tests do not exercise the three failing interleavings below.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01: Existing-file replacement still has a check-to-replace clobber window

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:157-173`
**Issue:** `write_file()` validates both the locked descriptor and the current directory entry at lines 157-167, then calls `os.replace()` separately at lines 168-173. `flock()` is advisory and protects only the opened inode; it does not prevent another process from unlinking or replacing the pathname. A replacement inserted after line 167 is therefore overwritten without ever matching `expected_snapshot`. A deterministic repro replaced the destination inside the `os.replace` call: `write_file()` returned `{'bytes_written': 5}` and the replacement's `b'EXTERNAL'` bytes became `b'MODEL'`. This is the same data-loss class CR-04 was intended to close.
**Fix:** Do not perform an unconditional pathname replacement after identity validation. Use a commit mechanism whose mutation is conditional on the destination still being the authorized object, or fail closed on platforms without such a primitive. If the implementation instead writes through the already verified descriptor, it must preserve failure atomicity and revalidate/report pathname identity after the write. Add a deterministic test that swaps the directory entry immediately after the last validation and proves the external replacement is never overwritten.

#### CR-02: A previously read file can disappear and be silently recreated

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:487-512`
**Issue:** `_execute_write_file()` decides whether an action is an overwrite solely from `resolved.exists()` at line 487. If the model previously read the target but another process deletes it before this check, `target_existed` becomes false, the still-present `_FileReadSnapshot` is ignored, and lines 547-554 call `write_file(..., expected_snapshot=None)` as a new-file creation. The live repro read `ORIGINAL`, deleted the file while producing the write action, then recreated it as `MODEL` and reported success. A disappeared observed target is stale and should require another `read_file`, not inherit the more permissive create policy.
**Fix:** Derive overwrite intent from the same-run snapshot, not current existence. When `read_snapshots` contains the resolved path, always validate its completeness/identity and pass its `expected_snapshot`; a missing destination must then return stale. Only use `expected_snapshot=None` when no read authorization exists. A failed `read_file` already clears the snapshot and can explicitly enable a later true create attempt.

```python
snapshot = read_snapshots.get(resolved)
if snapshot is not None:
    # Validate full observation, preview the authorized content, and always
    # pass snapshot.identity even if the path has since disappeared.
    expected_snapshot = snapshot.identity
else:
    expected_snapshot = None  # genuine create-only path
```

#### CR-03: Temp cleanup failure occurs after publication but is reported as write failure

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:141-153`
**Issue:** The create branch publishes the target with `os.link()` and only then unlinks the temporary name. If that unlink fails, the outer handler returns an error even though the destination already contains the model payload. In the isolated repro, the result was `{'error': '... cleanup failed'}` while the new target existed as `b'MODEL'`. If cleanup continues to fail, the `finally` block at lines 184-189 catches only `FileNotFoundError`, so `write_file()` raises `OSError` and leaves both the published target and temp file despite its “Never raises” contract. Callers cannot safely retry or infer filesystem state from the result.
**Fix:** Make publication the mutation commit point. Prefer an atomic no-replace move that does not require post-publication unlinking. If hard-link publication remains the fallback, record publication success before cleanup, never convert a committed write into an error result, and catch/report cleanup errors without raising. Add tests for one-shot and persistent `os.unlink` failures that assert a result consistent with the actual target and no uncaught exception.

### Warnings

#### WR-01: The new file backend makes an undeclared POSIX-only package

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:3`
**Issue:** The module imports `fcntl` unconditionally and later depends on directory file descriptors, `O_DIRECTORY`/`O_NOFOLLOW`, and `os.link(..., src_dir_fd=..., dst_dir_fd=...)`. `pyproject.toml` declares only Python `>=3.10` and no operating-system restriction. On Windows, importing `olla.loop` now fails at `import fcntl`, so the CLI cannot start; other platforms/filesystems may lack the required `dir_fd` or hard-link support even when ordinary file writes work. This is a portability regression introduced by the race-aware rewrite.
**Fix:** Either declare and enforce supported POSIX platforms with an actionable startup error, or isolate platform-specific implementations behind a common safe-write interface and provide a Windows-compatible atomic/locking backend. Capability checks must fail closed instead of silently dropping `O_NOFOLLOW`.

#### WR-02: Malformed and valid write actions can share one repetition signature

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:218-236`
**Issue:** A write missing its content line receives `("write_file", path, "missing-content-line")`. A valid write whose literal content is `missing-content-line` receives the exact same tuple when the path is already absolute. The direct repro confirmed equality. Alternating those semantically different actions can therefore increment the consecutive-call counter and stop before a third action even though the model did not repeat the same call.
**Fix:** Include an unambiguous action-status field in every signature, for example `("write_file", "invalid", "missing-content-line", path)` versus `("write_file", "valid", normalized_path, content)`; add a regression test for the literal marker content.

## Validation

- Scoped phase suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_loop.py tests/test_parser.py tests/test_prompts.py tests/test_tools/test_files.py` — `155 passed`.
- Full repository suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q` — `258 passed`.
- Ruff across all nine scoped files with `--no-cache` — passed.
- Focused prior-finding regression selection — `21 passed`, covering newline preservation, failed existing-target replace, delete/recreate identity, no-clobber creation/symlink handling, terminal sanitization, malformed/unknown repetition, and strict parser association.
- Independent race repro: swapping the destination at the final `os.replace()` overwrote the replacement and returned success (CR-01).
- Independent loop repro: deleting an observed target before write classification recreated it and returned success (CR-02).
- Independent cleanup repros: one unlink failure returned an error after publication; persistent failure raised and left target plus temp file (CR-03).
- Direct action repro confirmed the malformed/valid write signature collision (WR-02).
- No source files were modified.

---

_Reviewed: 2026-07-28T22:45:20Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
