# Architecture Research

**Domain:** Lightweight ReAct-style CLI agent wrapping local Ollama models
**Researched:** 2026-06-10
**Confidence:** MEDIUM-HIGH (component breakdown and loop pattern are well-established across minimal agent implementations; tag-parsing and stop-sequence specifics are synthesized from XML-tool-call best practices and small-model failure modes, not a single canonical source — flagged inline)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLI Entrypoint                           │
│  - argument parsing (click)                                       │
│  - flags: --model, --max-steps, --yes, --dry-run                  │
│  - constructs initial message list, instantiates loop, runs it    │
├────────────────────────────────────────────────────────────────-─┤
│                          Agent Loop (core)                        │
│  - owns conversation state (messages: list[dict])                 │
│  - per iteration: call ollama.chat() → parse → dispatch → observe │
│  - tracks step count vs --max-steps                                │
│  - terminates on <final> tag or step cap                          │
├──────────────┬──────────────────────────┬────────────────────────┤
│ Prompt /      │      Safety Gate          │     Tool Registry      │
│ Parsing Layer │  (between parse & exec)   │                        │
│               │                            │                        │
│ - system      │ - blocklist check          │ - shell                │
│   prompt      │ - confirm prompt           │ - read_file            │
│   template    │ - dry-run short-circuit    │ - write_file           │
│ - regex parse │ - reads tool metadata      │ - remember/recall      │
│   of <tool>/  │   (requires_confirm flag)  │   (scratchpad)         │
│   <args>/     │                            │ - each tool: name,     │
│   <final>     │                            │   schema, run(),       │
│               │                            │   requires_confirm     │
├──────────────┴──────────────────────────┴────────────────────────┤
│                        Ollama Backend (external)                  │
│  - ollama.chat(model, messages, options={"stop": [...]})          │
│  - runs locally, stateless per call — full history sent each time │
└─────────────────────────────────────────────────────────────────-┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| CLI entrypoint (`cli.py`) | Parse args/flags, build system prompt, construct loop, print final result | `click` command, thin — delegates everything to the loop |
| Agent loop (`loop.py`) | Own `messages` list, drive think→act→observe cycle, enforce `--max-steps`, decide termination | Plain `while` loop (not recursion — easier to reason about step counting and early exit) |
| Prompt/parsing layer (`parser.py` + prompt template) | Render system prompt with tool descriptions; parse raw model text into a structured action (`ToolCall(name, args)` or `Final(text)` or `None`) | Regex over known tags (`<tool>`, `<args>`, `<final>`), `re.DOTALL`, tolerant of surrounding prose |
| Safety gate (`safety.py`) | Sit between "parsed tool call" and "tool execution"; apply blocklist, confirm prompt, dry-run short-circuit, using per-tool metadata | Function `check(tool_call, tool, flags) -> Allow/Deny/NeedsConfirm` |
| Tool registry (`tools/`) | Define available tools, each with name, arg schema, `run(**args)`, and a `requires_confirm: bool` / `is_dangerous` flag | Dict of name → tool object/function; shell, read_file, write_file, remember |
| Ollama backend | Generate next assistant message given full message history | `ollama.chat(model=..., messages=..., options={"stop": [...]})` — stateless, local |

## Recommended Project Structure

```
olla/
├── pyproject.toml          # console-script entry point: olla = olla.cli:main
├── src/
│   └── olla/
│       ├── __init__.py
│       ├── cli.py           # click entrypoint, arg parsing, wires everything together
│       ├── loop.py           # AgentLoop: owns messages, runs think/act/observe cycle
│       ├── parser.py         # parse_response() -> ToolCall | Final | None; regex over tags
│       ├── prompts.py         # system prompt template, tool description rendering
│       ├── safety.py          # blocklist, confirm prompt, dry-run gate
│       └── tools/
│           ├── __init__.py    # tool registry: dict[name -> Tool]
│           ├── base.py         # Tool dataclass/protocol: name, description, args schema, run(), requires_confirm
│           ├── shell.py         # run shell command tool
│           ├── files.py          # read_file, write_file tools
│           └── memory.py          # remember/recall scratchpad tool
└── tests/
    ├── test_parser.py        # parsing edge cases: malformed tags, prose, multiple calls
    ├── test_safety.py          # blocklist, confirm, dry-run
    ├── test_loop.py             # loop termination, max-steps, message construction
    └── test_tools/
```

### Structure Rationale

- **Single flat package (`src/olla/`)**: v1 is ~5-7 small modules. A deep package hierarchy (`core/`, `infra/`, `domain/`) would be premature — flat structure keeps it navigable and matches the "minimal, no framework" philosophy in PROJECT.md.
- **`tools/` as its own subpackage**: tools are the part most likely to grow (web search deferred to v2, more file ops, etc.). Isolating them behind a registry + `Tool` protocol means adding a tool never touches `loop.py` or `parser.py`.
- **`parser.py` separate from `loop.py`**: parsing logic needs heavy unit testing against malformed/edge-case model output independent of any Ollama call — keeping it pure (string in, structured action out) makes this trivial.
- **`safety.py` separate from `tools/`**: safety is a cross-cutting policy (blocklist patterns, confirm UX, dry-run flag handling) that applies *based on* tool metadata but isn't owned by any single tool. Keeping it separate means tools stay simple (`run()` just does the thing) and the gate stays generic.
- **`prompts.py` separate from `parser.py`**: the system prompt and the parser are two halves of a contract (the prompt tells the model the tag format; the parser reads it back). Keeping them in separate files but co-evolving them is fine, but some projects merge these — acceptable to combine if it stays under ~100 lines.

## Architectural Patterns

### Pattern 1: Stateless-backend, stateful-client loop

**What:** Ollama's `chat()` endpoint is stateless — it has no memory between calls. All conversation state lives in the client (`messages: list[dict]`), and the *entire* history is re-sent on every iteration.

**When to use:** Always, for this architecture. This is not optional — it's how `ollama.chat()` works.

**Trade-offs:**
- Pro: simple, debuggable — the message list at any point in time *is* the full agent state, can be logged/dumped/replayed.
- Con: token cost grows linearly with steps. With `--max-steps 15` and small models (0.6B-7B context windows often 4K-8K), this is the primary scaling constraint (see Scaling Considerations).

**Example:**
```python
messages = [{"role": "system", "content": system_prompt}]
messages.append({"role": "user", "content": task})

for step in range(max_steps):
    response = ollama.chat(model=model, messages=messages, options={"stop": stop_sequences})
    raw = response["message"]["content"]
    messages.append({"role": "assistant", "content": raw})  # store raw tagged output verbatim

    action = parse_response(raw)
    if isinstance(action, Final):
        return action.text
    if action is None:
        # model produced no recognizable tag — nudge it
        messages.append({"role": "user", "content": "No valid <tool> or <final> tag found. Respond with one."})
        continue

    result = dispatch(action, registry, safety_flags)  # safety gate lives here
    messages.append({"role": "user", "content": f"Observation: {result}"})
else:
    return "Max steps reached without final answer."
```

### Pattern 2: ReAct via plain-text tags, NOT native `tool` role messages

**What:** olla deliberately does **not** use Ollama's native function-calling API (`tools=[...]` parameter, `role: "tool"` messages with `tool_call_id`). That mechanism requires the model to emit structured JSON tool calls, which 0.6B-4B models do unreliably (per PROJECT.md's own rationale).

Instead: the model's full raw text response — including the `<tool>name</tool><args>{...}</args>` tags — is appended to history as a normal `assistant` message. The tool's result (the "observation") is appended back as a `user` message (conventionally prefixed `Observation: ...`), not a `tool`-role message.

**This is a deliberate divergence** from the generic "append tool results as `role: tool`" pattern that appears in most Ollama/OpenAI tool-calling tutorials — that pattern assumes native structured tool calling, which this project explicitly avoids.

**When to use:** Any time the model's tool-calling reliability via native JSON schemas is in doubt — i.e., always for sub-7B local models.

**Trade-offs:**
- Pro: works with *any* instruction-tuned model regardless of native tool-calling support; prompt is shorter (no JSON schema boilerplate); model output is human-readable and easy to debug.
- Con: parsing is now your responsibility (see Pattern 4); the model can drift from the format, requiring format-reinforcement messages.

**Example message list after 2 tool calls:**
```python
[
  {"role": "system", "content": "You are olla... use <tool>NAME</tool><args>{...}</args> or <final>...</final>..."},
  {"role": "user", "content": "List files in the current directory and tell me which is largest."},
  {"role": "assistant", "content": "<tool>shell</tool><args>{\"command\": \"ls -la\"}</args>"},
  {"role": "user", "content": "Observation: total 48\n-rw-r--r-- 1 user user 12000 file1.py\n..."},
  {"role": "assistant", "content": "<final>The largest file is file1.py at 12KB.</final>"}
]
```

### Pattern 3: Stop sequences to prevent hallucinated observations

**What:** The single most common failure mode in tag-based ReAct loops on small models: the model emits a valid `<tool>...</tool><args>...</args>` block, then — because nothing stops it — *keeps generating* and fabricates its own `Observation: ...` and even a fake `<final>` tag, never actually yielding control back to the loop for real tool execution.

**Why it happens:** The model has seen many ReAct-style transcripts in training where `Observation:` follows an action; absent an explicit stop signal, it pattern-matches and completes the transcript itself.

**Prevention:** Pass `options={"stop": ["</args>", "Observation:"]}` (or equivalent, matching whatever the closing-tag convention is) to `ollama.chat()`. This truncates generation at the tool-call boundary, forcing a turn-taking structure: model emits action → generation stops → loop executes tool → loop appends real observation → model resumes.

**When to use:** Always, in the agent loop's `chat()` call. This is a loop-level concern, not a parser-level one — the parser should still defensively handle cases where a model ignores the stop sequence (some models occasionally emit stop tokens as literal text instead of triggering the API stop), but the primary defense is the `stop` parameter.

**Trade-offs:**
- Pro: eliminates the most common and confusing small-model failure mode; keeps the loop's control flow honest.
- Con: if the model emits `<final>` and the stop list includes a substring that happens to appear inside the final answer text, generation could truncate prematurely — mitigate by choosing stop sequences that only appear in the *scaffolding* (closing tags, "Observation:") and instructing the model never to use those literal strings in `<final>` content. Test this against your actual models — confidence on exact stop-sequence behavior is MEDIUM, verify empirically with the target Ollama models (Qwen3, Gemma).

### Pattern 4: Tolerant regex parsing over fixed tag vocabulary, full-buffer (not streaming)

**What:** Because olla's tag vocabulary is fixed and known (`<tool>`, `<args>`, `<final>` — not arbitrary tags), parse with targeted regexes for those specific tags rather than a generic `<(\w+)>...</\1>` matcher. Buffer the complete (non-streamed) response from `ollama.chat()`, then run regex extraction — do not attempt incremental/streaming parse for v1.

**When to use:** Always for v1. Streaming parsing adds significant complexity (partial-tag buffering, backtracking) for no real UX benefit in a one-shot CLI where the user is waiting for a tool result anyway.

**Trade-offs:**
- Pro: simple, testable in isolation, handles the realistic failure modes (prose before/after tags, minor whitespace/case variation, missing closing tags in some cases).
- Con: no live "thinking" output to the terminal during generation (acceptable trade-off for v1; `rich` could add a spinner instead).

**Parsing strategy, in order:**
1. Search for `<final>(.*?)</final>` (DOTALL, case-insensitive) anywhere in the response. If found, that wins — return `Final(text)` immediately, ignoring any `<tool>` blocks that might also be present (a model that emits both is signaling "I'm done," trust `<final>`).
2. Else search for `<tool>(.*?)</tool>` and `<args>(.*?)</args>` (DOTALL). If both found:
   - Parse `<args>` content as JSON. If JSON parsing fails, attempt one repair pass (strip trailing commas, fix smart quotes, wrap bare keys) before giving up.
   - If multiple `<tool>` blocks appear in one response, **execute only the first** and re-prompt next turn — do not speculatively execute multiple tool calls from one generation. Small models that emit multiple actions in one shot are often hallucinating a multi-step transcript rather than deliberately batching.
3. If neither `<final>` nor a complete `<tool>`+`<args>` pair is found: return `None` (unparseable). The loop should respond with a corrective `user` message (e.g., "I couldn't find a valid `<tool>` or `<final>` tag in your response. Use the format: ...") and consume one step toward `--max-steps` — corrective retries count against the budget to bound worst-case runaway loops.

**Example:**
```python
import re, json
from dataclasses import dataclass

FINAL_RE = re.compile(r"<final>(.*?)</final>", re.DOTALL | re.IGNORECASE)
TOOL_RE  = re.compile(r"<tool>(.*?)</tool>", re.DOTALL | re.IGNORECASE)
ARGS_RE  = re.compile(r"<args>(.*?)</args>", re.DOTALL | re.IGNORECASE)

@dataclass
class Final:
    text: str

@dataclass
class ToolCall:
    name: str
    args: dict

def parse_response(raw: str) -> Final | ToolCall | None:
    if m := FINAL_RE.search(raw):
        return Final(m.group(1).strip())

    tool_match = TOOL_RE.search(raw)
    args_match = ARGS_RE.search(raw)
    if tool_match and args_match:
        name = tool_match.group(1).strip()
        try:
            args = json.loads(args_match.group(1).strip())
        except json.JSONDecodeError:
            args = repair_and_parse_json(args_match.group(1).strip())  # best-effort repair
        return ToolCall(name=name, args=args)

    return None
```

## Data Flow

### Request Flow (one loop iteration)

```
[messages: list[dict]]
    ↓
ollama.chat(model, messages, options={"stop": [...]})  ← Ollama backend (local)
    ↓
response.message.content  (raw text, may include prose + tags)
    ↓
messages.append({"role": "assistant", "content": raw})   ← raw text stored verbatim
    ↓
parse_response(raw) → Final | ToolCall | None              ← parser.py
    ↓
   ┌─────────────┬──────────────────┬───────────────┐
   │ Final(text) │ ToolCall(name,args)│ None          │
   ↓             ↓                  ↓
 RETURN     safety_gate.check(tool, args, flags)   append corrective
            ↓                                        user message,
   ┌────────┴────────┐                               continue loop
   │ allowed         │ denied/needs-confirm
   ↓                 ↓
registry[name].run(**args)   prompt user / abort / dry-run print
   ↓
result: str
   ↓
messages.append({"role": "user", "content": f"Observation: {result}"})
    ↓
[loop continues, step += 1]
```

### State Management

```
messages: list[dict]   ← single source of truth for conversation state
    │
    ├── grows by 2 entries per loop iteration (assistant action, user observation)
    ├── re-sent in full to ollama.chat() every iteration (stateless backend)
    └── on loop exit (Final or max-steps): printed to user, then DISCARDED
                                            (no persistence between `olla` invocations — v1 is one-shot)

scratchpad (remember/recall tool):
    │
    ├── in-memory dict, owned by the memory tool instance
    ├── written via <tool>remember</tool><args>{"key":..., "value":...}</args>
    ├── read via <tool>recall</tool><args>{"key":...}</args> → returned as an Observation
    └── re-enters context the SAME way as any other tool result — as a user/Observation
        message in `messages`. There is no separate "memory channel"; the scratchpad is
        just a tool whose output happens to persist across steps within one run.
```

**No context compaction/summarization in v1.** Some agent architectures (e.g., long-running coding assistants) implement context compaction when approaching the model's context window. This is explicitly an **anti-pattern for olla v1**: the loop is bounded (`--max-steps`, default 15), one-shot, and targets small-context local models where summarization itself would cost a model call and risk losing the exact tag-formatted history the model needs to stay in-format. If context length becomes a real problem with `--max-steps 15` on a 4K-context model, the correct v1 mitigation is reducing `--max-steps` or trimming tool *output* (e.g., truncate shell stdout to N lines) — not summarizing the conversation.

### Key Data Flows

1. **Task → Final answer:** User's one-shot task string becomes the first `user` message; the loop runs until a `<final>` tag is parsed, at which point `Final.text` is printed to stdout and the process exits.
2. **Tool dispatch with safety gating:** `ToolCall(name, args)` → safety gate checks (a) is `name` in registry, (b) does `registry[name].requires_confirm` apply, (c) does `args` (for shell: the command string) match the blocklist, (d) is `--dry-run` set. Only if all checks pass does `registry[name].run(**args)` execute. The gate's decision (and dry-run output) becomes the Observation text either way — even a denial is reported back to the model as an observation so it can adjust ("Command blocked by safety policy: contains 'rm -rf'").
3. **Scratchpad round-trip:** `remember(key, value)` writes to an in-memory dict scoped to the current run; `recall(key)` (or however retrieval is exposed) reads it back. Both enter/exit the loop exactly like shell/file tool calls — no special-cased data path.

## Scaling Considerations

This is a single-user, local, one-shot CLI — "scaling" here means *step count and context growth within a single invocation*, not concurrent users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Few steps (1-5), small model (0.6B-1.7B) | Default behavior is fine. Full message-list resend per `ollama.chat()` call is cheap relative to a 4-8K context window. |
| Many steps (10-15, near `--max-steps` default), small context model | Tool output size becomes the dominant cost. Truncate large shell stdout/file reads (e.g., cap at ~2000 chars with a "...truncated" marker) before appending as Observation — otherwise a single `cat largefile.txt` can blow the context budget in 1-2 steps. |
| Larger models (7B, larger context) | Headroom is more forgiving; the same truncation defaults are still good hygiene and keep responses fast (less to re-process per call). |

### Scaling Priorities

1. **First bottleneck: tool output size, not step count.** A single `read_file` on a large file or `shell` command with verbose output can dominate the context window faster than accumulating 15 small steps. Mitigation: truncate tool output at the dispatch layer (in `safety.py` or a shared `tools/base.py` helper), before it's appended as an Observation — applies uniformly to all tools.
2. **Second bottleneck: step count vs `--max-steps`.** If a model frequently hits the cap without producing `<final>`, that's a prompt/format problem (model isn't converging), not an architecture problem — but the architecture should make this *visible* (e.g., print the full step count and last action when max-steps is hit, so the user can diagnose whether the model is looping on the same tool call).

## Anti-Patterns

### Anti-Pattern 1: Native Ollama tool-calling (`tools=[...]`, `role: "tool"`)

**What people do:** Reach for Ollama's structured function-calling API because it's the "modern" pattern documented everywhere and matches OpenAI conventions.

**Why it's wrong:** Per PROJECT.md, the 0.6B-4B models this CLI targets are unreliable at producing valid structured JSON tool calls. Forcing that schema either fails silently (model produces malformed JSON, native parsing throws) or requires the model to spend tokens on JSON syntax it's bad at, increasing both latency and error rate on constrained hardware.

**Do this instead:** Plain-text `<tool>/<args>/<final>` tags as `assistant`/`user` messages (Pattern 2 above). This is *the* core architectural decision for this project — don't second-guess it mid-implementation when native tool calling "looks easier."

### Anti-Pattern 2: Letting the model run unbounded after a tool call (no stop sequence)

**What people do:** Call `ollama.chat()` without a `stop` parameter, then try to parse out "the first tool call" from a response that may contain a hallucinated full multi-turn transcript (model wrote its own fake Observation and final answer).

**Why it's wrong:** Wastes generation time/tokens on text that will be discarded; worse, the parser may grab the model's *fabricated* final answer instead of executing the real tool, producing confidently wrong results that look correct.

**Do this instead:** Pattern 3 — pass `options={"stop": [...]}` so generation halts at the action boundary. Treat any text after the stop point as not-generated (it won't exist).

### Anti-Pattern 3: Recursive loop implementation for step counting

**What people do:** Implement the ReAct loop as `act()` calling itself recursively (common in tutorial code, including Anthropic's own examples), since it reads cleanly.

**Why it's wrong:** Makes `--max-steps` enforcement and dry-run/early-exit logic awkward (need to thread a counter through recursive calls or rely on Python's recursion limit as a backstop, which is fragile and produces ugly stack traces on hitting the cap).

**Do this instead:** Plain `for step in range(max_steps)` / `while` loop in `loop.py`. Step counting, dry-run short-circuiting, and final-answer early-return are all trivial control flow in an iterative loop.

### Anti-Pattern 4: Context summarization/compaction for a bounded one-shot loop

**What people do:** Borrow "context compaction at 85% window usage" patterns from long-running coding agents (Claude Code, etc.).

**Why it's wrong:** olla v1 is bounded by `--max-steps` (default 15) and is one-shot — the conversation never persists or grows unboundedly across invocations. Summarization adds an extra model call (cost, latency, another failure point) and risks the summarizer paraphrasing away the exact tag-formatted history the model needs for in-context pattern matching.

**Do this instead:** Bound growth at the source — truncate large tool outputs (Scaling Priorities #1) and keep `--max-steps` low enough that raw history fits. If this genuinely becomes insufficient, that's a v2 problem to revisit with real usage data, not a v1 architectural concern.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Ollama (local daemon, `localhost:11434`) | `ollama` Python client, `ollama.chat(model, messages, options)` | Stateless per call — full history resent. No native tool-calling param used (deliberate, see Pattern 2). `--model` flag passed straight through to `model=`; no validation needed beyond letting Ollama error if the model isn't pulled — surface that error cleanly to the user. |
| Local filesystem | `read_file`/`write_file` tools, plain Python `pathlib`/`open()` | No sandboxing in v1 beyond confirm-gating writes. Path resolution should be relative to CWD where `olla` is invoked — be explicit about this in tool descriptions sent to the model. |
| Local shell | `shell` tool via `subprocess.run(..., shell=True, capture_output=True, timeout=...)` | Blocklist + confirm gate sit in front of this (Safety Gate component). A timeout (e.g., 30-60s) is worth adding even though not in PROJECT.md explicitly — prevents a hung command from hanging the whole agent run indefinitely. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `cli.py` ↔ `loop.py` | Direct function/class call — `cli.py` builds config (model, max_steps, flags) and calls `AgentLoop(...).run(task)` | CLI owns argv parsing only; zero business logic in `cli.py`. |
| `loop.py` ↔ `parser.py` | Pure function call — `parse_response(raw_text) -> Final \| ToolCall \| None` | No shared state; parser is fully unit-testable without a loop or Ollama instance. |
| `loop.py` ↔ `safety.py` | `safety_gate.check(tool_call, tool_metadata, flags) -> Decision` (Allow / Deny / NeedsConfirm), and `safety_gate.confirm(prompt) -> bool` for interactive prompts | Loop calls the gate *before* calling `registry[name].run()`. Gate never calls tools directly — it only decides. |
| `loop.py` ↔ `tools/registry` | `registry[name].run(**args) -> str` | Tools return plain strings (the Observation text). Tools are the only component that touches subprocess/filesystem. |
| `safety.py` ↔ `tools/base.py` | Reads `Tool.requires_confirm` (bool) and possibly `Tool.is_dangerous_arg(args) -> bool` for fine-grained blocklist checks (e.g., shell-specific command pattern matching) | Keeps the blocklist *patterns* tool-specific (only `shell` has a command blocklist; `write_file` just needs confirm) while the *gate logic* (prompt user, honor `--yes`/`--dry-run`) stays generic in `safety.py`. |
| `loop.py` ↔ Ollama (`ollama.chat`) | `messages: list[dict]` in, `response.message.content: str` out, plus `options={"stop": [...]}` | This is the only network/subprocess-adjacent boundary that's "external" — everything else is in-process Python. |

## Build Order (Vertical Slices)

This maps directly to phase structure for the roadmap — each slice is independently runnable and testable.

1. **Slice 1 — Core loop, no safety, one tool (shell), hardcoded confirm-skip:**
   - `cli.py` (minimal: `--model`, positional task arg)
   - `loop.py` (iterative loop, message list, step counter, `--max-steps`)
   - `parser.py` (full Pattern 4 parsing — get this right early, it's load-bearing for everything)
   - `prompts.py` (system prompt describing `<tool>shell</tool>`, `<args>`, `<final>` format)
   - `tools/shell.py` (just `subprocess.run`, no blocklist yet)
   - Stop-sequence wiring (Pattern 3) — get this in from the start, retrofitting is painful once prompts are tuned around its absence/presence
   - **Goal:** `olla "list files in this directory"` works end-to-end against a real Ollama model.

2. **Slice 2 — Safety gate (blocklist, confirm, dry-run, `--yes`):**
   - `safety.py` + `tools/base.py` (`Tool` protocol with `requires_confirm`)
   - Wire shell tool through the gate
   - `--dry-run` and `--yes` flags in `cli.py`
   - **Goal:** dangerous commands are blocked or require confirmation; `--dry-run` shows planned actions without executing.

3. **Slice 3 — File tools:**
   - `tools/files.py` (`read_file`, `write_file`)
   - `write_file` flagged `requires_confirm=True` in registry, flows through existing gate with no new gate logic
   - **Goal:** model can read and write files, gated like shell.

4. **Slice 4 — Memory/scratchpad:**
   - `tools/memory.py` (`remember`, `recall`)
   - No safety implications (in-memory only, no `requires_confirm`)
   - **Goal:** model can stash and retrieve notes across steps within one run.

**Rationale for this order:** the loop + parser + stop-sequence combination (Slice 1) is the riskiest, highest-uncertainty part — it's where small-model quirks (Pattern 3's hallucinated observations, Pattern 4's malformed tags) will actually surface, and everything else is built on top of it. Safety (Slice 2) is explicitly called "non-negotiable" in PROJECT.md but is architecturally *additive* — it slots into the existing dispatch point without changing the loop or parser. File tools and memory (Slices 3-4) are then pure registry additions with zero changes to `loop.py`/`parser.py`/`safety.py` — the registry/gate design is validated by how cheaply these slot in.

## Sources

- [Ollama Python library (GitHub)](https://github.com/ollama/ollama-python) — `chat()` signature, message structure (MEDIUM confidence — repo README doesn't show multi-turn tool-call examples directly; message-list pattern is standard across OpenAI-compatible chat APIs and confirmed via DeepWiki community docs)
- [Conversation History — ollama/ollama-python (DeepWiki)](https://deepwiki.com/ollama/ollama-python/4.7-conversation-history) — confirms stateless backend, client-side history accumulation pattern (MEDIUM confidence, community-maintained doc)
- [A Super Simple ReAct Agent from Scratch (Medium)](https://medium.com/data-science-collective/a-super-simple-react-agent-87913949f69f) — confirms minimal loop structure (context window list, act() decision on stop condition), used to validate iterative-vs-recursive tradeoff (MEDIUM confidence, single blog source but pattern matches broader agent literature)
- [XML Tool Calls — Morph docs](https://docs.morphllm.com/guides/xml-tool-calls) — regex-based tag extraction strategy, malformed-XML recovery philosophy ("minor XML malformation is recoverable, unlike JSON") (MEDIUM confidence, vendor docs but principle is widely echoed)
- [gptme (GitHub)](https://github.com/gptme/gptme) — example of a "minimal core, extend via tools" local-agent architecture philosophy, validates registry-based tool extensibility pattern (MEDIUM confidence, large/more featureful project but architectural philosophy transfers)
- Stop-sequence / hallucinated-observation failure mode and fixed-tag-vocabulary parsing recommendation: synthesized from general small-model ReAct failure patterns and XML-parsing best-practice sources above — **flagged LOW-MEDIUM confidence as a specific claim**; recommend validating empirically against the project's actual target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive) early in Slice 1, since exact stop-token behavior can vary by model/template.

---
*Architecture research for: lightweight ReAct CLI agent (olla)*
*Researched: 2026-06-10*
