# Phase 7: Interactive REPL Mode - Research

**Researched:** 2026-09-09
**Domain:** Terminal REPL UX (`prompt_toolkit`) + session-lifetime agent state + token-budgeted rolling context trimming
**Confidence:** MEDIUM-HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session architecture**
- **D-01:** `run_loop()` is refactored to accept optional pre-existing session state (Scratchpad, messages list, read_snapshots) instead of always constructing its own. `run_loop()` still owns the ReAct step loop; the REPL owns the outer input/session loop and calls `run_loop()` once per turn, injecting/reusing prior state. — Reversibility: costly.
- **D-02:** Conversation history is one continuous `messages` list across the whole REPL session — system prompt once, then every user turn and its tool observations append to the same list. Rolling trim (D-07..D-10) manages growth, not per-turn resets.
- **D-03:** The repetition guard (`previous_signature`/`repeat_count`) resets at the start of each REPL turn — it only fires on repeats within a single turn's step loop, not across turn boundaries.
- **D-04:** `--max-steps` is a per-turn budget — each user input gets its own fresh allowance (default 50), same semantics as one-shot mode. No cumulative session-wide step cap.
- **D-05:** `read_snapshots` (file-read-before-overwrite safety state) persists across the whole REPL session — a file read in turn 1 still satisfies the read-before-write precondition in a later turn.
- **D-06:** The model provider/client is initialized once per session by default, but the user can switch models mid-session via a `/model <name>` slash command. `/model` is recognized as a control command (not sent to the LLM), re-runs `get_provider()` with the new model, and prints a confirmation. Conversation history transfers to the new model unchanged — `/model` does not reset messages, Scratchpad, read_snapshots, or `untrusted_observation_seen`.

**Rolling context trimming (REPL-03)**
- **D-07:** When history nears `num_ctx`, dropped turns are **summarized into a running digest** rather than deleted outright — the digest is appended to context in place of the removed turns' raw content. — Reversibility: costly.
- **D-08:** Only the system prompt and the current in-progress turn are protected from trimming; all prior completed turns are eligible for summarization/removal.
- **D-09:** Context budget is measured via **exact token counting using `tiktoken`** as a new dependency — chosen deliberately over a free char-count proxy or Ollama's own `eval_count` response field, even though this adds a dependency the project's stated constraints call "zero new heavy dependencies." — Reversibility: reversible. **User confirmed deliberately** after the constraint conflict was explicitly flagged.
- **D-10:** Trimming happens **proactively** — history size is checked and trimmed before every `provider.chat()` call in the REPL loop, never reactively after a context-overflow error.
- **D-11:** Summarization is performed by the **same session model**, via a dedicated short-summary prompt call, not a separate/smaller model. This adds one extra inference call per trim event on the same constrained hardware the project targets. — **User confirmed deliberately** after the extra-latency-cost conflict was flagged; accepted because trimming is expected to be infrequent (only on long sessions).

**REPL UX & controls**
- **D-12:** Exiting the REPL: pressing Ctrl+C once interrupts the current turn/generation without ending the session; pressing Ctrl+C twice (double-tap within a short window) exits the session. `/exit` and `/quit` slash commands also exit explicitly.
- **D-13:** `--yes` and `--dry-run` are fixed for the whole session at REPL launch (`olla --yes`) — no in-session slash command to toggle them per-turn.
- **D-14:** Step-by-step tool progress output ("Step N: running `<cmd>`...") prints identically inside REPL turns as in one-shot mode — reuse the existing `_display()`/progress printing unchanged, no REPL-specific formatting.
- **D-15:** Slash command surface for v1: `/model <name>`, `/exit`, `/quit`, and `/clear`. No other commands planned for this phase.

**Scratchpad/session lifecycle edge cases**
- **D-16:** `/clear` performs a full session reset: messages history, Scratchpad, read_snapshots, `untrusted_observation_seen`, AND the rolling-context summarization digest (D-07) are all wiped back to fresh-session defaults.
- **D-17:** `/model` (mid-session model switch) leaves all other session state untouched — read_snapshots, `untrusted_observation_seen`, and the summarization digest all survive a model switch unchanged (consistent with D-06's history-transfers decision).

### Claude's Discretion
- Exact prompt wording for the dedicated summarization call (D-11).
- Internal digest format/structure (e.g. single running paragraph vs. per-turn bullet list) as long as it's appended as context the model can read.
- `prompt_toolkit` configuration specifics: history file location, key bindings beyond what's decided (Ctrl+C/Ctrl+D behavior), multiline-editing trigger keys.
- Exact `/model` and `/clear` confirmation message wording.
- Whether `tiktoken`'s `cl100k_base` or another encoding is used as the counting proxy for non-OpenAI models — pick a reasonable default at implementation time since exact per-model tokenizers vary anyway (this is an approximation regardless of encoding choice).

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. `/clear` and `/model` were raised during discussion but fall within REPL-01/REPL-02's existing scope (session control commands), not new capabilities.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REPL-01 | Launching `olla` with no arguments starts an interactive terminal REPL with multiline editing and history via `prompt_toolkit` | `PromptSession(multiline=..., history=FileHistory(...))` verified API shape (Standard Stack, Code Examples); official REPL loop pattern for Ctrl+C/Ctrl+D fetched via Context7 (Code Examples §1) |
| REPL-02 | Multi-turn conversational session preserves Scratchpad memory across turns within the session | D-01/D-05/D-06 architecture; `run_loop()` signature change plan (Architecture Patterns §Pattern 1); `Scratchpad` contract change (Don't Hand-Roll, Common Pitfalls §5) |
| REPL-03 | Rolling conversation context management truncates older turns to remain within model `num_ctx` | `tiktoken` verified compatible + empirically tested (Standard Stack, Common Pitfalls §1-2); existing unused `provider.get_context_length()` as the `num_ctx` source (Don't Hand-Roll); trim-call-site placement inside `run_loop()`'s step loop, not just the outer REPL loop (Architecture Patterns §Pattern 3, Open Questions §1) |
</phase_requirements>

## Summary

This phase adds a `prompt_toolkit`-based REPL entry point (`olla` with no TASK arg) that drives the existing, already-battle-tested `run_loop()` step machinery once per conversational turn, threading session state (messages, Scratchpad, read_snapshots) through it instead of letting `run_loop()` construct fresh state every call. `prompt_toolkit` is already a well-known, stable, pure-Python-plus-`wcwidth` library (verified compatible with the project's Python `>=3.10` floor and confirmed on PyPI at 3.0.53) whose official tutorial's canonical REPL loop (`try: session.prompt() / except KeyboardInterrupt: continue / except EOFError: break`) maps directly onto D-12's Ctrl+C/Ctrl+D semantics — double-Ctrl+C-to-exit requires one small custom `KeyBindings` addition on top of that. `tiktoken` (0.14.0, `Requires-Python: >=3.9`, verified `cp310` wheel exists) is confirmed installable, but has two verified runtime gotchas that materially affect this constrained-hardware, may-be-offline project: (1) `get_encoding()` performs a blocking network fetch of the BPE rank file on first use (~3.5s cold, ~0.2s warm from `/tmp/data-gym-cache` in this environment) and (2) that fetch raises an **uncaught** `requests.exceptions.RequestException` subclass when the network is unavailable — a class this codebase's existing exception handling does not catch anywhere. Both must be handled explicitly by the planner (pre-warm at REPL startup with a visible message, and/or wrap the encoder call with a graceful char-count fallback) or a network hiccup will crash the whole session the first time trimming needs to run.

Architecturally, the most important non-obvious finding is that `provider.get_context_length()` **already exists** on both `OllamaProvider` and `OpenAICompatProvider` (implementing the shared `Provider` protocol) but is currently dead code — nothing in `loop.py` or `cli.py` calls it. This is the correct, already-built source for the trim budget (`num_ctx`) rather than re-hardcoding `8192` a second time or reading it from a new location. Trimming logic (D-09/D-10) should call `provider.get_context_length()`, not reinvent context-length lookup.

The second major finding is a genuine gap in the locked decisions: D-07's summarization-into-digest design interacts with the existing untrusted-content tagging system (`<untrusted_shell_output>`, `<untrusted_web_content>`, `<untrusted_file_content>`, `<untrusted_memory_content>` — all read directly from `src/olla/loop.py`) in a way CONTEXT.md does not address. When a turn containing untrusted tool output gets summarized away, the digest text produced by the LLM summarizer is **not** wrapped in those same untrusted-content tags, and the summarizer's output is itself conditioned on (i.e., could be influenced by) that untrusted content — a classic indirect-prompt-injection-survives-compaction risk. This is flagged prominently in Common Pitfalls and Security Domain below as something the plan must explicitly decide how to handle (e.g., wrap the digest itself in an `<untrusted_...>`-style tag, or instruct the summarization prompt to report facts only and never follow embedded instructions).

**Primary recommendation:** Build the REPL as a thin new module (`src/olla/repl.py` or similar) that owns a `PromptSession` + slash-command dispatch loop and calls the refactored `run_loop()` once per turn; source `num_ctx` from `provider.get_context_length()`; wrap all `tiktoken` encoder initialization in a try/except that falls back to a char-count proxy and prints a one-line warning rather than crashing; and explicitly decide (during planning, not implementation) how the summarization digest preserves — or deliberately drops — the untrusted-content trust boundary.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Terminal input/editing/history (REPL-01) | CLI process (new REPL module) | — | `prompt_toolkit` owns the terminal; no server/browser tier exists in this single-process CLI app |
| Slash-command dispatch (`/model`, `/exit`, `/quit`, `/clear`) | CLI process (new REPL module) | — | Control-plane logic that intercepts input before it reaches `run_loop()`/the model — must live in the outer session loop, not inside `run_loop()` |
| Per-turn ReAct step execution | `run_loop()` (existing) | — | Unchanged; REPL calls it once per turn per D-01 |
| Session state ownership (messages, Scratchpad, read_snapshots, digest) | New REPL module (outer loop) | `run_loop()` (receives injected state, mutates in place per turn) | D-01 explicitly relocates ownership outward; `run_loop()` becomes a per-turn executor over externally-owned state |
| Provider/model client | `providers/` factory (existing `get_provider()`) | REPL module (holds the returned instance across turns, re-invokes factory on `/model`) | Reuse existing factory; REPL just changes *when* it's called (once at launch, again on `/model`) instead of once per `run_loop()` invocation |
| Boolean flags that must survive a call and be visible to the caller (`untrusted_observation_seen`) | Session-state container owned by the REPL module | `run_loop()` (reads on entry, must communicate the updated value back out) | `run_loop()` returns `None` and `messages`/`scratchpad`/`read_snapshots` are mutable objects that "just work" when injected — `untrusted_observation_seen` is a plain `bool` reassigned throughout the step loop via `X or untrusted_observation_seen` (`src/olla/loop.py:1105-1163`), so a naive optional-parameter injection has no channel to propagate the updated value back to the REPL's session state. See Pattern 1 below — this needs either a return value from `run_loop()` or a small mutable session-state object (e.g. a dataclass) rather than a scalar parameter. |
| Token counting for trim budget | New trim-check helper (likely in `loop.py` or a new module) | `tiktoken` (external library) | Must sit at the same layer as `_stream_model_turn()`/`provider.chat()` call sites since D-10 requires a check before every model call |
| Context-length (`num_ctx`) source | `Provider.get_context_length()` (existing, currently unused) | — | Already implemented per-provider; do not reintroduce a second hardcoded constant |
| Summarization call | Same session `Provider` instance, via a dedicated prompt | — | D-11: same model, not a separate model — reuses the existing `provider.chat()`/`provider.stream_chat()` surface |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `prompt_toolkit` `[WARNING: flagged as suspicious — verify before using.]` | `>=3.0,<4` (verified installed: 3.0.53, latest on PyPI as of this session) [VERIFIED: pip index versions / installed package] | Multiline-editing terminal REPL with persistent history (REPL-01) | Industry-standard for Python interactive CLIs (IPython, `ptpython`, many DB shells build on it); official docs ship a canonical `PromptSession` REPL loop that directly matches D-12's Ctrl+C/Ctrl+D contract [VERIFIED: Context7 `/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52`] |
| `tiktoken` `[WARNING: flagged as suspicious — verify before using.]` | `>=0.11,<1` (verified installed/latest: 0.14.0) [VERIFIED: pip index versions] | Exact BPE token counting for the D-09 rolling-context trim budget | User-locked choice (D-09) over char-count or Ollama's `eval_count`; official OpenAI tokenizer library, Rust-backed for speed [CITED: github.com/openai/tiktoken] |

Both packages were flagged `SUS` by the automated package-legitimacy gate (see Package Legitimacy Audit below) — the planner must add a `checkpoint:human-verify` task before installing either.

**Installation:**
```bash
pip install "prompt_toolkit>=3.0,<4" "tiktoken>=0.11,<1"
```

**Version verification:** Ran directly against PyPI this session:
```
$ pip index versions prompt_toolkit
prompt_toolkit (3.0.53)  INSTALLED: 3.0.53  LATEST: 3.0.53

$ pip index versions tiktoken
tiktoken (0.14.0)  INSTALLED: 0.14.0  LATEST: 0.14.0
```
Both confirmed [VERIFIED: pip index versions, run this session] with wheel-level Python-floor checks:
- `prompt_toolkit-3.0.53-py3-none-any.whl` METADATA: `Requires-Python: >=3.10`, `Requires-Dist: wcwidth>=0.1.4` [VERIFIED: wheel METADATA inspected this session — file quoted verbatim: `Requires-Python: >=3.10` / `Requires-Dist: wcwidth>=0.1.4`]
- `tiktoken-0.14.0` METADATA: `Requires-Python: >=3.9`, `Requires-Dist: regex`, `Requires-Dist: requests`, and a `cp310`-tagged wheel exists (`tiktoken-0.14.0-cp310-cp310-manylinux_2_28_x86_64.whl`, downloaded successfully this session against `--python-version 3.10`) [VERIFIED: wheel METADATA + successful `pip download --python-version 3.10` this session]

Both are compatible with the project's declared `requires-python = ">=3.10"` floor [VERIFIED: pyproject.toml:8].

**New transitive dependency to note:** `tiktoken` unconditionally requires `requests` [VERIFIED: tiktoken-0.14.0 wheel METADATA `Requires-Dist: requests`], which the project does not currently depend on (it uses `httpx` throughout — `httpx>=0.27.0` in `pyproject.toml:16`). This means the dependency tree will carry **two** HTTP client libraries after this phase. Not a blocker, but worth a one-line note in the plan's dependency-addition task since it's a second full HTTP stack (`requests` + `urllib3` + `certifi`/`idna`/`charset_normalizer`) pulled in solely for `tiktoken`'s internal BPE-file download.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `prompt_toolkit.history.FileHistory` | bundled with `prompt_toolkit` | Persist REPL input history across process restarts | Pass `history=FileHistory(path)` to `PromptSession(...)`; constructor signature verified this session: `FileHistory(self, filename: _StrOrBytesPath) -> None` [VERIFIED: local `inspect.signature()` against installed 3.0.53] |
| `prompt_toolkit.patch_stdout.patch_stdout` | bundled with `prompt_toolkit` | Prevent tool-output `print()` calls (existing `_display()`/step-progress prints, D-14) from corrupting the active prompt's cursor position | Wrap the turn-processing call (`run_loop()` invocation) in `with patch_stdout():` inside the REPL's per-turn dispatch, since `run_loop()` prints while a `PromptSession` is conceptually "between prompts" |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tiktoken` exact counting (D-09, locked) | Character-count proxy (`len(content) // 4`) | Rejected by user explicitly (D-09) — cheaper, zero dependency, no network fetch, but less accurate. Kept only as the *fallback* when `tiktoken`'s encoder can't load (see Common Pitfalls §2) |
| `tiktoken` exact counting (D-09, locked) | Ollama's own `eval_count` response field | Rejected by user explicitly (D-09) — reflects actual server-side tokenization exactly for local Ollama models, but is only known *after* the call completes, which conflicts with D-10's requirement to trim *proactively before* the call |
| `prompt_toolkit` `PromptSession` | stdlib `input()` in a loop | No multiline editing, no persistent history, no key-binding customization — fails REPL-01's explicit requirement |
| Custom double-Ctrl+C via `KeyBindings` | `signal.signal(signal.SIGINT, ...)` at the OS level | `prompt_toolkit` explicitly documents that raw-mode terminal input does **not** deliver Ctrl+C as SIGINT — binding `c-c` directly in `KeyBindings` is the documented approach [CITED: Context7 `/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52`, "Advanced Topics/Key Bindings"] |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `prompt_toolkit` | PyPI | mature (10+ yr project; checker's `publishedAt` reflects latest 3.0.53 release date, not project age) | not reported by checker (`unknown-downloads`) | `github.com/prompt-toolkit/python-prompt-toolkit` (resolved by checker) | **SUS** (`unknown-downloads`) | Flagged — planner must add `checkpoint:human-verify`. Well-known library (backs IPython, `ptpython`); the SUS verdict here stems from the legitimacy checker's PyPI download-stats lookup returning no data, not from any actual red flag. |
| `tiktoken` | PyPI | mature (OpenAI's official tokenizer, published 2022+; checker's `publishedAt` again reflects the latest 0.14.0 release date, not project age) | not reported (`unknown-downloads`) | not resolved by checker (`no-repository` — the real repo is `github.com/openai/tiktoken`) | **SUS** (`too-new`, `unknown-downloads`, `no-repository`) | Flagged — planner must add `checkpoint:human-verify`. `too-new` is an artifact of the checker reading the latest-version publish date, not the package's first release; the checker also failed to resolve the (correct, real) source repo from PyPI metadata for this package. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `prompt_toolkit`, `tiktoken` — both per the automated legitimacy gate's heuristics failing to retrieve download/repo metadata for these specific packages, not evidence of actual illegitimacy. Both packages' identities and Python-floor compatibility were independently cross-checked this session via direct PyPI wheel METADATA inspection (see Standard Stack above) and via Context7 official-docs resolution for `prompt_toolkit`. The planner must still gate their installation behind a `checkpoint:human-verify` task per protocol, since the automated check did not clear either package to `OK`.

## Architecture Patterns

### System Architecture Diagram

```
                 ┌─────────────────────────────────────────────┐
                 │  olla (no TASK arg) — cli.py                 │
                 │  branch: task is None → launch REPL          │
                 └───────────────────┬───────────────────────────┘
                                     ▼
                 ┌─────────────────────────────────────────────┐
                 │  REPL module (new)                            │
                 │  • PromptSession(multiline, history=FileHistory)│
                 │  • owns: messages[], Scratchpad, read_snapshots,│
                 │    digest, provider, untrusted_observation_seen │
                 │  • patch_stdout() wraps each turn's run_loop()  │
                 └───────────────────┬───────────────────────────┘
                                     │  session.prompt() → raw text
                                     ▼
                    ┌────────────────────────────┐
                    │ starts with "/" ?            │
                    └───────┬─────────────┬────────┘
                       yes  │             │  no
                            ▼             ▼
              ┌───────────────────┐   ┌─────────────────────────────┐
              │ Slash dispatch      │   │  run_loop(task=text,          │
              │ /model <name> →     │   │    model, max_steps,           │
              │   get_provider()    │   │    system_prompt,               │
              │ /exit,/quit → break │   │    messages=<injected>,          │
              │ /clear → reset all  │   │    scratchpad=<injected>,         │
              │   session state     │   │    read_snapshots=<injected>,      │
              └───────────────────┘   │    ...)                              │
                                       │  — runs its existing step loop:       │
                                       │    parse → dispatch tool → safety      │
                                       │    check → execute → observe → repeat  │
                                       │    (unchanged internals, D-14)          │
                                       │  — BEFORE each provider.chat()/          │
                                       │    stream_chat() call inside the step    │
                                       │    loop: trim-check hook (tiktoken count  │
                                       │    vs provider.get_context_length(),      │
                                       │    summarize-and-replace oldest turns if   │
                                       │    over budget, per D-07..D-10)             │
                                       └───────────────────────────────────────────┘
                                                        │
                                                        ▼
                                       returns to REPL loop; state mutated in place;
                                       loop back to session.prompt() for next turn
```

### Recommended Project Structure
```
src/olla/
├── cli.py           # add: if not task → import and launch repl.main_loop() instead of UsageError
├── loop.py          # run_loop() gains optional session-state params (D-01); trim-check hook inserted
│                     #   before _stream_model_turn() calls inside the step loop
├── repl.py           # NEW — owns PromptSession, slash-command dispatch, session state construction/reset,
│                     #   patch_stdout wrapping, double-Ctrl+C tracking
├── context_trim.py   # NEW (or a section of loop.py) — tiktoken-based counting, trim decision,
│                     #   summarization-call helper, digest formatting (Claude's discretion on placement)
├── providers/        # unchanged — get_provider() reused for both initial launch and /model
└── tools/memory.py   # Scratchpad docstring/contract updated: "session-lifetime" not "invocation-lifetime"
```
Module naming/location for the trim logic and REPL loop is explicitly left to the planner per CONTEXT.md's "Claude's Discretion" — CONVENTIONS.md's module-private-helper (`_`-prefixed) and one-line-docstring conventions apply regardless of final file layout [VERIFIED: `.planning/codebase/CONVENTIONS.md:5-118`].

### Pattern 1: Outer session loop / inner step loop separation (D-01)
**What:** The REPL owns long-lived session state and the human-interaction loop; `run_loop()` remains the inner, bounded, single-turn step executor, now accepting that state as optional parameters instead of always constructing it.
**When to use:** Any time a step-bounded, one-shot execution engine needs to be reused across multiple invocations without losing state — exactly this phase's core refactor.
**Example (industry precedent, not olla-specific code):**
```python
# Source: Simon Willison's minimal ReAct pattern (til.simonwillison.net/llms/python-react-pattern)
# — outer __call__ holds self.messages across invocations; inner while loop bounded by max_turns.
class Agent:
    def __init__(self, system=""):
        self.messages = []
        if system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result
```
[CITED: https://til.simonwillison.net/llms/python-react-pattern]

Anthropic's own agent-architecture guidance formalizes this same boundary: the outer orchestrator owns session state, human interaction, and termination bounds; the inner loop queries the model, executes tools, and registers state updates [CITED: https://www.anthropic.com/research/building-effective-agents].

**olla-specific adaptation:** `run_loop()`'s existing signature (`task, model, max_steps, system_prompt, yes, dry_run, api_key, base_url, debug`) [VERIFIED: `src/olla/loop.py:994-1004`] needs new optional parameters for `messages: list[dict] | None`, `scratchpad: Scratchpad | None`, `read_snapshots: dict | None`. These three are mutable objects — injecting them and mutating in place is sufficient; the caller's copy sees every update with no extra plumbing.

`untrusted_observation_seen` is different and needs deliberate handling, not the same pattern: it is a plain `bool`, reassigned throughout the step loop via `X or untrusted_observation_seen` (`src/olla/loop.py:1105-1163`), and `run_loop()`'s return type is `None` (`src/olla/loop.py:1004`) — there is currently no channel for the loop to hand an updated bool back to a caller. D-06/D-16/D-17 all name `untrusted_observation_seen` as session state that must persist/reset alongside the others, so this is not optional to solve. The plan must pick one of: (a) change `run_loop()`'s return type to carry the updated flag back out, or (b) wrap the three-plus-one pieces of session state in a small mutable container (e.g. a dataclass) passed by reference, so the flag mutates in place the same way `messages`/`scratchpad`/`read_snapshots` do.

When session state is injected, `run_loop()` must skip its own construction at `src/olla/loop.py:1032-1050` (`messages = [...]`, `scratchpad = Scratchpad()`, `read_snapshots = {}`, `previous_signature = None`, `repeat_count = 0`, `untrusted_observation_seen = False`) and use the injected instances instead — except `previous_signature`/`repeat_count`, which D-03 says must always reset per-turn regardless of session-vs-one-shot mode.

### Pattern 2: `prompt_toolkit` canonical REPL loop (REPL-01, D-12)
**What:** The official `prompt_toolkit` REPL tutorial's loop shape maps directly onto D-12's single-Ctrl+C-interrupts / Ctrl+D-exits baseline; double-Ctrl+C-to-exit is a documented extension via custom `KeyBindings`.
**When to use:** REPL entry-point implementation (REPL-01).
**Example:**
```python
# Source: https://python-prompt-toolkit.readthedocs.io/en/3.0.52/pages/tutorials/repl.html
# Fetched via Context7 (/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52) this session.
from prompt_toolkit import PromptSession

def main():
    session = PromptSession()
    while True:
        try:
            text = session.prompt('> ')
        except KeyboardInterrupt:
            continue          # Ctrl+C: back to prompt (D-12 single-tap)
        except EOFError:
            break             # Ctrl+D: exit (D-12)
        else:
            print('You entered:', text)
    print('GoodBye!')
```
[VERIFIED: Context7 `/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52`, "Loop The REPL" page]

`PromptSession.__init__` confirmed this session (via `inspect.signature()` against the installed 3.0.53 package) to default `interrupt_exception=KeyboardInterrupt` and `eof_exception=EOFError`, and to accept `multiline: FilterOrBool = False` and `history: History | None = None` directly [VERIFIED: local `inspect.signature(PromptSession.__init__)` this session].

**Double-Ctrl+C extension (D-12):** `prompt_toolkit` has no built-in double-tap listener; the documented approach is a custom `KeyBindings` object bound to `c-c` (not OS-level `SIGINT`, since raw-mode terminal input does not deliver Ctrl+C as a signal) that tracks the last-interrupt timestamp and calls `event.app.exit(exception=KeyboardInterrupt)` if a second Ctrl+C arrives within a short threshold, otherwise clears/warns [CITED: python-prompt-toolkit docs, "Advanced Topics/Key Bindings" — corroborated independently by both the Context7 fetch confirming the `c-c` vs `<sigint>` distinction and a web-search pass].

### Pattern 3: Trim-check placement inside the step loop, not just the outer turn loop (D-10)
**What:** D-10 requires the token-budget check to run "before every `provider.chat()` call in the REPL loop." Because a single REPL *turn* can itself trigger multiple model calls, the operative interpretation — the one this research recommends the plan implement — is that the trim-check hook must be inserted **inside `run_loop()`'s existing step loop**, immediately before each model call, not only once at the REPL's outer per-turn entry point. D-08's "the current in-progress turn is protected from trimming" is otherwise vacuous: it only makes sense as a statement if trimming can fire *during* a turn, not just between turns.
**When to use:** Implementing D-09/D-10.

**All model call sites this applies to** (enumerated this session by reading `src/olla/loop.py` in full):
- `src/olla/loop.py:1069` — `_stream_model_turn(provider, messages, model=resolved_model)` inside the main `for step in step_iter:` step loop (`src/olla/loop.py:1053`). The primary site: a multi-step tool-use turn calls this once per ReAct step before reaching `<final>`.
- `src/olla/loop.py:1038` — `_stream_model_turn(provider, messages, model=resolved_model)` in the `dry_run` branch, which runs *before* `scratchpad`/`read_snapshots`/the step loop are even constructed (`src/olla/loop.py:1036-1044`). D-13 fixes `--dry-run` for the whole REPL session, meaning `olla --dry-run` in REPL mode is a real, repeated-turn session with D-02's single continuous `messages` list growing turn over turn — this path needs the same trim-check the main step loop gets, or a long dry-run REPL session's history grows unbounded with no trim at all.
- `src/olla/loop.py:522-531` — `_call_model_for_loop()` / `call_model()`, the legacy direct-`ollama.chat()` path used when `ollama.chat`/`call_model` are mocked in tests, or (per `call_model()`'s own branching at `src/olla/loop.py:506-510`) when no `api_key`/`base_url` is set and the model isn't an `openrouter/`/`openai/`-prefixed remote — i.e., it can be a live code path, not only a test seam. Trim logic that only hooks `_stream_model_turn` will miss any call that routes through this function instead.

**Why it matters:** If the trim-check only runs once per REPL turn (at the outer loop) or only at one of the three sites above, a long multi-step tool-use turn, a long `--dry-run` REPL session, or a call that happens to route through the legacy `call_model()` path can still blow past `num_ctx` with no trim ever firing.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Getting the model's context-window size for the trim budget | A second hardcoded `num_ctx` constant, or a new config lookup | `provider.get_context_length()` — already implemented on both `OllamaProvider` (`src/olla/providers/ollama.py:17-19`, returns the constructor's `num_ctx`, default 8192) and `OpenAICompatProvider` (`src/olla/providers/openai_compat.py:83-104`, dynamically fetches from the remote `/models` endpoint, falling back to 128000) | [VERIFIED: `src/olla/providers/ollama.py:17-19` — `def get_context_length(self) -> int: return self.num_ctx`] [VERIFIED: `src/olla/providers/openai_compat.py:83-104` — quoted verbatim: `def get_context_length(self) -> int:` / `"""Return context length for model, fetching dynamically if possible."""` / `if self._context_length is not None:` / `return self._context_length` / `try:` / `with httpx.Client(timeout=5.0) as client:` / `headers = {"Authorization": f"Bearer {self.api_key}"}` / `resp = client.get(f"{self.base_url}/models", headers=headers)` / `if resp.status_code == 200:` / `data = resp.json()` / `models_list = data.get("data", [])` / `for m in models_list:` / `if m.get("id") == self.model and "context_length" in m:` / `self._context_length = int(m["context_length"])` / `return self._context_length` / `except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):` / `self._context_length = 128000` / `return self._context_length` / `self._context_length = 128000` / `return self._context_length`] Confirmed via `grep` that this method is defined and unit-tested (`tests/test_providers.py:195`) but **never called** from `loop.py` or `cli.py` — it is currently dead code from the ReAct loop's perspective. `call_model()`'s legacy direct-`ollama.chat()` path (`src/olla/loop.py:511-517`) and `OllamaProvider`'s own `chat()`/`stream_chat()` (`src/olla/providers/ollama.py:27,46`) still hardcode/pass `num_ctx=8192` by default — this is the actual model-call-time context limit, so the trim budget derived from `get_context_length()` should match it (both currently resolve to 8192 for local Ollama unless the `OllamaProvider` is constructed with a different value, which nothing in the codebase currently does). |
| Persisting REPL input history across process restarts | A hand-rolled append-only text file + manual readline emulation | `prompt_toolkit.history.FileHistory(path)` passed to `PromptSession(history=...)` | [VERIFIED: local `inspect.signature(FileHistory.__init__)` this session — `(self, filename: _StrOrBytesPath) -> None`] Built-in, wired into Up/Down arrow navigation automatically; reimplementing this is exactly the kind of "deceptively complex" persistence/encoding/locking problem the project should not hand-roll. |
| Multiline input detection/continuation prompts | Custom raw-terminal-mode line buffering | `PromptSession(multiline=True, prompt_continuation=...)` or a custom `KeyBindings` `Enter` handler for auto-detect (open-bracket) mode | [CITED: python-prompt-toolkit official multiline-input docs] `prompt_toolkit` already solves cursor positioning, line wrapping, and continuation-margin rendering; this is core to why the project chose it over stdlib `input()`. |
| Suppressing print()-vs-prompt cursor corruption while D-14's step-progress output runs during a turn | Manual `\r`/ANSI cursor-save-restore sequences around every `_display()` call | `with patch_stdout(): ...` wrapped around the turn-processing call | [VERIFIED: local `inspect.signature(patch_stdout)` this session — `(raw: bool = False) -> Generator[None, None, None]`; CITED: official docs "asynchronous prompting" page] This is precisely the documented use case: background/interleaved prints while a prompt is conceptually active. |
| Exact token counting for the trim budget | A hand-rolled tokenizer or word-count heuristic | `tiktoken.get_encoding(<chosen encoding>)` (D-09, locked) | User-locked; official, Rust-backed OpenAI tokenizer library. |

**Key insight:** This phase touches two systems (`providers/` and `loop.py`) that already contain more of the needed machinery than CONTEXT.md's decision list implies — `get_context_length()` exists and is unused, and `run_loop()`'s step loop already iterates per-model-call, which is exactly where the trim hook belongs. The main net-new code is the REPL's outer loop, the slash-command dispatcher, and the trim/summarization helper — not a parallel tracking system for state `run_loop()` already manages internally.

## Runtime State Inventory

> D-01 is described in CONTEXT.md as a refactor of `run_loop()`'s ownership model (moving state construction from inside `run_loop()` to an external caller), so this section is included per the trigger condition for rename/refactor/state-model-change phases.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified by reading `Scratchpad` (`src/olla/tools/memory.py:69-121`, in-process `dict`, no external datastore), `read_snapshots` (`src/olla/loop.py:1047`, in-process `dict[Path, _FileReadSnapshot]`), and `messages` (in-process `list[dict]`). All three are pure in-memory Python objects with no database, file-backed collection, or external service keyed by an identifier that this phase renames or restructures. | None |
| Live service config | None — this phase does not touch any external service configuration (no n8n/Datadog/Tailscale/Cloudflare-style out-of-git config exists anywhere in this project; `olla` talks to a local Ollama server or a remote OpenAI-compatible API purely via its existing `providers/` HTTP calls, unchanged by this phase). | None |
| OS-registered state | None — `olla` has no OS-level task-scheduler, `pm2`, `launchd`, or `systemd` registration anywhere in the codebase or `.planning/` docs reviewed this session. | None |
| Secrets/env vars | **New:** `TIKTOKEN_CACHE_DIR` — an env var this project has never referenced before; if the plan wants deterministic/offline-friendly caching of the tiktoken BPE file (Common Pitfalls §1), it should be documented (e.g. in a README/config note), not silently left to `tiktoken`'s own default (`/tmp/data-gym-cache` on this host, OS-temp-dir elsewhere, which is not guaranteed to persist across reboots or be writable in all deployment environments). **New:** the `prompt_toolkit` `FileHistory` file itself is new *persistent on-disk state* this project has never had before — a plaintext file recording every line of REPL input across sessions, including anything a user pastes (see Security Domain, "History file" row). Existing secrets (`--api-key`, `OPENROUTER_API_KEY`/`OPENAI_API_KEY`, `config.toml` keys) are unaffected — code continues reading them via the existing `get_provider()`/`load_config()` paths, unchanged by this phase. | Code decision (pick and document a `TIKTOKEN_CACHE_DIR` / history-file-path policy) — not a data migration, since nothing pre-existing is being renamed or moved. |
| Build artifacts / installed packages | **New:** two dependencies (`prompt_toolkit`, `tiktoken`) are being added to `pyproject.toml`'s `dependencies` list. The project's editable install (`.venv/bin/olla`, confirmed this session via `direct_url.json` — `{"url":"file:///home/nacs/Documents/git/olla","dir_info":{"editable":true}}`) and its `uv.lock` [VERIFIED: `uv.lock` exists at repo root, confirmed via `ls` this session] will not automatically pick up the new dependencies until `uv sync` (or `pip install -e .` / `uv lock` regeneration) is re-run — this is a required step in the plan's dependency-addition task, not an automatic side effect of editing `pyproject.toml`. | Code edit (`pyproject.toml`) + required re-sync step (`uv sync` or equivalent) — not a data migration. |

**Nothing found in category:** Stored data, Live service config, and OS-registered state — all explicitly verified "none" above, not left blank.

## Common Pitfalls

### Pitfall 1: `tiktoken.get_encoding()` blocks on a network fetch the first time it's called
**What goes wrong:** The REPL hangs for several seconds (or fails outright, see Pitfall 2) the first time trimming needs to check token counts, with no visible explanation to the user.
**Why it happens:** `tiktoken` does not bundle its BPE rank tables in the wheel. `tiktoken/load.py` performs a blocking HTTP GET to `openaipublic.blob.core.windows.net` on the first `get_encoding()`/`encoding_for_model()` call, caching the result locally (default cache dir on this machine: `/tmp/data-gym-cache`, controllable via `TIKTOKEN_CACHE_DIR`) [VERIFIED: empirically reproduced this session — cold `tiktoken.get_encoding('cl100k_base')` took 3.50s; warm (post-cache) call took 0.23s; cache landed at `/tmp/data-gym-cache`]. On a resource-constrained/possibly-offline host, this cold-start cost lands unpredictably mid-conversation whenever the trim threshold is first crossed.
**How to avoid:** Load/warm the encoder once at REPL *startup* (not lazily at first trim-check), print a one-line "preparing token counter..." message if it's slow, and consider setting `TIKTOKEN_CACHE_DIR` to a stable project-local cache path so re-runs across sessions reuse the same download.
**Warning signs:** Unexplained multi-second pause on the first long REPL session; works fine in short test sessions that never cross the trim threshold.

### Pitfall 2: `tiktoken`'s first-use network fetch raises an exception type nothing in the codebase catches
**What goes wrong:** If the host has no network access (or a proxy/firewall blocks it) at the moment the encoder first initializes, the REPL crashes with an unhandled exception instead of degrading gracefully.
**Why it happens:** Empirically confirmed this session: with network blocked, `tiktoken.get_encoding('cl100k_base')` raised `requests.exceptions.ProxyError` (a subclass of `requests.exceptions.ConnectionError` → `requests.exceptions.RequestException`) [VERIFIED: reproduced this session with `http_proxy`/`https_proxy` pointed at a closed port — exact exception: `requests.exceptions.ProxyError: HTTPSConnectionPool(host='openaipublic.blob.core.windows.net', port=443): Max retries exceeded...`]. `requests.exceptions.RequestException` is not a subclass of `ollama.RequestError`, `ollama.ResponseError`, or `ProviderError`, so the narrow `except` clauses at `src/olla/loop.py:526` and `src/olla/loop.py:556-557` do not catch it. **The exact failure mode depends on where the trim-check call site lands** (see Pattern 3's enumeration of model call sites):
- If the trim-check helper is called from a scope with **no** enclosing `except Exception`, the exception propagates uncaught and crashes the whole REPL process.
- If it is called from **inside** `_stream_model_turn()` — a plausible reading of "before every `provider.chat()` call," since that is where every non-legacy model call already happens — it lands inside that function's existing `except Exception as error: # noqa: BLE001` handler at `src/olla/loop.py:562-564` [VERIFIED: `src/olla/loop.py:562-564` — quoted verbatim: `except Exception as error:  # noqa: BLE001` / `_display(f"Model request failed: {error}")` / `return None`]. That handler swallows the error, prints "Model request failed: ...", and returns `None`, which `run_loop()`'s step loop treats as "content is None" → `return` (`src/olla/loop.py:1070-1072`) — silently ending the turn with a generic message rather than crashing, but **also silently abandoning the trim/token-count step** rather than falling back to an alternate counting method. This is a *different and arguably worse* failure mode than an outright crash: the user sees a plausible-looking "Model request failed" message with no indication the real cause was the token counter, not the model.
**How to avoid:** Wrap all `tiktoken` encoder initialization (and, defensively, `encode()` calls, since re-fetch-on-cache-miss could recur) in its own explicit `try/except` catching `requests.exceptions.RequestException` **at the trim-check call site itself**, before it can reach either an uncaught-crash path or get silently absorbed by `_stream_model_turn()`'s broad handler — with a fallback to the char-count proxy (`len(text) // 4`-style estimate) the user chose *not* to use as the primary method (D-09) but which remains a reasonable degraded-mode fallback. Log/print a one-line warning so the user knows counting is approximate for the rest of the session, and so the failure is attributed to the token counter, not misdiagnosed as a model/provider failure.
**Warning signs:** REPL works in CI/dev (always-online) but crashes, or silently ends turns with a generic "Model request failed" message, for a user on a flight, in a sandboxed container with no egress, or behind a restrictive corporate proxy.

### Pitfall 3: `cl100k_base` (or any OpenAI encoding) is only an approximation for non-OpenAI local models
**What goes wrong:** The trim logic under- or over-triggers relative to the actual Ollama-reported token count for the model in use, either wasting context headroom (over-summarizing too early) or letting the real prompt exceed `num_ctx` (under-counting, causing the model server to silently truncate or error).
**Why it happens:** `cl100k_base`'s BPE merge tables and vocabulary (~100k tokens) differ from local open-weight model tokenizers (Llama 3: 128k vocab; Qwen 2.5: 151,643 vocab), so the token count `tiktoken` reports for the same text is not the count Ollama will actually use. WebSearch-sourced estimates suggest `cl100k_base` commonly **overestimates** English-prose token counts by roughly 10-20% relative to Llama-3-family tokenizers [ASSUMED — WebSearch synthesis via `antigravity:research`, not independently reproduced against a real Ollama tokenizer this session; treat the specific percentage as indicative, not exact]. Overestimation is the safer failure direction (triggers trimming slightly early rather than late), but the magnitude and even the *direction* of the skew varies by model family and is not something this research independently verified against Ollama's own tokenizer.
**How to avoid:** Treat the tiktoken-derived count as an approximation with a safety margin, not an exact budget — e.g., trim somewhat before reaching the literal `num_ctx` value (this is already implied by "before every `provider.chat()` call," but the trim *threshold* itself, e.g. 80-90% of `num_ctx` rather than 100%, is Claude's discretion and should be set conservatively given the unverified skew direction/magnitude across model families).
**Warning signs:** Model responses start getting cut off or degrading in quality on long sessions despite trimming appearing to run; or conversely, trimming/summarization fires surprisingly early on short sessions.

### Pitfall 4: Summarization digest may carry injected instructions past the existing untrusted-content framing
**What goes wrong:** D-07's summarize-and-replace design, combined with the existing WEB-04 trust-tagging system, creates a gap CONTEXT.md does not address: raw tool observations from `shell`, `read_file`/`list_dir`/`grep_files`, `fetch_url`/`search_web`, and `recall` are explicitly wrapped in `<untrusted_shell_output>`, `<untrusted_file_content>`, `<untrusted_web_content>`, `<untrusted_memory_content>` tags respectively before being appended to `messages` [VERIFIED: `src/olla/loop.py:421-483`, functions `_record_file_observation` (wraps in `<untrusted_file_content>`, used by `_execute_read_file`, `_execute_list_dir`, `_execute_grep_files`), `_record_memory_observation` (wraps in `<untrusted_memory_content>`), `_record_shell_observation` (wraps in `<untrusted_shell_output>`), `_record_web_observation` (wraps in `<untrusted_web_content>`) — four distinct literal tags, each function wrapping its own]. When a turn containing such content gets summarized and dropped per D-07, the LLM-generated digest text that replaces it is (a) not itself wrapped in any of these tags, and (b) was produced by a model call that *read* the untrusted content as input — meaning any prompt-injection payload embedded in that content could influence the wording the summarizer writes, and that wording then re-enters context without the `<untrusted_...>` framing that told earlier turns "treat this as data, not instructions."
**Why it happens:** This is a direct, structural consequence of combining D-07 (summarize untrusted-taggable content away) with the pre-existing WEB-04 trust-tagging system — CONTEXT.md locked the summarization mechanism but did not discuss its interaction with the tagging system, because WEB-04 shipped in a separate, already-completed phase (Phase 6) and this phase's design conversation did not revisit it.

**What this pitfall is *not*:** `untrusted_observation_seen` itself is a plain `bool` held outside `messages` (see Don't Hand-Roll table and Pattern 1) — trimming/summarizing a turn cannot clear or bypass that flag once it has been set, since nothing about D-07 touches it. The risk is narrower than a gating bypass: it is that injected *instructions* embedded in untrusted source content could survive into the digest's wording and be read by a later turn without the `<untrusted_...>` framing that previously signaled "don't follow this as an instruction," not that the confirm-gating mechanism stops firing.
**How to avoid:** This is a genuine open design question for the plan (see Open Questions §2), not something research can resolve on the user's behalf — options include: (a) wrap the digest itself in a new, planner-chosen untrusted-content tag (e.g. `<untrusted_summary_digest>` — a proposed name, not an existing one in the codebase) so downstream turns still treat it with the same caution, (b) have the summarization prompt explicitly instruct the model to report facts only and never execute/follow instructions found in the source material (defense-in-depth, not a full mitigation on its own), or (c) never summarize turns that contain untrusted-tagged content — only trim/summarize turns composed purely of trusted (user/assistant reasoning) content, evicting untrusted-tagged raw content outright instead of summarizing it. The planner should surface this explicitly rather than pick silently.
**Warning signs:** A prompt-injection payload embedded in fetched web content or shell output successfully influences model behavior in a *later* turn, after the turn that originally contained it has been trimmed away and only survives as unmarked digest wording.

### Pitfall 5: `Scratchpad`'s documented lifetime contract is currently one-invocation, and other code may rely on that
**What goes wrong:** Silently changing `Scratchpad`'s actual lifetime (session-long in the REPL path) without updating its docstring/contract, or without checking for other assumptions baked into its current "fresh per invocation" guarantee, could reintroduce the exact cross-run note-leakage bug Phase 4 deliberately prevented (per STATE.md: "[Phase 04]: Own exactly one Scratchpad inside each run_loop invocation so notes cannot cross runs.").
**Why it happens:** `Scratchpad.__init__` currently just initializes `self._values: dict[str, str] = {}` [VERIFIED: `src/olla/tools/memory.py:69-73`] with no external state — the "invocation lifetime" guarantee today comes entirely from `run_loop()` always constructing a fresh instance (`src/olla/loop.py:1046`), not from anything inside `Scratchpad` itself. D-01/D-05 correctly relax this only for the REPL path while the CLI one-shot path must keep constructing a fresh `Scratchpad()` per invocation, exactly as today.
**How to avoid:** Update the `Scratchpad` class docstring (currently `"Store notes for the lifetime of one owning run-loop invocation."`, `src/olla/tools/memory.py:70`) to reflect the dual contract (one-shot: per-invocation; REPL: per-session, reset only by `/clear`), and ensure the CLI one-shot code path (`cli.py` → `run_loop()` without session params) is unchanged and still gets a fresh instance every call.
**Warning signs:** Regression tests for the one-shot CLI path start seeing Scratchpad values leak across separate `olla` invocations in the same process/test run (shouldn't happen if each CLI invocation is still its own process, but matters for any in-process test harness that calls `run_loop()` multiple times).

## Code Examples

### Canonical `prompt_toolkit` REPL loop (REPL-01 / D-12 baseline)
```python
# Source: https://python-prompt-toolkit.readthedocs.io/en/3.0.52/pages/tutorials/repl.html
# Fetched via Context7 this session (/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52)
from prompt_toolkit import PromptSession

def main():
    session = PromptSession()
    while True:
        try:
            text = session.prompt('> ')
        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        else:
            print('You entered:', text)
    print('GoodBye!')
```

### `PromptSession` with history + multiline (REPL-01)
```python
# Constructor shape verified via inspect.signature() against installed prompt_toolkit 3.0.53 this session.
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

session = PromptSession(
    history=FileHistory(str(history_path)),  # FileHistory(filename: _StrOrBytesPath)
    multiline=False,        # or True — exact trigger-key behavior is Claude's discretion per CONTEXT.md
)
```

### `patch_stdout` around turn processing (D-14 — unchanged step-progress prints)
```python
# Source: https://python-prompt-toolkit.readthedocs.io/en/3.0.52/pages/reference.html
# patch_stdout signature verified via inspect.signature() this session: (raw: bool = False) -> Generator[None, None, None]
from prompt_toolkit.patch_stdout import patch_stdout

with patch_stdout():
    run_loop(task=text, model=model, max_steps=max_steps, system_prompt=SYSTEM_PROMPT,
              messages=session_messages, scratchpad=session_scratchpad,
              read_snapshots=session_read_snapshots, yes=yes, dry_run=dry_run, debug=debug)
```

### Reading token count against the provider's real context length (REPL-03 / D-09-10)
```python
# provider.get_context_length() verified as existing, currently-unused API:
# src/olla/providers/ollama.py:17-19 and src/olla/providers/openai_compat.py:83-104
import tiktoken

def count_tokens(messages: list[dict], encoding_name: str = "cl100k_base") -> int:
    enc = tiktoken.get_encoding(encoding_name)  # first call may block on network + take ~3.5s cold
    return sum(len(enc.encode(m.get("content", ""))) for m in messages)

budget = provider.get_context_length()  # existing, unused method — do not hardcode 8192 again
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `run_loop()` always constructs its own `Scratchpad`/`messages`/`read_snapshots` (one-shot only) | `run_loop()` accepts optional injected session state (D-01) | This phase | Enables REPL-02's cross-turn persistence without duplicating the ReAct step machinery |
| Rolling context handled reactively (none today — the codebase has no context-overflow handling at all; `call_model()` hardcodes a fixed `num_ctx: 8192`, `src/olla/loop.py:514`) | Proactive tiktoken-based trim-before-call with summarization digest (D-09/D-10) | This phase | REPL-03; also exposes the previously-dead `provider.get_context_length()` API for real use |

**Deprecated/outdated:** None — this is new capability, not a migration of existing REPL functionality.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cl100k_base` overestimates token counts for Llama-3-family local models by roughly 10-20% (specific percentage, and even the direction of skew for other model families such as Qwen) | Common Pitfalls §3 | If the skew is actually in the opposite direction (undercounting) for some model families, a fixed "trim slightly early" safety margin could still let real prompts exceed `num_ctx` for those models. Mitigate by using a conservative trim threshold below 100% of `get_context_length()` rather than relying on the skew direction. |
| A2 | The double-Ctrl+C-to-exit implementation pattern (custom `KeyBindings` binding `c-c`, timestamp-threshold check, `event.app.exit(exception=KeyboardInterrupt)`) is the standard/only documented way to achieve this in `prompt_toolkit` | Architecture Patterns §Pattern 2, Standard Stack | Low risk — corroborated by both a direct Context7 fetch (confirming the `c-c` vs `<sigint>` distinction) and an independent web search citing the same official docs page; not independently prototyped and run this session, so exact API call names (`event.app.exit(...)`) should be spot-checked against the installed `prompt_toolkit` version during implementation. |
| A3 | `tiktoken`'s reported "too-new"/"unknown-downloads"/"no-repository" signals from the automated package-legitimacy checker are checker limitations, not genuine legitimacy concerns, for this specific well-known package | Package Legitimacy Audit | If wrong, a genuinely risky package would be waved through based on reputation alone. Mitigated by independent verification this session: official PyPI listing exists, wheel METADATA is well-formed and consistent with the known OpenAI `tiktoken` project, `Requires-Python`/`Requires-Dist` fields are sane and match public knowledge of the library. Planner must still add the required `checkpoint:human-verify` task per protocol regardless of this assessment. |
| A4 | No mitigation for Pitfall 4 (summarization-vs-untrusted-content-tagging interaction) is specified — this is deliberately left as an open design question, not resolved by research | Common Pitfalls §4, Open Questions §2 | If the plan does not explicitly address this, the phase could ship a design that quietly weakens the WEB-04 prompt-injection defenses already built in Phase 6. This is the single highest-severity item in this research and should not be silently deferred during planning. |

**If this table is empty:** N/A — see entries above.

## Open Questions (RESOLVED)

All three questions below carry an explicit "Recommendation" this research resolves to an operative
interpretation; 07-01/07-02/07-03's plans implement exactly these recommendations (broad D-10 reading,
`<untrusted_summary_digest>` tagging, `cl100k_base`/0.85 threshold defaults) — none is left open for the
planner to re-litigate.

1. **Does D-10's "before every `provider.chat()` call in the REPL loop" mean the outer per-turn REPL loop, or every model call inside `run_loop()`'s step loop (including multi-step tool-use turns)? — Operative interpretation: the broad one.**
   - What we know: `run_loop()`'s step loop can call `_stream_model_turn()` (which calls `provider.chat()`/`provider.stream_chat()`) multiple times within a single REPL turn, once per ReAct step, before reaching a `<final>` answer.
   - What's unclear: CONTEXT.md's phrasing is ambiguous about which loop "the REPL loop" refers to at the sentence level.
   - Recommendation: **The plan should implement the broad reading — before every model call the REPL causes, including within a multi-step turn (see Architecture Patterns §Pattern 3 and its enumerated call sites)** — not treat this as a 50/50 toss-up. D-08's "current in-progress turn is protected from trimming" is only a meaningful constraint if trimming can otherwise happen *during* a turn; under the narrow (outer-loop-only) reading, D-08 would be vacuous, since there would be nothing mid-turn for it to protect against. The narrow reading also fails to prevent mid-turn context overflow on long tool-use turns, which is the exact failure REPL-03 exists to prevent. Treat this as the decided interpretation going into planning; use the confirm-with-user step only as a formality if the plan-checker or discuss-phase flags it, not as an open branch to design around.

2. **How should the summarization digest interact with the existing untrusted-content tagging system (WEB-04) — `<untrusted_shell_output>`, `<untrusted_file_content>`, `<untrusted_web_content>`, `<untrusted_memory_content>`?**
   - What we know: Raw untrusted tool output is explicitly tagged today [VERIFIED: `src/olla/loop.py:421-483`]; D-07's digest is not addressed by CONTEXT.md with respect to this tagging. `<untrusted_summary_digest>` (used above in Pitfall 4 / Common Pitfalls §4) is a **proposed** tag name for one possible mitigation, not something that exists in the codebase today.
   - What's unclear: Whether the user/planner wants the digest itself tagged as untrusted, the summarization prompt hardened against following embedded instructions, untrusted-tagged turns excluded from summarization entirely (evicted raw instead), or some other mitigation.
   - Recommendation: Do not implement silently — flag this explicitly in the phase plan as a discrete decision point (or a `checkpoint:human-verify`/discuss-phase follow-up) before writing the summarization-call code, since this affects the security posture established in Phase 6.

3. **Exact encoding name (`cl100k_base` vs `o200k_base` vs something else) and trim threshold percentage.**
   - What we know: Both are explicitly left to Claude's discretion per CONTEXT.md; `cl100k_base` is the more broadly-compatible/conservative default per WebSearch synthesis (Common Pitfalls §3).
   - What's unclear: No hard requirement either way; this is a tuning choice, not a correctness question.
   - Recommendation: Default to `cl100k_base` for broad compatibility, and pick a trim threshold meaningfully below 100% of `provider.get_context_length()` (e.g., 80-85%) to absorb encoding-skew uncertainty (A1) — exact percentage is an implementation-time judgment call, not something requiring further research.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `prompt_toolkit` | REPL-01 | ✓ (system-wide, not yet a project dependency) | 3.0.53 installed on this host; not present in `uv.lock`/`pyproject.toml` yet | Must be added to `pyproject.toml` `dependencies` — currently only present via an unrelated system package, not the project's own venv/lockfile [VERIFIED: `grep` of `uv.lock` found no `prompt_toolkit`/`prompt-toolkit` entry this session; `pip show prompt_toolkit` resolved to `/usr/lib/python3.14/site-packages/`, outside the project's `.venv`] |
| `tiktoken` | REPL-03 (D-09) | ✗ (not installed in this environment prior to this session's verification install) | 0.14.0 confirmed available on PyPI, `cp310` wheel confirmed downloadable | Must be added to `pyproject.toml` `dependencies`; first-use network fetch is itself a soft dependency on internet access (see Common Pitfalls §1-2) — fallback is the char-count proxy the user explicitly deprioritized (D-09) but which should still exist as degraded-mode error handling, not a primary strategy |
| Network access (for `tiktoken`'s first-use BPE download) | REPL-03 trim logic, indirectly | Assumed available in normal operation; **not guaranteed** on the "resource-constrained laptop" target host per PROJECT.md | n/a | Char-count proxy fallback (see Pitfall 2); pre-warming at REPL startup surfaces the failure early and visibly rather than mid-session |

**Missing dependencies with no fallback:** None outright-blocking; both `prompt_toolkit` and `tiktoken` are straightforward `pyproject.toml` additions already scoped/verified.

**Missing dependencies with fallback:** `tiktoken`'s network dependency has a fallback (char-count proxy) that must be implemented as an error-handling path, not skipped, given this project's stated resource-constrained/offline-adjacent hardware target.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8, with `pytest-mock` for the `mocker` fixture [VERIFIED: `pyproject.toml:24-28`] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]` [VERIFIED: `pyproject.toml:33-34`] |
| Quick run command | `pytest tests/test_repl.py -x` (new file — see Wave 0 Gaps) |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REPL-01 | `olla` with no TASK arg launches REPL instead of raising `UsageError` | unit (CLI dispatch, mocked) | `pytest tests/test_cli.py -k no_task_launches_repl -x` | ❌ Wave 0 — extend `tests/test_cli.py` following the existing `mocker.patch("olla.cli.run_loop")` pattern [VERIFIED: `tests/test_cli.py:15-27` pattern], patching the new REPL entry point instead |
| REPL-01 | `PromptSession` constructed with `multiline` + `FileHistory` | unit (construction args, mocked `PromptSession`) | `pytest tests/test_repl.py -k session_construction -x` | ❌ Wave 0 |
| REPL-01 | Ctrl+C once continues session; Ctrl+D exits; double-Ctrl+C exits | unit (simulate `KeyboardInterrupt`/`EOFError` from a mocked `session.prompt()`) | `pytest tests/test_repl.py -k exit_semantics -x` | ❌ Wave 0 |
| REPL-02 | Scratchpad value written in turn 1 is recallable in turn 2 within the same session | integration (drive `run_loop()` twice with the same injected `Scratchpad`, mocking the model) | `pytest tests/test_loop.py -k session_state_persists_across_calls -x` | ❌ Wave 0 — extend `tests/test_loop.py` following existing `test_run_loop_*` mocking conventions [VERIFIED: `tests/test_loop.py` function-name grep] |
| REPL-02 | `read_snapshots` from turn 1 satisfies write-precondition in turn 2 | integration | `pytest tests/test_loop.py -k read_snapshot_persists_across_turns -x` | ❌ Wave 0 |
| REPL-02 | `/clear` resets messages, Scratchpad, read_snapshots, `untrusted_observation_seen`, digest | unit (slash dispatch) | `pytest tests/test_repl.py -k clear_resets_all_state -x` | ❌ Wave 0 |
| REPL-02 | `/model` swaps provider but preserves all other state | unit (slash dispatch, mocked `get_provider`) | `pytest tests/test_repl.py -k model_switch_preserves_state -x` | ❌ Wave 0 |
| REPL-03 | Trim-check fires before `provider.chat()`/`stream_chat()` when token count exceeds threshold | unit (mocked `tiktoken`, mocked `provider.get_context_length()`) | `pytest tests/test_loop.py -k trim_check_fires -x` (or new `tests/test_context_trim.py`) | ❌ Wave 0 |
| REPL-03 | Summarization digest replaces dropped turns; system prompt + in-progress turn protected | unit | `pytest tests/test_context_trim.py -k digest_replaces_dropped_turns -x` | ❌ Wave 0 |
| REPL-03 | `tiktoken` network/init failure falls back gracefully rather than crashing | unit (mock `tiktoken.get_encoding` to raise `requests.exceptions.RequestException`) | `pytest tests/test_context_trim.py -k tiktoken_failure_fallback -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_repl.py tests/test_loop.py -x` (fast, scoped to touched files)
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_repl.py` — new file covering REPL entry point, `PromptSession` construction, slash-command dispatch, exit semantics
- [ ] `tests/test_context_trim.py` (or equivalent) — new file covering tiktoken counting, trim decision, summarization-call, and the network-failure fallback path
- [ ] Extend `tests/test_loop.py` — new `test_run_loop_*` cases for the D-01 injected-session-state parameters (messages/scratchpad/read_snapshots persisting across two sequential `run_loop()` calls sharing the same instances)
- [ ] Extend `tests/test_cli.py` — new case for the no-TASK-argument branch launching the REPL instead of raising `UsageError`
- [ ] Framework install: none — `pytest`/`pytest-mock` already present [VERIFIED: `pyproject.toml:24-28`]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | No auth surface — local CLI process talking to a local/configured model provider, unchanged by this phase |
| V3 Session Management | partially (conceptually, not web-session) | The REPL introduces a genuine multi-turn "session" concept for the first time; the closest applicable control is **not** leaking session state across sessions it shouldn't (D-16's full `/clear` reset) and not persisting sensitive data (API keys, secrets) into `FileHistory`'s on-disk file |
| V4 Access Control | no | Single-user local CLI; no multi-principal access boundary |
| V5 Input Validation | yes | Slash commands (`/model`, `/exit`, `/quit`, `/clear`) are **user-typed local input**, a different and more-trusted tier than model-generated tool args — confirm none of the 9 existing tool names collide with the 4 slash commands [VERIFIED: `src/olla/prompts.py:5` — quoted verbatim: `You have 9 tools available: \`read_file\`, \`write_file\`, \`shell\`, \`remember\`, \`recall\`, \`list_dir\`, \`grep_files\`, \`search_web\`, \`fetch_url\`.`; no overlap with `model, exit, quit, clear`]. `/model <name>` should still route through the existing `get_provider()`/model-string validation path unchanged — do not add a second, looser model-name validator for the REPL path. |
| V6 Cryptography | no | Nothing new — API keys continue to flow through the existing `--api-key`/config/env resolution in `get_provider()`, unchanged by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Indirect prompt injection surviving context compaction (Common Pitfalls §4) — untrusted tool content (tagged `<untrusted_shell_output>`, `<untrusted_file_content>`, `<untrusted_web_content>`, or `<untrusted_memory_content>` today, per `src/olla/loop.py:421-483`) gets summarized by the model itself, and the resulting digest is not tagged as untrusted, potentially causing later turns to read attacker-influenced wording without the framing that previously marked it as data-not-instructions | Tampering / Elevation of Privilege | No existing standard library solves this generically; mitigation must be a design decision in this phase (see Open Questions §2) — e.g., tag the digest itself as untrusted, or exclude untrusted-tagged turns from summarization and evict them outright instead |
| Unbounded conversation growth causing denial-of-service (context overflow, degraded/garbled model output, or a hard crash if trimming's own dependency — `tiktoken` — fails) | Denial of Service | Proactive trim-before-call (D-10) is the correct mitigation direction; must be paired with the graceful-fallback handling in Pitfall 2 so a `tiktoken` failure doesn't itself become the DoS vector |
| Slash-command spoofing via model output (a compromised/malicious tool-observation text containing a literal `/model attacker-controlled-endpoint` string) | Spoofing | Slash-command dispatch must only trigger on **raw `session.prompt()` input from the terminal**, never on text that flows through `messages`/tool observations — confirm the REPL module's slash-check happens before text is ever handed to `run_loop()` as a task, not on any text that later appears inside the conversation history |
| History file (`FileHistory`) persisting sensitive data across restarts | Information Disclosure | If a user pastes a secret (e.g., API key) as REPL input, it will be written to the on-disk history file by `FileHistory` — this is standard `prompt_toolkit`/shell-history behavior and not unique to olla, but worth a one-line doc/README note since this project already handles secrets carefully elsewhere (`mask_secret()` in `src/olla/debug.py`) |

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/python-prompt-toolkit_readthedocs_io_en_3_0_52` — fetched this session for `PromptSession`, multiline input, `patch_stdout`, and the canonical REPL loop / Ctrl+C-Ctrl+D key-binding pages.
- Local package inspection this session: `inspect.signature()` against installed `prompt_toolkit==3.0.53` (`PromptSession.__init__`, `FileHistory.__init__`, `patch_stdout`); `pip index versions` for `prompt_toolkit` and `tiktoken` against live PyPI; `pip download`/wheel `METADATA` inspection for `Requires-Python`/`Requires-Dist` on both packages; empirical reproduction of `tiktoken`'s cold/warm load timing and its offline-failure exception type.
- Direct codebase reads this session: `src/olla/loop.py`, `src/olla/cli.py`, `src/olla/tools/memory.py`, `src/olla/providers/{__init__,base,ollama,openai_compat}.py`, `pyproject.toml`, `.planning/codebase/{ARCHITECTURE,CONVENTIONS}.md`, `.planning/phases/07-interactive-repl-mode/07-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`.

### Secondary (MEDIUM confidence)
- `antigravity:research` (agy/Gemini-backed) fan-out searches for prompt_toolkit key-binding patterns, tiktoken non-OpenAI-model proxy accuracy, session/step-loop architecture precedents (Simon Willison's ReAct pattern, Anthropic's agent-building guide, `smolagents`, Aider, SWE-agent, OpenHands), and context-window trimming/summarization strategies — citations spot-checked for plausibility and cross-corroborated across ≥2 sources where used as load-bearing claims (e.g., double-Ctrl+C pattern corroborated by both Context7 and web search; summary-placement/KV-cache tradeoffs are general LLM-API knowledge, not olla-specific, and are cited as background context rather than direct implementation requirements since olla talks to local Ollama models without prompt-caching semantics).
- `github.com/openai/tiktoken`, `pypi.org/project/tiktoken/` — package identity, install footprint, dependency list (`regex`, `requests`).

### Tertiary (LOW confidence)
- The specific 10-20% `cl100k_base` overestimation figure for Llama-3-family tokenizers (Common Pitfalls §3, Assumptions A1) — WebSearch-sourced only, not independently reproduced against a real Ollama tokenizer this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — both packages' versions, Python-floor compatibility, and core API shapes verified directly against PyPI/installed wheels and Context7 official docs this session.
- Architecture: HIGH — grounded entirely in direct reads of the actual `run_loop()`/`cli.py`/`providers/` source this session, not inference from CONTEXT.md alone.
- Pitfalls: HIGH for tiktoken network/timing/exception behavior (empirically reproduced this session); MEDIUM for the encoding-accuracy-skew magnitude (WebSearch only); HIGH for the untrusted-content/summarization interaction (grounded in direct reads of `loop.py`'s existing tagging functions, reasoned from first principles, not externally sourced).

**Research date:** 2026-09-09
**Valid until:** 30 days (stable, mature libraries; the one fast-moving risk is `tiktoken`'s BPE-download endpoint availability, which is outside this project's control)
