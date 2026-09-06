---
phase: 03-file-tools
reviewed: 2026-07-30T13:10:18Z
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
  critical: 5
  warning: 1
  info: 0
  total: 6
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-30T13:10:18Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 03 is not safe to ship. All 167 scoped tests and all 270 repository tests pass, but deterministic probes reproduced three state-integrity failures in the revised file backend: a stale refusal can be returned after a displaced file has already been overwritten, interruption can leave an existing file truncated, and descriptor cleanup can raise after a new file has been successfully published. The confirmation renderer is spoofable through newline-bearing filenames, and file contents are inserted into the conversation as trusted user messages, enabling indirect prompt injection to reach auto-approved actions under `--yes`. Empty files are also represented to the model as literal non-file text.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Late stale detection occurs after the displaced file has already been overwritten

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:256-281`
**Issue:** The existing-file branch reads the original bytes and then mutates the open descriptor at line 258 before performing its final pathname check at lines 272-281. If another process moves the authorized inode elsewhere and installs a replacement at the requested path during `_write_descriptor()`, `write_file()` returns `stale=True`, but the moved object has already been replaced with model content. A deterministic probe renamed `target.txt` to `moved.txt` during `os.ftruncate()` and installed an `EXTERNAL` target; the call returned a stale refusal while `moved.txt` contained `MODEL`. The current regression only asserts that the newly installed target survives, so it misses corruption of the displaced object.
**Fix:** Do not mutate the authorized inode before the commit condition is established. Stage the replacement separately and use a commit mechanism that is conditional on the destination still naming the expected object; fail closed when that guarantee is unavailable. If descriptor writes remain as a fallback, restore and fsync `original` on every late-stat/mismatch path before returning, and add a regression that retains the displaced inode under another name and asserts that both objects preserve their pre-call bytes on a stale result.

### CR-02: Existing-file overwrite is not atomic and can leave the target truncated on interruption

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:119-128`
**Issue:** `_write_descriptor()` calls `ftruncate(0)` before writing the replacement bytes. The rollback at lines 259-270 handles only ordinary `OSError`/`ValueError` returns; process termination, `KeyboardInterrupt`, or another non-caught interruption after truncation bypasses it. A deterministic `KeyboardInterrupt` injected at the first `os.write()` left an `ORIGINAL` target as `b''`. This contradicts the module's “atomic writes” contract and creates direct data-loss risk.
**Fix:** Write and fsync the complete replacement in a temporary file while leaving the target untouched, then commit it atomically only after the snapshot/path identity checks succeed. Preserve the expected mode explicitly and integrate this with CR-01's conditional-commit requirement. Add an interruption regression that aborts after staging/truncation and proves the original pathname still contains its complete original bytes.

### CR-03: Descriptor cleanup can raise after a successful write and violate the never-raise contract

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:300-309`
**Issue:** `target_fd` and `directory_fd` are closed directly in `finally`, outside the function's exception handling. An `OSError` from either `os.close()` escapes, masking the result that was already computed. A deterministic create probe made `os.close()` fail after hard-link publication: `write_file()` raised `OSError("close failed")` even though the target existed with the complete `MODEL` payload. `read_file()` has the same uncaught cleanup pattern at lines 162-164. This crashes the loop and leaves the caller unable to tell whether the side effect committed.
**Fix:** Refactor cleanup so close failures are caught without retrying an fd whose close state is uncertain. Compute the result only after cleanup, returning an error when no commit occurred and a success plus `warning` when a committed write is intact but cleanup reported an error. Apply the same never-raise handling to `read_file()`, and add regressions for close failure both before and after publication.

### CR-04: Newline-bearing filenames can forge the confirmation metadata

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:102-135`
**Issue:** `_terminal_safe()` deliberately preserves line feeds, while `_render_write_preview()` interpolates the untrusted resolved path directly into `Resolved path`, byte-count, and unified-diff header lines. POSIX filenames may contain line feeds. A path named `innocent\nResolved path: /tmp/approved-target\nname.txt` therefore renders multiple apparent `Resolved path` lines immediately before the fixed `Proceed?` prompt. The user can no longer reliably identify the pathname being approved, recreating the confirmation-spoofing class that the terminal-control fix was intended to close.
**Fix:** Render paths and other single-line metadata through a context-specific encoder such as `ascii(str(resolved))`/`repr(str(resolved))` so newline, tab, backslash, and control characters are visibly escaped. Use that encoded value in create/overwrite headers, diff labels, step messages, and refusal messages; keep payload newlines only inside explicit content delimiters. Add create and overwrite confirmation tests using filenames containing `\n` and `\t`.

### CR-05: Untrusted file content is promoted to a user instruction and can drive auto-approved actions

**Classification:** BLOCKER
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:310-313`
**Issue:** `_record_observation()` appends every tool result, including arbitrary file contents from `_execute_read_file()`, as a new `role: "user"` message. This gives instructions embedded in a cloned repository or other attacker-controlled file the same conversation role as the actual task. The next model turn can follow those instructions and request a `write_file` or a CONFIRM-tier shell command; with `yes=True`, lines 421-434 skip confirmation and execute it. The shell blocklist does not prevent general-purpose commands such as `python`, `curl`, or `git`, so an indirect prompt injection can cause code execution or exfiltration.
**Fix:** Preserve provenance: send tool output using the model API's tool-result role/structure where supported and wrap file bytes in an explicit untrusted-data envelope reinforced by the system prompt. Do not let `--yes` auto-approve state-changing actions whose decision chain consumed untrusted observations unless those actions are constrained by a sandbox/capability policy. Add an adversarial integration test whose file contains a conflicting tool instruction and assert that it cannot trigger shell/write execution without an independent trusted authorization.

## Warnings

### WR-01: Empty files are reported to the model as the literal text `(no output)`

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:462-469`
**Issue:** The success branch uses `raw_content or "(no output)"`, so reading a zero-byte file appends `Observation: (no output)` instead of the file's actual empty content. This sentinel is appropriate for shell output but violates FILE-01 and the prompt's instruction to use the latest Observation as exact file contents. A model can consequently write the sentinel into an empty file or reason about content that was never present. A deterministic loop probe confirmed that the second model call received exactly `Observation: (no output)`.
**Fix:** Keep the model-facing observation byte-faithful (`Observation: ` for an empty file). If a terminal affordance is needed, display a clearly separate `(empty file)` label without inserting it into model history. Add a regression that reads an empty real file and asserts that the next model request does not contain the sentinel.

## Validation

- Scoped phase suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_loop.py tests/test_parser.py tests/test_prompts.py tests/test_tools/test_files.py` — `167 passed`.
- Full repository suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q` — `270 passed`.
- Ruff across all nine scoped files with `--no-cache` — passed.
- `git diff --check` for the scoped files — passed.
- Deterministic probes reproduced CR-01, CR-02, CR-03, CR-04, and WR-01; CR-05 follows directly from the role/provenance and `--yes` execution data flow.
- No source files were modified.

---

_Reviewed: 2026-07-30T13:10:18Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
