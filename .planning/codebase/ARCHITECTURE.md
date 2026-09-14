<!-- refreshed: 2026-09-14 -->
# Architecture

**Analysis Date:** 2026-09-14

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                       │
│                     `src/olla/cli.py`                        │
│   (click parses TASK + flags, loads config, picks model)     │
└──────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ReAct Loop Orchestrator                   │
│                    `src/olla/loop.py`                        │
│  run_loop() drives: call model → parse action → safety gate  │
│  → execute tool → record observation → repeat until <final>  │
└───────┬──────────────┬──────────────┬──────────────┬─────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────────┐ ┌────────────┐ ┌───────────┐ ┌────────────────┐
│   Parser     │ │  Providers │ │  Safety   │ │     Tools       │
│ `parser.py`  │ │`providers/`│ │`safety.py`│ │   `tools/*.py`  │
│ tag → action │ │ model chat │ │ argv gate │ │ shell/files/    │
│              │ │  (stream)  │ │ ALLOW/    │ │ inspect/memory/ │
│              │ │            │ │ CONFIRM/  │ │ web             │
│              │ │            │ │ BLOCK     │ │                 │
└──────────────┘ └─────┬──────┘ └───────────┘ └─────────────────┘
                        │
                        ▼
              ┌───────────────────────┐
              │  External / OS Layer  │
              │  Ollama server (HTTP) │
              │  OpenAI-compatible    │
              │  API (OpenRouter/     │
              │  OpenAI)              │
              │  Local filesystem     │
              │  subprocess (shell)   │
              │  Network (web tools)  │
              └───────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI entry point | Parse flags/task, load config, dispatch to loop or smoke test | `src/olla/cli.py` |
| ReAct loop | Drive reason→act→observe cycle, own conversation `messages` list | `src/olla/loop.py` |
| Action normalization | Parse one model turn into a typed `_Action` before any handler runs | `src/olla/loop.py` (`_prepare_action`) |
| Tag parser | Tolerant extraction of `<tool>/<args>/<final>` from raw model text | `src/olla/parser.py` |
| Provider abstraction | Uniform `chat`/`stream_chat`/`get_context_length` across backends | `src/olla/providers/base.py` |
| Provider factory | Route a model string (`openrouter/...`, `openai/...`, `ollama/...`, bare) to a provider instance | `src/olla/providers/__init__.py` |
| Ollama provider | Talk to local Ollama daemon via the `ollama` Python client | `src/olla/providers/ollama.py` |
| OpenAI-compatible provider | Talk to OpenRouter/OpenAI-style HTTP APIs via `httpx` | `src/olla/providers/openai_compat.py` |
| Safety gate | Pure function classifying a shell `argv` as ALLOW/CONFIRM/BLOCK | `src/olla/safety.py` |
| Shell tool | Execute a pre-parsed argv via `subprocess.run(shell=False)` | `src/olla/tools/shell.py` |
| File tools | Read/write files with stat-based staleness detection (TOCTOU-resistant) | `src/olla/tools/files.py` |
| Inspection tools | `list_dir` and `grep_files` (read-only, always auto-run) | `src/olla/tools/inspect.py` |
| Memory tool | Invocation-scoped scratchpad (`remember`/`recall`) with size caps | `src/olla/tools/memory.py` |
| Web tools | `fetch_url` (readable-text extraction) and `search_web` | `src/olla/tools/web.py` |
| Shared tool contract | `ToolResult` TypedDict and `FileSnapshot` identity type used by every tool | `src/olla/tools/base.py` |
| System prompt | Teaches the model the tag protocol and available tools | `src/olla/prompts.py` |
| Config loader | TOML config resolution (`~/.config/olla/config.toml` etc.) | `src/olla/config.py` |
| Debug logging | Verbose JSON-ish trace of loop internals gated by `--debug`/env | `src/olla/debug.py` |
| Smoke test | Format-compliance check of a model against the tag protocol | `src/olla/smoke.py` |

## Pattern Overview

**Overall:** Single-process, single-threaded ReAct (Reason → Act → Observe) agent loop. Not a framework — one flat `src/olla/` package with a thin CLI shell around a stateful `run_loop()` function.

**Key Characteristics:**
- No classes for the loop itself — `run_loop()` is a long, linear, step-driven function using local mutable state (`messages`, `read_snapshots`, `previous_signature`).
- Tool dispatch is a manual `if/elif` chain over a normalized `_Action.kind` string, not a registry or plugin system.
- Providers are a small Protocol-based abstraction (`Provider` in `providers/base.py`) with a factory function (`get_provider`) — not an ABC hierarchy.
- Safety is a pure, side-effect-free classification function (`safety.check`) completely decoupled from execution (`tools/shell.py`) and from prompting (`loop.py` owns the `Confirm.ask` UI).
- Security-by-construction: model output is parsed with regex/tolerant parsing (never `eval`/`exec`), shell commands run with `shell=False` over `shlex`-parsed argv, file writes require a same-run `read_file` first and a stat/digest snapshot match at write time.

## Layers

**CLI Layer:**
- Purpose: Translate command-line invocation into a `run_loop()` call
- Location: `src/olla/cli.py`
- Contains: `click` command definition, config merge (CLI flag > config.toml > env), smoke-test dispatch
- Depends on: `config.py`, `loop.py`, `prompts.py`, `smoke.py`, `debug.py`
- Used by: `pyproject.toml` `[project.scripts]` entry point (`olla = "olla.cli:main"`)

**Orchestration Layer (the loop):**
- Purpose: Own the ReAct step cycle and all conversation state
- Location: `src/olla/loop.py`
- Contains: `run_loop`, `_prepare_action`, `_preview_action` (dry-run), one `_execute_*` function per tool kind, observation recorders, terminal-safety helpers
- Depends on: `parser.py`, `providers/`, `safety.py`, `tools/*`, `debug.py`
- Used by: `cli.py`

**Parsing Layer:**
- Purpose: Convert raw model text into a structured intent (`final`/`tool`/`none`)
- Location: `src/olla/parser.py`
- Contains: pure regex-span logic, markdown-fence unwrapping, special-casing for tools whose `<args>` payload may itself contain protocol-looking text (`write_file`, `remember`, `recall`)
- Depends on: nothing internal (stdlib `re` only)
- Used by: `loop.py` (`_prepare_action`)

**Provider Layer:**
- Purpose: Normalize chat/streaming across local and remote model backends
- Location: `src/olla/providers/`
- Contains: `Provider` Protocol + `StreamChunk`/`ProviderError` (`base.py`), `OllamaProvider` (`ollama.py`), `OpenAICompatProvider` (`openai_compat.py`), routing factory (`__init__.py`)
- Depends on: `config.py` (for API keys/base URLs), external `ollama`/`httpx` clients
- Used by: `loop.py`, `smoke.py`

**Safety Layer:**
- Purpose: Classify shell commands before execution; never executes anything itself
- Location: `src/olla/safety.py`
- Contains: `ALLOWLIST` (read-only binaries), `_HARD_BLOCKED_BINARIES`, `_RM_DANGEROUS_TARGETS`, device-glob checks, fork-bomb regex, `env`/`find -exec`/`bash -c` unwrapping, `check(argv, yes) -> Decision`
- Depends on: stdlib only (`fnmatch`, `re`, `shlex`, `os`)
- Used by: `loop.py` (`_execute_shell`, `_preview_action`)

**Tools Layer:**
- Purpose: Perform the actual side-effecting or read-only operations
- Location: `src/olla/tools/`
- Contains: `shell.py` (subprocess), `files.py` (read/write with fd-based TOCTOU protection), `inspect.py` (list_dir/grep_files), `memory.py` (Scratchpad), `web.py` (fetch_url/search_web), `base.py` (shared `ToolResult`/`FileSnapshot` types)
- Depends on: stdlib (`os`, `subprocess`, `re`) plus `httpx`-style HTTP for `web.py`
- Used by: `loop.py` exclusively — tools have no knowledge of the loop or of each other

**Support Layer:**
- Purpose: Cross-cutting concerns not specific to any one tool
- Location: `src/olla/config.py`, `src/olla/debug.py`, `src/olla/prompts.py`, `src/olla/smoke.py`
- Contains: TOML config loading, debug tracing, the system prompt string, model format-compliance smoke test
- Depends on: stdlib (`tomllib`/`tomli`), nothing else internal
- Used by: `cli.py`, `loop.py`, `providers/`

## Data Flow

### Primary Request Path (one ReAct step)

1. `run_loop()` builds/extends `messages: list[dict]` and calls `_stream_model_turn()` (`src/olla/loop.py:534`), which streams tokens via `provider.stream_chat()` (`src/olla/providers/base.py:27`).
2. Raw model text is stripped of `<think>` blocks (`_strip_thinking`, `src/olla/loop.py:209`) then handed to `parse_response()` (`src/olla/parser.py:45`), which returns `{"type": "final"|"tool"|"none", ...}`.
3. `_prepare_action()` (`src/olla/loop.py:219`) normalizes the parsed dict into a frozen `_Action` dataclass, resolving file paths, splitting shell argv via `shlex`, and building a repeat-detection `signature` — all before any handler executes, so validation errors surface uniformly.
4. `run_loop()` dispatches on `action.kind` to one `_execute_*` function (`_execute_shell`, `_execute_read_file`, `_execute_write_file`, `_execute_list_dir`, `_execute_grep_files`, `_execute_fetch_url`, `_execute_search_web`, `_execute_memory`), each in `src/olla/loop.py`.
5. Shell actions are classified first by `safety.check()` (`src/olla/safety.py:254`) into ALLOW / CONFIRM / BLOCK; CONFIRM prompts via `rich.prompt.Confirm.ask` unless `--yes` was passed and no untrusted observation has been seen yet in this run.
6. Each tool call returns a `ToolResult` dict (`src/olla/tools/base.py:26`); the result is truncated (`truncate_output`, `src/olla/loop.py:485`) and appended back into `messages` as an `Observation:` message via one of the `_record_*_observation` helpers, which tag content by provenance (`<untrusted_shell_output>`, `<untrusted_file_content>`, etc.).
7. Loop repeats until the model emits `<final>...</final>` (returned immediately) or `max_steps` is exhausted (0 = unlimited via `itertools.count`).

### Write-File Safety Flow

1. Model must call `read_file` on a path in the *same run* before `write_file` can overwrite it; the read result is cached in `read_snapshots: dict[Path, _FileReadSnapshot]` (`src/olla/loop.py:1047`) keyed by resolved path.
2. At write time, `_execute_write_file()` (`src/olla/loop.py:730`) re-reads the file and compares content + `FileSnapshot` (device/inode/mtime/ctime/size/digest) against the cached snapshot — any mismatch triggers a "changed, disappeared, or became unreadable" refusal (`_read_again_observation`).
3. The parent directory is opened via `open_parent_directory()` (`src/olla/tools/files.py`) and its own snapshot compared before and after user confirmation, closing a TOCTOU window between preview and write.
4. `write_file()` performs the actual write using the open parent directory fd and expected snapshots; ambiguous outcomes are surfaced as `status: "uncertain"` rather than silently assumed successful.

### Dry-Run Path

1. `run_loop(..., dry_run=True)` performs exactly one model turn, parses it into an `_Action`, and calls `_preview_action()` (`src/olla/loop.py:567`) instead of any `_execute_*` function — no tool is actually invoked, no state is mutated, no confirmation prompt is shown (the would-be CONFIRM/BLOCK verdict is printed instead).

**State Management:**
- All state is local to `run_loop()`'s stack frame: `messages` (conversation history), `scratchpad` (`Scratchpad` instance for `remember`/`recall`), `read_snapshots` (write-safety cache), `previous_signature`/`repeat_count` (stuck-model detection), `untrusted_observation_seen` (confirm-escalation flag). Nothing is persisted across process invocations except the on-disk scratch targets written by `write_file` itself and the TOML config file.

## Key Abstractions

**`_Action` (frozen dataclass):**
- Purpose: One normalized, validated model action shared by both the dry-run preview path and the real execution path, so validation logic is written exactly once
- Examples: `src/olla/loop.py:97` (definition), built by `_prepare_action`
- Pattern: Parse-once-normalize-early — every field needed by any handler is precomputed (resolved `Path`, parsed `argv`, `_MemoryRequest`) so handlers only branch on `action.kind`, never re-parse `args_raw`

**`Provider` (Protocol):**
- Purpose: Structural-typing interface so `loop.py`/`smoke.py` never import a concrete provider class directly
- Examples: `src/olla/providers/base.py:20`, implemented by `OllamaProvider` and `OpenAICompatProvider`
- Pattern: `typing.Protocol` with three methods (`chat`, `stream_chat`, `get_context_length`); `get_provider()` factory hides construction/config resolution

**`ToolResult` (TypedDict, `total=False`):**
- Purpose: One shared, partial-by-default return shape for every tool so `loop.py` can uniformly check `"error" in result`
- Examples: `src/olla/tools/base.py:26`
- Pattern: Optional keys (`content`, `error`, `warning`, `snapshot`, `status`, ...) let each tool populate only what's relevant to its outcome

**`FileSnapshot` (TypedDict):**
- Purpose: Identity/version fingerprint of a file (device, inode, mtimes, size, mode, digest) used to detect concurrent modification between read and write
- Examples: `src/olla/tools/base.py:20`, produced by `src/olla/tools/files.py`, compared in `_execute_write_file` (`src/olla/loop.py:730`)
- Pattern: Stat-based optimistic concurrency control (compare-and-swap semantics for file writes)

**`Decision` (TypedDict, `Literal["ALLOW","CONFIRM","BLOCK"]`):**
- Purpose: The sole output of the safety gate; carries an optional `reason` only when `kind == "BLOCK"`
- Examples: `src/olla/safety.py:14`, produced by `check()`, consumed by `_execute_shell`/`_preview_action`
- Pattern: Closed-set decision type — no boolean flags, no partial trust levels

## Entry Points

**CLI (`olla` command):**
- Location: `src/olla/cli.py:main` (wired via `pyproject.toml` `[project.scripts]`)
- Triggers: User runs `olla "task description" --model ...`
- Responsibilities: Parse flags, merge config (`config.py`), select debug mode, dispatch to `run_smoke_test()` or `run_loop()`

**`run_loop()` (programmatic/library entry):**
- Location: `src/olla/loop.py:994`
- Triggers: Called by `cli.py:main`; also invoked directly in tests
- Responsibilities: Full agent lifecycle — provider resolution, message-loop driving, dry-run short-circuit, step-limit enforcement

**`run_smoke_test()`:**
- Location: `src/olla/smoke.py`
- Triggers: `olla --smoke-test --model <model>`
- Responsibilities: Verify a given model can produce well-formed `<tool>/<args>`/`<final>` output before running real tasks against it

## Architectural Constraints

- **Threading:** Single-threaded throughout. Model streaming (`provider.stream_chat`) is a synchronous generator consumed inline; no async/await, no worker threads, no concurrency primitives anywhere in `src/olla/`.
- **Global state:** `src/olla/debug.py` holds one module-level singleton flag `_DEBUG_ENABLED` mutated via `set_debug()`. No other module-level mutable state exists — `run_loop()` deliberately keeps everything else on the local stack frame.
- **Circular imports:** None observed. Dependency direction is strictly `cli.py` → `loop.py` → {`parser.py`, `providers/`, `safety.py`, `tools/*`, `debug.py`} → stdlib/third-party. `tools/*` modules do not import from `loop.py` or each other (except `tools/files.py`/`tools/inspect.py`/`tools/memory.py`/`tools/web.py` all import only `tools/base.py`).
- **Provenance tagging is mandatory:** every tool observation is wrapped in an `<untrusted_*_content>` marker before being appended to `messages` (see `_record_file_observation`, `_record_shell_observation`, `_record_web_observation`, `_record_memory_observation` in `src/olla/loop.py`) — this is a deliberate prompt-injection mitigation, not incidental formatting, and must be preserved when adding new tool types.
- **No tool registry:** Adding a new tool requires touching `parser.py` (if new tag shape), `_prepare_action` (new `_Action` fields/branch), a new `_execute_*` function, and the `if/elif` dispatch chain in `run_loop()` — there is no plugin/registration mechanism.

## Anti-Patterns

### Manual `if/elif` action dispatch instead of a handler map

**What happens:** `run_loop()` and `_preview_action()` both branch on `action.kind` with long `if/elif` chains (`src/olla/loop.py:1104-1176` and `:567-645`).
**Why it's wrong:** Adding a tool means editing two parallel dispatch chains plus `_prepare_action`; nothing enforces they stay in sync (e.g. a new `action.kind` without a `_preview_action` branch silently falls to the `else` case).
**Do this instead:** When adding a new tool kind, update both dispatch chains together and add a corresponding test in `tests/test_loop.py` that exercises the dry-run path, not just the execute path.

### Direct mutation of shared `messages` list from deep helper functions

**What happens:** Small helpers like `_record_observation`, `_execute_write_file`, etc. all take `messages: list[dict]` and append to it directly rather than returning a value for the caller to append.
**Why it's wrong:** Makes it easy to accidentally double-append or append in the wrong order if a new helper is inserted into the dispatch chain without care; message ordering is load-bearing for the model's context.
**Do this instead:** Keep exactly one `messages.append(...)` call per handler invocation (already the current convention) and always append immediately after producing the observation string — do not defer or batch appends.

## Error Handling

**Strategy:** Fail soft, in-band. Errors from tools/providers are converted into `Observation:`-prefixed strings appended to the conversation (so the model can see and react to them) rather than raised as exceptions that crash the loop. Only unrecoverable setup failures (`ProviderError` during provider construction, model call returning `None`) cause `run_loop()` to `return` early and print a diagnostic via `_display()`.

**Patterns:**
- Tool functions never raise for expected failure modes — they catch `OSError`/`FileNotFoundError`/etc. and return `{"error": "..."}` inside a `ToolResult` dict (see `tools/shell.py`, `tools/inspect.py`).
- `safety.check()` never raises; unclassifiable/empty input returns a `BLOCK` decision rather than an exception.
- Model/network failures (`ollama.RequestError`, `ollama.ResponseError`, `ProviderError`) are caught at the loop boundary (`_call_model_for_loop`, `_stream_model_turn`) and converted to a user-facing message; the loop then exits cleanly rather than propagating a traceback.

## Cross-Cutting Concerns

**Logging:** `debug_log()` (`src/olla/debug.py`) is the sole logging mechanism, gated by `--debug` flag, `OLLA_DEBUG` env var, or `debug = true` in config.toml. It pretty-prints JSON-serializable structures with a `[DEBUG]` prefix in magenta ANSI. No structured logging library, no log levels beyond on/off.

**Validation:** Two layers — (1) parser-level structural validation (`parser.py` rejects malformed/duplicated/nested tag structures), and (2) action-level semantic validation (`_prepare_action` resolves paths, validates shell quoting via `shlex.split`, checks memory key/value size limits).

**Authentication:** API keys for remote providers (OpenRouter/OpenAI) are resolved with a fixed precedence: CLI flag `--api-key` > environment variable (`OPENROUTER_API_KEY`/`OPENAI_API_KEY`) > provider-specific config.toml section > generic config.toml key (`src/olla/providers/__init__.py`). Keys are masked in debug output via `mask_secret()` (`src/olla/debug.py`) — never printed in full.

---

*Architecture analysis: 2026-09-14*
