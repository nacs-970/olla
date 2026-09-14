# Coding Conventions

**Analysis Date:** 2026-09-14

## Naming Patterns

**Files:**
- Lowercase snake_case module names matching their primary concern: `loop.py`, `parser.py`, `safety.py`, `config.py`, `debug.py`, `smoke.py`, `prompts.py`.
- Subpackages group related tool implementations under `src/olla/tools/` (`files.py`, `shell.py`, `web.py`, `inspect.py`, `memory.py`, `base.py`) and provider adapters under `src/olla/providers/` (`ollama.py`, `openai_compat.py`, `base.py`).
- Test files mirror the module under test 1:1: `src/olla/loop.py` -> `tests/test_loop.py`, `src/olla/tools/shell.py` -> `tests/test_tools/test_shell.py`.

**Functions:**
- Public API functions: short, verb-first snake_case — `run_loop`, `call_model`, `check`, `read_file`, `write_file`, `run_shell`, `parse_response`, `load_config`.
- Internal/private helpers are prefixed with a single leading underscore: `_prepare_action`, `_execute_shell`, `_resolve_file_path`, `_blocklist_match`, `_unwrap_env`. This prefix is used consistently across every module (`loop.py`, `safety.py`, `tools/files.py`) to separate the public contract from implementation detail.
- Predicate/boolean helpers read as questions or assertions: `_is_mocked`, `_is_dangerous_device_arg`, `parent_directory_matches_path`.

**Variables:**
- snake_case throughout; no camelCase anywhere in `src/olla/`.
- Module-level constants are SCREAMING_SNAKE_CASE: `MAX_OBSERVATION_CHARS`, `ALLOWLIST`, `_HARD_BLOCKED_BINARIES`, `_RM_DANGEROUS_TARGETS`, `MAX_KEY_CHARS` — private constants still get the leading underscore (`_DEVICE_GLOB`, `_ENV_FLAGS_WITH_ARG`).
- Compiled regexes are named `<PURPOSE>_RE`: `FINAL_OPEN_RE`, `TOOL_CLOSE_RE`, `THINK_TAG_RE`, `_FORK_BOMB_RE` (`src/olla/parser.py`, `src/olla/loop.py`, `src/olla/safety.py`).

**Types:**
- `TypedDict` is the standard shape for structured dict returns, not `pydantic` or dataclasses-as-DTOs: `ToolResult` and `FileSnapshot` in `src/olla/tools/base.py`, `Decision` in `src/olla/safety.py`. `total=False` is used deliberately when only a subset of keys is populated per code path (see `ToolResult` docstring).
- `@dataclass(frozen=True)` is used for internal, short-lived value objects that are never mutated after construction: `_MemoryRequest`, `_FileReadSnapshot`, `_Action` in `src/olla/loop.py`.
- `Literal[...]` is used for closed string enums inside TypedDicts (`Decision.kind`, `ToolResult.status`).
- Modern PEP 604 union syntax (`str | None`) is used everywhere instead of `Optional[str]` — this is a hard convention, not mixed with `typing.Optional`.

## Code Style

**Formatting:**
- No `.ruff.toml`/`[tool.ruff]` section exists in `pyproject.toml` — ruff runs with its default rule set (`ruff` listed under `[project.optional-dependencies].dev`, `pyproject.toml:24-28`). Do not assume custom line-length or rule overrides; match ruff's stock formatting (double quotes, trailing commas in multi-line calls, 4-space indent).
- Every module opens with a one-line docstring summarizing its responsibility (e.g. `"""Pure safety-gate decision: blocklist/allowlist check against resolved argv."""` in `src/olla/safety.py:1`). Follow this pattern for any new module.
- Multi-line function signatures wrap one parameter per line with a trailing comma when the call/signature would otherwise exceed ~88-100 columns (see `src/olla/loop.py:120-133`, `_execute_shell` signature).

**Linting:**
- `# noqa: BLE001` is used to intentionally suppress ruff's blind-except warning at the few sites where a genuinely broad `except Exception` is required for resilience against unpredictable third-party/model output (`src/olla/loop.py:562`, `src/olla/debug.py:43`). Reserve broad excepts for these narrow, explicitly-justified cases — prefer specific exception types elsewhere.
- `# type: ignore[no-redef]` is used for the `tomllib`/`tomli` conditional import shim (`src/olla/config.py:10`) — the standard pattern for Python-version-gated imports.
- `# pragma: no cover` marks branches that are structurally required but not exercised by the test suite (non-POSIX fallback import in `src/olla/tools/files.py:16`, `except ModuleNotFoundError` in `src/olla/config.py:9`).

## Import Organization

**Order:** stdlib, blank line, third-party, blank line, first-party `olla.*` — observed consistently in every module (see `src/olla/loop.py:1-35`, `src/olla/cli.py:1-11`).
1. Standard library (`os`, `re`, `shlex`, `difflib`, `itertools`, `dataclasses`, `pathlib`, `unittest.mock`)
2. Third-party (`click`, `ollama`, `rich.prompt`, `rich.text`, `httpx`)
3. First-party, absolute imports only: `from olla.debug import ...`, `from olla.tools.files import (...)` — never relative imports (`from .debug import`).

**Path Aliases:** None — the package is installed/imported as `olla` (via `src/` layout, `pyproject.toml:30-31`); no import aliasing or path rewriting is configured.

## Error Handling

**Patterns:**
- Tool-layer functions (`read_file`, `write_file`, `run_shell`, `fetch_url`, `search_web`, `grep_files`, `list_dir`) never raise for expected failure modes — they return a `ToolResult`/dict with an `"error"` key instead. Callers check `"error" in result` (see `src/olla/loop.py:715`, `src/olla/tools/shell.py`). This "errors as data" pattern is the dominant convention for anything the model-driven loop consumes.
- Exceptions are reserved for genuinely exceptional/programmer-error conditions: `RuntimeError` at import time when the POSIX file-tool backend requirements aren't met (`src/olla/tools/files.py:24-64`), `ValueError` for invalid `truncate_output(limit=-1)` calls (`src/olla/loop.py:487-488`).
- External SDK exceptions are caught narrowly and converted into user-facing diagnostics rather than propagated: `ollama.RequestError`, `ollama.ResponseError`, `ProviderError` are caught explicitly in `_call_model_for_loop` and `_stream_model_turn` (`src/olla/loop.py:526`, `553-556`), each producing a `_display(...)` message plus `return None` so the loop can exit cleanly.
- Parsing/resolution helpers that can fail return a `(value, error)` two-tuple instead of raising, so the caller decides how to surface the failure: `_resolve_file_path` -> `tuple[Path | None, str | None]` (`src/olla/loop.py:115-121`), `find_config_path`/`load_config` swallow `OSError`/`tomllib.TOMLDecodeError` and return `None`/`{}` (`src/olla/config.py:53-54`).
- Custom domain exceptions are minimal, single-purpose, and documented with a one-line docstring: `ProviderError(Exception)` in `src/olla/providers/base.py:8-9`.

## Logging

**Framework:** No structured logging library (`logging` module unused). Two purpose-built print-based mechanisms instead:
- `debug_log(title, content=None)` in `src/olla/debug.py` — gated by `is_debug()`, only active when `--debug`/`OLLA_DEBUG` env var/`debug` config key is set. Pretty-prints dicts/lists as indented JSON, prefixes every line with a magenta `[DEBUG]` ANSI tag. Used pervasively through `loop.py` to log step transitions, model calls, tool results (`src/olla/loop.py:416, 662, 689, ...`).
- `_display(text)` in `src/olla/loop.py:59-61` — the single sanctioned path for printing any *untrusted* (model- or tool-derived) text to the terminal; it always routes through `_terminal_safe()` first to escape control characters and invalid Unicode before printing (security-motivated convention, not just style — see `_terminal_safe` docstring `src/olla/loop.py:40-41`).

**Patterns:**
- Never `print()` untrusted content directly — always through `_display()`. Any new tool-result path must follow this.
- Debug logging is call-sited immediately before/after the operation it describes, with a `dict` payload of relevant context (e.g. `debug_log(f"Step {step} - Shell execution result", result)`).
- Secrets are never logged in the clear: `mask_secret()` (`src/olla/debug.py:21-27`) truncates API keys to a `first8...last4` form before they reach `debug_log`.

## Comments

**When to Comment:**
- Comments explain *why*, especially for security/safety-critical logic, referencing internal design decision IDs (`D-01`, `D-03`, `D-04`, `CR-01`, `CR-02`, `WR-02`) that trace back to design docs — see `src/olla/safety.py:18-22, 46-49, 204-214`. When touching `safety.py`, preserve and extend this ID-referencing comment style.
- Non-obvious regex or parsing logic gets a multi-line comment walking through the intent and edge cases handled (`src/olla/parser.py` docstrings, `src/olla/safety.py:204-231` for the `bash -c` unwrap logic).
- Comments call out what changed/why a prior approach was replaced, aiding future maintainers (e.g. `src/olla/tools/shell.py:62-64`: "Malformed-quoting handling ... is now the caller's responsibility").

**JSDoc/TSDoc:** N/A (Python project). Every public function and most private ones carry a one-line (occasionally multi-line) docstring summarizing behavior/intent, not parameter-by-parameter documentation — no Google/NumPy-style docstring sections are used.

## Function Design

**Size:** Functions are kept single-purpose; large branching logic (e.g. `_prepare_action` in `src/olla/loop.py:219-366`) is structured as a sequence of early-return `if tool == "...":` blocks per tool type rather than one large conditional expression. `run_loop` itself is long (`src/olla/loop.py:994-1179`) but delegates each action kind to a dedicated `_execute_<kind>` helper — prefer extracting a new `_execute_<x>` function over growing the main loop body.

**Parameters:** Functions with more than ~3 parameters use keyword-only arguments (`*,`) to force call-site clarity — see `_execute_shell(action, *, step, messages, yes, untrusted_observation_seen)` (`src/olla/loop.py:648-655`) and `_handle_memory(request, *, step, scratchpad, execute)`. Follow this pattern for new multi-parameter helpers.

**Return Values:** Prefer returning small structured values (`TypedDict`, frozen `dataclass`, `(value, error)` tuple) over raising or returning loosely-typed dicts. Boolean returns from `_execute_*` helpers signal "did this produce an untrusted observation" and are threaded back into `run_loop`'s `untrusted_observation_seen` state — follow this boolean-contract convention exactly when adding a new tool executor.

## Module Design

**Exports:** No `__all__` lists are used; modules rely on the underscore-prefix convention to signal private vs. public surface. `src/olla/__init__.py` is a 3-line placeholder with no re-exports — import from the concrete submodule (`from olla.loop import run_loop`), not from the package root.

**Barrel Files:** `src/olla/tools/__init__.py` is empty (no re-exports); `src/olla/providers/__init__.py` (102 lines) is the one exception — it acts as a small factory/registry module (`get_provider(...)`) rather than a pure barrel, and is the place to register any new provider implementation.

---

*Convention analysis: 2026-09-14*
