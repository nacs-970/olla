# Plan 03-03 Summary — CR-01 / CR-03 Gap Closure

**Phase:** 03-file-tools
**Plan:** 03-03-PLAN.md
**Wave:** 1 (sequential executor)
**Status:** ✅ COMPLETE
**Completed:** 2026-06-16

---

## Objective

Close two BLOCKER gaps from 03-VERIFICATION.md:

- **CR-01**: `read_file`/`write_file` crash `run_loop()` on paths containing `\x00` (embedded null byte). `ValueError` from `pathlib` was not caught; existing except clauses covered only `UnicodeDecodeError`/`OSError`.
- **CR-03**: `write_file` confirm-gate and dry-run preview silently accepted a model's path-only (no-newline) `args_raw`, presenting the unchanged `"Write to \`...\`?"` prompt. Approving would truncate an existing file to 0 bytes without any disclosure.

---

## Tasks Executed

### Task 1 — Fix CR-01: ValueError for null-byte paths (FILE-01)

**Files:** `src/olla/tools/files.py`, `tests/test_tools/test_files.py`

**Changes:**
- `read_file`: `except (UnicodeDecodeError, OSError)` → `except (UnicodeDecodeError, OSError, ValueError)`
- `write_file`: `except OSError` → `except (OSError, ValueError)`
- Empirically verified: `Path()` construction and `.parent` do not raise for null-byte paths on Python 3.14 (only `read_text`/`write_text` raise `ValueError`). Parent-dir guard outside try block remains safe.

**Tests added:**
- `test_read_file_null_byte_path_returns_error`: `read_file("some\x00path")` returns `{"error": ...}`, never raises
- `test_write_file_null_byte_path_returns_error`: `write_file("/tmp/x\x00y", "content")` returns `{"error": ...}`, never raises

**Commit:** `a59d151` — `fix(CR-01): catch ValueError for null-byte paths in read_file/write_file`

---

### Task 2 — Fix CR-03: disclose/refuse empty-content write_file (FILE-02)

**Files:** `src/olla/loop.py`, `tests/test_loop.py`

**Changes:**
- **Normal loop** (~line 181): changed `path, _, file_content = parsed["args_raw"].partition("\n")` to capture `sep`. Added guard: if `sep == ""` (no newline — model emitted only a path), refuse unconditionally **before** the `if not yes:` confirm block. Prints and appends an Observation (`"refused: write_file for {resolved} had no content line — nothing written"`). Does not call `Confirm.ask()` or `write_file()`.
- **Dry-run preview** (~line 71): changed `path, _, _ = ...` to capture `sep`. If `sep == ""`, prints `"...refused: no content line provided, nothing would be written"` instead of `"...would prompt for confirmation"`.
- **Legitimate empty-file case** (`args_raw == "path\n"`, `sep == "\n"`, `file_content == ""`): **unaffected** — still flows through the normal confirm prompt.

**Tests added:**
- `test_run_loop_write_file_no_newline_discloses_empty_write`: normal loop, interactive — refusal happens before `Confirm.ask`; `write_file` never called; Observation contains "refused"/"no content"
- `test_run_loop_write_file_no_newline_with_yes_still_discloses_or_refuses`: `yes=True` — refusal fires before the `if not yes:` gate; `write_file` never called
- `test_dry_run_write_file_no_newline_discloses_empty_write`: `dry_run=True` — output does NOT contain "would prompt for confirmation"; does contain "refused"/"no content"

**Commit:** `1ed14dd` — `fix(CR-03): disclose/refuse no-newline write_file before confirm-gate`

---

## Verification

```
python -m pytest -v -k "null_byte or no_newline"   # 5/5 pass
python -m pytest                                    # 151/151 pass
```

**Before:** 146 tests | **After:** 151 tests (+5 new)

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `sep == ""` (no newline) → refuse unconditionally, even under `--yes` | `--yes` skips the confirm prompt entirely; it cannot meaningfully "confirm" a disclosure that was never shown. Refusing before the gate is the only safe option. |
| Distinguish no-newline (`sep == ""`) from explicit empty-file (`sep == "\n"`, `content == ""`) | The explicit empty-file case is a deliberate model choice; only the ambiguous no-newline case is refused. |
| `ValueError` added to both except clauses; parent-dir guard left outside try | Empirical test confirmed `.parent` and `Path()` construction are safe for null-byte paths on Python 3.14 — only I/O methods raise. Minimal change to satisfy "Never raises". |

---

## Artifacts Produced

| Path | Change |
|------|--------|
| `src/olla/tools/files.py` | ValueError added to except clauses in `read_file` and `write_file` |
| `src/olla/loop.py` | `sep` captured in dry-run + normal-loop write_file blocks; refusal guard before confirm |
| `tests/test_tools/test_files.py` | +2 CR-01 regression tests |
| `tests/test_loop.py` | +3 CR-03 regression tests |

---

## Gaps NOT Touched

Per plan scope: CR-02 (accepted T-03-08), WR-01, WR-02, WR-03, IN-01 remain as documented in 03-VERIFICATION.md for future consideration.
