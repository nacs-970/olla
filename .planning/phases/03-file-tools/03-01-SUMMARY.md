---
phase: 03-file-tools
plan: 01
subsystem: tools
tags: [pathlib, react-loop, tdd, file-io]

# Dependency graph
requires:
  - phase: 02-safety-gate-loop-control
    provides: ReAct loop dispatch (run_loop), repetition guard, truncate_output, dry-run preview, parse_response tag parser
provides:
  - read_file(path) tool (olla.tools.files) - reads UTF-8 text via pathlib, returns ToolResult dict, never raises
  - ToolResult extended with path/content fields shared by all file tools
  - loop.py dispatch restructured to if/elif/else (shell / read_file / unknown) - extensible for write_file
  - generalized repetition guard (signature + message keyed by tool name)
  - SYSTEM_PROMPT documents read_file tool with example
affects: [03-02 (write_file - reuses if/elif/else dispatch shape and ToolResult contract)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "File tools return ToolResult dicts (path/content or path/error), never raise - mirrors shell tool's error-as-dict contract"
    - "Tool dispatch in loop.py is if/elif/else keyed on parsed['tool'], each branch self-contained (repetition guard, action, observation)"
    - "Repetition guard signature is (tool_name, identity_tuple) - shell uses (shell, argv tuple), read_file uses (read_file, args_raw); message templated as f'olla stopped: same {tool} call repeated 3x...'"

key-files:
  created:
    - src/olla/tools/files.py
    - tests/test_tools/test_files.py
  modified:
    - src/olla/tools/base.py
    - src/olla/loop.py
    - src/olla/prompts.py
    - tests/test_loop.py

key-decisions:
  - "read_file uses pathlib.Path.read_text(encoding='utf-8') with explicit except clauses for FileNotFoundError, IsADirectoryError, and (UnicodeDecodeError, OSError) - matches run_shell's never-raise dict contract"
  - "Repetition guard generalized via tuple signature + f-string message so existing shell literal ('olla stopped: same shell call repeated 3x...') renders unchanged while read_file gets its own ('...same read_file call...')"
  - "Provisioned .venv via uv venv + uv pip install -e '.[dev]' to install already-declared pyproject.toml dependencies (ollama, pydantic, etc.) - no new packages added, .venv already gitignored"

requirements-completed: [FILE-01]

# Metrics
duration: 35min
completed: 2026-06-15
---

# Phase 3 Plan 1: read_file Tool Summary

**read_file(path) tool wired end-to-end through the ReAct loop's dispatch, dry-run preview, and repetition guard, using pathlib + a never-raise ToolResult contract**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `read_file(path)` implemented in `src/olla/tools/files.py` - reads UTF-8 text via `pathlib.Path.read_text()`, returns `{"path": ..., "content": ...}` on success or `{"path": ..., "error": ...}` on FileNotFoundError/IsADirectoryError/UnicodeDecodeError/OSError, never raises
- `ToolResult` (olla.tools.base) extended with `path: str` and `content: str` fields, shared contract for shell and file tools
- `run_loop`'s dispatch (both dry-run preview and main loop) restructured from a binary `shell`-vs-unknown check into an if/elif/else over `shell` / `read_file` / unknown-tool, ready for `write_file` in plan 03-02
- Repetition guard generalized: signature is now `(tool_name, identity)` per tool (`("shell", tuple(argv))` vs `("read_file", args_raw)`), and the abort message is templated as `f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck"` - existing shell wording unchanged, read_file gets matching wording
- `SYSTEM_PROMPT` updated to teach the model about `read_file` with a worked example, alongside the existing `shell` tool

## Task Commits

1. **Task 1: RED - failing tests for read_file tool and loop dispatch** - `51e403e` (test)
2. **Task 2: GREEN - implement read_file and restructure loop dispatch** - `42deed2` (feat)

_TDD plan: test commit (RED) followed by feat commit (GREEN). No refactor commit needed - implementation was clean on first pass._

## Files Created/Modified
- `src/olla/tools/files.py` - new `read_file(path) -> ToolResult` function
- `tests/test_tools/test_files.py` - new tests for read_file success and not-found cases
- `src/olla/tools/base.py` - `ToolResult` gains `path` and `content` fields
- `src/olla/loop.py` - import `read_file`; dry-run and main dispatch restructured to if/elif/else (shell/read_file/unknown); repetition guard generalized per tool
- `src/olla/prompts.py` - `SYSTEM_PROMPT` documents `read_file` tool with example
- `tests/test_loop.py` - 6 new tests: read_file dispatch (no confirm prompt), large-output truncation, error observation, dry-run preview, unchanged repetition-guard coverage for shell, and new repetition-guard coverage for read_file

## Decisions Made
- `read_file` mirrors `run_shell`'s "never raise, return error-as-dict" contract exactly, using `pathlib.Path.read_text(encoding="utf-8")` with targeted except clauses (FileNotFoundError, IsADirectoryError, UnicodeDecodeError/OSError) - keeps the loop's `"error" in result` branch logic identical across both tools
- Repetition guard signature/message generalized rather than duplicated per-tool, so the existing literal string for shell (`"olla stopped: same shell call repeated 3x — model likely stuck"`) is produced by the same f-string that now also produces the read_file variant - zero risk of the two diverging in wording over time
- read_file has no confirm-gate or safety.check() call (ALLOW tier, read-only, no side effects) - confirmed by `mock_confirm.assert_not_called()` in the new dispatch test

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Provisioned missing Python dev environment (.venv)**
- **Found during:** Task 1 (RED verification)
- **Issue:** Worktree had no `.venv` and no editable `olla` install; `pytest` failed with `ModuleNotFoundError: No module named 'ollama'` even for pre-existing `tests/test_loop.py` (which depends on `src/olla/loop.py`'s existing `import ollama`), masking the expected RED failure for the new `read_file` tests
- **Fix:** Ran `uv venv` then `uv pip install -e ".[dev]"`, which installs `olla` in editable mode plus all dependencies already declared in `pyproject.toml` (`ollama>=0.6.2`, `click`, `rich`, `pytest`, `pytest-mock`, `ruff`) - no new/undeclared packages introduced
- **Files modified:** none (`.venv/` already covered by existing `.gitignore` entry `.venv/`)
- **Verification:** Re-ran `tests/test_tools/test_files.py` + `tests/test_loop.py -k read_file` via `.venv/bin/python -m pytest` - got the expected RED (`ModuleNotFoundError: No module named 'olla.tools.files'` for test_files.py; `AttributeError: ... does not have the attribute 'read_file'` / assertion failures for the 6 new test_loop.py tests), with `ollama` importing cleanly
- **Committed in:** n/a (no tracked files changed - `.venv/` is gitignored)

---

**Total deviations:** 1 auto-fixed (1 blocking - environment provisioning)
**Impact on plan:** Necessary to run any tests in this worktree at all; no new dependencies, no scope creep.

## Issues Encountered
None beyond the environment provisioning documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 115 new/changed tests + 109 pre-existing = 134 tests, all passing (`134 passed`)
- `read_file` tool fully wired: model can emit `<tool>read_file</tool><args>/path</args>`, loop dispatches, truncates large output, surfaces errors as Observations, and is covered by the repetition guard and dry-run preview
- `if/elif/else` dispatch shape in `loop.py` (dry-run and main loop) is the extension point plan 03-02 (`write_file`) will add a third branch to
- `ToolResult` already has `path`/`content` fields that `write_file` can reuse (write_file will likely also use `path` plus a success/error indicator)

---
*Phase: 03-file-tools*
*Completed: 2026-06-15*
