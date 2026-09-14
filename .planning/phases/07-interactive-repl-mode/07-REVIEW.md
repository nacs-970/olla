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
  warning: 5
  info: 2
  total: 8
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-09-15
**Depth:** standard
**Files Reviewed:** 12
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

## Info

### IN-01: Trailing whitespace

**File:** `src/olla/loop.py:338`
**Issue:** Blank line inside `_prepare_action()`'s `grep_files` branch contains trailing whitespace (`    ` after `recursive = True` block), inconsistent with the rest of the file.
**Fix:** Strip trailing whitespace (most `ruff`/formatter configs will auto-fix this).

### IN-02: Plaintext REPL history can capture secrets

**File:** `src/olla/repl.py:18-22, 65-69`
**Issue:** `PromptSession(history=FileHistory(...))` persists every line typed at the `>` prompt to `~/.olla_history` in plaintext, including any secret a user pastes as part of a task. This is already called out in a code comment as a known, accepted limitation for this phase, but is worth keeping on record as a real exposure surface (e.g. `.olla_history` is not obviously covered by typical `.gitignore`/backup-exclusion conventions the way shell history sometimes is).
**Fix:** No action required for this phase per the existing design note; consider a redaction pass or an opt-out flag in a future phase if this becomes a real user concern.

---

_Reviewed: 2026-09-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
