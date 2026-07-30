---
phase: 03-file-tools
reviewed: 2026-07-30T15:17:40Z
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
  warning: 2
  info: 0
  total: 8
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-07-30T15:17:40Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

The nine scoped files were read in full and reviewed for correctness, security, and maintainability. The scoped suite passes (187 tests), and Ruff reports no violations, but deterministic race probes reproduced four failures outside the current tests: a same-size concurrent target edit can be discarded, both create and overwrite can publish modified staging bytes while reporting the model payload's length, and a concurrent replacement of a newly created target is deleted. The existing overwrite path also syncs the directory before removing the displaced original, so successful cleanup is not durable, while the loop reports `commit_uncertain` results as successful writes. Finally, atomic replacement silently loses extended metadata.

## Narrative Findings (AI reviewer)

The findings below come from direct adversarial review and local deterministic probes. No structural/fallow findings were supplied.

## Critical Issues

### CR-01: Restoring mtime lets a concurrent edit bypass stale detection and be deleted

**Classification:** BLOCKER (Critical)
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:427-464`
**Issue:** After `RENAME_EXCHANGE`, the code overwrites the expected target `ctime_ns` with the newly published staging inode's ctime and then compares the displaced target against that normalized snapshot. There is no content digest. A concurrent writer can replace bytes with a same-size payload and restore the original mtime before the exchange; the exchange then supplies a fresh ctime that the code explicitly accepts. A deterministic probe changed `ORIGINAL` to same-length `EXTERNAL`, restored `mtime_ns`, and invoked the real exchange. `write_file()` returned `bytes_written: 5`, published `MODEL`, and unlinked the displaced external edit. This violates the race-aware stale-write contract and loses data.
**Fix:** Include an immutable content digest (and omitted identity fields such as uid/gid/link count) in the snapshot returned by `read_file`. Verify the target descriptor against that expected digest immediately before exchange and verify the still-open displaced target descriptor again after exchange, before unlinking it. Any mismatch must roll back or preserve the displaced object at a reported recovery path.

```python
expected_digest = expected_snapshot["digest"]
if _digest_descriptor(target_fd) != expected_digest:
    return _stale_result(path)

_exchange_files(directory_fd, temp_name, p.name)
if _digest_descriptor(target_fd) != expected_digest:
    return rollback_or_preserve_recovery_file()
```

### CR-02: Staging validation accepts attacker-modified bytes as the model payload

**Classification:** BLOCKER (Critical)
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:284-313`
**Issue:** `staging_name_matches()` compares the staging pathname's current stat to the staging descriptor's current stat. It never compares either object to the payload that was written and fsynced. If the staging inode is modified in place before `os.link()` or `_exchange_files()`, both current snapshots still agree. Deterministic create and overwrite probes truncated the staging inode to `ATTACKER` inside the publication hook; both calls returned `bytes_written: 5` for `MODEL`, while the destination contained `ATTACKER`. This allows a writable staging file to substitute bytes without detection.
**Fix:** Keep staging files mode `0600` until publication, capture a digest of `encoded`, and re-read/hash the retained staging descriptor immediately before and after publication. Compare the digest and byte count to the intended payload rather than comparing two mutable metadata snapshots. Prefer an anonymous `O_TMPFILE` or a private mode-0700 staging directory where supported so other directory writers cannot open or replace the staging object.

```python
payload_digest = hashlib.blake2b(encoded).digest()
if _digest_descriptor(staging_fd) != payload_digest:
    return _stale_result(path)
# Publish, then verify the retained descriptor again before reporting success.
```

### CR-03: Mismatch cleanup deletes a concurrent writer's replacement

**Classification:** BLOCKER (Critical)
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:358-370`
**Issue:** When the newly linked destination no longer matches the staging descriptor, the code assumes it owns the current destination name and unconditionally calls `os.unlink(p.name)`. A deterministic hook successfully linked the model staging file, atomically replaced the destination with `EXTERNAL`, and returned. `write_file()` detected the mismatch, deleted the external file, returned a stale error, and left only an `.olla.*.tmp` file. The same cleanup pattern also unlinks temporary names by pathname at lines 460-499 after earlier identity checks, leaving additional check-to-unlink races.
**Fix:** Never unlink a pathname after observing that it no longer identifies the object owned by this operation. Treat the destination as externally owned, leave it intact, and return a stale/uncertain result. Put exchange temporaries in a private directory (using separate source/destination dirfds with `renameat2`) so cleanup names cannot be replaced by another directory writer; otherwise preserve ambiguous objects and report recovery paths instead of deleting by name.

### CR-04: Existing-file cleanup is acknowledged before its directory entry is durable

**Classification:** BLOCKER (Critical)
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:458-464`
**Issue:** The overwrite path calls `fsync(directory_fd)` while the displaced original still exists at `.olla.*.tmp`, then unlinks that name and returns success without syncing the directory again. The observed order is `fsync-file`, `fsync-file`, `fsync-directory`, `unlink-displaced`. POSIX does not make the unlink durable until the containing directory is synced, so a crash after a reported success can resurrect a hidden copy of the old contents. That is both a cleanup defect and a confidentiality risk for overwritten secrets.
**Fix:** Remove the verified displaced name first, then fsync the directory after the unlink. If an earlier fsync is retained to make the exchange durable, perform a second directory fsync after cleanup and report a durability warning if it fails.

```python
os.unlink(temp_name, dir_fd=directory_fd)
temp_name = None
os.fsync(directory_fd)  # persists exchange and removal of the old name
```

### CR-05: `commit_uncertain` is rendered as a successful write

**Classification:** BLOCKER (Critical)
**Files:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:363-370`, `/home/nacs/Documents/git/olla/src/olla/loop.py:648-662`
**Issue:** The backend returns warning-only dictionaries for uncertain commits. The loop treats every result without an `error` key as success, defaults a missing `bytes_written` to zero, prints `wrote 0 bytes`, and clears the read snapshot. In a deterministic create probe, the destination contained `EXTERNAL` and the backend returned only `commit_uncertain: True` plus a warning; the loop's branch would tell the model the write succeeded. The rollback-failure result is similarly presented as an ordinary successful write even though the destination and recovery file require intervention.
**Fix:** Make the result contract discriminated (`status: success | stale | uncertain | error`) and handle `uncertain` before the success branch. The observation must say that the outcome is unknown, include the recovery path when present, and require a new `read_file`; it must never emit the normal `wrote N bytes` message.

```python
if result.get("commit_uncertain"):
    read_snapshots.pop(resolved, None)
    preview = f"write outcome uncertain: {result['warning']}; read_file before retrying"
elif "error" in result:
    ...
else:
    preview = f"wrote {result['bytes_written']} bytes to ..."
```

### CR-06: Atomic overwrite silently discards extended file metadata

**Classification:** BLOCKER (Critical)
**File:** `/home/nacs/Documents/git/olla/src/olla/tools/files.py:284-300`
**Issue:** For an existing file, the staging inode copies only permission bits before it replaces the destination. Ownership, POSIX ACLs, extended attributes, security labels, and other inode metadata are not copied. A deterministic probe set `user.olla-review=keep`, performed a successful overwrite, and then received `ENODATA` when reading the attribute. The operation reports full success despite losing metadata the user did not ask to change; loss of an ACL or security label can also change who may access the file.
**Fix:** Capture and copy supported ownership and extended metadata from `target_fd` to `staging_fd` before publication, then verify it. If the platform cannot preserve security-relevant metadata, refuse the overwrite or return an explicit warning requiring confirmation rather than silently dropping it. Add regressions for user xattrs and POSIX ACLs where supported.

## Warnings

### WR-01: An unclosed literal `<final>` inside a special payload hides a real outer final

**Classification:** WARNING
**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:35-42`
**Issue:** `FINAL_RE.finditer()` is non-overlapping. If write/memory payload text contains an unclosed literal `<final>` and a real `<final>done</final>` follows the args block, the first regex match consumes through the real closing tag; it is then discarded because its start is inside the args span, and the real outer opening is never considered. `parse_response()` returns the tool call instead of the documented final winner. For example, `<tool>write_file</tool><args>/tmp/a\nliteral <final> marker</args><final>done</final>` is parsed as `write_file`.
**Fix:** Replace the overlapping regex searches with one ordered tag tokenizer/stack, or explicitly scan the suffix after the matched outer `</args>` for final blocks before returning a special tool. Add this exact unclosed-literal regression.

### WR-02: `ToolResult` omits fields that production code returns and consumes

**Classification:** WARNING
**Files:** `/home/nacs/Documents/git/olla/src/olla/tools/base.py:17-34`, `/home/nacs/Documents/git/olla/src/olla/tools/files.py:363-369`
**Issue:** `write_file()` returns `commit_uncertain` and `recovery_path`, but neither key exists in the `ToolResult` TypedDict. The declared shared contract therefore rejects valid production results under static checking and gives callers no typed way to distinguish an uncertain commit from success—the ambiguity that contributes to CR-05.
**Fix:** Add the missing keys (or, preferably, define a discriminated write-result union with required fields per status) and exhaustively branch on that status in the loop.

---

_Reviewed: 2026-07-30T15:17:40Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
