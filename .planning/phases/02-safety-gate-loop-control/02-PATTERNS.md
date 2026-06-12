# Phase 2: Safety Gate + Loop Control - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 6 (1 new module + test, 2 modified source, 2 modified test, 1 config)
**Analogs found:** 4 / 6 (full match) + 2 partial (codebase has no precedent for `rich.Confirm`/EOFError or repetition-counter state — see "No Analog Found")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|----------------|
| `src/olla/safety.py` | utility (pure decision function) | transform | `src/olla/parser.py` | role-match (pure fn, dict/typed return, module-level constants) |
| `src/olla/loop.py` (modify) | controller (loop orchestration) | event-driven / request-response | itself (existing `run_loop`) | exact (extending existing dispatch branch) |
| `src/olla/cli.py` (modify) | controller (CLI entry point) | request-response | itself (existing `main`) | exact (extending existing flag wiring) |
| `tests/test_safety.py` | test | transform (pure-fn unit tests) | `tests/test_parser.py` | exact (pure fn, no mocking, direct dict/value assertions) |
| `tests/test_loop.py` (modify) | test | event-driven / request-response | itself (existing tests) | exact (extending existing `ollama.chat` mock + `mocker.patch` conventions) |
| `tests/test_cli.py` (modify) | test | request-response | itself (existing tests) | exact, but 2 tests are REWRITES not extensions (Pitfall 2) |
| `pyproject.toml` (modify) | config | — | itself | no analog — one-line dependency addition (`rich>=13`) |

## Pattern Assignments

### `src/olla/safety.py` (utility, transform — NEW FILE)

**Analog:** `src/olla/parser.py` (pure function, no I/O, module-level constants, dict-based discriminated return)

**Imports pattern** (`src/olla/parser.py` lines 1-3):
```python
"""Tolerant XML-tag parser for <tool>/<args>/<final> model output."""

import re
```
For `safety.py`, the equivalent would be:
```python
"""Pure safety-gate decision: blocklist/allowlist check against resolved argv."""

import fnmatch
```
No project-internal imports needed — `safety.py` must stay dependency-free (no `rich`, no `subprocess`) so `loop.py`'s dry-run path and real-run path can both call it with zero side effects (RESEARCH Pattern 1 / Anti-Patterns).

**Module-level constants pattern** (`src/olla/parser.py` lines 5-7):
```python
FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_RE = re.compile(r"<tool>(.*?)(?:</tool>|$)", re.DOTALL | re.IGNORECASE)
ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)
```
`safety.py` follows the same shape: module-level `ALLOWLIST` set, `_HARD_BLOCKED_BINARIES` set, `_RM_DANGEROUS_TARGETS` set, etc. — named constants at module scope, referenced by the single pure function below them. Same "define the data tables first, then the function that consumes them" ordering as `parser.py`.

**Core pure-function pattern** (`src/olla/parser.py` lines 10-31, full function):
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
**Pattern to copy:** a single pure function, no exceptions raised for "normal" outcomes, returns a dict (or here, per RESEARCH's recommendation, a small typed object) with a discriminator field (`"type"` in `parser.py` → `kind`/`"ALLOW"|"CONFIRM"|"BLOCK"` in `safety.py`). Ordered if/return chain mirrors `parser.py`'s "prefer final, else tool+args, else none" precedence — `safety.py`'s precedence is "BLOCK > ALLOW > CONFIRM" (RESEARCH Pattern 1).

**Return-shape note for planner:** The codebase convention (both `parser.py`'s `dict` return and `tools/base.py`'s `ToolResult` `TypedDict`) is **plain dicts/TypedDicts with a discriminator key**, not dataclasses. RESEARCH.md proposes a `@dataclass(frozen=True) class Decision`. Either is workable, but a `TypedDict`-based return (`{"kind": "BLOCK", "reason": "..."}`) is more consistent with the existing two analogs (`parser.py`'s dict-with-`"type"` and `tools/base.py`'s `ToolResult`). Flag for planner to decide — not a blocking issue either way.

**Reuse note (argv):** Per CONTEXT.md code_context, `safety.check(argv, ...)` must accept the SAME `argv` that `loop.py` already computes via `shlex.split(parsed["args_raw"])` (`src/olla/loop.py` line 52) and that `run_shell` independently recomputes (`src/olla/tools/shell.py` line 16) — do not re-split inside `safety.py`.

---

### `src/olla/loop.py` (controller, event-driven — MODIFY)

**Analog:** itself — extend the existing `run_loop` and the `parsed["tool"] == "shell"` branch.

**Imports pattern** (`src/olla/loop.py` lines 1-8, current):
```python
"""ReAct loop step execution."""

import shlex

import ollama

from olla.parser import parse_response
from olla.tools.shell import run_shell
```
New imports needed for Phase 2 (additive, same block style):
```python
from rich.console import Console
from rich.prompt import Confirm

from olla.safety import check as safety_check
```

**Insertion point — the `parsed["tool"] == "shell"` branch** (`src/olla/loop.py` lines 45-69, current, full branch):
```python
        if parsed["type"] == "tool":
            if parsed["tool"] != "shell":
                preview = f"unknown tool '{parsed['tool']}'"
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            try:
                argv = shlex.split(parsed["args_raw"])
            except ValueError as e:
                preview = f"error: could not parse command: {e}"
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            print(f"Step {step}: running {argv}...")
            result = run_shell(parsed["args_raw"])
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
**Pattern to copy for the new repetition-guard and safety-gate checks:** insert them between `argv = shlex.split(...)` (line 52) and `print(f"Step {step}: running {argv}...")` (line 58) — same "compute argv, then branch on outcome, each branch does `print(...)` + `messages.append({"role": "user", "content": f"Observation: {preview}"})` + `continue`" shape already used for the unknown-tool (lines 47-50) and malformed-args (lines 53-57) branches immediately above. The BLOCK and decline paths should follow this exact `preview`/`print`/`messages.append`/`continue` idiom — do not invent a new response shape.

**Observation-append idiom** (3 existing examples in lines 47-50, 53-57, 66-68) — copy verbatim shape:
```python
preview = "<message text>"
print(preview)
messages.append({"role": "user", "content": f"Observation: {preview}"})
continue
```
This is the exact shape for: D-04's "blocked by safety policy: <reason>" observation, and the CONFIRM-decline "declined by user" observation (RESEARCH Open Question 1 recommendation).

**`truncate_output` pattern** (`src/olla/loop.py` lines 13-19, unchanged, referenced for consistency):
```python
def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    """Truncate text to a head+tail preview if it exceeds `limit` chars."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2):]
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"
```
Not directly modified, but the new BLOCK/decline preview strings should be short enough to not need truncation — consistent with how the unknown-tool/malformed-args previews (lines 47, 54) are also untruncated short strings.

**`run_loop` signature and head** (`src/olla/loop.py` lines 28-39, current):
```python
def run_loop(task: str, model: str, max_steps: int, system_prompt: str) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for step in range(1, max_steps + 1):
        content = call_model(model, messages)
        parsed = parse_response(content)
        history_content = truncate_output(content) if parsed["type"] == "none" else content
        messages.append({"role": "assistant", "content": history_content})
```
Phase 2 adds `yes: bool` and `dry_run: bool` parameters to this signature (CONTEXT D-09/D-10, RESEARCH dry-run code example). Repetition-guard state (`prev_sig`, `repeat_count`) is initialized here, before the `for` loop, per RESEARCH Pattern 3.

**Max-steps message** (`src/olla/loop.py` line 78, current — for distinguishing from the new repetition message per D-07):
```python
    print(f"Reached max steps ({max_steps}) without a <final> answer.")
```
The new repetition-abort message (D-07: `"olla stopped: same shell call repeated 3x — model likely stuck"`) must be visibly distinct from this existing string — same `print(...)` + `return` shape, different wording.

---

### `src/olla/cli.py` (controller, request-response — MODIFY)

**Analog:** itself — extend existing flag definitions and `run_loop` call.

**Full current file** (`src/olla/cli.py`, 35 lines):
```python
"""CLI entry point wiring TASK + flags to the ReAct loop."""

import click

from olla.loop import run_loop
from olla.prompts import SYSTEM_PROMPT
from olla.smoke import run_smoke_test


@click.command()
@click.argument("task", required=False)
@click.option("--model", required=False, default=None, help="Ollama model name (no default)")
@click.option("--dry-run", is_flag=True)
@click.option("--max-steps", default=15, show_default=True, type=int)
@click.option("--yes", is_flag=True)
@click.option("--smoke-test", is_flag=True, help="Run format-compliance check against --model")
def main(task, model, dry_run, max_steps, yes, smoke_test):
    """Run an agentic task against a local Ollama model."""
    if smoke_test:
        if not model:
            raise click.UsageError("--smoke-test requires --model")
        run_smoke_test(model)
        return

    if not task:
        raise click.UsageError("TASK argument is required")
    if not model:
        raise click.UsageError("--model is required (no hardcoded default model, CLI-01)")

    if dry_run:
        click.echo("Note: --dry-run is not yet enforced (Phase 2); the agent may execute real commands.")
    if yes:
        click.echo("Note: --yes is not yet enforced (Phase 2); confirmation prompts are not implemented yet.")

    run_loop(task=task, model=model, max_steps=max_steps, system_prompt=SYSTEM_PROMPT)
```

**Pattern to copy:** the `--dry-run` and `--yes` flags ALREADY EXIST (lines 13, 15) — Phase 2 does not add new `@click.option` decorators for these two. Instead:
1. Delete the inert-notice block (lines 30-33).
2. Thread `dry_run=dry_run, yes=yes` into the `run_loop(...)` call (line 35), following the existing keyword-argument style (`task=task, model=model, max_steps=max_steps, system_prompt=SYSTEM_PROMPT`).
3. If `dry_run` triggers a fundamentally different code path (single model call, RESEARCH's separate dry-run branch), that branching can live either in `cli.py` (mirroring the existing `if smoke_test: ... return` early-return pattern at lines 19-23) or inside `run_loop` itself (RESEARCH's recommendation — `run_loop` takes `dry_run` and branches internally). The existing `smoke_test` early-return (lines 19-23) is the closest analog for an `if dry_run:`-style early branch in `cli.py` if the planner chooses that structure:
```python
    if smoke_test:
        if not model:
            raise click.UsageError("--smoke-test requires --model")
        run_smoke_test(model)
        return
```

---

### `tests/test_safety.py` (test, transform — NEW FILE)

**Analog:** `tests/test_parser.py` (pure function, direct call + dict/value assertions, NO mocking, NO `mocker` fixture)

**Full analog file** (`tests/test_parser.py`, 44 lines):
```python
"""Tests for olla.parser.parse_response."""

from olla.parser import parse_response


def test_final_tag():
    result = parse_response("<final>The answer is 42</final>")
    assert result == {"type": "final", "text": "The answer is 42"}


def test_tool_and_args():
    result = parse_response("<tool>shell</tool><args>ls -la /tmp</args>")
    assert result == {"type": "tool", "tool": "shell", "args_raw": "ls -la /tmp"}


def test_markdown_fence_tolerance():
    content = "```\n<tool>shell</tool><args>echo hi</args>\n```"
    result = parse_response(content)
    assert result == {"type": "tool", "tool": "shell", "args_raw": "echo hi"}
```
*(remaining tests in the file follow the identical "call function, assert on returned dict" shape — see lines 22-44 for `test_surrounding_prose_tolerance`, `test_unclosed_args_tag_tolerance`, `test_no_recognizable_tags`, `test_final_wins_over_tool`)*

**Pattern to copy for `test_safety.py`:**
```python
"""Tests for olla.safety.check."""

from olla.safety import check


def test_allowlisted_binary_allows():
    decision = check(["ls", "-la"], yes=False)
    assert decision.kind == "ALLOW"  # or decision["kind"] == "ALLOW" if dict-based


def test_rm_rf_root_blocks():
    decision = check(["rm", "-rf", "/"], yes=False)
    assert decision.kind == "BLOCK"
    assert "rm" in decision.reason


def test_non_allowlisted_binary_confirms():
    decision = check(["git", "status"], yes=False)
    assert decision.kind == "CONFIRM"
```
One test function per D-03 blocklist rule (sudo/su/shutdown/reboot/poweroff/halt outright-block; `rm -rf` targets `/`, `~`, `/*`, `$HOME`, `.`; `dd`/`mkfs*` on `/dev/sd*|nvme*|hd*`; fork-bomb string; `chmod`/`chown -R /`), plus allowlist membership tests (D-01) and the BLOCK > ALLOW > CONFIRM ordering test (e.g., a hypothetical binary that's both allowlisted AND blocklisted, if such an overlap can be constructed — otherwise test ordering via the empty-argv BLOCK case vs. allowlist). No `mocker`, no `capsys` — every test is a direct call + assertion, exactly like `test_parser.py`.

---

### `tests/test_loop.py` (MODIFY — additions)

**Analog:** itself — existing `mocker.patch("olla.loop.ollama.chat")` + `side_effect` list convention.

**`ollama.chat` two-step `side_effect` pattern** (`tests/test_loop.py` lines 48-67, full test):
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
```
**Pattern to copy:** every new confirm-gate / repetition / dry-run / blocked-command test follows this exact shape — `mock_chat.side_effect = [...]` for the sequence of model responses, `mocker.patch("olla.loop.run_shell")` (and now also `mocker.patch("olla.loop.Confirm.ask", ...)` per RESEARCH's mock-target note: "patch where it's looked up", i.e. `olla.loop.Confirm.ask` not `rich.prompt.Confirm.ask`), then `run_loop(...)`, then assert on `capsys.readouterr().out` and/or `mock_run_shell.assert_called_once()` / `assert_not_called()`.

**Observation-message assertion pattern** (`tests/test_loop.py` lines 71-75):
```python
    # The same truncated string used for the printed preview must be the one
    # appended to the message history as the Observation.
    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: hi\n"
```
**Pattern to copy:** for the new "blocked by safety policy: <reason>" and "declined by user" observations, assert `obs_messages[0]["content"] == "Observation: blocked by safety policy: ..."` etc., using this exact `call_args_list[N].kwargs["messages"]` extraction.

**Max-steps regression test** (`tests/test_loop.py` lines 159-179, full test) — needed as the analog for the NEW repetition-abort test, since both produce a distinct early-`return`-with-message:
```python
def test_run_loop_max_steps_no_final(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "I am thinking about it."}}
    mocker.patch("olla.loop.run_shell")

    run_loop(task="ponder", model="test-model", max_steps=2, system_prompt="sys")

    captured = capsys.readouterr()
    assert "Reached max steps (2) without a <final> answer." in captured.out
    assert mock_chat.call_count == 2
```
**Pattern to copy for the repetition-guard test:** use `mock_chat.side_effect = [<same shell call> x3, <final>]` (or `return_value` for a repeated identical tool call), assert the D-07 string `"olla stopped: same shell call repeated 3x — model likely stuck"` appears in `captured.out`, assert `mock_run_shell.call_count == 2` (3rd identical call never executes, per RESEARCH Pattern 3), and assert the max-steps string does NOT appear (distinctness check).

---

### `tests/test_cli.py` (MODIFY — 2 REWRITES + 2 signature-update checks)

**Analog:** itself — existing `CliRunner` + `mock_run_loop.assert_called_once_with(...)` convention.

**`CliRunner` + exact-signature-assertion pattern** (`tests/test_cli.py` lines 30-39, full test):
```python
def test_task_and_model_call_run_loop_with_defaults(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model"])

    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something", model="some-model", max_steps=15, system_prompt=SYSTEM_PROMPT
    )
```
**REQUIRED UPDATE (not optional):** if `run_loop`'s signature gains `yes`/`dry_run` params (per `loop.py` changes above), this test's `assert_called_once_with(...)` (lines 37-39) and `test_max_steps_option_threaded_through`'s equivalent (lines 49-51) will FAIL unless updated to include the new kwargs (e.g., `yes=False, dry_run=False`). This is a REQUIRED edit, not a side effect to discover later.

**Tests requiring REWRITE (Pitfall 2)** — `tests/test_cli.py` lines 54-73, full current versions:
```python
def test_dry_run_flag_prints_inert_notice(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--dry-run"])

    assert result.exit_code == 0
    assert "--dry-run is not yet enforced" in result.output
    mock_run_loop.assert_called_once()


def test_yes_flag_prints_inert_notice(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()

    result = runner.invoke(main, ["do something", "--model", "some-model", "--yes"])

    assert result.exit_code == 0
    assert "--yes is not yet enforced" in result.output
    mock_run_loop.assert_called_once()
```
**Both MUST be rewritten** (the asserted strings `"--dry-run is not yet enforced"` / `"--yes is not yet enforced"` are deleted from `cli.py` in Phase 2 — these assertions will fail otherwise, which is EXPECTED per RESEARCH Pitfall 2, not a regression to "fix" by re-adding the notices):
- `test_dry_run_flag_prints_inert_notice` → rewrite to assert `dry_run=True` is threaded to `run_loop` (`mock_run_loop.assert_called_once_with(..., dry_run=True, ...)`), OR — if dry-run logic lives in `cli.py` itself rather than `run_loop` — mock `ollama.chat`/`run_loop` appropriately and assert the `"Step 1 would run:"` / `"Model would answer directly:"` output per D-09/D-10.
- `test_yes_flag_prints_inert_notice` → rewrite to assert `yes=True` is threaded to `run_loop` (`mock_run_loop.assert_called_once_with(..., yes=True, ...)`).

Both rewrites keep the existing `CliRunner` + `mocker.patch("olla.cli.run_loop")` + `assert_called_once_with(...)` skeleton (lines 30-39 above) — only the final assertion changes.

---

### `pyproject.toml` (config — MODIFY)

**No analog** — single-line addition to the existing `dependencies` list.

**Current** (`pyproject.toml` lines 9-12):
```toml
dependencies = [
    "ollama>=0.6.2",
    "click>=8.1,<9",
]
```
**Add** (per RESEARCH Standard Stack, A1): `"rich>=13",` as a third entry — `rich` 15.0.0 is already installed in this environment; `rich>=13` (no upper bound) avoids forcing a downgrade. CLAUDE.md's `rich>=13,<14` is stale advisory research, not a hard constraint.

---

## Shared Patterns

### Observation-append idiom (applies to `loop.py` BLOCK and CONFIRM-decline branches)
**Source:** `src/olla/loop.py` lines 47-50, 53-57, 66-68 (three existing instances of the same shape)
**Apply to:** the new "blocked by safety policy: <reason>" branch (D-04) and "declined by user" branch (RESEARCH Open Question 1)
```python
preview = "<message>"
print(preview)
messages.append({"role": "user", "content": f"Observation: {preview}"})
continue
```

### Pure-function-with-discriminated-dict-return idiom (applies to `safety.py`)
**Source:** `src/olla/parser.py` lines 10-31 (`parse_response`), `src/olla/tools/base.py` lines 6-17 (`ToolResult` TypedDict)
**Apply to:** `safety.check(argv, yes) -> Decision` — no I/O, ordered precedence checks, dict/TypedDict-style discriminated return (`"type"`/`"kind"` key) consistent with both existing analogs; reconcile with RESEARCH's proposed `@dataclass(frozen=True) Decision` at planning time.

### `mocker.patch` + `side_effect` list for multi-step `ollama.chat` sequences
**Source:** `tests/test_loop.py` lines 48-53 (and repeated at lines 78-83, 99-105, 121-128, 141-150)
**Apply to:** all new `test_loop.py` confirm-gate/repetition/dry-run/blocked-command tests
```python
mock_chat = mocker.patch("olla.loop.ollama.chat")
mock_chat.side_effect = [
    {"message": {"content": "<tool>shell</tool><args>...</args>"}},
    {"message": {"content": "<final>done</final>"}},
]
```

### `argv` reuse (no re-splitting)
**Source:** `src/olla/loop.py` line 52 (`argv = shlex.split(parsed["args_raw"])`) and `src/olla/tools/shell.py` line 16 (`argv = shlex.split(args_raw)`, returned in `ToolResult["argv"]`)
**Apply to:** `safety.check(argv, ...)` call site in `loop.py`, and the repetition-guard signature `("shell", tuple(argv))` — both consume the SAME `argv` computed once at line 52, per CONTEXT.md code_context's explicit instruction not to re-split.

## No Analog Found

Files/concerns with no close codebase match — planner should rely on RESEARCH.md's Code Examples section directly for these:

| Concern | Role | Data Flow | Reason |
|---------|------|-----------|--------|
| `rich.Confirm.ask` confirm-prompt call + `try/except EOFError` wrapper | I/O (loop.py addition) | request-response | `grep` for `Confirm`/`rich` across `src/` and `tests/` returns zero matches — no prior `rich` usage anywhere in the codebase. RESEARCH.md's "Confirm-gate integration in `run_loop`" code example (D-01/D-02/D-04/D-09) and Pitfall 1's `try/except EOFError` snippet are the only available reference; verified against installed `rich` 15.0.0 source per RESEARCH's Sources section. |
| Repetition-guard counter state (`prev_sig`, `repeat_count`) | loop-local state (loop.py addition) | event-driven | No existing loop in the codebase tracks cross-iteration state beyond `messages` — this is genuinely new control flow. RESEARCH Pattern 3 (`(prev_sig, repeat_count)` pair, initialized before the `for` loop) is the only available reference. |
| `--dry-run` single-model-call preview branch | controller (loop.py or cli.py addition) | request-response (single-shot) | No existing "run once and stop" branch exists — `run_loop`'s only early-`return`s are `<final>` (line 41-43) and implicitly max-steps (end of loop, line 78). RESEARCH's "`--dry-run` single-step preview (D-09/D-10)" code example is the reference; the `<final>`-vs-`<tool>`-vs-`none` branching structure to reuse for dry-run IS present in the codebase (lines 41, 45, 71) even though the "stop after one call" wrapper is new. |

## Metadata

**Analog search scope:** `src/olla/` (all 8 `.py` files), `tests/` (all 6 `.py` files), `pyproject.toml`
**Files scanned:** 14 (8 source + 6 test files) + 1 config
**Pattern extraction date:** 2026-06-12
