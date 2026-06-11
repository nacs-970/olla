---
phase: 01-core-loop-shell-tool-cli
plan: quick-260611-upi
type: execute
wave: 1
depends_on: []
files_modified: [src/olla/loop.py, tests/test_loop.py]
autonomous: true
requirements: [LOOP-01, LOOP-02]

must_haves:
  truths:
    - "A real no-output successful shell command (e.g. touch <file>) produces an Observation of exactly '(no output)', not an empty Observation"
    - "When the model emits a <tool> tag with a name other than 'shell', the loop returns an 'unknown tool' observation and does NOT call run_shell"
    - "The known-tool ('shell') path continues to work exactly as before"
  artifacts:
    - path: "src/olla/loop.py"
      provides: "Fixed combined-output branch (WR-01) and tool-name dispatch (Finding 2)"
    - path: "tests/test_loop.py"
      provides: "Regression test for real no-output success shape, and dispatch tests for unknown-tool path"
  key_links:
    - from: "src/olla/loop.py:run_loop"
      to: "src/olla/tools/shell.py:run_shell"
      via: "only called when parsed['tool'] == 'shell'"
      pattern: "parsed\\[.tool.\\] == .shell."
---

<objective>
Fix two tech-debt findings from the Phase 01 checkpoint audit (01-AUDIT.md, Findings 1 and 2), both in `src/olla/loop.py`'s `run_loop` tool-handling branch:

1. **WR-01 (dead-code fix):** The `combined` output branch in `run_loop` has a dead `else` clause — `run_shell` always returns `stdout`/`stderr` keys (possibly empty strings) on success, so the `elif "stdout" in result or "stderr" in result` branch is always taken, and `combined` becomes `""` instead of `"(no output)"` for genuinely no-output successes (e.g. `touch file`).

2. **Tool-name dispatch (Finding 2):** `parsed["tool"]` is parsed but never checked — `run_shell` is called unconditionally for any `parsed["type"] == "tool"`. Add a minimal name-based dispatch: if `parsed["tool"] != "shell"`, return an `unknown tool` observation without calling `run_shell`. This establishes the dispatch point Phase 3 will extend with new tools.

Purpose: Close the last two open warnings from the Phase 01 audit so Phase 01 is fully clean before Phase 2 starts. Both fixes are small, isolated, and independent — they touch the same file but different branches, kept as 2 separate atomic commits.

Output: Updated `src/olla/loop.py` and `tests/test_loop.py`, all tests green.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/01-core-loop-shell-tool-cli/01-AUDIT.md
@.planning/phases/01-core-loop-shell-tool-cli/.continue-here.md

<interfaces>
<!-- Current src/olla/loop.py run_loop tool-handling branch (lines 45-64) -->
<!-- Executor edits this directly; do not explore further. -->

```python
        if parsed["type"] == "tool":
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
            elif "stdout" in result or "stderr" in result:
                combined = result.get("stdout", "") + result.get("stderr", "")
            else:
                combined = "(no output)"
            preview = truncate_output(combined)
            print(preview)
            messages.append({"role": "user", "content": f"Observation: {preview}"})
            continue
```

<!-- src/olla/parser.py parse_response output shape -->
<!-- parsed["tool"] is the stripped <tool>...</tool> text, e.g. "shell" -->
```python
    if tool_match and args_match:
        return {
            "type": "tool",
            "tool": tool_match.group(1).strip(),
            "args_raw": args_match.group(1).strip(),
        }
```

<!-- src/olla/tools/shell.py run_shell return shapes -->
<!-- Success: {"argv":[...], "returncode":0, "stdout":"", "stderr":""} (keys always present) -->
<!-- Error:   {"argv":[...], "error": "..."} or {"error": "..."} (no argv if shlex.split itself failed) -->

<!-- tests/test_loop.py existing test at line 100 — this is the test that masks WR-01: -->
<!-- It mocks run_shell returning {"argv": [...], "returncode": 0} with NO stdout/stderr -->
<!-- keys. This shape never occurs in the real run_shell — repoint it to the real shape. -->
```python
def test_run_loop_tool_result_missing_output_keys(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>touch foo</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["touch", "foo"], "returncode": 0}

    run_loop(task="touch a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "(no output)" in captured.out

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert obs_messages[0]["content"] == "Observation: (no output)"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task A: Fix WR-01 dead-code in combined-output branch</name>
  <files>src/olla/loop.py, tests/test_loop.py</files>
  <behavior>
    - Test: `test_run_loop_tool_result_real_no_output_success` (renamed/repointed from
      `test_run_loop_tool_result_missing_output_keys`) — mock `run_shell` to return
      `{"argv": ["touch", "foo"], "returncode": 0, "stdout": "", "stderr": ""}` (the
      REAL shape `run_shell` produces on success: keys present, values empty strings).
      Assert the printed output contains `(no output)` and the appended message
      history has `"Observation: (no output)"` exactly.
    - RED check: confirm this test FAILS against the current (unfixed) `loop.py` —
      with the unfixed code, `"stdout" in result` is True, so `combined = "" + "" = ""`,
      producing `Observation: ` (empty), not `Observation: (no output)`. Run
      `PYTHONPATH=src .venv/bin/python -m pytest tests/test_loop.py -k real_no_output -q`
      and confirm it fails before editing `loop.py`.
    - GREEN: after the `loop.py` fix below, the same test passes.
  </behavior>
  <action>
    In `tests/test_loop.py`, rename `test_run_loop_tool_result_missing_output_keys` to
    `test_run_loop_tool_result_real_no_output_success` and change the mocked
    `run_shell.return_value` to `{"argv": ["touch", "foo"], "returncode": 0, "stdout": "", "stderr": ""}`
    (matching the real `run_shell` success shape from `src/olla/tools/shell.py` — keys
    always present). Keep the existing assertions (printed `(no output)`, message
    history `"Observation: (no output)"`).

    Run the test first to confirm RED (fails on current code) per the behavior block.

    Then in `src/olla/loop.py`, replace the three-branch `if/elif/else` (lines ~55-60)
    that computes `combined`:

    ```
    if "error" in result:
        combined = result["error"]
    elif "stdout" in result or "stderr" in result:
        combined = result.get("stdout", "") + result.get("stderr", "")
    else:
        combined = "(no output)"
    ```

    with a two-branch version where the no-output check is on the actual combined
    string content, not key presence:

    ```
    if "error" in result:
        combined = result["error"]
    else:
        combined = result.get("stdout", "") + result.get("stderr", "")
        if not combined:
            combined = "(no output)"
    ```

    This is per WR-01 in 01-AUDIT.md (Finding 1) and `.continue-here.md` Task 3.
    Run the full `test_loop.py` suite to confirm GREEN (the renamed test now passes,
    and no other test regresses — `test_run_loop_tool_then_final` still asserts
    `"Observation: hi\n"` for non-empty output, unaffected by this change).

    Commit this task's changes separately (one commit for Task A).
  </action>
  <verify>
    <automated>cd /home/nacs/Documents/git/olla && PYTHONPATH=src .venv/bin/python -m pytest tests/test_loop.py -q</automated>
  </verify>
  <done>
    `src/olla/loop.py`'s combined-output branch checks `if not combined` (string
    content) rather than key presence. `tests/test_loop.py` has
    `test_run_loop_tool_result_real_no_output_success` using the real `run_shell`
    success shape (`stdout`/`stderr` keys present as empty strings), and this test
    fails on the pre-fix code and passes on the post-fix code. Full `test_loop.py`
    suite passes.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task B: Add tool-name dispatch (unknown-tool branch) in run_loop</name>
  <files>src/olla/loop.py, tests/test_loop.py</files>
  <behavior>
    - Test: `test_run_loop_unknown_tool_returns_observation` — mock `ollama.chat` to
      first return `<tool>write_file</tool><args>foo.txt</args>` then `<final>done</final>`.
      Mock `run_shell` (must NOT be called). Assert:
      - printed output contains `unknown tool 'write_file'`
      - message history contains `"Observation: unknown tool 'write_file'"` exactly
        (use the same `obs_messages` filter pattern as `test_run_loop_tool_then_final`)
      - `mock_run_shell.assert_not_called()`
    - The existing `test_run_loop_tool_then_final` (tool == "shell") already covers the
      known-tool path and must continue to pass unchanged — do not duplicate it.
    - RED check: confirm the new test FAILS against current `loop.py` (it currently
      calls `run_shell` unconditionally regardless of `parsed["tool"]`, so
      `mock_run_shell.assert_not_called()` fails and no "unknown tool" text is printed).
  </behavior>
  <action>
    Add `test_run_loop_unknown_tool_returns_observation` to `tests/test_loop.py` per
    the behavior block above, modeled on `test_run_loop_tool_then_final`'s structure
    (mock_chat.side_effect list, mock_run_shell, obs_messages filter). Run it to
    confirm RED on current code.

    Then in `src/olla/loop.py`, inside the `if parsed["type"] == "tool":` block, add
    a guard at the very top — BEFORE the `shlex.split` call and BEFORE the
    `print(f"Step {step}: running ...")` line — that checks `parsed["tool"]`:

    ```
    if parsed["tool"] != "shell":
        preview = f"unknown tool '{parsed['tool']}'"
        print(preview)
        messages.append({"role": "user", "content": f"Observation: {preview}"})
        continue
    ```

    This must short-circuit before `argv = shlex.split(...)`, before the "Step N:
    running..." print, and before `run_shell` is called — an unknown tool name should
    not attempt to parse args or print a misleading "running" line. This is per
    Finding 2 in 01-AUDIT.md and `.continue-here.md` Task 4 — establishes the dispatch
    point Phase 3 will extend with new tool names (e.g. "write_file", "read_file").

    Run the full `test_loop.py` suite to confirm GREEN — the new test passes, and
    `test_run_loop_tool_then_final` / `test_run_loop_malformed_args_recovers` (both
    use `tool == "shell"`) still pass unchanged.

    Commit this task's changes separately (one commit for Task B).
  </action>
  <verify>
    <automated>cd /home/nacs/Documents/git/olla && PYTHONPATH=src .venv/bin/python -m pytest tests/test_loop.py -q</automated>
  </verify>
  <done>
    `src/olla/loop.py`'s tool-handling branch checks `parsed["tool"] != "shell"` first
    and returns an `Observation: unknown tool '<name>'` without calling `run_shell`
    or attempting `shlex.split`/printing "Step N: running...". The known-tool
    ("shell") path is unchanged and its existing tests still pass.
    `tests/test_loop.py` has `test_run_loop_unknown_tool_returns_observation` covering
    the unknown-tool path (asserts `mock_run_shell.assert_not_called()`).
  </done>
</task>

</tasks>

<verification>
Run the full project test suite to confirm no regressions across both fixes:

```bash
cd /home/nacs/Documents/git/olla && PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

Expect 42/42 passing (41 existing + 1 new from Task B; Task A renames/repoints an
existing test rather than adding one, so net change is +1 overall).
</verification>

<success_criteria>
- `src/olla/loop.py` combined-output branch uses `if not combined:` (content check),
  not `elif "stdout" in result or "stderr" in result:` (key-presence check).
- `src/olla/loop.py` tool-handling branch dispatches on `parsed["tool"]`: only "shell"
  reaches `run_shell`; any other tool name returns
  `Observation: unknown tool '<name>'` without calling `run_shell`.
- `tests/test_loop.py` has a test using the REAL `run_shell` success shape
  (`stdout`/`stderr` keys present as empty strings) that fails pre-fix and passes
  post-fix.
- `tests/test_loop.py` has a test for the unknown-tool dispatch path asserting
  `run_shell` is not called.
- Full test suite (`PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`) passes.
- Two separate commits, one per task (Task A: WR-01 fix, Task B: tool dispatch).
</success_criteria>

<output>
Create `.planning/quick/260611-upi-fix-wr-01-dead-code-in-loop-py-and-add-t/260611-upi-SUMMARY.md` when done.
</output>
