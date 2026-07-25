# Coding Conventions

**Analysis Date:** 2026-07-25

## Naming Patterns

**Files:**
- Use lowercase `snake_case.py` module names, as in `src/olla/safety.py`, `src/olla/parser.py`, and `src/olla/tools/files.py`.
- Name test modules `test_<module>.py` and mirror the package grouping where useful: `tests/test_loop.py` covers `src/olla/loop.py`, while `tests/test_tools/test_files.py` covers `src/olla/tools/files.py`.
- Keep package markers as `__init__.py`; `src/olla/__init__.py` exposes package metadata, while `src/olla/tools/__init__.py` and the test package markers are empty.

**Functions:**
- Use lowercase `snake_case` for public functions: `parse_response()` in `src/olla/parser.py`, `run_loop()` in `src/olla/loop.py`, and `read_file()` in `src/olla/tools/files.py`.
- Prefix module-private helpers with one underscore: `_blocklist_match()`, `_unwrap_env()`, and `_is_dangerous_device_arg()` in `src/olla/safety.py`.
- Name tests `test_<behavior>`, including the condition and expected outcome: `test_run_loop_confirm_declined_does_not_run_shell()` in `tests/test_loop.py` and `test_rm_dangerous_targets_block()` in `tests/test_safety.py`.
- Use imperative verbs for actions (`run_`, `read_`, `write_`, `check_`) and predicate-style `_is_...` names for Boolean helpers.

**Variables:**
- Use `snake_case` for locals and parameters: `max_steps`, `system_prompt`, `repeat_count`, and `file_content` in `src/olla/loop.py`.
- Give intermediate values role-oriented names (`parsed`, `decision`, `preview`, `combined`) rather than encoding their concrete type.
- Prefix implementation-only module data with `_`, as in `_DEVICE_PREFIXES` and `_ENV_FLAGS_WITH_ARG` in `src/olla/safety.py`.

**Types:**
- Use `PascalCase` for type contracts: `ToolResult` in `src/olla/tools/base.py` and `Decision` in `src/olla/safety.py`.
- Use built-in generic syntax (`list[str]`, `set[str]`, `tuple | None`) compatible with the declared Python 3.10 floor in `pyproject.toml`.
- Keep structured dictionary contracts as `TypedDict` when callers inspect keys directly. Both `ToolResult` and `Decision` use `total=False` to represent result variants.

## Code Style

**Formatting:**
- Ruff is the only formatter/linter dependency declared in `pyproject.toml`; `uv.lock` pins Ruff 0.15.17.
- No `[tool.ruff]`, `[tool.ruff.format]`, Black, isort, EditorConfig, or pre-commit configuration is present. Ruff therefore uses its defaults.
- Use four-space indentation, double-quoted strings, trailing commas in multiline literals/calls, and blank lines between module sections, matching `src/olla/safety.py` and `tests/test_loop.py`.
- Keep imports and definitions separated by two blank lines at module scope.
- Run `ruff format --check src tests` before treating formatting as clean. As analyzed, it reports that nine files would be reformatted, including `src/olla/loop.py`, `src/olla/safety.py`, and `tests/test_loop.py`; formatting is not currently enforced.

**Linting:**
- Run `ruff check src tests`. This command passes for the current tracked source and maintained tests.
- No custom rule selection, ignores, per-file ignores, or target version are configured in `pyproject.toml`; do not assume rules beyond Ruff defaults.
- Preserve Python 3.10 compatibility. `tests/test_safety.py` explicitly guards against reintroducing Python-3.11-only `typing.NotRequired` or `typing.Required`.

## Import Organization

**Order:**
1. Standard-library imports, such as `shlex` and `pathlib.Path` in `src/olla/loop.py`.
2. Third-party imports, such as `ollama` and `rich.prompt.Confirm` in `src/olla/loop.py`.
3. Absolute application imports rooted at `olla`, such as `from olla.parser import parse_response`.

- Separate each import group with one blank line.
- Prefer specific imported names (`from pathlib import Path`) over importing a whole standard-library module when only one object is used.
- Patch dependencies where they are consumed, so tests use targets such as `"olla.loop.run_shell"` and `"olla.cli.run_loop"` rather than patching the defining module.

**Path Aliases:**
- No path aliases are configured.
- Use absolute package imports beginning with `olla.` throughout `src/olla/` and `tests/`; do not introduce relative imports without a repository-wide reason.

## Error Handling

**Patterns:**
- Tool boundary functions return a `ToolResult` error variant rather than raising expected operational failures. `read_file()` and `write_file()` in `src/olla/tools/files.py` return `{"path": ..., "error": ...}`; `run_shell()` in `src/olla/tools/shell.py` returns `{"argv": ..., "error": ...}`.
- Catch narrow, anticipated exception classes at the boundary where recovery is possible. `src/olla/tools/files.py` handles filesystem and decoding exceptions; `src/olla/tools/shell.py` handles `FileNotFoundError` and `subprocess.TimeoutExpired`.
- Convert user/model input failures into visible observations and continue when the loop can recover. `src/olla/loop.py` catches `ValueError` from `shlex.split()` and appends an `Observation:` message.
- Fail closed on unavailable confirmation input. `src/olla/loop.py` catches `EOFError` from `Confirm.ask()` and treats it as a declined action.
- Use `click.UsageError` for invalid CLI combinations in `src/olla/cli.py`.
- Return early after terminal conditions rather than nesting the remaining logic: direct final responses, dry-run previews, repetition limits, and invalid CLI input all follow this pattern in `src/olla/loop.py` and `src/olla/cli.py`.
- Avoid broad `except Exception`; no broad exception handlers are used in tracked `src/olla/`.

## Logging

**Framework:** Built-in `print()` plus Rich confirmation prompts

**Patterns:**
- Use `print()` for user-facing loop progress, observations, warnings, and final answers in `src/olla/loop.py` and `src/olla/smoke.py`.
- Use `rich.prompt.Confirm` only for interactive approval prompts in `src/olla/loop.py`.
- Keep messages actionable and include the affected command/path or safety reason.
- Truncate model/tool output with `truncate_output()` from `src/olla/loop.py` before printing it or placing it in message history.
- No Python `logging` configuration, structured logger, log levels, or telemetry hooks are present. New output should follow the CLI-facing `print()` convention unless a logging subsystem is deliberately introduced.

## Comments

**When to Comment:**
- Start each module with a concise one-line module docstring explaining its responsibility, as every nonempty file under `src/olla/` does.
- Comment safety-sensitive reasoning, non-obvious parsing behavior, and compatibility constraints. `src/olla/safety.py` documents wrapper recursion, false-positive avoidance, malformed input, and filesystem-equivalent path forms.
- Preserve requirement and review identifiers such as `D-03`, `CR-01`, and `WR-02` when a branch implements a specific contract; examples are concentrated in `src/olla/safety.py`, `src/olla/loop.py`, and their regression tests.
- Avoid comments that merely narrate obvious code. Most straightforward functions in `src/olla/parser.py` and `src/olla/tools/files.py` rely on names and docstrings instead.

**JSDoc/TSDoc:**
- Not applicable; the project is Python.
- Use Python docstrings on production modules, public functions, public type contracts, and complex private helpers. Docstrings describe inputs, return variants, and failure behavior in `src/olla/tools/files.py`, `src/olla/tools/shell.py`, and `src/olla/safety.py`.
- Test functions generally rely on descriptive names; add inline comments only for regression context or a subtle assertion, as in `tests/test_safety.py` and `tests/test_loop.py`.

## Function Design

**Size:** Most helpers are short and single-purpose; keep parsing, file I/O, shell execution, and safety classification in their existing modules. `run_loop()` in `src/olla/loop.py` and `_blocklist_match()` in `src/olla/safety.py` are branch-heavy orchestration functions, so additions should reuse or extract helpers rather than deepen their branches unnecessarily.

**Parameters:** Production functions use explicit type annotations and keyword defaults, as in `run_shell(argv: list[str], timeout: int = 30)` and `run_loop(..., yes: bool = False, dry_run: bool = False)`. CLI callback `main()` in `src/olla/cli.py` is the exception because Click supplies its parameters.

**Return Values:**
- Use explicit return annotations on production functions.
- Return `None` for side-effecting orchestration (`run_loop()`, `run_smoke_test()`).
- Return typed result dictionaries for tools and safety decisions (`ToolResult`, `Decision`).
- Keep result discriminators stable. Parser callers branch on `parsed["type"]`, while safety callers branch on `decision["kind"]`.
- Do not raise for normal tool failures; return the established `error` key and omit success-only keys.

## Module Design

**Exports:** Import concrete symbols directly from their implementation modules, for example `from olla.tools.files import read_file, write_file`. `src/olla/__init__.py` exposes only `__version__`.

**Barrel Files:** Barrel re-exports are not used. `src/olla/tools/__init__.py` is empty; add new tool implementations as focused modules under `src/olla/tools/` and import them explicitly at their call sites.

**Boundary Pattern:**
- Keep external-library calls behind small functions that are easy to patch: Ollama calls are isolated by `call_model()` in `src/olla/loop.py`, filesystem work by `src/olla/tools/files.py`, and subprocess work by `src/olla/tools/shell.py`.
- Keep policy evaluation pure. `check()` in `src/olla/safety.py` returns a decision and does not prompt or execute; `src/olla/loop.py` owns the side effect.
- Preserve the model protocol as plain dictionary messages and parser result dictionaries until a coordinated type-contract change is made across `src/olla/parser.py`, `src/olla/loop.py`, and `tests/test_loop.py`.

---

*Convention analysis: 2026-07-25*
