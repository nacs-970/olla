# Phase 7: Interactive REPL Mode - Pattern Map

**Mapped:** 2026-09-09
**Files analyzed:** 9 (4 new, 5 modified)
**Analogs found:** 7 / 9 (2 have no in-codebase analog — new terminal/tokenizer machinery)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/olla/repl.py` (new) | controller / entry-module | event-driven (interactive input loop) | `src/olla/smoke.py` | role-match |
| `src/olla/context_trim.py` (new) | utility/service | transform (count → decide → summarize) | `src/olla/providers/openai_compat.py::get_context_length` (fallback shape) + `loop.py::truncate_output` (budget-limit shape) | role-match (partial — counting itself has no analog) |
| `src/olla/loop.py` (modified: `run_loop()` signature + trim hook) | controller / core loop | request-response (per-step) | itself (existing `run_loop()`, `_stream_model_turn()`, `_record_*_observation()`) | exact (self-modification) |
| `src/olla/cli.py` (modified: no-TASK branch) | controller / CLI entry | request-response (dispatch) | existing `--smoke-test` branch in the same file (`cli.py:59-63`) | exact |
| `src/olla/tools/memory.py` (modified: docstrings) | model | CRUD (in-memory) | itself (existing `Scratchpad`) | exact (self-modification) |
| `pyproject.toml` (modified: deps) | config | — | itself (existing `dependencies` list) | exact |
| `tests/test_repl.py` (new) | test | request-response / event-driven | `tests/test_cli.py:15-27` (dispatch mocking) + `tests/test_providers.py:185-196` (constructor-arg assertion shape) | role-match |
| `tests/test_context_trim.py` (new) | test | transform | `tests/test_loop.py:2402-2424` (fake-response iterator harness) | role-match |
| `tests/test_loop.py` (modified: session-state persistence cases) | test | request-response | `tests/test_loop.py:2402-2424` (existing) | exact |
| `tests/test_cli.py` (modified: new REPL-branch case + rewrite of `test_missing_task_raises_usage_error`) | test | request-response | itself (existing `test_missing_model_raises_usage_error`, `test_task_and_model_call_run_loop_with_defaults`) | exact |

## Pattern Assignments

### `src/olla/repl.py` (new — controller, event-driven)

**Analog:** `src/olla/smoke.py` (role-match — closest precedent for "a module `cli.py` dispatches to that owns its own `get_provider()` call, builds its own `messages`, prints, and returns"). **No analog exists** in this codebase for the actual terminal machinery (`PromptSession`, `FileHistory`, `KeyBindings`/double-Ctrl+C, `patch_stdout`) — for that machinery, follow RESEARCH.md's "Code Examples" section verbatim (Context7-sourced, verified against installed `prompt_toolkit==3.0.53`), not a codebase analog.

**Module docstring + imports pattern** (`src/olla/smoke.py:1-13`):
```python
"""Format-compliance smoke test (D-07/D-08): three-way classifier + runner."""

import re
from unittest.mock import Mock

from olla.loop import call_model
from olla.prompts import SYSTEM_PROMPT
from olla.providers import ProviderError, get_provider
```
Follow this shape for `repl.py`: a one-line module docstring naming the phase/decision IDs it implements, plain top-of-file imports (no lazy imports), pulling `get_provider`/`ProviderError` from `olla.providers` and `run_loop` from `olla.loop`.

**Provider init + error handling pattern** (`src/olla/smoke.py:52-59`, and mirrored in `run_loop()` at `loop.py:1009-1015`):
```python
try:
    provider, _ = get_provider(
        model=model, api_key=api_key, base_url=base_url
    )
except ProviderError as error:
    print(f"Smoke test failed to initialize model '{model}': {error}")
    return
```
Copy this exact try/except/print/return shape for both the REPL's initial launch-time provider init and the `/model <name>` mid-session re-init (D-06) — `/model` should call `get_provider()` again through this same path, not a looser validator (RESEARCH.md Security Domain, V5).

**`_is_mocked()` duplication convention** (`src/olla/smoke.py:33-34`, mirrored in `loop.py`):
```python
def _is_mocked(obj: object) -> bool:
    return isinstance(obj, Mock) or hasattr(obj, "mock_calls")
```
The codebase's convention is to **duplicate** this helper locally per module rather than import it from `loop.py` — follow the same convention in `repl.py`/`context_trim.py` if a test-mocking guard is needed there.

**Dispatch-from-`cli.py` pattern to mirror** (`src/olla/cli.py:59-63`, the `--smoke-test` branch — the exact analog for the new no-TASK branch):
```python
if smoke_test:
    if not model:
        raise click.UsageError("--smoke-test requires --model")
    run_smoke_test(model, api_key=api_key, base_url=base_url)
    return
```
The new no-TASK REPL branch in `cli.py` should follow this identical guard → call-other-module → `return` shape, placed **before** the existing `if not task: raise click.UsageError(...)` check (`cli.py:65-66`), not after — a no-TASK invocation must launch the REPL instead of ever reaching that error.

**No-analog terminal machinery (use RESEARCH.md Code Examples directly):**
- `PromptSession(history=FileHistory(...), multiline=...)` construction — RESEARCH.md lines 353-363.
- Canonical Ctrl+C/Ctrl+D loop shape — RESEARCH.md lines 233-251.
- `patch_stdout()` wrapping around each turn's `run_loop()` call (D-14) — RESEARCH.md lines 365-375.
- Double-Ctrl+C via custom `KeyBindings` (D-12) — no verified code example in RESEARCH.md beyond the citation; implement per the documented `c-c` binding + timestamp-threshold approach described in RESEARCH.md Pattern 2 (lines 230-256), spot-check exact `event.app.exit(...)` call against installed `prompt_toolkit==3.0.53` (RESEARCH.md Assumption A2).

---

### `src/olla/context_trim.py` (new — utility, transform)

**Analog for the num_ctx source (do not re-hardcode):** `src/olla/providers/ollama.py:17-19` and `src/olla/providers/openai_compat.py:83-104`.
```python
# src/olla/providers/ollama.py:17-19
def get_context_length(self) -> int:
    """Return configured context length."""
    return self.num_ctx
```
Call `provider.get_context_length()` for the trim budget (RESEARCH.md "Don't Hand-Roll" table) — this method already exists and is currently dead code; do not reintroduce a second hardcoded `8192`.

**Analog for graceful external-fetch degradation (the tiktoken network-failure fallback, Pitfall 2):** `src/olla/providers/openai_compat.py:83-104` — the codebase's canonical "external fetch, cache on instance, `except (...)`: assign hardcoded fallback and return" shape:
```python
def get_context_length(self) -> int:
    """Return context length for model, fetching dynamically if possible."""
    if self._context_length is not None:
        return self._context_length
    try:
        with httpx.Client(timeout=5.0) as client:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = client.get(f"{self.base_url}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models_list = data.get("data", [])
                for m in models_list:
                    if m.get("id") == self.model and "context_length" in m:
                        self._context_length = int(m["context_length"])
                        return self._context_length
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
        self._context_length = 128000
        return self._context_length
    self._context_length = 128000
    return self._context_length
```
Copy this shape for the `tiktoken` encoder init: try the real fetch/init once, cache it, `except requests.exceptions.RequestException:` fall back to the char-count proxy and print a one-line warning (Pitfall 2) — do not let the exception propagate uncaught, and do not silently absorb it inside `_stream_model_turn()`'s broad handler either (see Shared Patterns below).

**Analog for the budget-limit pure-function shape:** `src/olla/loop.py:485-495` (`truncate_output`):
```python
def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    """Truncate text to a head+tail preview if it exceeds `limit` chars."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if len(text) <= limit:
        return text
    head_len = limit // 2
    tail_len = limit - head_len
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len else ""
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"
```
Follow this style for the trim-decision helper: pure function, explicit numeric limit parameter with a sane module-level default constant (mirror `MAX_OBSERVATION_CHARS = 2000` at `loop.py:37`), deterministic behavior, no side effects — the token-counting/trim-decision function should be equally pure and testable in isolation.

**No analog for the counting mechanism itself:** nothing in this codebase does BPE/token counting today — `tiktoken.get_encoding(...)` + `enc.encode(...)` is genuinely new; use RESEARCH.md's verified code example (lines 377-388) as the starting point, not a codebase pattern.

**Open design point to carry into the plan, not resolve here:** if the plan adopts Open Questions §2 option (a) (tag the digest as untrusted), the digest-insertion pattern to copy is `_record_web_observation` below — do not silently pick an option; the plan must surface this explicitly per RESEARCH.md.

---

### `src/olla/loop.py` (modified — `run_loop()` signature + trim hook)

**Analog:** itself — the existing state-construction block and step loop are the pattern to extend, not replace.

**Current state-construction block to make conditional** (`loop.py:1032-1050`):
```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": task},
]
if dry_run:
    debug_log("Executing dry run turn")
    content = _stream_model_turn(provider, messages, model=resolved_model)
    if content is None:
        return
    action = _prepare_action(content)
    debug_log("Dry run action parsed", {"kind": action.kind, "tool": action.tool})
    _preview_action(action, yes=yes)
    return

scratchpad = Scratchpad()
read_snapshots: dict[Path, _FileReadSnapshot] = {}
previous_signature: tuple | None = None
repeat_count = 0
untrusted_observation_seen = False
```
**Sequencing hazard (verified this session, not flagged in RESEARCH.md):** the `dry_run` early-return sits *above* the `scratchpad`/`read_snapshots` construction. D-13 fixes `--dry-run` for the whole REPL session, meaning a `olla --dry-run` REPL session still needs injected session state threaded through *before* this branch — otherwise dry-run REPL turns silently get no session state at all. When adding the optional `messages`/`scratchpad`/`read_snapshots`/`untrusted_observation_seen` parameters, the injection/default-construction logic must run before the `if dry_run:` branch, not after it.

**`previous_signature`/`repeat_count` reset (D-03):** these two must **always** reset fresh at `run_loop()` entry regardless of one-shot-vs-session mode — do not make these injectable, unlike the other three state pieces (RESEARCH.md Pattern 1).

**`untrusted_observation_seen` propagation gap (RESEARCH.md Pattern 1, verified at `loop.py:1104-1163`):** this is a plain `bool`, reassigned via `X or untrusted_observation_seen` throughout the step loop, and `run_loop()` returns `None` — there is no channel today to hand the updated value back to a REPL caller. Pick one: (a) change `run_loop()`'s return type, or (b) wrap it in the same mutable session-state container as `messages`/`scratchpad`/`read_snapshots`. This is a required design choice for the plan, not optional.

**Model call sites requiring the trim hook (all three, per Pattern 3):**
- `loop.py:1069` — `_stream_model_turn(provider, messages, model=resolved_model)` inside the main step loop (primary site).
- `loop.py:1038` — same call in the `dry_run` branch.
- `loop.py:522-531` — `_call_model_for_loop()`/`call_model()` legacy direct-`ollama.chat()` path.

---

### `src/olla/cli.py` (modified — no-TASK branch)

**Analog:** the existing `--smoke-test` branch in the same file (`cli.py:59-63`, quoted above under `repl.py`). Insert the new branch using the identical guard/dispatch/return shape, positioned before the `if not task:` UsageError check at `cli.py:65-66` (which must remain for the case where `task` is missing *and* `--smoke-test` wasn't passed *and* the REPL path wasn't taken for some other reason — but a bare `olla` with no args should hit the new REPL branch first).

**Constraint this modification must preserve (verified in `tests/test_cli.py:36-53`):**
```python
def test_task_and_model_call_run_loop_with_defaults(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()
    result = runner.invoke(main, ["do something", "--model", "some-model"])
    assert result.exit_code == 0
    mock_run_loop.assert_called_once_with(
        task="do something",
        model="some-model",
        max_steps=50,
        system_prompt=SYSTEM_PROMPT,
        yes=False,
        dry_run=False,
        api_key=None,
        base_url=None,
        debug=False,
    )
```
This test asserts the **exact, exhaustive** kwarg set passed to `run_loop()` from the one-shot CLI path. Adding optional session-state parameters to `run_loop()`'s signature (D-01) is only safe if `cli.py`'s existing one-shot call site does **not** start passing them (e.g. `messages=None`, `scratchpad=None`, ...) — if it does, this exact-match assertion breaks and must be updated. Treat "does the one-shot call site's kwargs change" as a decision the plan must make explicitly, not a side effect to discover during implementation.

---

### `src/olla/tools/memory.py` (modified — docstring contract)

**Analog:** itself. **The invocation-lifetime contract exists in two places, not one** (RESEARCH.md's Pitfall 5 names only line 70):
- Module docstring, `memory.py:1`: `"""Invocation-local scratchpad memory with explicit remember and recall calls."""`
- Class docstring, `memory.py:70`: `"""Store notes for the lifetime of one owning run-loop invocation."""`

Both need updating to reflect the dual contract (one-shot CLI: per-invocation, unchanged; REPL: per-session, reset only by `/clear` per D-16). `Scratchpad.__init__` itself (`memory.py:72-73`) needs no code change — the lifetime guarantee today comes entirely from `run_loop()` always constructing a fresh instance, not from anything inside the class.

---

### `pyproject.toml` (modified — dependencies)

**Analog:** itself — existing `dependencies` list shape (`pyproject.toml:12-18`):
```toml
dependencies = [
    "ollama>=0.6.2",
    "click>=8.1,<9",
    "rich>=13",
    "httpx>=0.27.0",
    "tomli>=1.1.0; python_version < '3.11'",
]
```
Add `"prompt_toolkit>=3.0,<4"` and `"tiktoken>=0.11,<1"` to this list following the same `name>=X,<Y` pin style already used for `click`. Both packages are flagged `SUS` by the automated legitimacy gate (RESEARCH.md Package Legitimacy Audit) — the plan must include a `checkpoint:human-verify` task before this dependency addition is executed, and a follow-up `uv sync` (or equivalent re-lock) step, since editing `pyproject.toml` alone does not update `uv.lock`/the editable install.

---

### `tests/test_repl.py` (new)

**Analog 1 — dispatch/mocking shape:** `tests/test_cli.py:15-27`:
```python
def test_missing_model_raises_usage_error(mocker):
    mock_run_loop = mocker.patch("olla.cli.run_loop")
    runner = CliRunner()
    result = runner.invoke(main, ["do something"])
    assert result.exit_code != 0
    assert "--model" in result.output
    mock_run_loop.assert_not_called()
```
Use `mocker.patch("olla.repl.run_loop")`/`mocker.patch("olla.repl.get_provider")` in the same style to test slash-command dispatch (`/model`, `/exit`, `/quit`, `/clear`) without touching a real model or terminal.

**Analog 2 — asserting constructor-call args (for `PromptSession(...)` construction):** `tests/test_providers.py:185-196`:
```python
mock_resp = MagicMock()
mock_resp.status_code = 200
mock_resp.json.return_value = {"data": [...]}
with patch("httpx.Client.get", return_value=mock_resp):
    context_len = provider.get_context_length()
    assert context_len == 131072
```
Use the same `MagicMock` + `with patch("olla.repl.PromptSession", ...)` shape to assert `PromptSession` is constructed with `history=FileHistory(...)` and the expected `multiline` value, and to simulate `session.prompt()` raising `KeyboardInterrupt`/`EOFError` for the exit-semantics tests (RESEARCH.md test map row: `pytest tests/test_repl.py -k exit_semantics -x`).

---

### `tests/test_context_trim.py` (new)

**Analog — fake-response iterator + call-capture harness:** `tests/test_loop.py:2402-2424`:
```python
responses = iter([
    {"message": {"content": tool_content}},
    {"message": {"content": "<final>done</final>"}},
])
messages_by_call = []

def fake_chat(**kwargs):
    messages_by_call.append([message.copy() for message in kwargs["messages"]])
    return next(responses)

mocker.patch("olla.loop.ollama.chat", side_effect=fake_chat)
```
Use the same iterator/side_effect/copy-and-capture pattern to test the summarization call (mock `provider.chat()` to return a canned digest string) and to assert the digest replaces dropped turns while the system prompt and in-progress turn survive (D-08). For the `tiktoken`-failure fallback test, mock `tiktoken.get_encoding` to raise `requests.exceptions.RequestException` directly (RESEARCH.md test map row) — this mirrors the `except (httpx.HTTPError, ...)` fallback-assignment shape already proven in `openai_compat.py:83-104`.

---

### `tests/test_loop.py` (modified — new session-persistence cases)

**Analog:** the same harness at `tests/test_loop.py:2402-2424` — call `run_loop()` twice with the same injected `Scratchpad`/`messages`/`read_snapshots` instances (not two fresh ones) and assert state (e.g. a `remember`ed key, or a `read_snapshots` entry) is visible on the second call. This is the existing codebase's closest precedent for "drive `run_loop()` more than once and inspect what carried over between calls," even though today it's used for a single-call multi-step scenario rather than two separate `run_loop()` invocations.

---

### `tests/test_cli.py` (modified)

**Analog:** itself — `test_task_and_model_call_run_loop_with_defaults` (`test_cli.py:36-53`) is the pattern for the new "no TASK → REPL launched" case; use the identical `mocker.patch(...)` + `CliRunner().invoke(main, [...])` + `assert_called_once_with(...)`/`assert_not_called()` shape.

**Required deletion, not just addition (verified this session — not flagged in RESEARCH.md's test map):** `test_missing_task_raises_usage_error` (`test_cli.py:26-33`) currently asserts that invoking `main` with no args raises a `UsageError` containing `"TASK"`. Under REPL-01, a no-TASK invocation must launch the REPL instead — this existing test's assertion becomes **false** and must be rewritten (not merely supplemented) to assert the REPL entry point is invoked instead of a `UsageError`.

---

## Shared Patterns

### Provider factory reuse (D-06)
**Source:** `src/olla/providers/__init__.py:9-91` (`get_provider()`)
**Apply to:** `repl.py` initial launch and every `/model <name>` mid-session switch — same factory call, no second/looser model-string validator (RESEARCH.md Security Domain V5).

### Provider-init error handling
**Source:** `src/olla/smoke.py:52-59` / `src/olla/loop.py:1009-1015` (identical try/except/print/return shape across both existing call sites)
**Apply to:** `repl.py` — both initial launch and `/model` re-init should follow this exact shape, not a bespoke error path.

### `_is_mocked()` duplication convention
**Source:** `src/olla/smoke.py:33-34` (and the equivalent in `loop.py`)
**Apply to:** Any new module (`repl.py`, `context_trim.py`) that needs a test-mocking guard — duplicate locally, do not import cross-module.

### External-fetch-with-cached-fallback shape
**Source:** `src/olla/providers/openai_compat.py:83-104`
**Apply to:** `context_trim.py`'s `tiktoken` encoder initialization — try once, cache, catch the specific exception type, fall back to a hardcoded/degraded value, never let it propagate uncaught or land inside `_stream_model_turn()`'s broad `except Exception` (`loop.py:562-564`), which would silently swallow the trim step and misattribute the failure as "Model request failed."

### Untrusted-content tagging (existing WEB-04 system — open interaction with D-07, not to be broken silently)
**Source:** `src/olla/loop.py:421-483` — four wrapper functions, each appending `{"role": "tool", "content": "Observation: <untrusted_X>...\n</untrusted_X>"}`:
```python
def _record_web_observation(messages: list[dict], preview: str) -> None:
    """Record fetched/searched web content as explicitly untrusted tool data."""
    debug_log("Web observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_web_content>\n"
                f"{preview}\n"
                "</untrusted_web_content>"
            ),
        }
    )
```
Trusted observations use `{"role": "user", "content": f"Observation: {preview}"}` instead (`_record_observation`, `loop.py:414-418`) — no tag wrapper.
**Apply to:** the summarization digest, **if and only if** the plan resolves Open Questions §2 by choosing to tag the digest as untrusted (e.g. a new `<untrusted_summary_digest>` tag, following this exact wrapper shape). This is a decision point the plan must surface explicitly, not something to copy silently — the planner may instead choose to exclude untrusted-tagged turns from summarization entirely (evict raw instead) or harden the summarization prompt. All three options are named in RESEARCH.md Common Pitfalls §4 / Open Questions §2.

### Test dispatch/mocking style
**Source:** `tests/test_cli.py:15-27`, `tests/test_providers.py:185-196`, `tests/test_loop.py:2402-2424`
**Apply to:** all four new/modified test files — `mocker.patch("olla.<module>.<name>")` + `CliRunner`/direct-call + `assert_called_once_with(...)`/`assert_not_called()`, and the fake-response-iterator + message-capture harness for anything driving `run_loop()`/`provider.chat()` more than once.

## No Analog Found

| File/Concern | Role | Data Flow | Reason |
|---|---|---|---|
| `PromptSession`/`FileHistory`/`KeyBindings`/`patch_stdout` construction and wiring (`repl.py`) | controller | event-driven | No terminal-input/REPL machinery exists anywhere in this codebase today — use RESEARCH.md's verified Code Examples (lines 233-388), sourced from Context7 against installed `prompt_toolkit==3.0.53`, not a codebase pattern. |
| `tiktoken` token-counting function itself (`context_trim.py`) | utility | transform | No tokenization/counting code exists in this codebase — `openai_compat.py`'s fetch-and-cache *shape* is a fair analog for the surrounding error-handling, but the counting mechanism (`enc.encode(...)`) is genuinely new; use RESEARCH.md's verified code example (lines 377-388). |

## Metadata

**Analog search scope:** `src/olla/` (all modules), `tests/` (all test files), `pyproject.toml`
**Files scanned:** `src/olla/loop.py`, `src/olla/cli.py`, `src/olla/tools/memory.py`, `src/olla/providers/{__init__,base,ollama,openai_compat}.py`, `src/olla/smoke.py`, `tests/test_cli.py`, `tests/test_loop.py`, `tests/test_providers.py`, `pyproject.toml`
**Pattern extraction date:** 2026-09-09
**Tracked-source gate:** all 12 analog file paths verified via `git ls-files` this session — all tracked, none from a gitignored/mirrored path.
