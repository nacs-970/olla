# Phase 4: Memory Tool - Research

**Researched:** 2026-07-25
**Domain:** Invocation-local bounded key/value scratchpad integrated into a synchronous ReAct loop
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Store and Recall Contract
- **D-01:** Expose two explicit tools: `remember` only writes and `recall` only reads. Do not overload one tool or inject all notes into every model turn.
- **D-02:** `remember` uses a non-JSON line format: the trimmed first line is the key and every remaining character is the value. `recall` accepts one trimmed raw key. Keys are trimmed, while values are preserved verbatim.
- **D-03:** A normal write returns `remembered: <key>`. A successful non-empty recall returns the stored value verbatim.

### Key, Update, and Empty-Value Rules
- **D-04:** Keys are case-sensitive after trimming. Writing an existing key atomically replaces its previous value.
- **D-05:** A missing lookup returns `memory not found: <key>`. An empty lookup key returns `invalid recall: key must not be empty`.
- **D-06:** Reject `remember` when the key is empty or when no value line was supplied. A present but zero-character value is valid. Storing it returns `remembered empty: <key>`; recalling it returns `memory is empty: <key>`.
- **D-07:** An empty note consumes one key and zero value characters. Whitespace-only values are not empty: preserve and account for their exact characters.

### Scratchpad Limits
- **D-08:** Enforce all three bounds: at most 2,000 characters per value, at most 32 keys, and at most 16,000 combined value characters.
- **D-09:** Any write that would exceed a bound is rejected atomically. Never evict an existing key or truncate a new value to make it fit.

### User-Visible Behavior and Dry Run
- **D-10:** Print `Step N: remembering <key>...` and `Step N: recalling <key>...`. Print write acknowledgments, recalled values, and errors to the terminal and return the same result as the model's `Observation`. Do not print the stored value during `remember`.
- **D-11:** Neither memory tool requires confirmation; the scratchpad has no host side effects. `--yes` therefore does not change memory behavior.
- **D-12:** `--dry-run` validates the proposed call but neither reads nor mutates memory. Preview `remember` with the key and value length (`Step 1 would remember: <key> (N chars)`) and preview `recall` with its key (`Step 1 would recall: <key>`), never the stored value.

### Prompt Teaching and Recoverable Errors
- **D-13:** Preserve all existing shell/file prompt teaching. Add concise `remember`/`recall` format rules plus one compact, concrete transcript that stores a short fact, shows `remembered: <key>`, recalls it later, shows the recalled value, and uses it in `<final>`.
- **D-14:** Malformed writes use distinct actionable errors: `invalid remember: key must not be empty` and `invalid remember: expected key on first line and value on remaining lines`.
- **D-15:** An oversized value reports its actual character count and the limit: `memory value too large: <N> characters; maximum is 2000`.
- **D-16:** Whole-scratchpad failures are distinct: `memory key limit reached: maximum is 32` or `memory capacity exceeded: write would use <N> of 16000 characters`.

### the agent's Discretion
- Exact internal data types and helper/function names, provided the public behavior above remains exact.
- Whether the memory adapter returns new dedicated `ToolResult` fields or reuses an existing content field.
- Exact test decomposition and internal dispatch refactor needed to avoid duplicating loop control logic.

### Deferred Ideas (OUT OF SCOPE)
- MEM-02 context compaction remains a v2 requirement. Phase 4 must not trim or summarize earlier observations when `remember` is called.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | `remember(key, value)` scratchpad tool for cross-turn notes | The recommended parser-preservation seam, invocation-local `Scratchpad`, bounded replacement algorithm, two-tool loop dispatch, prompt transcript, and three-layer test map implement the requirement without adding persistence or compaction. [VERIFIED: `.planning/REQUIREMENTS.md`, Phase 4 CONTEXT.md, codebase] |
</phase_requirements>

## Project Constraints (from AGENTS.md)

The checkout has no repository `AGENTS.md` or `RTK.md`; the following user-supplied directives are binding for planning and execution. [VERIFIED: codebase inspection and task context]

- Never run `git reset --hard`, `git checkout .`, `git restore .`, or `git clean -fd`.
- Ask permission before any destructive git operation.
- If checkout/comparison is needed, clone to `/tmp` and work there.
- Retrieve an original file with `git show HEAD:filename`.
- Preserve original code and logic as much as possible.
- Do not create, rename, or switch branches.
- Preserve the current dirty-worktree changes in `src/olla/loop.py`, `src/olla/prompts.py`, `tests/test_loop.py`, Phase 3 planning files, and untracked helper files.

## Summary

Phase 4 should be planned as an additive vertical slice through four existing seams: preserve `remember` payloads in `parse_response()`, implement a focused in-memory adapter, create exactly one adapter instance inside each `run_loop()` invocation, and teach both tools in `SYSTEM_PROMPT`. No CLI flag, safety-policy change, persistent store, automatic memory injection, or external package is needed. [VERIFIED: Phase 4 CONTEXT.md and codebase]

Use a `Scratchpad` class backed by Python's built-in `dict`, with pure argument-parsing helpers shared by normal and dry-run paths. Parse with `partition("\n")`, trim only the key, keep the remainder byte-for-byte as a Python string, validate all projected limits before assigning, and compute total capacity with replacement delta. Python documents strings as Unicode-code-point sequences and dictionaries as mutable mappings whose existing entries are replaced by later values; this matches the locked `len(str)` and overwrite semantics. [CITED: https://docs.python.org/3.10/reference/datamodel.html] [CITED: https://docs.python.org/3.10/library/stdtypes.html]

The highest-risk work is integration behavior, not the storage container: the current parser strips ordinary arguments and removes code fences, `run_loop()` duplicates dispatch/repetition logic across tools, dry-run has a separate dispatch tree, and generic falsy-output handling would collapse the deliberately distinct empty-memory messages. Plan adapter unit tests first, then parser preservation tests, then mocked three-turn remember→recall→final loop tests and invocation-isolation tests. [VERIFIED: `src/olla/parser.py`, `src/olla/loop.py`, existing tests]

**Primary recommendation:** Add `tools/memory.py` with a run-local `Scratchpad` and pure parsers, then wire normalized memory calls through the existing observation/repetition conventions without touching the safety gate or CLI. [VERIFIED: Phase 4 CONTEXT.md and codebase architecture]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Parse `remember`/`recall` micro-formats | Model Protocol / API Backend | — | `parser.py` owns tag extraction, while a memory-specific pure parser owns first-line/key/value semantics. [VERIFIED: codebase architecture and D-02] |
| Hold bounded notes | Tool Adapter / In-memory Storage | Application Orchestration | `tools/memory.py` owns note invariants; `run_loop()` owns the one-instance-per-invocation lifetime. [VERIFIED: codebase architecture and D-08/D-09] |
| Dispatch and repetition control | Application Orchestration | Tool Adapter | `run_loop()` already owns dispatch, normalized signatures, terminal rendering, and observations. [VERIFIED: `src/olla/loop.py`] |
| Dry-run preview | CLI / Client Orchestration | Model Protocol | The loop validates parsed arguments and renders a one-step preview, then exits without adapter access. [VERIFIED: `src/olla/loop.py` and D-12] |
| Prompt teaching | Model Protocol | — | `SYSTEM_PROMPT` is the single tool-contract teaching surface. [VERIFIED: `src/olla/prompts.py` and D-13] |

## Standard Stack

### Core

| Library / Component | Version | Purpose | Why Standard |
|---------------------|---------|---------|--------------|
| Python built-in `dict` and `len` | Python `>=3.10` | Case-sensitive key/value storage and character/key counts | Already available, constant-size bounded workload, correct replacement semantics, and no serialization or dependency cost. [VERIFIED: `pyproject.toml`] [CITED: https://docs.python.org/3.10/library/stdtypes.html] |
| `olla.tools.base.ToolResult` | Current codebase | Return success content or recoverable error data without raising | Matches every existing tool adapter and the loop's error-to-observation convention. [VERIFIED: `src/olla/tools/base.py`, `src/olla/tools/files.py`, `src/olla/tools/shell.py`] |
| `parse_response()` + memory-specific pure parsers | Current codebase + new module helper | Preserve the raw tagged payload, then apply the per-tool line micro-format | Keeps tolerant tag extraction separate from memory validation and gives dry-run a no-state validation path. [VERIFIED: `src/olla/parser.py` and D-02/D-12] |
| `run_loop()` invocation-local object | Current codebase | Own one scratchpad for the whole task and discard it on return | Existing messages and repetition counters already use this lifetime. [VERIFIED: `src/olla/loop.py` and codebase architecture] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | Declared `>=8`; installed `9.0.3` | Boundary tables, adapter state tests, parser tests, and mocked loop integration | Use for every locked output and exact-limit boundary. [VERIFIED: `pyproject.toml`, environment] [CITED: https://docs.pytest.org/en/stable/how-to/parametrize.html] |
| pytest-mock | Declared `>=3.14`; installed `3.15.1` | Mock Ollama and confirm no memory confirmation/host calls occur | Use in `tests/test_loop.py`, following its established `mocker.patch()` pattern. [VERIFIED: `pyproject.toml`, environment, `tests/test_loop.py`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Run-local `Scratchpad` class | Module-global dictionary | A global is shorter but leaks state across `run_loop()` invocations and tests, violating the phase boundary. Do not use it. [VERIFIED: D-01 and codebase state-lifetime convention] |
| Class owning invariant checks | Free functions plus a caller-owned dictionary | Workable, but spreads key-count, capacity, and replacement-delta invariants across call sites; keep them together in the adapter. [VERIFIED: D-08/D-09; recommendation under the agent's discretion] |
| Built-in dictionary | LRU cache, database, file, or vector store | These add eviction or persistence semantics explicitly forbidden in Phase 4. [VERIFIED: Phase 4 boundary and D-09] |

**Installation:**

```bash
# No installation. Phase 4 uses the standard library and existing dev dependencies.
```

**Version verification:** The project declares Python `>=3.10`, pytest `>=8`, and pytest-mock `>=3.14`; the active `.venv` provides Python 3.14.6, pytest 9.0.3, and pytest-mock 3.15.1. [VERIFIED: `pyproject.toml` and environment probe]

## Package Legitimacy Audit

Not required: Phase 4 installs no external packages and recommends no new registry dependency. [VERIFIED: Standard Stack and `pyproject.toml`]

## Architecture Patterns

### System Architecture Diagram

```text
User task
   |
   v
run_loop() creates messages + one Scratchpad
   |
   v
Ollama (external local service) --> raw <tool>/<args> response
   |
   v
parse_response()
   |
   +--> <final> --------------------------------------> terminal, stop
   |
   +--> remember raw payload --> parse key/value
   |         |
   |         +--> dry-run: validate shape/value size
   |         |               --> preview key + len(value), stop
   |         |
   |         +--> normal: repetition check
   |                       --> validate projected bounds
   |                       --> assign dict entry
   |                       --> acknowledgment
   |
   +--> recall raw key ----> trim/validate key
             |
             +--> dry-run: preview key, stop (no lookup)
             |
             +--> normal: repetition check --> dict lookup --> value/status
                                                        |
                                                        v
                         terminal result == Observation payload
                                                        |
                                                        v
                                              next Ollama turn
```

This flow keeps the scratchpad behind the existing model-protocol boundary and creates no filesystem, database, network, or confirmation path. [VERIFIED: Phase 4 CONTEXT.md and codebase]

### Recommended Project Structure

```text
src/olla/
├── parser.py                 # preserve remember payload like write_file payload
├── loop.py                   # instantiate/run/preview remember + recall
├── prompts.py                # advertise five tools and add one memory transcript
└── tools/
    ├── base.py               # reuse content/error fields; no change required
    └── memory.py             # parsers, constants, Scratchpad invariants
tests/
├── test_parser.py            # remember preservation + recall trimming cases
├── test_loop.py              # dispatch, dry-run, repetition, isolation, E2E
├── test_prompts.py           # five-tool contract and compact memory transcript
└── test_tools/
    └── test_memory.py        # unit/boundary/atomicity tests
```

The only new production file should be `src/olla/tools/memory.py`; the other production changes extend existing protocol and orchestration seams. [VERIFIED: codebase and Phase 4 code context]

### Pattern 1: Parse Once, Preserve the Value

**What:** Add `remember` to the parser's payload-preserving tool set, then use `partition("\n")` in a memory-specific parser. Trim the first field only and return the untouched remainder as the value. [VERIFIED: D-02 and current `write_file` preservation pattern]

**When to use:** Both normal execution and dry-run, so malformed-call wording and value length cannot diverge. [VERIFIED: D-12/D-14/D-15]

**Example:**

```python
# Source: derived from D-02, D-06, D-14, D-15 and Python str semantics.
from dataclasses import dataclass

MAX_VALUE_CHARS = 2_000


@dataclass(frozen=True)
class RememberCall:
    key: str
    value: str


def parse_remember_args(args_raw: str) -> tuple[RememberCall | None, str | None]:
    key_line, separator, value = args_raw.partition("\n")
    key = key_line.strip()
    if not key:
        return None, "invalid remember: key must not be empty"
    if not separator:
        return None, (
            "invalid remember: expected key on first line and value on remaining lines"
        )
    if len(value) > MAX_VALUE_CHARS:
        return None, (
            f"memory value too large: {len(value)} characters; maximum is 2000"
        )
    return RememberCall(key=key, value=value), None
```

`str.partition("\n")` preserves every character after the first delimiter, including an empty string, spaces, and later newlines; `.splitlines()` or `.strip()` on the full payload would destroy locked value semantics. [VERIFIED: D-02/D-06/D-07; recommendation validated against Python behavior]

### Pattern 2: Validate Projected State, Then Assign

**What:** Compute whether a key is new, the old value length, and projected total before mutating the dictionary. Check value size, new-key count, and projected total in deterministic order; assign only after every check passes. [VERIFIED: D-08/D-09]

**When to use:** Every normal `remember` call, including replacement of an existing key. [VERIFIED: D-04]

**Example:**

```python
# Source: derived from D-04 and D-08/D-09; dict behavior is documented at:
# https://docs.python.org/3.10/library/stdtypes.html#mapping-types-dict
MAX_KEYS = 32
MAX_TOTAL_CHARS = 16_000


class Scratchpad:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def remember(self, call: RememberCall) -> dict[str, str]:
        is_new = call.key not in self._values
        old_size = 0 if is_new else len(self._values[call.key])
        projected = sum(len(value) for value in self._values.values())
        projected = projected - old_size + len(call.value)

        if is_new and len(self._values) >= MAX_KEYS:
            return {"error": "memory key limit reached: maximum is 32"}
        if projected > MAX_TOTAL_CHARS:
            return {
                "error": (
                    "memory capacity exceeded: "
                    f"write would use {projected} of 16000 characters"
                )
            }

        self._values[call.key] = call.value
        if call.value == "":
            return {"content": f"remembered empty: {call.key}"}
        return {"content": f"remembered: {call.key}"}
```

Recomputing at most 32 value lengths avoids a second mutable total counter and makes replacement accounting directly auditable; the bounded workload makes this cost negligible. [VERIFIED: D-08; implementation recommendation]

### Pattern 3: Invocation-Local Dependency, Explicit Recall

**What:** Construct `scratchpad = Scratchpad()` inside `run_loop()`, after entering the function and before either dry-run or normal dispatch. Never put it at module scope, in a default argument, or in CLI state. [VERIFIED: Phase boundary and existing invocation-local message/repetition state]

**When to use:** Exactly once per `run_loop()` call; both memory tools share that one object during normal iterations. [VERIFIED: MEM-01 and D-01]

**Example:**

```python
# Source: existing run_loop state-lifetime pattern plus D-01/D-12.
def run_loop(...):
    messages = [...]
    scratchpad = Scratchpad()
    ...
```

### Pattern 4: Result-as-Observation, with Empty-State Exceptions

**What:** Reuse `ToolResult["content"]` for acknowledgments, recalled values, and `memory is empty`; reuse `ToolResult["error"]` for invalid/missing/limit results. Render the selected string once, print it, and append `Observation: {result_text}`. [VERIFIED: D-03/D-05/D-06/D-10 and existing adapter convention]

**When to use:** Every normal memory call. Do not route an empty stored value through the generic `(no output)` fallback; `recall` must convert it to `memory is empty: <key>` first. [VERIFIED: D-06 and `src/olla/loop.py` falsy-output behavior]

### Pattern 5: Normalize Repetition Signatures Before Dispatch

**What:** Extend the existing repetition helper/path rather than copying the same counter block twice. Use `("remember", key, value)` after key trimming and `("recall", key)` after key trimming; for malformed inputs use the raw payload so three identical bad calls still stop. [VERIFIED: Phase 2 repetition convention and D-02]

**When to use:** Before adapter execution or lookup, matching the existing abort-before-third-execution behavior. [VERIFIED: `src/olla/loop.py` and `tests/test_loop.py`]

### Anti-Patterns to Avoid

- **Adding `remember` as an ordinary parser tool:** ordinary args are fence-stripped and `.strip()`ed, corrupting leading/trailing value characters. Preserve its payload like `write_file`. [VERIFIED: `src/olla/parser.py` and D-02]
- **A module-global or reusable default scratchpad:** leaks data between one-shot invocations. Instantiate inside `run_loop()`. [VERIFIED: phase boundary]
- **Mutate then roll back:** a failed capacity/key/value check can expose partial state or make derived counts drift. Validate projected state before the one assignment. [VERIFIED: D-09]
- **Count a replacement as a new key or add its entire value to total:** use membership plus `total - old_len + new_len`. [VERIFIED: D-04/D-08]
- **Use truthiness to classify an empty note:** `""` is a valid stored value with dedicated acknowledgment/recall messages; whitespace-only strings are non-empty. Compare with `== ""`. [VERIFIED: D-06/D-07]
- **Call the adapter during dry-run:** parse and validate the proposed call but do not invoke `remember()` or `recall()`. [VERIFIED: D-12]
- **Fold memory into the shell safety gate:** memory has no host side effects and must never confirm; `--yes` is irrelevant. [VERIFIED: D-11]
- **Compact history after remembering:** MEM-02 is deferred and must not enter this phase. [VERIFIED: `.planning/REQUIREMENTS.md` and Deferred Ideas]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Key/value storage | Custom map, registry, cache, or linked structure | Python `dict` | Native case-sensitive lookup, replacement, membership, and key count exactly cover the bounded contract. [CITED: https://docs.python.org/3.10/library/stdtypes.html] |
| Character accounting | UTF-8 byte counters or tokenizer calls | `len(str)` | The decisions explicitly use Python character semantics; strings are Unicode-code-point sequences. [VERIFIED: Phase 4 code context] [CITED: https://docs.python.org/3.10/reference/datamodel.html] |
| Eviction | LRU/FIFO policy | Atomic rejection | D-09 forbids eviction and truncation. [VERIFIED: D-09] |
| Persistence | JSON/TOML file, SQLite, or vector database | Invocation-local object | Cross-run persistence is outside the phase boundary. [VERIFIED: Phase boundary] |
| Tool schema | JSON/function-calling schema | Existing tag protocol plus line micro-format | Project-wide D-02 forbids JSON tool args. [VERIFIED: Phase 1 CONTEXT.md and Phase 4 D-02] |
| Confirmation policy | Memory-specific confirmation or safety rule | Existing no-confirm dispatch tier | D-11 defines no host side effects and no confirmation. [VERIFIED: D-11] |
| Boundary-test loops | Repetitive one-off tests | `pytest.mark.parametrize` | pytest provides first-class parametrized test cases. [CITED: https://docs.pytest.org/en/stable/how-to/parametrize.html] |

**Key insight:** This phase is stateful only inside one synchronous Python call; introducing a storage framework would add semantics the product explicitly rejects and make lifecycle correctness harder, not easier. [VERIFIED: phase boundary and codebase architecture]

## Common Pitfalls

### Pitfall 1: Parser Normalization Corrupts the Value

**What goes wrong:** Leading spaces, trailing newlines, whitespace-only notes, or code fences disappear before the adapter sees them. [VERIFIED: current ordinary-args parser path]

**Why it happens:** `parse_response()` removes code fences and calls `.strip()` for every tool except `write_file`. [VERIFIED: `src/olla/parser.py`]

**How to avoid:** Put `remember` in the payload-preserving branch and add parser regressions for interior fences, leading spaces, trailing newline, explicit empty value, and whitespace-only value. [VERIFIED: D-02/D-06/D-07]

**Warning signs:** `len(value)` differs from the literal captured payload or a recall omits whitespace stored in the test input. [VERIFIED: D-02]

### Pitfall 2: “No Value Line” Is Confused with an Empty Value

**What goes wrong:** `<args>key</args>` is accepted as empty, or `<args>key\n</args>` is rejected. [VERIFIED: D-06]

**Why it happens:** `splitlines()` and truthiness checks erase whether the separator existed. [VERIFIED: Python string behavior and current write-file precedent]

**How to avoid:** Use `partition("\n")` and inspect the separator independently from `value == ""`. Give empty-key precedence when the first line trims empty, then missing-value-line, then size errors. [VERIFIED: D-06/D-14; precedence recommendation under discretion]

**Warning signs:** The same error string is returned for both forms. [VERIFIED: D-14]

### Pitfall 3: Replacement Accounting Rejects Legal Writes

**What goes wrong:** Overwriting at 32 keys is rejected, or replacing a long value with a short one incorrectly exceeds 16,000. [VERIFIED: D-04/D-08]

**Why it happens:** The implementation counts every call as a new key and uses `total + len(new)` rather than subtracting the old value. [VERIFIED: projected-state analysis]

**How to avoid:** Test `is_new` separately and compute `projected = total - old_len + new_len`. Include full-key-set overwrite and full-capacity shrink/grow tests. [VERIFIED: D-04/D-08/D-09]

**Warning signs:** A rejected replacement changes the subsequently recalled old value or changes later capacity behavior. [VERIFIED: D-09]

### Pitfall 4: State Outlives `run_loop()`

**What goes wrong:** A second CLI task can recall a key from the first task, or unit tests become order-dependent. [VERIFIED: phase boundary]

**Why it happens:** The store is created at module import, on a long-lived registry, or as a mutable default argument. [VERIFIED: Python state-lifetime reasoning]

**How to avoid:** Instantiate in the function body and add a test that runs two mocked loops sequentially with the same key. [VERIFIED: existing run-loop test style]

**Warning signs:** Tests only verify two calls within one run and never verify a fresh second run. [VERIFIED: validation-gap analysis]

### Pitfall 5: Dry-Run Reads or Mutates Real State

**What goes wrong:** Recall preview leaks a stored value, or remember preview changes a later result. [VERIFIED: D-12]

**Why it happens:** Dry-run calls the adapter and suppresses only output. [VERIFIED: dry-run architecture risk]

**How to avoid:** Call only the pure argument parser/size validator, print key and length, and return before lookup/assignment. Assert adapter methods are not called. [VERIFIED: D-12 and existing dry-run tests]

**Warning signs:** Dry-run tests assert only terminal text and do not spy on memory calls. [VERIFIED: validation-gap analysis]

### Pitfall 6: Write Output Leaks the Note

**What goes wrong:** `remember` prints the value in its step line, acknowledgment, debug output, or dry-run preview. [VERIFIED: D-10/D-12]

**Why it happens:** One generic tool-preview renderer includes raw args. [VERIFIED: loop refactor risk]

**How to avoid:** Render memory previews from normalized key plus `len(value)` only; test a sentinel secret is absent from captured stdout. [VERIFIED: D-10/D-12]

**Warning signs:** Any `remember` branch formats `args_raw` directly. [VERIFIED: D-10]

### Pitfall 7: Generic No-Output Handling Erases Empty-Memory Semantics

**What goes wrong:** Recalling an empty note returns `(no output)` rather than `memory is empty: <key>`. [VERIFIED: D-06 and current generic fallback]

**Why it happens:** Existing shell/read branches convert falsy content to `(no output)`. [VERIFIED: `src/olla/loop.py`]

**How to avoid:** Make `Scratchpad.recall()` produce the explicit non-empty status string before result rendering. [VERIFIED: D-06]

**Warning signs:** The memory branch shares a raw `if not combined` fallback with file/shell output. [VERIFIED: integration analysis]

### Pitfall 8: Prompt Growth or Compaction Scope Creep

**What goes wrong:** The implementation injects all notes into each prompt or removes earlier observations after remember, changing context behavior and token accounting. [VERIFIED: D-01 and Deferred Ideas]

**Why it happens:** Earlier project research proposed memory-triggered compaction, but MEM-02 explicitly moved that behavior to v2. [VERIFIED: `.planning/research/FEATURES.md` and `.planning/REQUIREMENTS.md`]

**How to avoid:** Add only explicit tool descriptions and one compact transcript; recall returns one selected note through the normal observation channel. [VERIFIED: D-01/D-13]

**Warning signs:** `messages` is rewritten after `remember`, or scratchpad contents appear in every model call. [VERIFIED: phase boundary]

### Pitfall 9: Root-Level Helper Files Break Unscoped pytest Collection

**What goes wrong:** Running plain `pytest` collects untracked `test_fix.py`, `test_replace.py`, and `test_temp.py`, causing three collection errors unrelated to Phase 4. [VERIFIED: test run on 2026-07-25]

**Why it happens:** There is no pytest config restricting discovery to `tests/`, and the dirty worktree includes root files matching `test_*.py`. [VERIFIED: codebase inspection]

**How to avoid:** Use `.venv/bin/python -m pytest tests ...` in every plan verification command and do not edit/delete the user's helper files. [VERIFIED: 151 tests passed with scoped command]

**Warning signs:** Collection fails before any `tests/` case runs. [VERIFIED: test run]

## Code Examples

Verified patterns from project decisions and official sources:

### Recall with Missing and Empty Distinction

```python
# Source: D-03/D-05/D-06; dict membership semantics:
# https://docs.python.org/3.10/library/stdtypes.html#mapping-types-dict
def recall(self, key: str) -> dict[str, str]:
    if key not in self._values:
        return {"error": f"memory not found: {key}"}
    value = self._values[key]
    if value == "":
        return {"content": f"memory is empty: {key}"}
    return {"content": value}
```

### Dry-Run Without Store Access

```python
# Source: D-12 and existing run_loop dry-run architecture.
call, error = parse_remember_args(parsed["args_raw"])
if error is not None:
    print(error)
    return
assert call is not None
print(f"Step 1 would remember: {call.key} ({len(call.value)} chars)")
return
```

### Compact Prompt Transcript

```text
# Source: D-13 exact required teaching sequence.
<tool>remember</tool><args>meeting_time
3pm</args>
Observation: remembered: meeting_time

<tool>recall</tool><args>meeting_time</args>
Observation: 3pm

<final>The meeting is at 3pm.</final>
```

Keep all current read/write/shell teaching and examples, change the tool count from three to five, add concise formats for both memory tools, and append exactly one memory transcript. [VERIFIED: D-13 and current `SYSTEM_PROMPT`]

## State of the Art

| Old / Generic Approach | Phase 4 Approach | When Changed | Impact |
|------------------------|------------------|--------------|--------|
| JSON object arguments for multi-field tools | First line is key; untouched remainder is value | Project-wide Phase 1 D-02, reaffirmed Phase 4 D-02 | Avoids structured JSON and preserves the small-model protocol. [VERIFIED: Phase 1 and Phase 4 CONTEXT.md] |
| Unbounded scratchpad | 2,000/value, 32 keys, 16,000 total | Phase 4 D-08/D-09 | Gives deterministic memory and context exposure bounds without eviction. [VERIFIED: Phase 4 CONTEXT.md] |
| Automatic injection of all memory | Explicit `recall(key)` only | Phase 4 D-01 | Keeps prompt overhead bounded to the requested note. [VERIFIED: D-01] |
| Persistent/cross-session memory | One object per `run_loop()` invocation | Phase 4 boundary | Prevents cross-task leakage and adds no storage dependency. [VERIFIED: Phase boundary] |
| Memory-triggered compaction proposal | No compaction in v1 | MEM-02 deferred to v2 | Preserves current loop history behavior. [VERIFIED: `.planning/REQUIREMENTS.md` and Deferred Ideas] |

**Deprecated/outdated:**

- Upstream research examples that encode memory arguments as JSON are superseded by Phase 1 D-02 and Phase 4 D-02. [VERIFIED: `.planning/research/ARCHITECTURE.md` and locked contexts]
- Upstream feature research recommending memory-triggered compaction is superseded by MEM-02's v2 placement. [VERIFIED: `.planning/research/FEATURES.md` and `.planning/REQUIREMENTS.md`]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. All implementation-affecting claims are locked decisions, live-code observations, environment probes, or cited official documentation. | — | — |

No user confirmation is required before planning. [VERIFIED: research audit]

## Open Questions

No unresolved planning questions. Use this deterministic validation precedence when one malformed write violates several rules: empty key, missing value line, per-value size, new-key limit, then total capacity. This is an internal recommendation under the agent's discretion and preserves every locked exact error. [VERIFIED: D-14/D-16 and the agent's Discretion]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Production and tests | ✓ | 3.14.6; project floor `>=3.10` | Keep syntax/API compatible with 3.10. [VERIFIED: environment and `pyproject.toml`] |
| Project `.venv` | Reproducible test command | ✓ | Python 3.14.6 environment | System pytest 9.0.3 is also present. [VERIFIED: environment] |
| pytest | Validation | ✓ | 9.0.3 | None needed. [VERIFIED: environment] |
| pytest-mock | Mocked loop integration | ✓ | 3.15.1 | `unittest.mock` if the existing dev dependency is unavailable. [VERIFIED: environment and `pyproject.toml`] |
| uv | Dependency runner | ✓, sandbox cache unavailable | 0.11.32 | Run `.venv/bin/python -m pytest ...`; this succeeds without uv cache writes. [VERIFIED: environment test] |
| Ollama CLI | Optional manual model smoke | ✓ | client 0.30.5 | Mock `olla.loop.ollama.chat` for automated phase tests. [VERIFIED: environment and existing tests] |
| Ollama daemon | Optional manual model smoke | ✗ | Not listening on `127.0.0.1:11434` | Start the local daemon for manual UAT; automated tests remain unblocked. [VERIFIED: environment probe] |

**Missing dependencies with no fallback:**

- None for implementation or automated validation. [VERIFIED: environment audit]

**Missing dependencies with fallback:**

- The Ollama daemon is not running; use the established mocked-chat integration tests during implementation and start Ollama only for optional manual model UAT. [VERIFIED: environment and `tests/test_loop.py`]
- `uv run` cannot create its cache temporary file in the current sandbox; use the existing `.venv` directly. [VERIFIED: environment test]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 with pytest-mock 3.15.1. [VERIFIED: environment] |
| Config file | None; scope commands explicitly to `tests/`. [VERIFIED: codebase inspection] |
| Quick run command | `.venv/bin/python -m pytest tests/test_tools/test_memory.py tests/test_parser.py tests/test_loop.py tests/test_prompts.py -q` |
| Full suite command | `.venv/bin/python -m pytest tests -q` |

The scoped baseline is green at 151 tests; the unscoped repository-root command is not a valid phase gate while the user's root helper files remain present. [VERIFIED: test runs on 2026-07-25]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | Parse/store/recall, overwrite, empty/missing results, all exact limits, atomic rejection | Unit | `.venv/bin/python -m pytest tests/test_tools/test_memory.py -q` | ❌ Wave 0 |
| MEM-01 | Preserve remember value verbatim while trimming keys | Unit | `.venv/bin/python -m pytest tests/test_parser.py -q -k 'remember or recall'` | ✅ extend existing |
| MEM-01 | Normal/dry-run dispatch, no confirmation, repetition, invocation isolation | Integration | `.venv/bin/python -m pytest tests/test_loop.py -q -k 'remember or recall or memory'` | ✅ extend existing |
| MEM-01 | Tool list, concise formats, worked remember→recall→final transcript | Unit | `.venv/bin/python -m pytest tests/test_prompts.py -q` | ❌ Wave 0 |
| MEM-01 | Three model turns complete using the recalled note | Mocked E2E | `.venv/bin/python -m pytest tests/test_loop.py::test_run_loop_remember_recall_then_final -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** Run the directly affected memory/parser/loop/prompt test file command. [VERIFIED: existing test speed]
- **Per wave merge:** `.venv/bin/python -m pytest tests -q`. [VERIFIED: 151 tests pass in 2.02 seconds]
- **Phase gate:** Full scoped suite green, plus the mocked three-turn MEM-01 flow and exact stdout/Observation assertions. [VERIFIED: roadmap success criteria and D-10]

### Wave 0 Gaps

- [ ] `tests/test_tools/test_memory.py` — adapter contract, all boundaries, replacements, whitespace, atomic failure, and state isolation.
- [ ] `tests/test_prompts.py` — five-tool advertisement, both formats, exact acknowledgment/recall transcript, and preservation of existing file/shell teaching.
- [ ] `tests/test_parser.py` additions — raw remember payload preservation and trimmed recall.
- [ ] `tests/test_loop.py` additions — normal dispatch, dry-run no-access spies, no confirmation, repetition signatures, two-run isolation, and remember→recall→final.

No framework install or configuration file is needed. [VERIFIED: existing dev dependencies and environment]

## Security Domain

ASVS is principally a web-application verification standard; this phase is a local synchronous CLI feature, but its input-validation and resource-bound principles still apply. [CITED: https://owasp.org/www-project-application-security-verification-standard/]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No identity boundary or credential handling exists in the memory tool. [VERIFIED: phase boundary and codebase] |
| V3 Session Management | No | The scratchpad is invocation-local application state, not an authenticated web session. [VERIFIED: phase boundary] |
| V4 Access Control | No | There are no users, roles, resources, or authorization decisions in this adapter. [VERIFIED: codebase] |
| V5 Input Validation | Yes | Validate key presence, separator presence, value length, key count, and projected capacity before mutation; return stable errors. [VERIFIED: D-05/D-06/D-08/D-09] [CITED: https://owasp.org/www-project-application-security-verification-standard/] |
| V6 Cryptography | No | The phase stores no secrets persistently, encrypts nothing, and adds no cryptographic protocol. [VERIFIED: phase boundary] |

### Known Threat Patterns for the Memory Tool

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized or many notes exhaust process/context resources | Denial of Service | Enforce the three exact caps and reject without eviction/truncation. [VERIFIED: D-08/D-09] |
| Failed replacement partially changes state | Tampering | Compute projected state first; perform one assignment only after validation. [VERIFIED: D-09] |
| Remember/dry-run output exposes a sensitive note | Information Disclosure | Never render the value on write or preview; show only key and length. [VERIFIED: D-10/D-12] |
| State leaks into a later CLI invocation | Information Disclosure | Construct the scratchpad inside `run_loop()` and test two-run isolation. [VERIFIED: phase boundary] |
| Automatic memory injection changes model behavior | Tampering | Return a note only through explicit `recall`; never inject the full store. [VERIFIED: D-01] |

## Sources

### Primary (HIGH confidence)

- Live codebase: `src/olla/parser.py`, `src/olla/loop.py`, `src/olla/prompts.py`, `src/olla/tools/base.py`, `src/olla/tools/files.py`, and tests — current integration seams and conventions. [VERIFIED: codebase]
- `.planning/phases/04-memory-tool/04-CONTEXT.md` — locked behavior, limits, dry-run, prompt, and scope decisions. [VERIFIED: project artifact]
- `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` — MEM-01 scope and success criteria; MEM-02 deferral. [VERIFIED: project artifacts]
- `.planning/codebase/ARCHITECTURE.md` — state lifetime, tool boundary, protocol boundary, and controller anti-pattern. [VERIFIED: codebase map refreshed 2026-07-25]
- Executed test/environment probes — 151 scoped tests green; Python/dev-tool versions; Ollama daemon unavailable. [VERIFIED: environment]

### Secondary (MEDIUM confidence)

- https://docs.python.org/3.10/reference/datamodel.html — strings as Unicode-code-point sequences and character semantics. [CITED: official Python documentation]
- https://docs.python.org/3.10/library/stdtypes.html — dictionary mapping, length, membership, and replacement semantics. [CITED: official Python documentation]
- https://docs.pytest.org/en/stable/how-to/parametrize.html — table-driven boundary tests. [CITED: official pytest documentation]
- https://docs.pytest.org/en/stable/explanation/fixtures.html — fresh, reliable state setup per test. [CITED: official pytest documentation]
- https://owasp.org/www-project-application-security-verification-standard/ — ASVS purpose and security-control verification framing. [CITED: official OWASP project]

### Tertiary (LOW confidence)

- None. [VERIFIED: research audit]

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new package; runtime/container semantics verified in project and official Python docs. [VERIFIED: codebase and cited docs]
- Architecture: HIGH — the phase follows live parser, adapter, loop, and prompt seams with locked lifecycle decisions. [VERIFIED: codebase and Phase 4 CONTEXT.md]
- Pitfalls: HIGH — derived from exact locked edge cases and reproduced current parser/test behavior. [VERIFIED: codebase and test runs]
- Security: MEDIUM — ASVS is web-focused, so applicability is a scoped control screening rather than a claim of ASVS conformance. [CITED: official OWASP project]

**Research date:** 2026-07-25
**Valid until:** 2026-08-24 (30 days; stable standard-library design, but the dirty integration files may change). [VERIFIED: current codebase state]
