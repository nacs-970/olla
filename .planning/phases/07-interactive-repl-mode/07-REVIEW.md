---
phase: 07-interactive-repl-mode
reviewed: 2026-09-15T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/olla/repl.py
  - src/olla/loop.py
  - src/olla/cli.py
  - src/olla/tools/memory.py
  - src/olla/context_trim.py
  - pyproject.toml
  - uv.lock
  - tests/test_repl.py
  - tests/test_loop.py
  - tests/test_cli.py
  - tests/test_context_trim.py
  - tests/test_debug.py
findings:
  critical: 1
  warning: 6
  info: 5
  total: 12
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-09-15 (initial), 2026-09-15 (incremental pass, plan 07-04)
**Depth:** standard
**Files Reviewed:** 12 (full phase scope); 3 changed in the 07-04 incremental pass
**Status:** issues_found

## Summary

Reviewed the REPL controller, ReAct loop, CLI wiring, memory tool, and rolling
context-trim module introduced/touched in this phase. The codebase has a
deliberately strong, consistently-applied terminal-safety discipline
(`_terminal_safe()` / `_display()`) and a careful TOCTOU-resistant write-file
path carried over from earlier phases — most of the code is solid and well
tested. However, the new streaming code path in `_stream_model_turn()`
(the "single chokepoint" the trim-check was wired into) bypasses that exact
sanitization discipline for the model's live token stream, which is a real
regression against the codebase's own established threat model. There are
also several quality/robustness gaps in the new context-trim feature: it is
a documented no-op for the most common context-overflow scenario (a single
long-running task), the startup encoder warm-up is only wired into the REPL
entry point (not the one-shot CLI path it was designed to help), and its
failure handling is narrower than the surrounding code implies.

**Incremental pass — plan 07-04 (diff `b45b7341333b86788e5e1ab6bcd5848f7ec67bb0..HEAD`):**
This pass reviews only the files changed by gap-closure plan 07-04:
`src/olla/repl.py` (new `_build_key_bindings()` binding Alt+Enter to
newline-insert), `tests/test_loop.py` (new cross-turn stale-snapshot
regression test), and `tests/test_repl.py` (new tests for the key binding).
All 166 tests in `tests/test_repl.py` + `tests/test_loop.py` pass, and
`ruff check` is clean on the three changed files. The new functional code
is small and its behavior was verified both by the shipped tests and by
independent reproduction against the installed `prompt_toolkit==3.0.53`
source (see WR-06 below). No new Critical issues were found; CR-01 below
predates this diff and remains open in `src/olla/loop.py` (out of scope for
this incremental pass, not re-verified here). One new Warning and three new
Info items were found and are appended to their respective sections below
(IDs continue from the existing sequence: WR-06, IN-03..05).

## Critical Issues

### CR-01: Streamed model output bypasses terminal-escape sanitization

**File:** `src/olla/loop.py:577-583`

**Issue:** Every other piece of text that originates from, or has been
influenced by, the model or tool output is funneled through `_display()`,
which applies `_terminal_safe()` to strip/escape control characters and raw
ANSI sequences before printing (see `_display()` at `loop.py:60-62`, and its
use for shell output, file content, memory recall, web content, and even the
final `<final>` answer at `loop.py:1158`). This is the codebase's explicit,
documented defense against a model echoing attacker-controlled terminal
escape sequences that entered context via an untrusted observation (a file,
shell output, or web fetch tagged `<untrusted_*_content>`).

`_stream_model_turn()` — the "single chokepoint" every real (non-mocked)
model call goes through — does not follow this pattern. It prints each
streamed chunk directly:

```python
for chunk in provider.stream_chat(messages):
    if chunk.is_thought:
        print(f"\033[2m{chunk.text}\033[0m", end="", flush=True)
    else:
        print(chunk.text, end="", flush=True)
    full_response.append(chunk.text)
print()
```

`chunk.text` is raw, unsanitized model output. A small local model that
echoes or repeats content from a previously-read untrusted file (a very
common failure mode for the 0.6B-7B range this project targets) will have
any embedded terminal escape sequences in that file written straight to the
user's terminal in real time — before the same text is ever re-rendered
through `_display()`/`_terminal_safe()` (e.g. the `<final>` branch calls
`_display(action.text)` only *after* the content has already been streamed
raw). This defeats the sanitization boundary the rest of the file relies on,
and is exploitable purely by getting the model to read or quote
attacker-controlled content (a file, `fetch_url`/`search_web` result, or
shell output) back in its response.

**Fix:** Route streamed output through the same sanitizer, either per-chunk
or via a buffered pass, e.g.:

```python
for chunk in provider.stream_chat(messages):
    safe_text = _terminal_safe(chunk.text)
    if chunk.is_thought:
        print(f"\033[2m{safe_text}\033[0m", end="", flush=True)
    else:
        print(safe_text, end="", flush=True)
    full_response.append(chunk.text)  # keep raw text for parsing/history
```
Note `_terminal_safe()` currently assumes it receives a complete string and
scans character-by-character; a chunk boundary could in principle split a
multi-byte escape sequence across two `chunk.text` calls, so also consider
sanitizing per-line/per-flush rather than per-arbitrary-chunk if that proves
to matter in practice, or buffer full lines before printing.

## Warnings

### WR-01: `warm_encoder()` is never called on the one-shot CLI path

**File:** `src/olla/cli.py` (no call), contrast with `src/olla/repl.py:59`

**Issue:** The code and comments in `repl.py` and `context_trim.py` are
explicit that `warm_encoder()` exists specifically so the ~3.5s cold
`tiktoken.get_encoding()` network fetch is paid up front, with a visible
"preparing token counter..." message, "rather than landing unexplained
mid-conversation" (`repl.py:56-58`, `context_trim.py:112-118`). `cli.py`'s
one-shot path (`run_loop()` called directly with a `task`) never calls
`context_trim.warm_encoder()`. Since `_stream_model_turn()` calls
`context_trim.should_trim()` → `count_tokens_or_fallback()` → `get_encoder()`
on the very first step of every invocation, the exact "unexplained
mid-conversation" cold-fetch delay this feature was built to avoid still
occurs for every one-shot CLI task — it happens silently between the first
model call being dispatched and the user seeing the first streamed token.

**Fix:** Call `context_trim.warm_encoder()` once in `cli.py`'s `main()`
before invoking `run_loop()` for the one-shot task path (mirroring
`repl.py:59`), or move the warm-up into `run_loop()` itself so both entry
points get it for free.

### WR-02: Trim digest is spliced in as a `tool`-role message with no adjoining turn

**File:** `src/olla/context_trim.py:101-109`

**Issue:** `summarize_and_trim()` always replaces the trimmed span with a
single `{"role": "tool", ...}` message. After a trim, message[0] is
`system` and message[1] is this `tool`-role digest, immediately followed by
the next turn's `user` message. Some chat templates (including some Ollama
model templates) expect a `tool` message to be preceded by an `assistant`
message containing the corresponding tool call, and may reject, warn, or
silently mis-render a `system → tool → user` sequence that has no
originating assistant turn. Given `num_ctx` defaults to 8192 (small) and
this project explicitly targets small models across a wide range of
template strictness, a trim firing mid-REPL-session risks degrading or
breaking the next model call for some models, which would be hard to
diagnose from the user's side (it would look like the model just got worse
after a few turns).

**Fix:** Consider using `role: "user"` (wrapped in the existing
`<untrusted_summary_digest>` tag) for the injected digest instead of
`role: "tool"`, since `user`-role messages are essentially universally
accepted at any position in a chat template, and the untrusted-tag wrapping
already carries the provenance signal that `role: "tool"` was presumably
meant to add.

### WR-03: Rolling context trim is a no-op within any single task/turn

**File:** `src/olla/loop.py:1087` (`turn_start_index`), `src/olla/loop.py:552-567` (`_stream_model_turn`)

**Issue:** `protected_from_index` is fixed at the index of the just-appended
task message for the entire duration of one `run_loop()` call, and only ever
decreases (via the length-delta recompute) when an *earlier* turn's history
is trimmed — never when the *current* turn's own accumulated steps grow
large. This is confirmed intentional and is explicitly tested
(`tests/test_loop.py::test_run_loop_one_shot_trim_check_is_effectively_a_noop`,
named exactly for this behavior), but it means the trim feature only ever
helps *between* separate REPL turns. It provides zero protection against the
much more common overflow scenario: a single long-running agentic task
(one `run_loop()` call) that does many `read_file`/`shell`/`grep_files`
steps and accumulates a large `messages` list entirely within
`protected_from_index:`. For the one-shot CLI path this makes the feature
inert for its entire lifetime (also see WR-01). Given the project's stated
goal of staying responsive on small local models with small `num_ctx`
budgets, a single task that reads a few files can still blow the context
window with no mitigation from this mechanism.

**Fix:** At minimum, document this limitation clearly in user-facing
`--help`/README text so it isn't mistaken for general protection. Longer
term, consider allowing trimming within the current turn's own
already-completed step exchanges (e.g. protect only the most recent N steps
plus the original task, rather than the entire in-progress turn) so long
single-task runs get some benefit too.

### WR-04: `get_encoder()` only guards against network failures, not other plausible local failures

**File:** `src/olla/context_trim.py:34-39`

**Issue:** The `except requests.exceptions.RequestException:` clause is
explicitly scoped (per the docstring) to the offline/proxy-blocked case.
`tiktoken.get_encoding()` also reads/writes a local on-disk cache (by
default under a cache dir derived from `TIKTOKEN_CACHE_DIR`/`DATA_GYM_CACHE_DIR`
or a temp dir); a permissions error, full disk, or a corrupted/partial cache
file on that path raises `OSError`/`PermissionError`/other exceptions that
are not `requests.exceptions.RequestException` subclasses. Such an error
would propagate uncaught out of `get_encoder()` through
`count_tokens_or_fallback()` → `should_trim()` → `_stream_model_turn()`,
crashing the whole REPL/CLI turn mid-conversation — exactly the failure mode
this function's design comment says it exists to avoid ("that failure is
caught here specifically... reported once... so later calls... don't retry
the failed fetch").

**Fix:** Either broaden the guard to also catch `OSError` (covers
permission/disk/cache-corruption cases) or explicitly accept the narrower
scope but say so in the docstring rather than implying all "can't load the
encoder" failures are handled.

### WR-05: Production code branches on whether it is being unit-tested

**File:** `src/olla/loop.py:10, 232-234, 524-528, 572`

**Issue:** `loop.py` imports `unittest.mock.Mock` at module scope and defines
`_is_mocked(obj)` (`isinstance(obj, Mock) or hasattr(obj, "mock_calls")`),
then uses it in `call_model()` and `_stream_model_turn()` to decide whether
to take the "fake"/legacy `ollama.chat()`/`call_model()` path instead of the
real `provider.stream_chat()` streaming path. This means shipped production
code inspects its own call sites for test-mocking artifacts and changes
behavior accordingly — a test concern leaking into the runtime code path.
Besides being an unusual pattern to maintain (any object that happens to
expose a `mock_calls` attribute for unrelated reasons would silently divert
production traffic away from the real streaming path), it means the
streaming code path (where CR-01 lives) is *never exercised by most of the
loop-level tests*, since they mock `ollama.chat`/`call_model` and thus take
the non-streaming branch — reducing the odds that a regression like CR-01
gets caught by the existing test suite.

**Fix:** Prefer dependency injection (pass a `call_model`/`stream_chat`
callable into `run_loop()`/`_stream_model_turn()` with a production default)
over runtime mock-detection, so tests substitute behavior explicitly rather
than being auto-detected.

### WR-06: Alt+Enter-inserted lines render with no continuation prefix in single-line mode

**File:** `src/olla/repl.py:26-35, 79-83` (`_build_key_bindings()`, `PromptSession(multiline=False, key_bindings=...)`)

**Issue:** `_build_key_bindings()` binds Alt+Enter to
`event.current_buffer.insert_text("\n")`, and `PromptSession` is constructed
with `multiline=False`. This is verified to correctly capture the inserted
newline in the *returned* string (both the shipped
`test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session` test and
an independent repro against the installed `prompt_toolkit==3.0.53` confirm
`"line1\x1b\rline2\r"` returns `"line1\nline2"`). However, prompt_toolkit's
own `PromptSession._get_continuation()` (`shortcuts/prompt.py:1313-1327`)
only pads the continuation prefix for lines after the first when
`is_true(self.multiline)` is true:
```python
if continuation is None and is_true(self.multiline):
    continuation = " " * width
```
Since this session is constructed with `multiline=False`, `continuation`
stays `None` and `to_formatted_text(None, ...)` resolves to an empty
fragment (confirmed: `to_formatted_text(None, style=...) == FormattedText([])`).
The input window's height is unconstrained (`_get_default_buffer_control_height()`
returns a bare `Dimension()` unless a completion menu needs space, so the
second line does render, it is not clipped) — but it renders flush against
column 0 with none of the `" " * width` alignment padding a genuine
multiline session would show under the `> ` prompt. A user who presses
Alt+Enter to compose a multi-line task will see subsequent lines start at
the terminal's left edge, visually disconnected from the `> ` prompt above
them, rather than aligned as a continuation of the same input the way
prompt_toolkit's native multiline mode would render it. This is a display
gap in a mechanism this diff exists specifically to enable (multi-line
compose-then-submit), not a correctness bug in the captured/returned text.

**Fix:** Pass an explicit `prompt_continuation` callable/string to
`PromptSession` (e.g. matching the `> ` prompt width with spaces) so
Alt+Enter-inserted lines get the same visual alignment a `multiline=True`
session would provide, independent of the `multiline` flag's other
(submit-key) behavior.

## Info

### IN-01: Trailing whitespace

**File:** `src/olla/loop.py:338`
**Issue:** Blank line inside `_prepare_action()`'s `grep_files` branch contains trailing whitespace (`    ` after `recursive = True` block), inconsistent with the rest of the file.
**Fix:** Strip trailing whitespace (most `ruff`/formatter configs will auto-fix this).

### IN-02: Plaintext REPL history can capture secrets

**File:** `src/olla/repl.py:18-22, 65-69`
**Issue:** `PromptSession(history=FileHistory(...))` persists every line typed at the `>` prompt to `~/.olla_history` in plaintext, including any secret a user pastes as part of a task. This is already called out in a code comment as a known, accepted limitation for this phase, but is worth keeping on record as a real exposure surface (e.g. `.olla_history` is not obviously covered by typical `.gitignore`/backup-exclusion conventions the way shell history sometimes is).
**Fix:** No action required for this phase per the existing design note; consider a redaction pass or an opt-out flag in a future phase if this becomes a real user concern.

### IN-03: `_build_key_bindings()` silently overrides prompt_toolkit's own default Meta+Enter binding, undocumented

**File:** `src/olla/repl.py:26-35`
**Issue:** prompt_toolkit's built-in emacs key-binding set already binds
Alt+Enter (`"escape", "enter"`) to `accept-line` — i.e. "force submit,
regardless of mode" (`prompt_toolkit/key_binding/bindings/emacs.py:156`,
comment: `# Meta + Enter: always accept input.`). `_build_key_bindings()`
registers a new, unconditional (`filter`-less) binding for the exact same
key combination that instead inserts a newline, and per
`Application._create_key_bindings()`'s merge-priority order
(`application.py:1451-1503`), the session's own `key_bindings` argument
outranks the library's `_default_bindings`, so this repurposing wins (this
was independently verified against `prompt_toolkit==3.0.53`, and is also
what the shipped end-to-end pipe-input test demonstrates). The behavior
itself is correct and covered by a real-input test. What's missing is that
neither the code comment nor the docstring on `_build_key_bindings()`
mentions that this *replaces* an existing, differently-purposed default
binding rather than claiming previously-unbound key real estate — a future
maintainer reading only the docstring ("leaving plain Enter bound to
prompt_toolkit's own default... behavior") could reasonably assume Alt+Enter
itself was unbound before this change.
**Fix:** Add a one-line comment noting this binding intentionally overrides
prompt_toolkit's default `accept-line` binding for Alt+Enter, repurposing it
for newline-insertion since this REPL always uses `multiline=False`.

### IN-04: `_insert_newline(event)` has no type annotation, inconsistent with the rest of the file

**File:** `src/olla/repl.py:32`
**Issue:** Every other function signature in `repl.py` is fully type
annotated (e.g. `main_loop(model: str, max_steps: int, ...)`,
`_build_key_bindings() -> KeyBindings`), but `def _insert_newline(event) -> None:`
leaves `event` unannotated. The correct type is
`prompt_toolkit.key_binding.key_processor.KeyPressEvent`.
**Fix:** `def _insert_newline(event: KeyPressEvent) -> None:` and add the
import.

### IN-05: New tests couple to internal `mock.call_args` aliasing and `prompt_toolkit` `Binding` internals

**File:** `tests/test_loop.py` (new `test_run_loop_stale_snapshot_is_refused_across_repl_turn_boundary`), `tests/test_repl.py:55-65` (new `test_alt_enter_key_binding_inserts_newline_without_submitting`)
**Issue:** Two minor test-robustness points, neither of which currently
causes a false pass on the behavior each test is named for:
1. In the new `test_loop.py` test, `messages = mock_model.call_args_list[1].args[1]`
   captures a reference to `session_state.messages`, the same list object
   mutated in place throughout `run_loop()`. Because `mock.call_args`
   stores a reference (not a copy) of the arguments it was called with,
   inspecting it after the run completes reflects the *final* state of the
   shared list rather than a snapshot at call time — so the subsequent
   `any(...)` assertion checks "does this message exist anywhere in the
   final list" rather than "was this exact message present in what was
   sent to the second model call." It happens to be correct here because
   the stronger, order-sensitive assertions in the same test
   (`mock_write.assert_not_called()`, `mock_confirm.assert_not_called()`,
   and the direct `target.read_text()` check) are the ones actually
   carrying the regression-detection weight; the messages assertion is
   weaker than its position in the test suggests.
2. `test_alt_enter_key_binding_inserts_newline_without_submitting` asserts
   `len(kb.bindings) == 1` and `kb.bindings[0].keys == (Keys.Escape, Keys.ControlM)`,
   reaching into `KeyBindings`' internal `bindings` list/`Binding` shape.
   This is not part of prompt_toolkit's documented public API and is only
   protected by the `>=3.0,<4` pin in `pyproject.toml`; a minor-version
   internal refactor within that range could break this test without any
   behavior change. The same test's final two assertions
   (`insert_text.assert_called_once_with("\n")` /
   `validate_and_handle.assert_not_called()`) are also somewhat tautological
   given the handler's current one-line body — they mechanically restate
   what `_insert_newline()`'s source already shows, rather than exercising
   it through the framework. The real behavioral proof that Alt+Enter
   inserts-without-submitting lives in the companion
   `test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session` test,
   which drives a real `PromptSession` end to end — that test is the one
   that would actually catch a prompt_toolkit-internals regression here.
**Fix:** No action required — the real-input end-to-end test already
provides the load-bearing regression coverage for both points. Consider
trimming the internals-coupled assertions in
`test_alt_enter_key_binding_inserts_newline_without_submitting` (or keeping
it only as a fast unit-level smoke check) and treating the pipe-input test
as the canonical spec for this feature.

---

_Reviewed: 2026-09-15T00:00:00Z (initial); 2026-09-15 (incremental, plan 07-04)_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
