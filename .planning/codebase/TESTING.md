# Testing Patterns

**Analysis Date:** 2026-09-14

## Test Framework

**Runner:**
- `pytest` >= 8 (`pyproject.toml:25`, dev-only dependency group `[project.optional-dependencies].dev`)
- Config: `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]` (`pyproject.toml:33-34`). No `conftest.py` exists anywhere in the repo — all fixtures are either pytest built-ins (`tmp_path`, `capsys`, `monkeypatch`) or the `pytest-mock` `mocker` fixture; no shared custom fixtures.

**Assertion Library:**
- Plain `assert` statements (pytest's rewritten assert, no separate assertion library like `hamcrest`).

**Run Commands:**
```bash
pytest                          # Run all tests (testpaths=tests)
pytest tests/test_loop.py       # Run a single module
pytest -k test_name             # Run tests matching a substring
pytest -x                       # Stop on first failure
```
No coverage tool (`pytest-cov` etc.) is configured — coverage is not measured or enforced.

## Test File Organization

**Location:**
- Fully separate `tests/` directory (not co-located with source), mirroring `src/olla/` structure 1:1: `tests/test_loop.py` <-> `src/olla/loop.py`, `tests/test_tools/test_shell.py` <-> `src/olla/tools/shell.py`.
- `tests/test_tools/` subpackage mirrors `src/olla/tools/` subpackage exactly, including an empty `tests/test_tools/__init__.py` matching `src/olla/tools/__init__.py`.

**Naming:**
- Test files: `test_<module_name>.py`.
- Test functions: `test_<behavior_under_test>()`, written as a full sentence describing the scenario and expected outcome, e.g. `test_env_wrapping_blocked_command_blocks`, `test_run_loop_handles_ollama_client_errors`, `test_fork_bomb_as_echo_data_allows` (`tests/test_safety.py`). Names encode the input shape and the expected verdict — follow this "condition_then_outcome" naming style for new tests.

**Structure:**
```
tests/
├── __init__.py
├── test_cli.py            # click.testing.CliRunner-based CLI wiring tests
├── test_config.py
├── test_debug.py
├── test_loop.py           # largest file (2913 lines) — ReAct loop orchestration
├── test_parser.py         # pure-function tag parsing tests
├── test_prompts.py
├── test_providers.py
├── test_safety.py         # pure-function blocklist/allowlist decision tests
├── test_smoke.py
└── test_tools/
    ├── __init__.py
    ├── test_files.py      # largest tools file (784 lines) — atomic write/race safety
    ├── test_inspect.py
    ├── test_memory.py
    ├── test_shell.py
    └── test_web.py
```

## Test Structure

**Suite Organization:**
Tests are flat functions grouped by file, not `class Test...` blocks — no test classes are used anywhere in the suite. Related scenarios are grouped by proximity/section comments within a file rather than by class.

```python
# tests/test_safety.py — representative pure-function test style
def test_env_wrapping_blocked_command_blocks():
    decision = check(["env", "rm", "-rf", "/"], yes=False)
    assert decision["kind"] == "BLOCK"
    assert "'env' wraps a blocked command" in decision["reason"]
```

**Patterns:**
- No setup/teardown methods (`setup_method`/`yield`-fixtures) — each test is self-contained; state needed is built inline or via `pytest-mock`'s `mocker`/stdlib `tmp_path`.
- `@pytest.mark.parametrize` is used heavily for input/output matrices, including stacked (multiple) parametrize decorators on a single test to cross-product two independent variables:
```python
@pytest.mark.parametrize(
    "error",
    [ollama.RequestError("daemon failed\x1b[31m"), ollama.ResponseError("daemon failed\x1b[31m", 500)],
    ids=["request-error", "response-error"],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["normal", "dry-run"])
def test_run_loop_handles_ollama_client_errors(mocker, capsys, error, dry_run):
    ...
```
(`tests/test_loop.py:74-99`) — always supply explicit `ids=` for parametrize cases when the raw values wouldn't be self-explanatory in test output.
- Assertions favor substring/`in` checks over full equality when testing free-text output (`assert "sudo" in decision["reason"]`, `assert "hello" in result["stdout"]`), reserving exact `==` for structured values (dict keys, argv lists, counts).

## Mocking

**Framework:** `pytest-mock` (`mocker` fixture) is the standard mocking mechanism — `unittest.mock` is imported directly only inside production code (`src/olla/loop.py:10`, `_is_mocked` helper), not in tests.

**Patterns:**
```python
# Mocking the LLM call boundary (tests/test_loop.py:58-71)
def test_call_model(mocker):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<final>42</final>"}}
    result = call_model("test-model", messages)
    mock_chat.assert_called_once_with(model="test-model", messages=messages, ...)

# Mocking a multi-turn conversation via side_effect list (tests/test_loop.py:139-145)
mock_chat.side_effect = [
    {"message": {"content": "<tool>shell</tool><args>echo hi</args>"}},
    {"message": {"content": "<final>done</final>"}},
]

# Mocking an httpx client chain (tests/test_tools/test_web.py:72-99)
mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
client_instance = mock_client_cls.return_value.__enter__.return_value
stream_cm = client_instance.stream.return_value
stream_cm.__enter__.return_value.iter_bytes.return_value = [html]

# Mocking config at the CLI boundary via monkeypatch, applied autouse (tests/test_cli.py:10-12)
@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    monkeypatch.setattr("olla.cli.load_config", lambda *a, **kw: {})
```
- Always patch at the point of use (`olla.loop.ollama.chat`, `olla.tools.web.httpx.Client`, `olla.cli.run_loop`), not at the source module — matches how `unittest.mock.patch`/`mocker.patch` resolve import bindings.
- `_is_mocked()` in `src/olla/loop.py:214-216` is a production-code affordance that detects `unittest.mock.Mock` instances at runtime, letting `call_model`/`_stream_model_turn` fall back to the simple non-streaming path when the model client is mocked in tests — be aware of this when writing new tests against streaming code paths.

**What to Mock:**
- External process/network boundaries: `ollama.chat`, `httpx.Client`, `run_shell` (when testing `loop.py` orchestration, not `shell.py` itself), `subprocess.run` equivalents.
- CLI-level collaborators when testing `cli.py` wiring (`run_loop`, `load_config`) so tests assert on call arguments, not on the loop's actual behavior.

**What NOT to Mock:**
- Pure functions are tested directly with real inputs/outputs, never mocked: `check()` (safety), `parse_response()` (parser), `truncate_output()`, `_terminal_safe()`.
- Real filesystem operations in `tools/files.py` and `tools/shell.py` are exercised against the real OS via `tmp_path`/real subprocess calls (`echo`, `false`, `sleep`, `python3 -c ...`) rather than mocked — these tools are POSIX-primitive-heavy (fcntl locks, dir_fd, O_NOFOLLOW) and the test suite deliberately verifies real kernel behavior instead of mocking `os`/`fcntl`.

## Fixtures and Factories

**Test Data:**
- No fixture/factory library or `tests/fixtures/` directory. Sample data (HTML documents, model responses, argv lists) is defined as module-level constants or inline literals close to the tests that use them:
```python
# tests/test_tools/test_web.py:14-30
_SAMPLE_HTML = """
<html>...
"""
```
- Temporary files/directories use pytest's built-in `tmp_path` fixture directly (`tests/test_tools/test_shell.py:46-51`, `tests/test_tools/test_files.py`) rather than a custom fixture wrapper.

**Location:** Inline within the test file that consumes the data; no separate fixtures module exists.

## Coverage

**Requirements:** None enforced — no `pytest-cov`, no coverage config, no CI coverage gate detected in the repo.

**View Coverage:**
Not applicable — no coverage tooling installed. To add ad hoc coverage: `pip install pytest-cov && pytest --cov=olla`.

## Test Types

**Unit Tests:**
- The overwhelming majority of the suite: pure-function tests for `safety.check`, `parser.parse_response`, `debug.mask_secret`; isolated-boundary tests for `loop.py` internals with `ollama.chat`/`run_shell` mocked out.

**Integration Tests:**
- `tests/test_loop.py` exercises `run_loop()` end-to-end (multi-step ReAct loop, real `_prepare_action`/`_execute_*` dispatch) with only the outermost model call and/or shell execution mocked — this is the closest thing to an integration test and is the largest test file in the repo (2913 lines).
- `tests/test_tools/test_files.py` and `tests/test_tools/test_shell.py` integration-test against the real filesystem/subprocess layer (no mocking of `os`, `fcntl`, or `subprocess`).
- `tests/test_cli.py` uses `click.testing.CliRunner` to integration-test argument parsing -> `run_loop` invocation, with `run_loop` itself mocked so only the CLI wiring is under test.

**E2E Tests:**
- `src/olla/smoke.py` + `tests/test_smoke.py` provide a format-compliance smoke test (`olla --smoke-test --model <model>`) that talks to a real local Ollama model to verify it can produce well-formed `<tool>/<args>`/`<final>` output — this is the project's closest equivalent to an E2E test, but it is a manual/opt-in CLI flag, not part of the automated `pytest` suite (requires a live Ollama daemon).

## Common Patterns

**Async Testing:**
Not applicable — the entire codebase is synchronous (sync `ollama.chat`, sync `httpx.Client`, sequential ReAct loop per `STACK.md`/project design). No `pytest-asyncio` or `async def` tests exist.

**Error Testing:**
```python
# Asserting a raised exception with message match (tests/test_loop.py:53-55)
def test_truncate_output_rejects_negative_limit():
    with pytest.raises(ValueError, match="limit must be non-negative"):
        truncate_output("text", limit=-1)

# Asserting an error surfaced through the "errors as data" ToolResult contract
# (tests/test_tools/test_shell.py:20-23)
def test_command_not_found():
    result = run_shell(["nonexistent-command-xyz"])
    assert "command not found" in result["error"]
```
- When testing user-facing error output from the loop, capture stdout with `capsys` and assert on the rendered (terminal-safe-escaped) text, e.g. verifying `\x1b` control bytes were escaped to `\\x1b[31m` (`tests/test_loop.py:83-99`).

---

*Testing analysis: 2026-09-14*
