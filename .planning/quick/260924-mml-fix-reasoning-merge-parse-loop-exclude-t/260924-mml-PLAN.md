---
phase: quick-260924-mml
plan: quick-260924-mml
type: execute
wave: 1
depends_on: []
files_modified:
  - src/olla/parser.py
  - tests/test_parser.py
  - src/olla/loop.py
  - tests/test_loop.py
autonomous: true
requirements: [QUICK-260924-mml]

estimate:
  tokens: 60000
  raw_tokens: 45000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "Reasoning (thought) chunks from a provider stream are never concatenated into the content that parse_response sees, and never stored in assistant history, unless the empty-content fallback fires"
    - "A reasoning stream that mentions the final tag in prose, followed by content `<final>/home/nacs</final>`, produces the final answer /home/nacs on the first model call with no retry nudge"
    - "The retry nudge is still role user, starts with the `[olla harness:` marker, and contains no literal protocol tags (tool, args, final)"
    - "An args opener in prose (not directly preceded by a tool envelope) no longer opens an opaque payload span, so it cannot hide later final tags"
    - "write_file / remember / recall payloads that contain literal protocol-looking text are still opaque; duplicate outer finals and multiple tool blocks are still rejected"
    - "When non-thought content is empty or whitespace-only and the thought text alone parses to a final or tool, _stream_model_turn returns the thought text and writes a debug_log line; it never does this when content has non-whitespace text"
  artifacts:
    - path: "src/olla/parser.py"
      provides: "Envelope-anchored _args_payload_spans"
    - path: "src/olla/loop.py"
      provides: "Thought-excluding _stream_model_turn with empty-content reasoning fallback; harness-labeled retry nudge"
    - path: "tests/test_parser.py"
      provides: "Regression tests for prose args opener and opaque write_file payloads"
    - path: "tests/test_loop.py"
      provides: "Updated dimmed-thinking and nudge assertions; fallback tests; end-to-end reasoning-merge regression test"
  key_links:
    - from: "src/olla/loop.py:_stream_model_turn"
      to: "src/olla/loop.py:_prepare_action -> parser.parse_response"
      via: "return value (content only, or thought text via fallback)"
      pattern: "full_response"
    - from: "src/olla/loop.py:_stream_model_turn fallback"
      to: "src/olla/parser.py:parse_response"
      via: "parse_response(_strip_thinking(thought_text))"
      pattern: "_strip_thinking\\(thought"
---

<objective>
Fix the reasoning-merge parse loop seen with an OpenRouter reasoning model (prompt `pwd`, shell step worked, then every turn got the retry nudge and the final answer was garbage prose).

Four fixes from the orchestrator's fix spec (diagnosis already verified; do not re-investigate):
- A. `_stream_model_turn` appends only non-thought chunk text to the parsed/returned content.
- B. The retry nudge stays `role: "user"` but is clearly labeled as an automated harness message and has no literal protocol tags.
- C. `_args_payload_spans` opens a payload span only when a tool envelope comes directly before the args opener.
- D. Empty-content reasoning fallback in `_stream_model_turn`.

Purpose: the parser stops seeing reasoning prose, so small and reasoning models do not loop. It also removes reasoning tokens from history, which supports the project's core value of minimal per-turn token overhead.
Output: patched `src/olla/parser.py`, `src/olla/loop.py`, and tests. Two atomic commits.

Preserve original code and logic as much as possible (user golden rule). Change only what each fix needs.
</objective>

<execution_context>
@/home/nacs/.claude/gsd-core/workflows/execute-plan.md
@/home/nacs/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/olla/parser.py
@src/olla/loop.py
@src/olla/providers/openai_compat.py
@tests/test_parser.py
@tests/test_loop.py

Key facts gathered during planning:
- `src/olla/parser.py` line 31 `_args_payload_spans` currently treats every args opener as a span start and runs the span to the matching close or to end of content. The spans feed only the outer-final detection (lines 56-75). Tool parsing (line 80 `first_args_open`, the special-tool branch at lines 81-122, and the global counts at lines 124-127) does NOT use the spans.
- `src/olla/loop.py` line 224 `THINK_TAG_RE`/`_strip_thinking`; line 237 `_prepare_action` already calls `parse_response(_strip_thinking(content))`. `parse_response` is already imported in loop.py. `debug_log(title, content=None)` is imported from `olla.debug` (line 17).
- `src/olla/loop.py` lines 552-600 `_stream_model_turn`: the append of `chunk.text` to `full_response` sits outside the `if chunk.is_thought` branch (bug A). The mocked early return (`_is_mocked(call_model) or _is_mocked(ollama.chat)` then `_call_model_for_loop`) stays unchanged.
- `src/olla/loop.py` lines 1239-1247: the `else:` branch appends the retry nudge to `session.messages` (bug B). Line 1158 `history_content` stores the returned content in history.
- Tests that use `is_thought=True`: `tests/test_loop.py:2578` (`test_stream_model_turn_dimmed_thinking`, which locks in bug A and must be updated) and `tests/test_providers.py:104` (provider-level; confirm it does not go through `_stream_model_turn`, and leave it unchanged if it does not).
- The only test that matches the old nudge string is `tests/test_loop.py:294` (`test_run_loop_max_steps_no_final`).
- Use `/usr/bin/grep` directly for any grep during execution. The rtk wrapper mangles grep output in this repo.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Parser - only an envelope-preceded args opener opens a payload span (fix C)</name>
  <files>src/olla/parser.py, tests/test_parser.py</files>
  <read_first>
    - src/olla/parser.py (whole file, 165 lines)
    - tests/test_parser.py (existing 26 tests, especially the special-tool payload test around line 156 and the `<tool>remember<args>` case at line 99)
  </read_first>
  <behavior>
    - Test (i), bug-report regression: content is the prose line the model produced, followed by the real answer. Example: `the user keeps saying "No <tool> or <final> tag found. Respond using <tool>/<args> or <final> only." but I am using <final> tags. Nothing else.<final>/home/nacs</final>`. parse_response must NOT return type final with text starting `tag found`. The expected result is type none, because there are several outer final openers. That result is correct and safe. Assert both `type == "none"` and that no returned text contains `tag found`.
    - Test (ii): `Use <tool>/<args> format.\n<final>done</final>` returns `{"type": "final", "text": "done"}`.
    - Test (iii): a `write_file` call whose payload contains a literal final block, e.g. `<tool>write_file</tool>\n<args>notes.md\n<final>not an answer</final>\n</args>`, still returns type tool, tool `write_file`, and an args_raw that contains the literal final block. Also cover the unclosed form, with no args close tag (the stop-sequence case).
    - Optional extra: whitespace or case variants of the envelope (`<TOOL> write_file </TOOL>\n\n<ARGS>...`) still open a span.
  </behavior>
  <action>
Per fix C. Write the three regression tests first in tests/test_parser.py. Run them and confirm that (i) and (ii) fail against the current code (RED).

Then change ONLY `_args_payload_spans` in src/olla/parser.py:
- Add one new module-level compiled regex next to the existing ones, e.g. `TOOL_ENVELOPE_ARGS_RE`. It is case-insensitive (`re.IGNORECASE`, like the others) and matches: the tool opener, optional whitespace, a bare tool name `[A-Za-z0-9_-]+`, optional whitespace, an optional tool close tag, optional whitespace, then the args opener.
- In `_args_payload_spans`, iterate `TOOL_ENVELOPE_ARGS_RE.finditer(content)` instead of `ARGS_OPEN_RE.finditer(content)`. Each span starts at `match.end()` (just after the args opener). It ends at the next args close tag after that point, or at `len(content)` if there is none. That end rule is unchanged.
- Update the docstring in one line: spans now open only after a tool envelope, so prose that quotes the args tag cannot mask later tags.

Do NOT touch anything else in parser.py. `first_args_open`, the special-tool branch, the suffix check, the global tool/args counts, and the final-selection logic all stay exactly as they are. Duplicate outer finals and multiple tool blocks must still be rejected. Fix C only changes which final openers count as outer.

Run the full test_parser.py suite. Every existing test must still pass, together with the new ones (GREEN). Commit atomically: `fix(quick-260924-mml): anchor args payload spans to tool envelope`, with a body that explains that a prose args mention used to open an unterminated span (the args close tag is the stop sequence), which hid the real final block.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest -q tests/test_parser.py &amp;&amp; .venv/bin/ruff check src tests</automated>
  </verify>
  <done>All previous test_parser.py tests plus the new (i), (ii), and (iii) tests pass. `_args_payload_spans` is the only function changed in parser.py. ruff is clean. There is one commit for this task.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Loop - exclude thought chunks from content, harness-labeled nudge, empty-content reasoning fallback (fixes A, B, D)</name>
  <files>src/olla/loop.py, tests/test_loop.py</files>
  <read_first>
    - src/olla/loop.py lines 224-243 (`_strip_thinking`, `_prepare_action`), lines 552-600 (`_stream_model_turn`), lines 1150-1250 (run_loop step body, `history_content`, retry nudge)
    - tests/test_loop.py lines 275-296 (`test_run_loop_max_steps_no_final`), lines 2566-2625 (`test_stream_model_turn_dimmed_thinking`, `test_stream_model_turn_no_thinking_produces_no_live_output`, `test_run_loop_final_answer_prints_once_with_marker`)
    - tests/test_providers.py around line 104 (the only other `is_thought=True` user; confirm it is provider-level and unaffected by A/D)
  </read_first>
  <behavior>
    - A: `test_stream_model_turn_dimmed_thinking` now expects `result == "<final>Hello world</final>"`. The thought text is still rendered live and dimmed (the existing capsys assertions stay).
    - B: `test_run_loop_max_steps_no_final` finds corrective messages by the `[olla harness:` marker (still `role == "user"`, still 2 of them). It also asserts that each corrective message's content contains none of the literal tag strings for tool, args, or final.
    - D fires: stream = thought chunk containing `<final>x</final>` plus no non-thought chunks (or only whitespace chunks). `_stream_model_turn` returns the thought text, and `olla.loop.debug_log` is called once for the fallback (patch it with mocker and assert).
    - D does not fire when content is non-empty: thought `<final>x</final>` plus content `plain text` returns `plain text`.
    - D does not fire when the thought is ambiguous: thought with two final blocks plus empty content returns the empty/whitespace content, not the thought text.
    - End-to-end regression: patch `olla.loop.get_provider` with a MagicMock provider, the same way `test_run_loop_final_answer_prints_once_with_marker` does. Do NOT patch `olla.loop.ollama.chat` or `call_model`, because `_is_mocked` would then take the early-return path and skip the fixed code. The stream has one thought chunk that mentions the final tag in prose (e.g. `I should answer with <final> tags now.`), then a content chunk `<final>/home/nacs</final>`. Assert that `* /home/nacs` appears exactly once in the output and that `mock_provider.stream_chat.call_count == 1` (no nudge loop). Do NOT assert that the final tag is absent from the output: the dimmed thought text is printed live and contains it.
  </behavior>
  <action>
Write or update the tests listed in behavior first, and confirm that the new ones fail (RED). Then apply the three fixes in src/olla/loop.py.

Fix A (in `_stream_model_turn`): add a second accumulator for thought text, e.g. `thought_parts: list[str]`. In the stream loop, append `chunk.text` to `thought_parts` inside the existing `if chunk.is_thought:` branch, and append to `full_response` only for non-thought chunks (an `else`). Keep the dimmed live print exactly as it is. Keep the existing comment about non-thought chunks next to the non-thought append.

Fix D (same function, right after the stream loop and the existing bare print, before returning): join both accumulators into `content` and `thought_text`. If `content.strip()` is empty, and `thought_text.strip()` is non-empty, and `parse_response(_strip_thinking(thought_text))["type"] != "none"`, then call `debug_log` with a short title such as "Empty content; using reasoning fallback" and a preview of the thought text, and return `thought_text`. In every other case return `content`. Never use the fallback when content has any non-whitespace text. No extra gating is needed: a tool call taken from reasoning still goes through `_prepare_action`, the safety check, and the confirm gate in run_loop.

The mocked early-return path (`_is_mocked(call_model) or _is_mocked(ollama.chat)` then `_call_model_for_loop`) and the exception handlers stay unchanged.

Fix B (the run_loop `else:` branch around line 1239): keep `"role": "user"`, because mid-conversation system messages break some chat templates such as Gemma. Replace only the content string with: `[olla harness: automated format check, not a message from the user] Your last reply contained no valid tool call or final answer outside your reasoning. Reply again with exactly one tool block or one final block, formatted as the system prompt shows.` It contains no literal protocol tags. Do NOT change the user-facing display strings (the `_preview_action` "no valid tag" message and the max-steps display). They go to the terminal, not to the model.

Update `test_stream_model_turn_dimmed_thinking` to expect `"<final>Hello world</final>"` and revise its docstring. Update the marker match in `test_run_loop_max_steps_no_final`. Run the full suite and ruff (GREEN).

Commit atomically: `fix(quick-260924-mml): keep reasoning out of parsed content; label retry nudge`. The body must say that `test_stream_model_turn_dimmed_thinking` previously asserted the merged string `considering...<final>Hello world</final>`, which locked in the bug: reasoning was concatenated into parsed content and history, so prose final mentions produced multiple outer finals and caused the nudge loop (present since 7b5c413). Also mention the harness-labeled nudge and the empty-content fallback.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest -q &amp;&amp; .venv/bin/ruff check src tests</automated>
  </verify>
  <done>The full pytest suite is green, including the updated dimmed-thinking and nudge tests, the three fallback tests, and the end-to-end reasoning-merge regression test. ruff is clean. Only `_stream_model_turn` and the nudge content changed in loop.py. There is one commit for this task.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| model output -> parser | Untrusted model text (content, and via fix D, reasoning) is interpreted as protocol tags |
| parsed tool call -> shell/file tools | Parsed actions execute commands and write files |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-mml-01 | Elevation of Privilege | `_stream_model_turn` fallback D (tool calls taken from reasoning) | medium | mitigate | The fallback fires only when content is empty/whitespace AND the reasoning alone parses unambiguously (not type none). The returned text still goes through `_prepare_action`, the existing safety blocklist check, and the confirm gate in run_loop, exactly like normal content. The fallback is logged via debug_log. |
| T-mml-02 | Tampering | `parser._args_payload_spans` (prose misread as a protocol tag) | medium | mitigate | Spans open only after a strict tool envelope (bare `[A-Za-z0-9_-]+` name). Duplicate outer finals and multiple tool blocks are still rejected, so ambiguous output resolves to type none (a safe retry), never to an executed action. Regression tests (i) to (iii) cover this. |
| T-mml-03 | Spoofing | Retry nudge (role user) | low | mitigate | The nudge content is prefixed `[olla harness: automated format check, not a message from the user]` so the model does not treat it as a human instruction. It has no protocol tags that could be quoted back as a tool call. |
| T-mml-04 | Information Disclosure | Reasoning text in history | low | accept | Fix A removes reasoning from history in the normal case. In the fallback case the history holds only reasoning that already parsed as an action, which is the same exposure as normal content. |
</threat_model>

<verification>
- `.venv/bin/python -m pytest -q`: full suite green
- `.venv/bin/ruff check src tests`: clean
- `git log --oneline -2` shows the two task commits
</verification>

<success_criteria>
- The REPL scenario (reasoning that mentions the final tag, then content `<final>/home/nacs</final>`) answers `/home/nacs` on the first call, with no nudge loop. The end-to-end test proves this.
- Reasoning is excluded from parsed content and history, except for the guarded empty-content fallback.
- The nudge is harness-labeled, role user, and free of protocol tags.
- A prose args mention can no longer hide later tags. All existing parser strictness is preserved.
</success_criteria>

<output>
Create `.planning/quick/260924-mml-fix-reasoning-merge-parse-loop-exclude-t/260924-mml-SUMMARY.md` when done.
</output>
