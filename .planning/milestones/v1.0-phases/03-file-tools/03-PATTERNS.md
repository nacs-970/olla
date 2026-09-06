# Phase 3: File Tools - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 6 (2 new, 4 modified)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/olla/tools/files.py` (new) | tool/utility | file-I/O | `src/olla/tools/shell.py` | role-match (shell is process-I/O, files is filesystem-I/O — same `ToolResult`/error-as-dict contract) |
| `tests/test_tools/test_files.py` (new) | test | file-I/O | `tests/test_tools/test_shell.py` | exact (same module shape: pure-function tool tests, no mocking) |
| `src/olla/loop.py` (modified — dispatch + confirm-gate) | controller/loop | request-response + event-driven (per-step dispatch) | itself (existing shell ALLOW/CONFIRM/BLOCK dispatch, lines 83-137) | exact — new branches are siblings of the existing shell branch |
| `src/olla/parser.py` (modified — fence-strip/`.strip()` fix) | utility/transform | transform | itself (`parse_response`, lines 10-31) | exact — same function, scoped fix |
| `src/olla/prompts.py` (modified — `SYSTEM_PROMPT`) | config/prompt | request-response (model-facing schema doc) | itself (`SYSTEM_PROMPT`, lines 3-19) | exact — additive tool-schema entries |
| `tests/test_loop.py` (modified — new dispatch/dry-run/repetition-guard tests) | test | request-response + event-driven | itself (existing CONFIRM-tier / dry-run / repetition-guard tests, lines 183-282, 384-427, 490-547) | exact — new tests mirror existing structure |
| `tests/test_parser.py` (modified — fence/newline preservation cases) | test | transform | itself (`test_markdown_fence_tolerance`, lines 16-19) | exact — same test module, new cases for write_file content |

## Pattern Assignments

### `src/olla/tools/files.py` (new tool module, file-I/O)

**Analog:** `src/olla/tools/shell.py` (full file, 29 lines) + `src/olla/tools/base.py` (full file, 18 lines)

**Imports pattern** (`shell.py` lines 1-5):
```python
"""Shell tool: subprocess.run(shell=False) over a pre-parsed argv."""

import subprocess

from olla.tools.base import ToolResult
```
For `files.py`, mirror this exactly but import `pathlib.Path` instead of `subprocess`:
```python
"""File tools: read/write text files via pathlib, errors-as-dict per ToolResult."""

from pathlib import Path

from olla.tools.base import ToolResult
```

**`ToolResult` contract** (`base.py` lines 6-17, full):
```python
class ToolResult(TypedDict, total=False):
    """Shape returned by every tool implementation (shell, and future file tools).

    `total=False` allows partial dicts — e.g. error-only results from
    FileNotFoundError/timeout cases that omit stdout/stderr.
    """

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    error: str
```
**Action required:** Add new optional fields (`content: str`, `bytes_written: int`, `path: str`) to this `TypedDict` — `total=False` makes this additive/non-breaking. Do not create a separate `FileToolResult` type unless the planner decides the dict shapes diverge enough to warrant it; the existing single shared contract is the established convention (one `ToolResult` for "every tool implementation").

**Core pattern — function signature + docstring + error-as-dict** (`shell.py` lines 8-28, full):
```python
def run_shell(argv: list[str], timeout: int = 30) -> ToolResult:
    """Run a shell command safely via subprocess.run(shell=False).

    `argv` must already be parsed (e.g. via shlex.split() by the caller).
    Returns a ToolResult dict. On success: argv, returncode, stdout, stderr.
    On FileNotFoundError or timeout: argv plus an `error` message.
    """
    if not argv:
        return {"argv": argv, "error": "empty command"}
    try:
        result = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout)
        return {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError:
        return {"argv": argv, "error": f"command not found: {argv[0]}"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "error": f"command timed out after {timeout}s"}
```

**Apply this exact shape to `read_file`/`write_file`** — guard clause first (empty-input check analog), `try` wrapping the I/O call, multiple `except` clauses each returning a one-line `{"error": "..."}` dict with a human-readable prefix (`"command not found: ..."` -> `"file not found: ..."`, `"command timed out after..."` -> `"permission denied: ..."`, etc.). RESEARCH.md's Code Examples section already has the exact target implementation for both functions (`read_file` using `p.read_text(encoding="utf-8")` with `FileNotFoundError`/`IsADirectoryError`/`PermissionError`/`UnicodeDecodeError`; `write_file` using `p.write_text(content, encoding="utf-8")` with `FileNotFoundError`/`IsADirectoryError`/`PermissionError`) — that code is the analog-derived target, not a deviation from `shell.py`'s pattern.

**Error handling pattern:** every branch returns a dict, never raises — identical to `shell.py`. No new exception types, no custom error hierarchy (per RESEARCH.md "Don't Hand-Roll").

---

### `tests/test_tools/test_files.py` (new test file, file-I/O)

**Analog:** `tests/test_tools/test_shell.py` (full file, 49 lines)

**Imports + structure pattern** (lines 1-3):
```python
"""Tests for olla.tools.shell.run_shell."""

from olla.tools.shell import run_shell
```
Mirror as:
```python
"""Tests for olla.tools.files.read_file and write_file."""

from olla.tools.files import read_file, write_file
```

**Test pattern — plain function calls, dict-key assertions, no mocking** (lines 6-23):
```python
def test_echo_success():
    result = run_shell(["echo", "hello"])
    assert result["argv"] == ["echo", "hello"]
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]
    assert result["stderr"] == ""


def test_command_not_found():
    result = run_shell(["nonexistent-command-xyz"])
    assert result["argv"] == ["nonexistent-command-xyz"]
    assert "command not found" in result["error"]
```

For `test_files.py`, use pytest's built-in `tmp_path` fixture (stdlib pytest, no new fixture needed per RESEARCH.md Wave 0 Gaps) instead of relying on real binaries on `$PATH`:
```python
def test_read_file_success(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world", encoding="utf-8")

    result = read_file(str(f))

    assert result["content"] == "hello world"


def test_read_file_not_found(tmp_path):
    missing = tmp_path / "nope.txt"

    result = read_file(str(missing))

    assert "file not found" in result["error"]


def test_write_file_success(tmp_path):
    target = tmp_path / "out.txt"

    result = write_file(str(target), "new content\n")

    assert target.read_text(encoding="utf-8") == "new content\n"
    assert result["bytes_written"] == len("new content\n".encode("utf-8"))
    assert result["path"] == str(target.resolve())
```

**Empty/error-case style** (`test_shell.py` lines 40-43, the "trivial input -> error dict" shape):
```python
def test_empty_argv_errors():
    result = run_shell([])
    assert result["argv"] == []
    assert "empty command" in result["error"]
```
Mirror for `write_file` parent-directory-missing case:
```python
def test_write_file_missing_parent_dir_errors(tmp_path):
    target = tmp_path / "nonexistent_dir" / "out.txt"

    result = write_file(str(target), "content")

    assert "parent directory does not exist" in result["error"]
```

---

### `src/olla/loop.py` (modified — dispatch branches + confirm-gate)

**Analog:** itself — the existing shell ALLOW/CONFIRM/BLOCK dispatch (lines 83-137) and the `--dry-run` branch (lines 37-68)

**Current imports** (lines 1-12, full):
```python
"""ReAct loop step execution."""

import shlex

import ollama
from rich.prompt import Confirm

from olla.parser import parse_response
from olla.safety import check
from olla.tools.shell import run_shell

MAX_OBSERVATION_CHARS = 2000
```
Add: `from pathlib import Path` and `from olla.tools.files import read_file, write_file`.

**Truncation helper to reuse as-is** (lines 15-21, full — do not modify):
```python
def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    """Truncate text to a head+tail preview if it exceeds `limit` chars."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2):]
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"
```
`read_file` dispatch calls `truncate_output(content_or_error)` exactly like the shell branch calls `truncate_output(combined)` (line 134).

**Current "unknown tool" gate — Pitfall 2 site #1, normal loop** (lines 83-88):
```python
        if parsed["type"] == "tool":
            if parsed["tool"] != "shell":
                preview = f"unknown tool '{parsed['tool']}'"
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
```
**Pitfall 2 site #2, `--dry-run` branch** (lines 49-51):
```python
        if parsed["tool"] != "shell":
            print(f"Model would call unknown tool '{parsed['tool']}'")
            return
```
**Both must change** from `!= "shell"` equality checks to an `if/elif/else` (or dispatch dict) that recognizes `"shell"`, `"read_file"`, `"write_file"`, with `else` retaining the "unknown tool" observation/preview for anything else.

**Repetition-guard signature — Pitfall 3 site** (lines 97-106):
```python
            sig = ("shell", tuple(argv))
            if sig == prev_sig:
                repeat_count += 1
            else:
                prev_sig = sig
                repeat_count = 1

            if repeat_count >= 3:
                print("olla stopped: same shell call repeated 3x — model likely stuck")
                return
```
Generalize to `sig = (parsed["tool"], parsed["args_raw"])` (or a tool-specific normalized form) computed once per step **before** branching into shell/read_file/write_file-specific logic, so all three tools share the same repetition-guard check. The guard message should likely become tool-name-aware (e.g. `f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck"`), but verify against RESEARCH.md's test map (`test_run_loop_repetition_guard_covers_file_tools`) for exact expected wording.

**`read_file` dispatch — Pattern 2 from RESEARCH.md, mirrors the shell ALLOW-tier's "no confirm, truncate, print, append Observation" shape** (lines 125-137 as the structural analog):
```python
            print(f"Step {step}: running {argv}...")

            result = run_shell(argv)
            if "error" in result:
                combined = result["error"]
            else:
                combined = result.get("stdout", "") + result.get("stderr", "")
                if not combined:
                    combined = "(no output)"
            preview = truncate_output(combined)
            print(preview)
            messages.append({"role": "user", "content": f"Observation: {preview}"})
            continue
```
New `read_file` branch follows the same `result = tool(...)` -> `"error" in result` check -> `truncate_output` -> `print` -> append `Observation:` -> `continue` shape (RESEARCH.md Pattern 2 gives the exact target code).

**`write_file` confirm-gate — Pattern 3 from RESEARCH.md, mirrors the shell CONFIRM-tier exactly** (lines 116-123, full):
```python
            if decision["kind"] == "CONFIRM" and not yes:
                try:
                    approved = Confirm.ask(f"Run `{' '.join(argv)}`?", default=False)
                except EOFError:
                    approved = False
                if not approved:
                    messages.append({"role": "user", "content": "Observation: declined by user"})
                    continue
```
`write_file` reuses this `if not yes: try/except EOFError -> approved` shape verbatim, but **always** (no `decision["kind"]` check — `safety.check()` is never called), with the prompt text showing `Path(path_str).resolve()` (per Pitfall 4, display-only) — RESEARCH.md Pattern 3 has the exact target code.

**Step-print pattern to mirror** (line 125): `print(f"Step {step}: running {argv}...")` — for file tools use an analogous one-liner, e.g. `print(f"Step {step}: reading {path}...")` / `print(f"Step {step}: writing to {resolved}...")`, keeping the `Step N: <verb> <target>...` shape consistent across all three tools.

---

### `src/olla/parser.py` (modified — Pitfall 1 fence/`.strip()` fix)

**Analog:** itself, `parse_response` (full file, 32 lines)

**Current implementation** (lines 10-31, full):
```python
def parse_response(content: str) -> dict:
    """Tolerantly extract <tool>/<args>/<final> from model output.

    Strips markdown code fences, then prefers <final> if present, else a
    complete <tool>+<args> pair, else returns the original raw content.
    """
    stripped = re.sub(r"```[a-zA-Z]*\n?|```", "", content)

    final_match = FINAL_RE.search(stripped)
    if final_match:
        return {"type": "final", "text": final_match.group(1).strip()}

    tool_match = TOOL_RE.search(stripped)
    args_match = ARGS_RE.search(stripped)
    if tool_match and args_match:
        return {
            "type": "tool",
            "tool": tool_match.group(1).strip(),
            "args_raw": args_match.group(1).strip(),
        }

    return {"type": "none", "raw": content}
```

**Regex constants to preserve** (lines 5-7, full — do not change these patterns themselves):
```python
FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_RE = re.compile(r"<tool>(.*?)(?:</tool>|$)", re.DOTALL | re.IGNORECASE)
ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)
```

**What must change (Pitfall 1):**
1. Line 16's `re.sub(r"```[a-zA-Z]*\n?|```", "", content)` runs on the **entire** `content` before `ARGS_RE` extracts `args_raw` — this deletes legitimate fence lines from `write_file` content. Per RESEARCH.md Pitfall 1, either (a) restructure to a targeted leading/trailing-fence unwrap applied once at the boundary (not a global `re.sub`), or (b) extract `args_raw` for `write_file` from the *original* `content` (pre-`re.sub`) and only fence-strip the tool-name/path portion.
2. Line 28's `args_match.group(1).strip()` must **not** be applied to `write_file`'s file-content portion — only the first-line path should be `.strip()`'d (per Pattern 1: `path, _, file_content = args_raw.partition("\n")`, where `path` may be stripped but `file_content` must be preserved verbatim, including trailing newline).

**Constraint:** `test_markdown_fence_tolerance` (existing, `tests/test_parser.py` lines 16-19) and `test_tool_and_args` (lines 11-13) must continue passing — the fix must be scoped/conditional, not a removal of fence-tolerance for `shell`/non-write_file tools.

---

### `src/olla/prompts.py` (modified — `SYSTEM_PROMPT`)

**Analog:** itself, `SYSTEM_PROMPT` (full file, 19 lines)

**Current structure** (lines 3-19, full):
```python
SYSTEM_PROMPT = """You are a helpful assistant that completes tasks using tools.

You have one tool available: `shell`. To run it, respond with:
<tool>shell</tool><args>the raw shell command to run</args>

When you have the final answer for the user, respond with:
<final>your answer text here</final>

Only output one tag block per turn. Do not explain your reasoning outside the tags.

Example:
<tool>shell</tool><args>ls -la /tmp</args>
Observation: total 0
drwxrwxrwt 2 root root 40 Jan 1 00:00 .

<final>The /tmp directory is empty.</final>
"""
```

**Pattern to follow:** Same triple-quoted module-level string constant, same terse "tool name -> tag-shape" enumeration style, one example block per tool. Add `read_file`/`write_file` entries following the "You have one tool available: `shell`..." -> "You have N tools available: ..." pluralization, each with its own `<tool>X</tool><args>...</args>` shape line. RESEARCH.md's Code Examples section provides an illustrative extended version (including the path-on-first-line encoding rule and the `</args>`-in-content caveat from Pitfall 5) — planner should tune wording for token budget (project's core value: minimal per-turn overhead for 0.6B-4B models) but must preserve: (1) the encoding rule stated explicitly with an example, (2) the `</args>` caveat as a one-line warning.

---

### `tests/test_loop.py` (modified — new dispatch/dry-run/repetition-guard tests)

**Analog:** itself — existing CONFIRM-tier tests (lines 222-282), dry-run tests (lines 384-427), repetition-guard tests (lines 490-547)

**Mocking/structure pattern — CONFIRM approved/declined/`--yes`/EOFError, full quartet** (lines 222-296):
```python
def test_run_loop_confirm_approved_runs_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["git", "status"], "returncode": 0, "stdout": "clean\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "clean\n" in captured.out
    mock_confirm.assert_called_once()
    mock_run_shell.assert_called_once()


def test_run_loop_confirm_declined_does_not_run_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=False)

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys")

    mock_confirm.assert_called_once()
    mock_run_shell.assert_not_called()
    assert mock_chat.call_count == 2

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: declined by user"


def test_run_loop_confirm_tier_with_yes_skips_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["git", "status"], "returncode": 0, "stdout": "clean\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    mock_confirm.assert_not_called()
    mock_run_shell.assert_called_once()
```

**For `write_file` tests, mirror this exact triplet** (`test_run_loop_write_file_confirm_approved`, `test_run_loop_write_file_confirm_declined`, `test_run_loop_write_file_yes_skips_prompt` from RESEARCH.md's test map), patching `mocker.patch("olla.loop.Confirm.ask", return_value=True/False)` and either using `tmp_path` for real I/O or `mocker.patch("olla.tools.files.write_file", ...)` — RESEARCH.md leaves this choice to the planner. For `test_run_loop_write_file_shows_resolved_path`, assert on the string passed to `Confirm.ask` (`mock_confirm.call_args`) containing the resolved path.

**ALLOW-tier (no-prompt) pattern for `read_file`** (lines 183-198, full):
```python
def test_run_loop_allow_tier_no_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="list files", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "file1\n" in captured.out
    mock_confirm.assert_not_called()
    mock_run_shell.assert_called_once()
```
`read_file` tests mirror this: `mock_confirm.assert_not_called()` is the key assertion that read_file never prompts.

**Dry-run pattern** (lines 414-427, "unknown tool" dry-run case — closest analog before the fix, and the regression this fix must avoid):
```python
def test_dry_run_unknown_tool_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>browse</tool><args>https://example.com</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="browse the web", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Model would call unknown tool 'browse'" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()
```
New `test_dry_run_previews_read_file`/`test_dry_run_previews_write_file` follow the same `mock_chat.return_value` (single response) + `mock_chat.call_count == 1` + `mock_confirm.assert_not_called()` shape, but assert on the new preview text (e.g. "Step 1 would read: ..." / "Step 1 would write to ... — would prompt for confirmation").

**Repetition-guard pattern** (lines 490-505, full):
```python
def test_run_loop_repetition_guard_aborts_before_third_call(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""}

    run_loop(task="list files repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same shell call repeated 3x — model likely stuck" in captured.out
    assert mock_run_shell.call_count == 2
    assert mock_chat.call_count == 3
```
`test_run_loop_repetition_guard_covers_file_tools` mirrors this with three identical `<tool>read_file</tool><args>/tmp/x</args>` (or `write_file`) responses, asserting the same `"...repeated 3x..."` message (tool-name-aware if the message format changes) and that the tool's underlying function is called only twice before the guard fires.

**Note on the "unknown tool" test that currently uses `write_file`:** `test_run_loop_unknown_tool_returns_observation` (lines 79-97) currently uses `<tool>write_file</tool><args>foo.txt</args>` as its "unknown tool" example — **this test will break once `write_file` is recognized**. The planner must either repurpose this test to use a genuinely unknown tool name (e.g. `browse`, matching the dry-run analog at line 416) or remove/rewrite it; this is a required, not incidental, change once Pitfall 2 is fixed.

---

### `tests/test_parser.py` (modified — fence/newline preservation cases for Pitfall 1)

**Analog:** itself, `test_markdown_fence_tolerance` (lines 16-19, full) and `test_tool_and_args` (lines 11-13, full)

**Existing fence-tolerance test (must keep passing)** (lines 16-19):
```python
def test_markdown_fence_tolerance():
    content = "```\n<tool>shell</tool><args>echo hi</args>\n```"
    result = parse_response(content)
    assert result == {"type": "tool", "tool": "shell", "args_raw": "echo hi"}
```

**New cases mirror this exact `parse_response(content)` -> dict-equality shape**, e.g.:
```python
def test_write_file_args_preserve_interior_fences():
    content = (
        "<tool>write_file</tool><args>/tmp/README.md\n"
        "# Title\n"
        "```python\n"
        'print("hi")\n'
        "```\n"
        "</args>"
    )
    result = parse_response(content)
    assert result["tool"] == "write_file"
    path, _, file_content = result["args_raw"].partition("\n")
    assert path == "/tmp/README.md"
    assert "```python" in file_content
    assert "```" in file_content.rstrip("\n").rsplit("\n", 1)[-1] or file_content.count("```") == 2


def test_write_file_args_preserve_trailing_newline():
    content = "<tool>write_file</tool><args>/tmp/notes.txt\nline one\nline two\n</args>"
    result = parse_response(content)
    path, _, file_content = result["args_raw"].partition("\n")
    assert path == "/tmp/notes.txt"
    assert file_content.endswith("\n")
```
RESEARCH.md's test map names this `test_write_file_args_preserve_fences_and_newline` (singular test) — planner may combine into one parametrized test or keep separate; either follows the existing module's flat-function, no-fixtures style (no `tmp_path`/`mocker` needed for parser tests — `parse_response` is a pure function, per `tests/test_parser.py`'s current zero-fixture style across all 7 existing tests).

---

## Shared Patterns

### `ToolResult` error-as-dict contract
**Source:** `src/olla/tools/base.py` (full, 18 lines) and `src/olla/tools/shell.py` lines 25-28
**Apply to:** `src/olla/tools/files.py` (`read_file`, `write_file`)
```python
class ToolResult(TypedDict, total=False):
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    error: str
```
Every error path returns `{"error": "<human-readable message>"}` (or `{"argv": ..., "error": ...}` for shell) — never raises. Extend with `content`, `bytes_written`, `path` fields (all optional via `total=False`).

### Confirm-gate mechanism (`Confirm.ask` + `--yes` + EOFError-as-decline)
**Source:** `src/olla/loop.py` lines 116-123
**Apply to:** `write_file` dispatch in `run_loop`
```python
if not yes:
    try:
        approved = Confirm.ask(f"Run `{' '.join(argv)}`?", default=False)
    except EOFError:
        approved = False
    if not approved:
        messages.append({"role": "user", "content": "Observation: declined by user"})
        continue
```
For `write_file`: same shape, prompt text `f"Write to \`{resolved}\`?"`, **no `decision["kind"]` check** — always prompts (unless `--yes`).

### Output truncation (`truncate_output`)
**Source:** `src/olla/loop.py` lines 15-21 (full function, reproduced above)
**Apply to:** `read_file` dispatch — `preview = truncate_output(content_or_error)` before printing/appending to `messages`, exactly as the shell branch does for `combined` (stdout+stderr).

### Per-step `Observation:` message-append pattern
**Source:** `src/olla/loop.py` lines 134-136 (and repeated at lines 86-87, 112-113, 121-122)
**Apply to:** All new dispatch branches (`read_file`, `write_file`, unknown-tool fallback)
```python
preview = truncate_output(combined)
print(preview)
messages.append({"role": "user", "content": f"Observation: {preview}"})
continue
```
Every terminal branch of the per-step dispatch follows `print(preview)` then `messages.append({"role": "user", "content": f"Observation: {preview}"})` then `continue` — new branches must follow this exactly so `history_content`/Observation-pairing invariants (verified by tests like `test_run_loop_tool_then_final`, lines 70-76) hold.

### `parse_response` dict-shape contract
**Source:** `src/olla/parser.py` lines 24-29
**Apply to:** No change to the `{"type": "tool", "tool": ..., "args_raw": ...}` shape itself — `write_file`'s two "arguments" remain encoded inside the single `args_raw` string (Pattern 1, `partition("\n")`). Do not add new dict keys (e.g. `"path"`/`"content"`) to `parse_response`'s return value — the path/content split happens in `loop.py` (or `tools/files.py`), per RESEARCH.md Pattern 1.

## No Analog Found

None — every file in scope has an exact or near-exact analog within the existing codebase (Phase 1/2 already established the shell tool, `ToolResult`, `Confirm.ask`/`--yes`/EOFError, `truncate_output`, and the parser/test conventions that Phase 3 extends). RESEARCH.md's Code Examples section supplies the target implementation where the analog needs adaptation rather than direct copying (notably `tools/files.py`'s function bodies and the extended `SYSTEM_PROMPT`).

## Metadata

**Analog search scope:** `src/olla/` (all modules), `tests/` (all test modules), `.planning/phases/03-file-tools/03-RESEARCH.md`
**Files scanned:** `loop.py`, `parser.py`, `prompts.py`, `safety.py` (referenced, not modified), `tools/base.py`, `tools/shell.py`, `tools/__init__.py`, `tests/test_loop.py`, `tests/test_parser.py`, `tests/test_tools/test_shell.py`
**Pattern extraction date:** 2026-06-14
