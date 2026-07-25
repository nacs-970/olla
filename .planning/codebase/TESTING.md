# Testing Patterns

**Analysis Date:** 2026-07-25

## Test Framework

**Runner:**
- pytest >=8 is declared in `pyproject.toml`; `uv.lock` pins pytest 9.1.0, while the analyzed `.venv` reports pytest 9.0.3.
- Config: `pyproject.toml` is detected as the pytest root configuration file, but it contains no `[tool.pytest.ini_options]` section. There is no `pytest.ini`, `tox.ini`, `noxfile.py`, or `conftest.py`.
- Plugins: `pytest-mock` >=3.14 is declared in `pyproject.toml` and pinned to 3.15.1 in `uv.lock`. The active environment also exposes AnyIO through transitive dependencies, but the suite does not use async tests.

**Assertion Library:**
- pytest assertion rewriting over plain Python `assert`.
- `unittest.mock` assertions are used through pytest-mock objects, for example `assert_called_once_with()`, `assert_not_called()`, and `call_count` in `tests/test_cli.py` and `tests/test_loop.py`.

**Run Commands:**
```bash
.venv/bin/python -m pytest tests                    # Run the maintained suite
.venv/bin/python -m pytest tests/test_safety.py     # Run one module
.venv/bin/python -m pytest tests/test_loop.py -k dry_run  # Run a behavioral subset
```

- The maintained command `.venv/bin/python -m pytest tests` passes 151 tests.
- Running bare `.venv/bin/python -m pytest` currently also discovers root-level untracked scratch files `test_fix.py`, `test_replace.py`, and `test_temp.py`, which fail during collection. Use the explicit `tests` path until discovery is constrained in `pyproject.toml` or those scratch files are moved/renamed.
- Watch mode: Not configured. No `pytest-watch`, `ptw`, or equivalent dependency is declared.
- Coverage: Not configured. No `pytest-cov`, `coverage.py`, coverage settings, or repository coverage command is present.

## Test File Organization

**Location:**
- Tests live in the top-level `tests/` tree, separate from the `src/olla/` package.
- Top-level package modules map to `tests/test_<module>.py`: `src/olla/parser.py` → `tests/test_parser.py`; `src/olla/safety.py` → `tests/test_safety.py`.
- Tool submodules mirror the source subtree: `src/olla/tools/files.py` → `tests/test_tools/test_files.py`.
- `tests/__init__.py` and `tests/test_tools/__init__.py` are empty package markers.

**Naming:**
- Name files `test_<subject>.py`.
- Name tests `test_<unit>_<condition>_<expected_result>` when the full behavior needs to be explicit, such as `test_run_loop_block_tier_with_yes_still_blocks()` in `tests/test_loop.py`.
- Keep one behavioral outcome per test even when setup is substantial.

**Structure:**
```text
tests/
├── __init__.py
├── test_cli.py
├── test_loop.py
├── test_parser.py
├── test_safety.py
├── test_smoke.py
└── test_tools/
    ├── __init__.py
    ├── test_files.py
    └── test_shell.py
```

## Test Structure

**Suite Organization:**
```python
def test_run_loop_confirm_approved_runs_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {
        "argv": ["git", "status"],
        "returncode": 0,
        "stdout": "clean\n",
        "stderr": "",
    }
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(
        task="check status",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
    )

    captured = capsys.readouterr()
    assert "clean\n" in captured.out
    mock_confirm.assert_called_once()
    mock_run_shell.assert_called_once()
```

This is the established arrange/act/assert pattern from `tests/test_loop.py`: create dependency behavior, call one public entry point, then assert both output and collaborator interactions.

**Patterns:**
- Setup is local to each test; there are no shared custom fixtures or setup classes.
- Use pytest built-in fixtures directly in function parameters: `capsys` for CLI output and `tmp_path` for isolated filesystem state.
- Use the pytest-mock `mocker` fixture for dependency replacement and call inspection.
- Test sequences with `side_effect` lists, especially model turn progression in `tests/test_loop.py`.
- Assert returned dictionaries directly for parsers and tools, as in `tests/test_parser.py` and `tests/test_tools/test_files.py`.
- Assert safety invariants using both the decision discriminator and the human-readable reason in `tests/test_safety.py`.
- Verify negative side effects with `assert_not_called()` for blocked, declined, dry-run, and invalid-input paths.
- There is no class-based suite organization, parametrization, autouse fixture, or teardown hook.

## Mocking

**Framework:** pytest-mock 3.15.1 (lockfile version), backed by `unittest.mock`

**Patterns:**
```python
mock_chat = mocker.patch("olla.loop.ollama.chat")
mock_chat.side_effect = [
    {"message": {"content": "<tool>read_file</tool><args>/tmp/in.txt</args>"}},
    {"message": {"content": "<final>done</final>"}},
]

mock_read_file = mocker.patch("olla.loop.read_file")
mock_read_file.return_value = {
    "path": "/tmp/in.txt",
    "content": "original content\n",
}
```

- Patch the name in the consumer module. `tests/test_loop.py` patches `"olla.loop.read_file"` and `"olla.loop.run_shell"` because those are the references `run_loop()` calls.
- Configure return dictionaries with the same `ToolResult` shape used by production code.
- Use `side_effect` for ordered model responses and injected exceptions such as `EOFError`.
- Inspect `call_args_list` when the mutable message history is part of the contract.

**What to Mock:**
- Ollama network/model calls (`olla.loop.ollama.chat`, `olla.smoke.call_model`).
- Loop-level shell and filesystem dispatch when testing orchestration (`olla.loop.run_shell`, `olla.loop.read_file`, `olla.loop.write_file`).
- Interactive confirmation (`olla.loop.Confirm.ask`).
- CLI orchestration boundaries (`olla.cli.run_loop`, `olla.cli.run_smoke_test`).

**What NOT to Mock:**
- Pure parsing and classification functions in `src/olla/parser.py`, `src/olla/smoke.py`, and `src/olla/safety.py`; pass concrete strings or argv lists.
- File I/O when directly testing `src/olla/tools/files.py`; use `tmp_path`.
- Harmless subprocess behavior when directly testing `src/olla/tools/shell.py`; current tests run `echo`, `false`, a missing binary, and `sleep` with a short timeout.
- Click argument parsing in `tests/test_cli.py`; invoke the real `main` command through `click.testing.CliRunner`.

## Fixtures and Factories

**Test Data:**
```python
def test_write_file_success(tmp_path):
    path = tmp_path / "out.txt"

    result = write_file(str(path), "hello\n")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert result["bytes_written"] == 6
    assert "error" not in result
```

**Location:**
- Test data is defined inline in each test.
- Temporary files and directories are created with pytest's `tmp_path` fixture in `tests/test_tools/test_files.py`.
- Model response transcripts are inline `mock_chat.side_effect` lists in `tests/test_loop.py`.
- Smoke prompts are production constants in `src/olla/smoke.py` and are referenced by `tests/test_smoke.py`.
- No `tests/fixtures/`, factory module, snapshot directory, golden files, or custom `conftest.py` exists.

## Coverage

**Requirements:** None enforced. `pyproject.toml` has no coverage target, pytest option, fail-under threshold, or pytest-cov dependency; no CI workflow publishes coverage.

**View Coverage:**
```bash
# Not configured: the repository has no supported coverage command.
```

- Do not claim a coverage percentage from the number of tests. Add a coverage dependency and checked-in configuration before making coverage a gate.
- Current behavioral depth is highest in `tests/test_loop.py` and `tests/test_safety.py`; the test suite validates 151 cases but does not measure line or branch coverage.

## Test Types

**Unit Tests:**
- `tests/test_parser.py` exercises parser outputs from concrete model strings.
- `tests/test_safety.py` exercises pure argv classification and regression cases.
- `tests/test_smoke.py` exercises response classification and mocks model calls in the smoke runner.
- `tests/test_tools/test_files.py` and `tests/test_tools/test_shell.py` exercise concrete boundary helpers with local resources.

**Integration Tests:**
- `tests/test_cli.py` invokes the real Click command parser with `CliRunner` while mocking downstream orchestration.
- `tests/test_loop.py` exercises multi-turn ReAct control flow with mocked external boundaries and verifies output, observations, safety decisions, confirmations, repetition guards, and tool dispatch.
- `test_run_loop_read_then_write_end_to_end()` in `tests/test_loop.py` is an orchestration integration test; it still mocks model and filesystem boundaries.
- The production `--smoke-test` flow in `src/olla/smoke.py` is a manual model integration path. Its automated tests mock `call_model()`, so the test suite does not require a running Ollama server.

**E2E Tests:**
- Not used. No test invokes the installed `olla` executable against a live Ollama model and real tool lifecycle.
- No browser, container, or cross-process E2E framework is configured.

## Common Patterns

**Async Testing:**
```python
# Not applicable: source and tests are synchronous.
```

- There are no `async def` functions, event-loop fixtures, or `pytest.mark.asyncio` markers in `src/olla/` or `tests/`.

**Error Testing:**
```python
def test_command_not_found():
    result = run_shell(["nonexistent-command-xyz"])
    assert result["argv"] == ["nonexistent-command-xyz"]
    assert "command not found" in result["error"]


def test_run_loop_confirm_eoferror_declines_safely(mocker, capsys):
    mocker.patch("olla.loop.Confirm.ask", side_effect=EOFError)
    # Invoke run_loop with a CONFIRM-tier command, then assert the tool is not called.
```

- Expected tool failures are asserted as result dictionaries containing `"error"` because production boundaries intentionally do not raise.
- Inject exceptions only when testing a caught dependency failure (`EOFError` from confirmation input).
- Use exact equality for stable structured outputs and substring assertions for human-readable errors that include dynamic paths or exception details.
- For security regressions, assert both `yes=False` and `yes=True` where bypass resistance is part of the invariant, as in `tests/test_safety.py` and `tests/test_loop.py`.
- For malformed or blocked loop actions, verify the failure becomes an `Observation:` message and execution proceeds or stops at the specified guard.

## Quality Gates

```bash
.venv/bin/python -m pytest tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

- The maintained test suite and Ruff lint check pass.
- Ruff format checking currently reports nine files requiring formatting, including `src/olla/cli.py`, `src/olla/loop.py`, `src/olla/safety.py`, and several corresponding tests.
- No `.github/workflows/`, pre-commit hook, Makefile, task runner, tox, or nox configuration enforces these commands automatically.

---

*Testing analysis: 2026-07-25*
