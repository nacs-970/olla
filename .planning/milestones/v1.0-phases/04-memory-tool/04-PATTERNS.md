# Phase 4: Memory Tool - Pattern Map

**Mapped:** 2026-07-25
**Files analyzed:** 8 new/modified files
**Analogs found:** 8 / 8

> **Working-tree note:** `src/olla/loop.py`, `src/olla/prompts.py`, and
> `tests/test_loop.py` are currently modified. The excerpts below intentionally
> describe the live working tree that Phase 4 must preserve and extend.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/olla/tools/memory.py` | service / tool adapter | CRUD | `src/olla/tools/files.py` | role-match |
| `src/olla/parser.py` | utility / protocol parser | transform | `src/olla/parser.py` (`write_file` branch) | exact |
| `src/olla/loop.py` | controller / orchestrator | request-response | `src/olla/loop.py` (`read_file` dispatch) | exact |
| `src/olla/prompts.py` | config / protocol contract | transform | `src/olla/prompts.py` | exact |
| `tests/test_tools/test_memory.py` | test | CRUD | `tests/test_tools/test_files.py` | role-match |
| `tests/test_parser.py` | test | transform | `tests/test_parser.py` (`write_file` preservation tests) | exact |
| `tests/test_loop.py` | test | request-response | `tests/test_loop.py` (mocked tool flows) | exact |
| `tests/test_prompts.py` | test | transform | `tests/test_parser.py` (direct contract assertions) | role-match |

## Pattern Assignments

### `src/olla/tools/memory.py` (service / tool adapter, CRUD)

**Analog:** `src/olla/tools/files.py`

This is the closest adapter-shape match, but not an exact state-management
match. Copy the import/result/error conventions from the live adapter and use
the projected-state algorithm from `04-RESEARCH.md` for the novel bounded-store
logic.

**Imports and shared result contract** (`src/olla/tools/files.py` lines 1-5):

```python
"""File tools: read_file/write_file read and write UTF-8 text files via pathlib."""

from pathlib import Path

from olla.tools.base import ToolResult
```

For memory, replace the `pathlib` import with the standard-library types used
by the chosen call representation, but retain the absolute
`olla.tools.base` import.

**Non-raising adapter pattern** (`src/olla/tools/files.py` lines 8-23):

```python
def read_file(path: str) -> ToolResult:
    """Read a file's contents as UTF-8 text.

    Returns a ToolResult dict. On success: path, content.
    On error (not found, is a directory, not readable as text): path plus
    an `error` message. Never raises.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
        return {"path": path, "content": content}
    except FileNotFoundError:
        return {"path": path, "error": f"file not found: {path}"}
    except IsADirectoryError:
        return {"path": path, "error": f"is a directory: {path}"}
    except (UnicodeDecodeError, OSError, ValueError) as e:
        return {"path": path, "error": f"could not read {path}: {e}"}
```

Apply the same “return data or recoverable error; never raise for expected
input/state failures” contract. Successful acknowledgments and recalls belong
in `content`; malformed calls, missing keys, and limit failures belong in
`error`.

**Phase-specific bounded replacement pattern**
(`.planning/phases/04-memory-tool/04-RESEARCH.md` lines 242-265):

```python
class Scratchpad:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def remember(self, call: RememberCall) -> dict[str, str]:
        is_new = call.key not in self._values
        old_size = 0 if is_new else len(self._values[call.key])
        projected = sum(len(value) for value in self._values.values())
        projected = projected - old_size + len(call.value)

        if is_new and len(self._values) >= MAX_KEYS:
            return {"error": "memory key limit reached: maximum is 32"}
        if projected > MAX_TOTAL_CHARS:
            return {
                "error": (
                    "memory capacity exceeded: "
                    f"write would use {projected} of 16000 characters"
                )
            }

        self._values[call.key] = call.value
        if call.value == "":
            return {"content": f"remembered empty: {call.key}"}
        return {"content": f"remembered: {call.key}"}
```

Use `ToolResult` as the return annotation. Validate the per-value limit before
the key-count and projected-total checks. Perform the single dictionary
assignment only after every check passes.

**Validation pattern:** parse `remember` with `partition("\n")`, check the
separator independently of `value == ""`, strip only the key, and preserve the
remainder exactly. Parse `recall` by stripping one raw key. The validation
precedence is empty key, missing value line, value size, new-key limit, total
capacity.

**Auth/guard pattern:** none. This adapter must not import or call
`olla.safety.check` or `Confirm`; invocation-local memory has no host side
effect.

---

### `src/olla/parser.py` (utility / protocol parser, transform)

**Analog:** the existing `write_file` preservation branch in
`src/olla/parser.py`

**Imports pattern** (`src/olla/parser.py` lines 1-7):

```python
"""Tolerant XML-tag parser for <tool>/<args>/<final> model output."""

import re

FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_RE = re.compile(r"<tool>(.*?)(?:</tool>|$)", re.DOTALL | re.IGNORECASE)
ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)
```

No new parser dependency is required.

**Raw-payload preservation pattern** (`src/olla/parser.py` lines 21-32):

```python
raw_tool_match = TOOL_RE.search(content)
raw_args_match = ARGS_RE.search(content)
if (
    raw_tool_match
    and raw_args_match
    and raw_tool_match.group(1).strip() == "write_file"
):
    return {
        "type": "tool",
        "tool": "write_file",
        "args_raw": raw_args_match.group(1),
    }
```

Extend this preservation seam to `remember`. The tool name is normalized, but
`raw_args_match.group(1)` must pass through untouched. Do not route `remember`
through the ordinary stripping path.

**Ordinary transform and fallback pattern** (`src/olla/parser.py` lines 34-49):

```python
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

Keep `recall` on this ordinary path: its one raw key is intentionally trimmed.
Retain the tolerant `none` fallback and final-over-tool precedence.

**Error handling pattern:** parsing does not raise or manufacture
tool-specific validation errors. It returns a normalized parse dictionary;
`memory.py` validates memory micro-formats.

---

### `src/olla/loop.py` (controller / orchestrator, request-response)

**Analog:** the existing `read_file` dispatch in `src/olla/loop.py`

**Imports pattern** (`src/olla/loop.py` lines 3-12):

```python
import shlex
from pathlib import Path

import ollama
from rich.prompt import Confirm

from olla.parser import parse_response
from olla.safety import check
from olla.tools.files import read_file, write_file
from olla.tools.shell import run_shell
```

Add memory imports alongside the other `olla.tools` imports. Keep orchestration
dependencies in the loop and storage invariants in `tools/memory.py`.

**Invocation-local state pattern** (`src/olla/loop.py` lines 32-37):

```python
def run_loop(task: str, model: str, max_steps: int, system_prompt: str, yes: bool = False, dry_run: bool = False) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
```

Construct exactly one `Scratchpad()` in this function body beside the existing
invocation-local state. Never create it at module scope or in CLI state.

**Dry-run parse/preview/return pattern** (`src/olla/loop.py` lines 39-49):

```python
if dry_run:
    content = call_model(model, messages)
    parsed = parse_response(content)

    if parsed["type"] == "final":
        print(f"Model would answer directly: {parsed['text']}")
        return

    if parsed["type"] == "none":
        print(f"Model produced no valid <tool>/<final> tag: {content}")
        return
```

Add memory branches inside this early-return tree. Call pure argument parsers
only. `remember` prints key plus `len(value)` and `recall` prints the key;
neither branch may invoke scratchpad read/write methods or echo a stored value.

**Repetition guard pattern** (`src/olla/loop.py` lines 149-159):

```python
elif parsed["tool"] == "read_file":
    sig = ("read_file", parsed["args_raw"])
    if sig == prev_sig:
        repeat_count += 1
    else:
        prev_sig = sig
        repeat_count = 1

    if repeat_count >= 3:
        print(f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck")
        return
```

Normalize memory signatures before dispatch: `("remember", key, value)` and
`("recall", key)`. Preserve the existing “abort before third execution”
behavior. If dispatch is refactored to remove duplication, keep all current
tool behavior unchanged.

**Result-to-observation pattern** (`src/olla/loop.py` lines 161-173):

```python
print(f"Step {step}: reading {parsed['args_raw']}...")

result = read_file(parsed["args_raw"])
if "error" in result:
    combined = result["error"]
else:
    combined = result.get("content", "")
    if not combined:
        combined = "(no output)"
preview = truncate_output(combined)
print(preview)
messages.append({"role": "user", "content": f"Observation: {preview}"})
continue
```

Use the same selected string for terminal output and `Observation`. For memory,
do not apply the generic falsy-content fallback: `Scratchpad.recall()` must
already translate a stored `""` to `memory is empty: <key>`.

**Auth/guard pattern:** follow the no-prompt `read_file` branch, not the shell
or `write_file` branches. `remember` and `recall` must not call
`olla.safety.check` or `Confirm.ask`, regardless of `yes`.

---

### `src/olla/prompts.py` (config / protocol contract, transform)

**Analog:** the existing `SYSTEM_PROMPT` in `src/olla/prompts.py`

**Prompt definition and tool-teaching pattern** (`src/olla/prompts.py` lines
1-24):

```python
"""System prompt teaching the <tool>/<args>/<final> tag contract."""

SYSTEM_PROMPT = """You are a helpful assistant that completes tasks using tools.

You have 3 tools available: `read_file`, `write_file`, `shell`.

To read a file, respond with:
<tool>read_file</tool><args>path/to/file</args>

To write a file, respond with the path on the first line and the file
content on the remaining lines:
<tool>write_file</tool><args>path/to/file
file content goes here
on one or more lines</args>

To run a shell command, respond with:
<tool>shell</tool><args>the raw shell command to run</args>

When you have the final answer for the user, respond with:
<final>your answer text here</final>

Only output one tag block per turn. Do not explain your reasoning outside the tags.
Never include a literal </args> sequence inside file content — it will cut off your output early.
NEVER use the `shell` tool to read or write files (e.g., do not use cat, echo, sed, or awk). Always use the `read_file` and `write_file` tools instead.
```

Change the count and list additively from three tools to five. Add concise,
concrete sections for `remember` and `recall` without changing the existing
shell/file teaching or examples.

**Worked-example pattern** (`src/olla/prompts.py` lines 26-38):

```python
Example:
<tool>read_file</tool><args>notes.txt</args>
Observation: meeting at 3pm

<final>The notes say there's a meeting at 3pm.</final>

Example:
<tool>write_file</tool><args>notes.txt
meeting at 4pm
</args>
Observation: wrote 15 bytes to notes.txt

<final>I updated the meeting time to 4pm.</final>
```

Append one compact memory transcript with
`remember -> Observation -> recall -> Observation -> final`, matching the
exact D-13 wording. Do not replace any existing example.

**Error handling/validation pattern:** prompt text teaches the protocol; it
does not implement validation. Include the line-oriented input shapes and one
valid sequence, leaving exact failure strings to the adapter.

---

### `tests/test_tools/test_memory.py` (test, CRUD)

**Analog:** `tests/test_tools/test_files.py`

**Imports and direct result assertions** (`tests/test_tools/test_files.py`
lines 1-14):

```python
"""Tests for olla.tools.files.read_file."""

from olla.tools.files import read_file, write_file


def test_read_file_success(tmp_path):
    path = tmp_path / "hello.txt"
    path.write_text("hello from file\n")

    result = read_file(str(path))

    assert result["path"] == str(path)
    assert result["content"] == "hello from file\n"
    assert "error" not in result
```

Import the public memory types/functions directly. Create a fresh
`Scratchpad()` per test, call it, and assert exact result dictionaries/strings,
not just substrings, for locked public behavior.

**Error and non-mutation test shape** (`tests/test_tools/test_files.py` lines
17-24 and 38-45):

```python
def test_read_file_not_found(tmp_path):
    path = tmp_path / "nope.txt"

    result = read_file(str(path))

    assert "error" in result
    assert str(path) in result["error"]
    assert "content" not in result
```

```python
def test_write_file_missing_parent_dir_errors(tmp_path):
    path = tmp_path / "nonexistent_dir" / "out.txt"

    result = write_file(str(path), "content")

    assert "error" in result
    assert "parent directory" in result["error"]
    assert not path.parent.exists()
```

For memory failures, follow each rejected write with a recall (and, where
relevant, a subsequent legal write) to prove atomicity and unchanged capacity.
Use `pytest.mark.parametrize` for boundary tables: 2,000/2,001 characters,
32/33 keys, 16,000/16,001 total characters, replacement shrink/grow, empty
value, and whitespace-only value.

---

### `tests/test_parser.py` (test, transform)

**Analog:** existing `write_file` payload-preservation tests in the same file

**Preservation regression pattern** (`tests/test_parser.py` lines 46-59):

```python
def test_write_file_args_preserve_interior_fences():
    content = "<tool>write_file</tool><args>/tmp/out.md\n# Title\n```\ncode block\n```\n</args>"
    result = parse_response(content)
    assert result["type"] == "tool"
    assert result["tool"] == "write_file"
    assert "```" in result["args_raw"]


def test_write_file_args_preserve_trailing_newline():
    content = "<tool>write_file</tool><args>/tmp/out.txt\nhello\n</args>"
    result = parse_response(content)
    assert result["type"] == "tool"
    assert result["tool"] == "write_file"
    assert result["args_raw"].endswith("hello\n")
```

Mirror these tests for `remember`, but assert the complete `args_raw` equality
so leading spaces, trailing newlines, whitespace-only values, explicit empty
values, and interior fences are proven verbatim. Add a `recall` case showing
ordinary whitespace trimming. Keep the missing-args fallback test shape from
lines 62-65.

---

### `tests/test_loop.py` (test, request-response)

**Analog:** existing mocked tool flows in the same file

**Mocked multi-turn result/Observation parity pattern**
(`tests/test_loop.py` lines 51-78):

```python
def test_run_loop_tool_then_final(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>echo hi</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {
        "argv": ["echo", "hi"],
        "returncode": 0,
        "stdout": "hi\n",
        "stderr": "",
    }

    run_loop(task="say hi", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "Step 1: running ['echo', 'hi']..." in captured.out
    assert "hi\n" in captured.out
    assert "done" in captured.out

    # The same truncated string used for the printed preview must be the one
    # appended to the message history as the Observation.
    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: hi\n"
```

Use this for normal `remember` and `recall`, asserting exact step text, terminal
text, and `Observation` payload. Also assert the remembered value never appears
in stdout during the write step.

**No-confirm tool pattern** (`tests/test_loop.py` lines 203-218):

```python
def test_run_loop_read_file_dispatch_no_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/some/path</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/some/path", "content": "hello from file\n"}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="read a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "hello from file" in captured.out
    mock_confirm.assert_not_called()
    mock_read_file.assert_called_once()
```

Run the memory equivalent both with default options and `yes=True`;
`Confirm.ask` must remain uncalled.

**Dry-run no-execution pattern** (`tests/test_loop.py` lines 633-648):

```python
def test_dry_run_previews_write_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\ncontent\n</args>"}}
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    resolved = str(Path("/tmp/x.txt").resolve())
    assert "would write" in captured.out
    assert resolved in captured.out
    assert "would prompt for confirmation" in captured.out
    assert mock_chat.call_count == 1
    mock_confirm.assert_not_called()
    mock_write_file.assert_not_called()
```

Patch or spy on memory methods and assert they are not called. For remember,
assert only key and character count appear; for recall, assert no lookup/value
appears.

**Repetition guard pattern** (`tests/test_loop.py` lines 730-745):

```python
def test_run_loop_repetition_guard_covers_read_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/same/path", "content": "hello\n"}

    run_loop(task="read same file repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same read_file call repeated 3x — model likely stuck" in captured.out
    assert mock_read_file.call_count == 2
    assert mock_chat.call_count == 3
```

Cover both memory tools and assert the third identical call aborts before a
third mutation/lookup.

**Three-turn E2E pattern** (`tests/test_loop.py` lines 847-866):

```python
def test_run_loop_read_then_write_end_to_end(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/tmp/in.txt</args>"}},
        {"message": {"content": "<tool>write_file</tool><args>/tmp/out.txt\nmodified content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/tmp/in.txt", "content": "original content\n"}
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/out.txt", "bytes_written": 17}
    mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="read a file and write a modified copy", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "done" in captured.out
    mock_read_file.assert_called_once()
    mock_write_file.assert_called_once()
    assert mock_chat.call_count == 3
```

Adapt this to the required `remember -> recall -> final` flow and inspect the
second and third model-call message histories. Add a separate two-invocation
test proving a key remembered in the first `run_loop()` is missing in the
second.

---

### `tests/test_prompts.py` (test, transform)

**Analog:** `tests/test_parser.py`

There is no existing prompt-specific suite. Use the repository’s small,
direct-contract test style.

**Minimal import and exact assertion pattern** (`tests/test_parser.py` lines
1-8):

```python
"""Tests for olla.parser.parse_response."""

from olla.parser import parse_response


def test_final_tag():
    result = parse_response("<final>The answer is 42</final>")
    assert result == {"type": "final", "text": "The answer is 42"}
```

Import `SYSTEM_PROMPT` directly and use plain assertions. Verify:

- all five tool names and the five-tool count;
- the line-oriented `remember` format and trimmed-key/raw-value rule;
- the raw-key `recall` format;
- one complete remember/acknowledge/recall/value/final transcript;
- preservation of the current read/write/shell teaching and examples.

Avoid snapshotting the entire prompt; focused semantic assertions make additive
wording changes less brittle while still protecting D-13.

## Shared Patterns

### Tool Result Contract

**Source:** `src/olla/tools/base.py` lines 1-20  
**Apply to:** `src/olla/tools/memory.py`, `src/olla/loop.py`

```python
"""Shared tool-result contract for all olla tools."""

from typing import TypedDict


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
    path: str
    content: str
    bytes_written: int
```

The existing `content` and `error` fields are sufficient. New dedicated fields
are unnecessary unless implementation clarity materially improves.

### Raw Payload Ownership

**Source:** `src/olla/parser.py` lines 21-32  
**Apply to:** `src/olla/parser.py`, `src/olla/tools/memory.py`,
`tests/test_parser.py`

The generic parser owns tolerant tag extraction and raw payload preservation.
The memory adapter owns first-line key/value parsing and exact error wording.
Do not duplicate tag parsing in the adapter or memory validation in
`parse_response()`.

### Invocation Lifetime

**Source:** `src/olla/loop.py` lines 32-37, 85-88  
**Apply to:** `src/olla/loop.py`, `tests/test_loop.py`

`messages`, `prev_sig`, and `repeat_count` already live for exactly one
`run_loop()` call. Place the scratchpad at this same lifetime. Do not use a
module global, mutable default, CLI singleton, file, or database.

### Recoverable Errors Become Observations

**Source:** `src/olla/loop.py` lines 163-173  
**Apply to:** all normal memory dispatch and integration tests

Select `result["error"]` or `result["content"]`, print that same text, then
append `Observation: {text}`. Malformed memory calls and missing keys are model-
recoverable; they should not terminate the loop or raise.

### No Confirmation or Safety Gate

**Source:** `src/olla/loop.py` lines 149-173 (`read_file` branch)  
**Apply to:** `remember`, `recall`, normal mode, `--yes`, and dry-run tests

Memory follows the no-prompt branch. Keep it outside `check()` and
`Confirm.ask()`. Dry-run returns before any adapter access.

### Scoped Test Commands

**Source:** `.planning/phases/04-memory-tool/04-RESEARCH.md` lines 510-546  
**Apply to:** all Phase 4 verification

Use:

```bash
.venv/bin/python -m pytest tests/test_tools/test_memory.py tests/test_parser.py tests/test_loop.py tests/test_prompts.py -q
.venv/bin/python -m pytest tests -q
```

Do not run unscoped root `pytest`: the dirty worktree contains unrelated
root-level `test_*.py` helper files that break collection.

## No Analog Found

No Phase 4 file lacks a usable analog. Two caveats remain:

| File | Missing Exact Pattern | Planner Fallback |
|------|-----------------------|------------------|
| `src/olla/tools/memory.py` | No existing bounded, invocation-local stateful adapter | Use the live `ToolResult` adapter shape plus the projected-state algorithm in `04-RESEARCH.md` lines 188-290 |
| `tests/test_prompts.py` | No existing prompt-contract test module | Use direct-import/plain-assert style from `tests/test_parser.py` and assert focused prompt invariants |

## Planner Guardrails

- Preserve all existing shell/file prompt teaching and loop behavior.
- Do not add CLI flags, safety-policy rules, persistence, automatic memory
  injection, listing, eviction, truncation, or context compaction.
- Keep values verbatim and use Python `len(str)` character counts.
- Treat `<args>key</args>` as missing a value line and
  `<args>key\n</args>` as a valid empty value.
- Compute replacement capacity as
  `current_total - len(old_value) + len(new_value)` before mutation.
- Do not print the value during `remember` or its dry-run preview.
- Preserve the current dirty-worktree edits in `loop.py`, `prompts.py`, and
  `tests/test_loop.py`.

## Metadata

**Analog search scope:** `src/olla/`, `src/olla/tools/`, `tests/`,
`tests/test_tools/`  
**Repository files scanned:** 19 Python source/test files  
**Concrete analog files read:** 10 (`parser.py`, `loop.py`, `prompts.py`,
`tools/base.py`, `tools/files.py`, `tools/shell.py`, `test_parser.py`,
`test_loop.py`, `test_tools/test_files.py`, and `test_tools/test_shell.py`)  
**Primary analogs assigned:** 6 unique paths  
**Pattern extraction date:** 2026-07-25
