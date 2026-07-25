<!-- refreshed: 2026-07-25 -->
# Architecture

**Analysis Date:** 2026-07-25

## System Overview

```text
┌───────────────────────────────────────────────────────────────────────┐
│                         CLI Interface Layer                           │
│  console script `olla` → Click command `src/olla/cli.py`             │
├────────────────────────────────────┬──────────────────────────────────┤
│ Normal task mode                   │ Format-compliance smoke mode     │
│ `src/olla/loop.py`                 │ `src/olla/smoke.py`              │
└──────────────────┬─────────────────┴────────────────┬─────────────────┘
                   │                                  │
                   ▼                                  │
┌─────────────────────────────────────────────────────┴─────────────────┐
│                     Model Protocol Boundary                           │
│  prompt: `src/olla/prompts.py`                                        │
│  Ollama call: `src/olla/loop.py:26`                                   │
│  response parsing/classification: `src/olla/parser.py`,               │
│                                   `src/olla/smoke.py`                  │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ parsed tool request
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                 Orchestration and Safety Policy                       │
│  step/history/repetition control: `src/olla/loop.py`                  │
│  ALLOW / CONFIRM / BLOCK policy: `src/olla/safety.py`                 │
└──────────────────┬─────────────────────────────────┬──────────────────┘
                   │                                 │
                   ▼                                 ▼
┌───────────────────────────────┐     ┌─────────────────────────────────┐
│ Shell Adapter                 │     │ File Adapters                   │
│ `src/olla/tools/shell.py`     │     │ `src/olla/tools/files.py`       │
│ `subprocess.run(shell=False)` │     │ `pathlib.Path`                  │
└───────────────────────────────┘     └─────────────────────────────────┘
                   │                                 │
                   ▼                                 ▼
            Host processes                    Host filesystem
```

The application is a small synchronous CLI. It keeps the complete session in an
in-memory Ollama message list, asks a local model for one XML-tagged action at a
time, executes or rejects that action, and returns the resulting observation to
the model. There is no server process, database, background worker, event bus, or
persistent application state.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Package metadata | Exposes the package version | `src/olla/__init__.py` |
| CLI composition root | Declares Click arguments/options, validates invocation mode, and routes to task or smoke execution | `src/olla/cli.py` |
| ReAct controller | Owns conversation history, step limits, repetition detection, confirmation gates, tool dispatch, and terminal output | `src/olla/loop.py` |
| Model boundary | Calls `ollama.chat()` with the fixed stop sequences and context size | `src/olla/loop.py:26` |
| Protocol parser | Converts tolerant `<final>` or `<tool>/<args>` output into a discriminated dictionary | `src/olla/parser.py` |
| Prompt contract | Teaches models the three supported tools and the one-tag-block-per-turn protocol | `src/olla/prompts.py` |
| Safety policy | Classifies parsed shell argv as `ALLOW`, `CONFIRM`, or `BLOCK` | `src/olla/safety.py` |
| Smoke runner | Measures prompt-format compliance for normal and thinking model modes | `src/olla/smoke.py` |
| Tool result contract | Defines the shared partial result fields returned by all tool adapters | `src/olla/tools/base.py` |
| Shell adapter | Executes pre-parsed argv without a shell and translates process outcomes into `ToolResult` | `src/olla/tools/shell.py` |
| File adapters | Read and write UTF-8 text and translate filesystem failures into `ToolResult` | `src/olla/tools/files.py` |

## Pattern Overview

**Overall:** Synchronous functional core with a thin CLI composition root and
ports-and-adapters-style external boundaries.

**Key Characteristics:**

- Keep invocation wiring in `src/olla/cli.py`; pass explicit values into
  `run_loop()` rather than storing runtime configuration globally.
- Keep session state local to `src/olla/loop.py`. The `messages`, `prev_sig`,
  and `repeat_count` values belong to one invocation and are discarded on exit.
- Treat model output as untrusted protocol text. Parse it in
  `src/olla/parser.py`, tokenize shell arguments with `shlex.split()`, then
  evaluate policy in `src/olla/safety.py` before reaching a tool adapter.
- Keep infrastructure adapters thin. `src/olla/tools/shell.py` and
  `src/olla/tools/files.py` perform I/O and return data; orchestration,
  confirmation, and presentation remain in `src/olla/loop.py`.
- Report recoverable tool failures as data through
  `src/olla/tools/base.py:6`, allowing the loop to feed failures back to the
  model as observations.
- Use one model action per iteration. The system prompt in
  `src/olla/prompts.py:22` and the loop in `src/olla/loop.py:88` enforce the
  sequential reason → act → observe shape.

## Layers

**CLI Interface:**

- Purpose: Convert command-line input into one of the two application flows.
- Location: `src/olla/cli.py`
- Contains: One Click command, one positional task, and execution flags.
- Depends on: `src/olla/loop.py`, `src/olla/prompts.py`, and
  `src/olla/smoke.py`.
- Used by: The `olla` console script declared in `pyproject.toml`.

**Application Orchestration:**

- Purpose: Drive the iterative model/tool interaction and render user-visible
  progress.
- Location: `src/olla/loop.py`
- Contains: `run_loop()`, `call_model()`, and `truncate_output()`.
- Depends on: Ollama, Rich confirmation prompts, the parser, safety policy, and
  concrete tool adapters.
- Used by: `src/olla/cli.py` and, for `call_model()`,
  `src/olla/smoke.py`.

**Model Protocol:**

- Purpose: Define and decode the compact text contract used by small local
  models.
- Location: `src/olla/prompts.py`, `src/olla/parser.py`
- Contains: `SYSTEM_PROMPT`, tolerant regular expressions, and
  `parse_response()`.
- Depends on: Python's `re` module only.
- Used by: `src/olla/cli.py`, `src/olla/loop.py`, and
  `src/olla/smoke.py`.

**Policy:**

- Purpose: Decide whether a shell request is read-only, confirmation-required,
  or forbidden.
- Location: `src/olla/safety.py`
- Contains: Command allowlist, destructive-operation block rules, wrapper
  unwrapping, and the `Decision` result contract.
- Depends on: Standard-library argument/path pattern utilities.
- Used by: Shell branches in `src/olla/loop.py`.

**Tool Infrastructure:**

- Purpose: Isolate host-process and host-filesystem I/O behind simple
  functions.
- Location: `src/olla/tools/`
- Contains: `run_shell()`, `read_file()`, `write_file()`, and `ToolResult`.
- Depends on: `subprocess`, `pathlib`, and `typing`.
- Used by: Tool dispatch in `src/olla/loop.py`.

**Diagnostic Flow:**

- Purpose: Check whether a selected model follows olla's XML tag protocol.
- Location: `src/olla/smoke.py`
- Contains: Fixed prompts, response classifiers, two think-mode passes, and
  threshold reporting.
- Depends on: `call_model()` from `src/olla/loop.py` and `SYSTEM_PROMPT` from
  `src/olla/prompts.py`.
- Used by: The `--smoke-test` branch in `src/olla/cli.py`.

## Data Flow

### Primary Request Path

1. Packaging resolves the `olla` executable to `olla.cli:main`
   (`pyproject.toml:16`).
2. Click parses the task and flags; `main()` rejects missing task/model input
   and calls `run_loop()` (`src/olla/cli.py:17`).
3. `run_loop()` initializes system and user messages in invocation-local state
   (`src/olla/loop.py:34`).
4. Each step calls the local Ollama server through `ollama.chat()`
   (`src/olla/loop.py:26`) and parses the returned text through
   `parse_response()` (`src/olla/loop.py:90`).
5. A `<final>` response is printed and terminates the invocation
   (`src/olla/loop.py:94`).
6. A shell request is tokenized with `shlex.split()`, checked by
   `src/olla/safety.py:251`, optionally confirmed with Rich, and passed as argv
   to `src/olla/tools/shell.py:8` (`src/olla/loop.py:98`).
7. A `read_file` request goes directly to `src/olla/tools/files.py:8`; a
   `write_file` request is split into path/content, validated for a content
   line, confirmed unless `--yes` is set, and sent to
   `src/olla/tools/files.py:26` (`src/olla/loop.py:149`,
   `src/olla/loop.py:174`).
8. Tool output or an error is truncated to a head/tail preview, printed, and
   appended as a user-role `Observation:` message
   (`src/olla/loop.py:145`, `src/olla/loop.py:170`,
   `src/olla/loop.py:212`).
9. The loop repeats until a final answer, three identical consecutive calls,
   or `max_steps` is reached (`src/olla/loop.py:88`,
   `src/olla/loop.py:115`, `src/olla/loop.py:233`).

### Dry-Run Flow

1. `--dry-run` still performs exactly one model call
   (`src/olla/loop.py:39`).
2. The response is parsed, and the first proposed result/action is described.
3. Shell requests still pass through the safety classifier, but no
   confirmation or adapter call occurs.
4. File requests report the resolved target or malformed-write refusal, but
   never access the filesystem.
5. The function returns after the preview; no observation is sent back to the
   model.

### Smoke-Test Flow

1. `--smoke-test --model NAME` bypasses task validation and routes to
   `run_smoke_test()` (`src/olla/cli.py:19`).
2. Each prompt in `FIXED_PROMPTS` runs once with `think=False` and once with
   `think=True` (`src/olla/smoke.py:39`).
3. `classify_response()` labels output as compliant, reverted native syntax,
   or non-compliant (`src/olla/smoke.py:27`).
4. The runner prints per-mode counts and warns when non-thinking compliance is
   below 80% (`src/olla/smoke.py:49`).

**State Management:**

- Keep all mutable application state inside `run_loop()` in
  `src/olla/loop.py`: a list of Ollama-compatible message dictionaries and the
  current repetition signature/count.
- No conversation, approval, tool, or smoke-test state is persisted.
- Module-level values in `src/olla/prompts.py`, `src/olla/safety.py`,
  `src/olla/smoke.py`, and `src/olla/loop.py` are protocol/policy constants.

## Key Abstractions

**Model Message History:**

- Purpose: Carry the user task, assistant protocol output, and tool
  observations between sequential Ollama calls.
- Examples: `src/olla/loop.py:34`, `src/olla/smoke.py:42`
- Pattern: Plain dictionaries compatible with the Ollama Python client's
  `messages` parameter.

**Parsed Model Response:**

- Purpose: Normalize untrusted model text into `final`, `tool`, or `none`
  control variants.
- Examples: `src/olla/parser.py:10`, `src/olla/loop.py:90`
- Pattern: String-discriminated dictionaries. Preserve `write_file` payloads
  verbatim because whitespace and code fences are data.

**Decision:**

- Purpose: Separate shell safety policy from prompting and execution.
- Examples: `src/olla/safety.py:10`, `src/olla/safety.py:251`
- Pattern: `TypedDict` with `kind` set to `ALLOW`, `CONFIRM`, or `BLOCK` and a
  human-readable reason for blocked requests.

**ToolResult:**

- Purpose: Give shell and file adapters one non-raising result vocabulary.
- Examples: `src/olla/tools/base.py`, `src/olla/tools/files.py`,
  `src/olla/tools/shell.py`
- Pattern: A `total=False` `TypedDict`; success and error results populate only
  fields relevant to that adapter.

**Tool Signature:**

- Purpose: Detect a model stuck on the same consecutive request.
- Examples: `src/olla/loop.py:108`, `src/olla/loop.py:150`,
  `src/olla/loop.py:175`
- Pattern: Invocation-local tuple containing the tool name and normalized
  argument representation.

## Entry Points

**Installed CLI:**

- Location: `pyproject.toml:16`
- Triggers: Running `olla` after installing the package.
- Responsibilities: Import and execute `olla.cli:main`.

**Click Command:**

- Location: `src/olla/cli.py:10`
- Triggers: Installed console script or direct invocation by Click tests.
- Responsibilities: Parse input, enforce mode-specific required values, and
  route to the selected application flow.

**ReAct Task Runner:**

- Location: `src/olla/loop.py:32`
- Triggers: A normal CLI invocation with task and model.
- Responsibilities: Own the conversation lifecycle and all model/tool
  coordination.

**Format Smoke Runner:**

- Location: `src/olla/smoke.py:36`
- Triggers: CLI invocation with `--smoke-test`.
- Responsibilities: Exercise fixed prompts and report model protocol
  compatibility without executing tools.

## Architectural Constraints

- **Threading:** Use the synchronous call path. `ollama.chat()`,
  `subprocess.run()`, confirmation prompts, and file I/O all block the single
  CLI process; there is no async or worker-thread layer.
- **Global state:** Do not put invocation state at module scope. Existing
  module-level state is limited to constants in `src/olla/prompts.py`,
  `src/olla/safety.py`, `src/olla/smoke.py`, and `src/olla/loop.py`.
- **Circular imports:** None detected. Preserve the downward dependency
  direction: `cli` → `loop`/`smoke`; `smoke` → `loop`; `loop` →
  parser/policy/tools; tools → shared result type.
- **Execution boundary:** Shell commands execute directly on the host via
  `subprocess.run(shell=False)` in `src/olla/tools/shell.py`; file tools access
  host paths through `pathlib` in `src/olla/tools/files.py`. There is no
  sandbox layer.
- **Protocol boundary:** Keep tool names and argument formatting synchronized
  across `src/olla/prompts.py`, `src/olla/parser.py`, dispatch in
  `src/olla/loop.py`, and the relevant adapter under `src/olla/tools/`.
- **Model turn size:** Tool observations are capped by
  `MAX_OBSERVATION_CHARS` in `src/olla/loop.py`, and Ollama is called with an
  8192-token context plus fixed stop sequences.
- **Safety ordering:** For shell actions, tokenize first, classify with
  `src/olla/safety.py`, then prompt/execute. `--yes` may skip a `CONFIRM`
  prompt but must never convert `BLOCK` to an executable result.
- **Write semantics:** A `write_file` payload must include a newline separating
  path from content; reject the request before confirmation when it does not
  (`src/olla/loop.py:186`).
- **Working directory:** Relative shell and file paths inherit the process
  working directory. Path resolution in `src/olla/loop.py` is for disclosure
  in confirmation/preview text, not a containment check.

## Anti-Patterns

### Expanding the Controller Branch Matrix

**What happens:** `run_loop()` repeats signature tracking, error-to-observation
translation, preview rendering, and continuation logic separately for shell,
read, and write branches in `src/olla/loop.py`.

**Why it's wrong:** Adding another tool by copying a branch increases the
number of places where repetition protection, confirmation semantics, and
observation formatting can diverge.

**Do this instead:** Keep the existing behavior stable while extracting only a
shared, explicit dispatch/result path when a new tool requires it. Keep host I/O
in a focused module under `src/olla/tools/`, and retain safety/confirmation in
`src/olla/loop.py` or a dedicated policy layer rather than moving it into the
adapter.

### Treating Dictionary Variants as Interchangeable

**What happens:** Parser outputs, safety decisions, Ollama messages, and tool
results are all plain dictionaries with different optional keys in
`src/olla/parser.py`, `src/olla/safety.py`, `src/olla/loop.py`, and
`src/olla/tools/base.py`.

**Why it's wrong:** Accessing a key before checking the variant discriminator
causes runtime `KeyError` failures and blurs which layer owns a result.

**Do this instead:** Branch on `parsed["type"]`, `decision["kind"]`, or the
presence of `result["error"]` exactly as `src/olla/loop.py` does before reading
variant-specific keys. If the protocol grows, introduce separate typed
contracts near `src/olla/parser.py` and `src/olla/tools/base.py` rather than
adding unrelated optional fields to one dictionary.

### Bypassing the Policy Boundary

**What happens:** The controller imports concrete adapters in
`src/olla/loop.py`, so a new call site can technically invoke
`src/olla/tools/shell.py` without passing through `src/olla/safety.py`.

**Why it's wrong:** Direct shell execution would skip block rules and
confirmation, breaking the central safety invariant.

**Do this instead:** Route every model-originated shell argv through
`check()` in `src/olla/safety.py` from the orchestration layer before calling
`run_shell()` in `src/olla/tools/shell.py`. Keep direct adapter calls limited
to adapter tests such as `tests/test_tools/test_shell.py`.

## Error Handling

**Strategy:** Recover from malformed model output and expected host-operation
failures inside the loop, convert the failure into user-visible text and an
`Observation:` message where another model turn can help. Stop cleanly for
terminal input, safety, repetition, and step-limit conditions.

**Patterns:**

- `parse_response()` in `src/olla/parser.py` tolerates surrounding prose,
  markdown fences, and unclosed tags; it returns `type="none"` instead of
  raising for unrecognized output.
- Shell quote errors are caught around `shlex.split()` in
  `src/olla/loop.py:100` and become corrective observations.
- `read_file()`, `write_file()`, and `run_shell()` catch expected operational
  exceptions and return an `error` field from `src/olla/tools/`.
- `EOFError` during a Rich confirmation is treated as a declined action in
  `src/olla/loop.py:127` and `src/olla/loop.py:201`.
- Blocked, declined, unknown, and malformed actions remain part of the model
  conversation as observations so the model can choose another action.
- Model transport/server exceptions from `ollama.chat()` are not translated
  in `src/olla/loop.py:26`; they propagate out through the Click invocation.

## Cross-Cutting Concerns

**Logging:** There is no logging framework. Write task progress, observations,
final answers, and smoke diagnostics to standard output with `print()` in
`src/olla/loop.py` and `src/olla/smoke.py`; Rich is used only for confirmation
input in `src/olla/loop.py`.

**Validation:** Click validates CLI option shape in `src/olla/cli.py`; the
parser validates the model protocol in `src/olla/parser.py`; `shlex` validates
shell quoting in `src/olla/loop.py`; policy validation lives in
`src/olla/safety.py`; tool adapters validate operational preconditions in
`src/olla/tools/`.

**Authentication:** Not applicable. The application talks to the user's local
Ollama service through the default client configuration in
`src/olla/loop.py`; no identity or credential layer exists in the repository.

---

*Architecture analysis: 2026-07-25*
