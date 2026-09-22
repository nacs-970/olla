---
phase: 05-safe-inspection-tools
plan: 01
status: complete
requirements: [INSPECT-01, INSPECT-02, INSPECT-03]
files_modified:
  - src/olla/tools/inspect.py
  - src/olla/loop.py
  - src/olla/prompts.py
  - tests/test_tools/test_inspect.py
  - tests/test_loop.py
  - tests/test_prompts.py
---

## What shipped

`list_dir(path)` and `grep_files(pattern, path, recursive=False)` — two read-only inspection tools the model can call and have executed immediately, no confirmation prompt.

- **`src/olla/tools/inspect.py`** (new): both adapters. `list_dir` uses `os.scandir`, sorts directories-first-then-alphabetical, caps at 50 entries + truncation note, shows `[d]`/`[f]`/`[l]` markers with human-readable sizes, never follows symlinks, includes dotfiles. `grep_files` compiles the pattern with `re.error` guarded, walks with `.git`-pruning via `dirnames[:]` mutation when `recursive=True`, skips binary files (null-byte sniff, first 8000 bytes), skips symlinked files, caps at 25 match lines in scan order + truncation note.
- **`src/olla/loop.py`**: `_Action` gained `pattern`/`recursive` fields. New `list_dir`/`grep_files` branches in `_prepare_action()`, `_execute_list_dir()`/`_execute_grep_files()`, and `run_loop()` dispatch — both bypass `safety.check()` entirely (D-09) and record output via `_record_file_observation()` (untrusted tagging), matching `read_file`'s precedent exactly. `_preview_action()` covers both for `--dry-run`.
- **`src/olla/prompts.py`**: tool roster documentation for both tools' tag contracts, including `grep_files`' three-line wire format (pattern / path / optional `recursive=true`).
- Tests: new `tests/test_tools/test_inspect.py` (adapter-level behavior per plan's `<behavior>` blocks), plus `tests/test_loop.py` dispatch/error/gate-consequence tests proving both tools reach the model with zero `Confirm.ask()` calls and that a later CONFIRM-tier shell turn still re-confirms under `--yes` (untrusted-observation gate actually fires, not just wrapper-string presence).

## Verification

- `pytest`: 397 passed.
- `ruff check src tests`: all checks passed.
- `src/olla/safety.py` and `src/olla/parser.py`: zero diff (D-09 lock and parser-unchanged constraint both held).
- Manually confirmed the gate-consequence tests assert `Confirm.ask` **was** called on the post-inspection CONFIRM-tier shell turn and that "Confirmation required: this action follows untrusted tool output." is printed — the load-bearing proof, not just the `<untrusted_file_content>` substring.

## Deviations from plan

- Fixed 3 tests during execution that had a message-indexing bug (asserting on `messages[-1]` of the *next* `ollama.chat` call's captured kwargs, which — because `messages` is a mutable list captured by reference — reflected later appends made after that call returned, not the tool observation). Reworked to filter by role/content-prefix, matching the existing convention already used elsewhere in `tests/test_loop.py` (e.g. `test_run_loop_read_file_error_observation`).
- Two gate-consequence tests patched `run_shell` but never asserted on the mock; added `mock_run_shell.assert_called_once()` to make the mock meaningful (confirms the shell action actually dispatched post-confirmation, not just that `Confirm.ask` was called).
- Minor ruff cleanups in `inspect.py` (SIM113 enumerate, 2x SIM102 combined conditionals) with no behavior change.

## Requirements delivered

INSPECT-01, INSPECT-02, INSPECT-03 — all `must_haves.truths` and `success_criteria` from `05-01-PLAN.md` verified against the actual test suite, not just self-reported.
