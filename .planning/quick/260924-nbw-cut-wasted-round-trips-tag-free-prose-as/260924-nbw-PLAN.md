---
phase: quick-260924-nbw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/olla/debug.py
  - src/olla/loop.py
  - tests/test_debug.py
  - tests/test_loop.py
autonomous: true
requirements: [QUICK-260924-nbw]

estimate:
  tokens: 60000
  raw_tokens: 60000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "When the model replies with plain prose that has no protocol tags, the loop shows it once as `* <prose>` and ends in one model call. There is no retry nudge."
    - "Prose that has partial or malformed protocol tags, or content that is only whitespace, still takes the `none` path and gets the harness nudge."
    - "An HTTP-200 stream with no deltas is retried once inside `_stream_model_turn`. The trim check runs only once. An empty assistant message never goes into history."
    - "Every `debug_log` line goes to stderr. Stdout (the dimmed reasoning stream and final answers) has no `[DEBUG]` text."
    - "Assistant history for tool calls is always `<tool>NAME</tool><args>ARGS</args>`, with the closing `</args>` present. For final answers it is always `<final>TEXT</final>`."
  artifacts:
    - path: src/olla/debug.py
      provides: "debug_log printing to sys.stderr"
    - path: src/olla/loop.py
      provides: "prose-as-final in _prepare_action, empty-stream retry in _stream_model_turn, canonical history plus empty-skip in run_loop"
    - path: tests/test_loop.py
      provides: "regression tests for all four fixes"
    - path: tests/test_debug.py
      provides: "debug output assertions on .err"
  key_links:
    - from: "run_loop assistant append"
      to: "_Action.tool / _Action.args_raw / _Action.text"
      via: "f-string canonical envelope"
      pattern: "<args>{action.args_raw}</args>"
    - from: "_prepare_action none-branch"
      to: "olla.parser TOOL_OPEN_RE/TOOL_CLOSE_RE/ARGS_OPEN_RE/ARGS_CLOSE_RE/FINAL_OPEN_RE/FINAL_CLOSE_RE"
      via: "import from olla.parser"
      pattern: "FINAL_CLOSE_RE"
---

<objective>
Remove the wasted model round-trips seen in the live OpenRouter REPL run (`nvidia/nemotron-3-ultra-550b-a55b:free`, task "create simple calculator python file"). Steps 3-5 of that run each resent about 6k characters of context to get one answer. There were two causes: a plain-prose reply was nudged instead of being accepted, and an empty stream appended an empty assistant message and was then nudged again. The same run showed two more problems. History stored `<tool>read_file</tool><args>calculator.py` without the `</args>` that the stop sequence strips, which small models may copy. `debug_log` also printed in the middle of the dimmed reasoning line on stdout.

Purpose: This serves olla's core value, minimal per-turn token overhead on small local models. The user approved all four fixes (fix_spec 1-4). Keep all code and logic outside these fixes unchanged. Do NOT touch `src/olla/parser.py` or `src/olla/smoke.py`, which keeps its own strict regex.

Output: Changes to `src/olla/debug.py` and `src/olla/loop.py`, updated and new tests, and two atomic commits on `main`.

Branch note: The user already approved committing directly on `main` for quick tasks, which matches the repo history (see 260924-mml). If GSD's protected-branch check fires, do NOT stop. Commit on `main`.
</objective>

<execution_context>
@/home/nacs/.claude/gsd-core/workflows/execute-plan.md
@/home/nacs/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.planning/quick/260924-mml-fix-reasoning-merge-parse-loop-exclude-t/260924-mml-SUMMARY.md
@src/olla/debug.py
@src/olla/parser.py

Key locations (loop.py at HEAD 80ac33b):
- `_prepare_action` at about line 237. It parses `parse_response(_strip_thinking(content))`. For `none` it currently returns `_Action("none", "response", ("none", content), text=content)`.
- `_stream_model_turn` at about lines 552-612. It runs the trim check, then the `_is_mocked(call_model) or _is_mocked(ollama.chat)` early return to `_call_model_for_loop`, then one `provider.stream_chat(messages)` loop that collects non-thought chunks into `content` and thought chunks into `thought_text`. It prints a newline, then runs the reasoning fallback (content empty, reasoning parses to non-none), then returns content. ProviderError, ollama errors, and Exception are caught and return None.
- `run_loop` step body at about lines 1154-1262. Line 1170 is `history_content = truncate_output(content) if action.kind == "none" else content`, followed by the assistant append. The final branch uses `_display(f"* {action.text}")`. The `else:` branch at about line 1250 appends the `[olla harness: ...]` nudge as role user.
- The parser exports compiled regexes `TOOL_OPEN_RE, TOOL_CLOSE_RE, ARGS_OPEN_RE, ARGS_CLOSE_RE, FINAL_OPEN_RE, FINAL_CLOSE_RE`, all with re.IGNORECASE. `args_raw` is stripped for normal tools. It is left unstripped for `write_file` and `remember`, and stripped for `recall`.

Planner pre-verification: the planner applied rough versions of all 4 fixes to a scratch copy. The full suite then showed EXACTLY these 6 existing failures and nothing else (478 others passed):
- tests/test_debug.py::test_debug_log_when_enabled (fix 3)
- tests/test_debug.py::test_run_loop_logs_in_debug_mode (fix 3)
- tests/test_loop.py::test_run_loop_truncates_none_response_in_history (fix 1)
- tests/test_loop.py::test_run_loop_max_steps_no_final (fix 1)
- tests/test_loop.py::test_dry_run_none_response_prints_preview_and_stops (fix 1)
- tests/test_loop.py::test_repetition_guard_covers_every_non_final_response[no protocol tags here-response] (fix 1)

Fix 4 (canonical history) broke no existing test. It was also confirmed that `_prepare_action` returns kind `none` for all of these inputs after fix 1: `<tool>shell`, `"<tool>" + "x"*N`, `no <final>a</final><final>b</final>`, whitespace-only, `see <TOOL> here`, and `<think>only</think>`. It returns kind `final` with the stripped text for `  plain prose \n` and for `<think>hmm</think> The answer is 4`.

Grep note: use `/usr/bin/grep` because the rtk grep wrapper mangles output in this repo.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Debug output to stderr + canonical assistant history (fixes 3, 4)</name>
  <files>src/olla/debug.py, src/olla/loop.py, tests/test_debug.py, tests/test_loop.py</files>
  <behavior>
    - test_debug_log_when_enabled: `[DEBUG]`, the title, and `"key": "val"` appear in `capsys.readouterr().err`.
    - test_debug_log_when_disabled: both `.out` and `.err` are empty strings.
    - test_run_loop_logs_in_debug_mode: `[DEBUG]`, `Loop initialization`, `Step 1/1`, and `Raw model response` appear in `.err`. `Done` stays checked on `.out`, because it comes from the `* Done` final display.
    - New test_run_loop_tool_call_history_is_canonical: mock `olla.loop.ollama.chat` with side_effect `<tool>shell</tool><args>pwd` (no closing tag, as the stop sequence produces) and then `<final>done</final>`, and patch `olla.loop.run_shell`. The first assistant message in the second call's `messages` equals `<tool>shell</tool><args>pwd</args>`, so it ends with `</args>`. The final assistant entry equals `<final>done</final>`.
    - Optional test: a `write_file` call records history whose `<args>` payload matches `action.args_raw` byte for byte, including the leading path line and the content newline.
  </behavior>
  <action>
Fix 3, per fix_spec item 3: In `src/olla/debug.py`, add `import sys`. Pass `file=sys.stderr` to all three `print` calls in `debug_log`: the title-only line, the bold title line, and the per-line body. Leave `is_debug`, `set_debug`, `mask_secret`, the ANSI prefix, and the JSON formatting as they are.

Update `tests/test_debug.py` as described in <behavior>. Run `/usr/bin/grep -rn "DEBUG" tests/*.py tests/test_tools/*.py` to confirm that no other test reads debug text from `.out`. The planner's scratch run found only these two failures.

Fix 4, per fix_spec item 4: In `run_loop` in `src/olla/loop.py`, replace the single-line `history_content = ...` expression with a three-way choice:
- For `action.kind == "none"`, keep `truncate_output(content)`.
- For `action.kind == "final"`, use `f"<final>{action.text}</final>"`.
- For every other kind, use `f"<tool>{action.tool}</tool><args>{action.args_raw}</args>"`. This covers shell (including a malformed shell call), read_file, write_file, list_dir, grep_files, fetch_url, search_web, memory, and unknown.

Every non-final, non-none `_Action` already carries `tool` and `args_raw`. `args_raw` is unstripped for write_file and remember, so the payload round-trips exactly. Do not re-strip it. Keep the append statement itself, which Task 2 wraps with the empty-skip.

A side effect of this change is that reasoning-fallback content and surrounding prose no longer go into history. Add the new canonical-history test to `tests/test_loop.py`. Leave the existing tests as they are, because none of them fail under fix 4.

Commit directly on `main`. The user has approved this; do not stop at the protected-branch check. Stage only the four files. Use the message `fix(quick-260924-nbw): debug_log to stderr; canonical tool-call history` and end it with the Co-Authored-By trailer from the system attribution.
  </action>
  <verify>
    <automated>cd /home/nacs/Documents/git/olla && .venv/bin/python -m pytest -q tests/test_debug.py tests/test_loop.py && /usr/bin/grep -n 'file=sys.stderr' src/olla/debug.py && .venv/bin/ruff check src tests</automated>
  </verify>
  <done>`debug_log` writes only to stderr. The three debug tests assert on `.err`. Assistant history for a tool call ends with `</args>`, and history for a final answer is `<final>TEXT</final>`. test_debug.py and test_loop.py are green, ruff is clean, and the change is committed on main.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Tag-free prose becomes final + retry empty stream once (fixes 1, 2)</name>
  <files>src/olla/loop.py, tests/test_loop.py</files>
  <behavior>
    - `_prepare_action("  The file already exists.  \n")` returns kind `final` with text `The file already exists.`.
    - `_prepare_action("<think>hmm</think> The answer is 4")` returns kind `final` with text `The answer is 4`.
    - `_prepare_action("see <TOOL> here")` returns kind `none`, because the tag check is case-insensitive.
    - `_prepare_action("<tool>shell")` returns kind `none`, because it is a partial tag.
    - `_prepare_action("no <final>a</final><final>b</final>")` returns kind `none`.
    - `_prepare_action("   \n")` and `_prepare_action("<think>only</think>")` return kind `none`.
    - New run_loop prose test: mock `ollama.chat` to return plain prose once. The output contains `* <prose>` exactly once and `mock_chat.call_count == 1`. No `[olla harness:` message is in history. The assistant history entry equals `<final><prose></final>`, which comes from Task 1's canonical history.
    - New empty-then-final test: patch ONLY `olla.loop.get_provider` and return a MagicMock provider with `get_context_length.return_value = 8192` and `stream_chat.side_effect = [[], [StreamChunk(text="<final>ok</final>", is_thought=False)]]`. The output has `* ok` once. `stream_chat.call_count == 2`, which proves the retry happened inside one step with no nudge.
    - New empty-then-empty test: patch ONLY `olla.loop.get_provider`, with `stream_chat.side_effect = [[], [], [StreamChunk(text="<final>ok</final>", is_thought=False)]]`, and pass `session=SessionState(messages=[], scratchpad=Scratchpad(), read_snapshots={})`. After run_loop: `session.messages` has no assistant entry whose content is blank after `.strip()`, there is exactly one message starting with `[olla harness:`, and `stream_chat.call_count == 3`.
  </behavior>
  <action>
Fix 1, per fix_spec item 1, changes only `_prepare_action` in `src/olla/loop.py`. `parser.py` and `smoke.py` are not touched.

1. Widen the existing `from olla.parser import parse_response` line to also import `ARGS_CLOSE_RE, ARGS_OPEN_RE, FINAL_CLOSE_RE, FINAL_OPEN_RE, TOOL_CLOSE_RE, TOOL_OPEN_RE`.
2. Define a module-level tuple `_PROTOCOL_TAG_RES` that holds those six regexes. They are already case-insensitive.
3. In `_prepare_action`, compute `stripped = _strip_thinking(content)` once and pass it to `parse_response`.
4. In the `parsed["type"] == "none"` branch, compute `prose = stripped.strip()`. If `prose` is non-empty and none of `_PROTOCOL_TAG_RES` matches it (`.search`), return `_Action("final", "final", None, text=prose)`.
5. Otherwise, return the existing `none` action exactly as it is now, with the signature and text built from the raw `content`.

Leave the rest of `_prepare_action` unchanged. The dry-run preview then shows "Model would answer directly: ..." for prose. This is accepted per fix_spec.

Fix 2, per fix_spec item 2, touches `_stream_model_turn` and `run_loop`.
- Move the per-attempt streaming body into a small local or module helper. That body is the `for chunk in provider.stream_chat(messages)` loop, with its dimmed thought printing and the trailing `print()`. The helper returns `(content, thought_text)`.
- The trim check and the `_is_mocked` early return to `_call_model_for_loop` stay above the helper and run once. Do not change the mocked path.
- Inside the existing `try`, call the helper. If `content.strip()` and `thought_text.strip()` are both empty, call `debug_log("Empty model stream; retrying once")` and call the helper exactly once more.
- Then run the existing reasoning-fallback check and `return content` as they are now.
- The same except clauses cover both attempts. If the retry is also empty, the result is `""`.
- Keep the existing comment about non-thought chunks next to the accumulation line.

In `run_loop`, wrap the assistant-message append (introduced in Task 1) so it is skipped only when `action.kind == "none"` and `not content.strip()`. The retry-nudge `else:` branch is unchanged and still appends the nudge, because consecutive user messages are fine.

Update exactly the 4 fix-1 failures the planner found. Change their canned text into malformed tag text so they still exercise the nudge path:
- test_run_loop_max_steps_no_final: use content `<tool>shell`.
- test_run_loop_truncates_none_response_in_history: use `long_text = "<tool>" + "x" * (MAX_OBSERVATION_CHARS + 500)`. The existing truncate_output assertions still hold.
- test_dry_run_none_response_prints_preview_and_stops: use content `<tool>shell`. Assert `Model produced no valid <tool>/<final> tag: <tool>shell` in the output.
- test_repetition_guard_covers_every_non_final_response: change the `"no protocol tags here"` param to `"<tool>shell without args"`. Keep tool_name `response`.

Add the new tests from <behavior>. For the two stream tests, patch ONLY `olla.loop.get_provider`, exactly as test_run_loop_reasoning_mentioning_final_tag_does_not_loop does. If `ollama.chat` or `call_model` is also patched, `_is_mocked` short-circuits and `stream_chat` never runs. `SessionState` and `Scratchpad` are already importable in test_loop.py, since existing tests use them.

Commit directly on `main`. The user has approved this; do not stop at the protected-branch check. Stage only these two files. Use the message `fix(quick-260924-nbw): accept tag-free prose as final; retry empty stream once` and end it with the Co-Authored-By trailer.
  </action>
  <verify>
    <automated>cd /home/nacs/Documents/git/olla && .venv/bin/python -m pytest -q && .venv/bin/ruff check src tests</automated>
  </verify>
  <done>Plain prose ends the turn in one call with `* prose` shown once. Malformed tags, partial tags, and whitespace still get nudged. An empty stream is retried once, so there are 2 `stream_chat` calls with 1 final and no nudge. A double-empty stream leaves no blank assistant message in history. The full suite is green, ruff is clean, and the change is committed on main.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| model output to terminal | Untrusted model text (now including tag-free prose) is shown as a final answer |
| model output to chat history | The canonical envelope rebuilt from parsed fields is sent back to the model |
| debug output to stderr | Debug payloads may include config and secrets |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-nbw-01 | Tampering | `_prepare_action` prose-final to `_display` | low | mitigate | A prose final is display-only and never reaches shell, write, or confirm paths. It is printed through the existing `_display`/`_terminal_safe` escaping, which is covered by test_final_output_escapes_terminal_controls_and_surrogates. |
| T-nbw-02 | Elevation | Prose that is a partial tool attempt gets accepted as final | low | mitigate | Any protocol tag, open or close, in any case, keeps the `none` path, so a partial or malformed tool call is never silently swallowed. Tool execution still goes only through the parser, the safety check, and the confirm gate. |
| T-nbw-03 | Tampering | Canonical history envelope | low | accept | It uses `action.tool` and `action.args_raw` exactly as parsed. `write_file`/`remember` payloads round-trip unstripped, and no new parsing surface is added. |
| T-nbw-04 | Information disclosure | `debug_log` to stderr | low | accept | Only the output stream changes. Secrets still go through `mask_secret`, and debug stays opt-in (`OLLA_DEBUG`/`--debug`). |
| T-nbw-05 | Denial of service | Empty-stream retry | low | mitigate | There is exactly one retry per model turn, with no loop. The trim check does not run again, and a second empty result falls through to the nudge path, which is still bounded by max_steps and the repetition guard. |
</threat_model>

<verification>
- `.venv/bin/python -m pytest -q`: full suite green, with at least 484 tests plus the new ones
- `.venv/bin/ruff check src tests`: clean
- `git log --oneline -2` shows the two `fix(quick-260924-nbw)` commits on main
- Recommended manual check after merge (not blocking): run `OLLA_DEBUG=1 olla 2>/tmp/olla-debug.log` against the same OpenRouter model and task, and check that the dimmed reasoning line on stdout has no `[DEBUG]` text.
</verification>

<success_criteria>
- The live scenario from the evidence finishes in step 3 (prose accepted) instead of step 5, which saves two full-context round-trips.
- No empty assistant messages go into history. Tool-call history always ends with `</args>`.
- Debug output can be redirected apart from the answer stream.
- `parser.py` and `smoke.py` are unchanged (`git diff --stat HEAD~2 -- src/olla/parser.py src/olla/smoke.py` is empty).
</success_criteria>

<output>
Create `/home/nacs/Documents/git/olla/.planning/quick/260924-nbw-cut-wasted-round-trips-tag-free-prose-as/260924-nbw-SUMMARY.md` when done
</output>
