# Phase 4: Memory Tool - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a bounded, invocation-local scratchpad to the existing ReAct loop. The model can store a short note with `remember(key, value)`, retrieve it in a later turn with `recall(key)`, and use the recalled fact to finish a multi-step task. Memory lasts only for one `run_loop` invocation: Phase 4 adds no disk persistence, cross-run state, automatic memory injection, listing API, or context compaction.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — core value, lightweight dependency constraints, invocation model, and the v1 memory-tool commitment.
- `.planning/REQUIREMENTS.md` — MEM-01 is Phase 4 scope; MEM-02 context compaction remains v2 and must not be pulled into this phase.
- `.planning/ROADMAP.md` — Phase 4 goal, dependency on Phase 3, MVP mode, and the two success criteria.

### Locked Prior Decisions
- `.planning/phases/01-core-loop-shell-tool-cli/01-CONTEXT.md` — D-02 locks per-tool non-JSON micro-formats; D-05/D-06 lock visible step/observation behavior.
- `.planning/phases/02-safety-gate-loop-control/02-CONTEXT.md` — repetition signatures and dry-run/observation conventions that the memory tools must preserve.

### Research and Current Architecture
- `.planning/research/ARCHITECTURE.md` — invocation-local `remember`/`recall` scratchpad flow and no-confirm boundary. Its JSON argument examples are superseded by Phase 1 D-02 and this context's D-02.
- `.planning/research/FEATURES.md` — scratchpad token-cost analysis. Its suggested compaction is deferred by `.planning/REQUIREMENTS.md` MEM-02 and is not Phase 4 work.
- `.planning/research/PITFALLS.md` — unbounded scratchpad growth risk that motivates D-08/D-09.
- `.planning/codebase/ARCHITECTURE.md` — current loop, parser, prompt, tool-adapter, state-lifetime, and repetition-guard integration points.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/olla/loop.py` `run_loop()` — owns invocation-local `messages`, repetition state, dry-run routing, tool dispatch, step output, observation truncation, and terminal/model result delivery.
- `src/olla/prompts.py` `SYSTEM_PROMPT` — current three-tool contract and validated shell/file examples; extend it without rewriting existing guidance.
- `src/olla/tools/base.py` `ToolResult` — shared non-raising adapter result vocabulary for success and error observations.
- `tests/test_loop.py` — established mocked-Ollama patterns for dispatch, dry-run, repetition, error observation, visible output, and multi-step tool-to-final flows.

### Established Patterns
- Tool adapters perform focused work and return data/errors; orchestration, dry-run, repetition detection, and presentation remain in `run_loop()`.
- Every parsed tool call gets a normalized repetition signature, and the third identical consecutive call aborts before execution.
- Errors become printed `Observation:` messages so the model can correct its next action.
- Values and counts use Python character semantics (`len(str)`), matching the character-based limits selected above.

### Integration Points
- `src/olla/parser.py` currently trims ordinary `<args>` payloads and preserves only `write_file` payloads verbatim. `remember` needs equivalent payload preservation while still trimming only its first-line key.
- `src/olla/loop.py` needs normal and dry-run dispatch for `remember`/`recall`, using one scratchpad instance for the full invocation.
- A focused memory adapter belongs under `src/olla/tools/`, matching `shell.py` and `files.py`; planner decides its exact public functions and result fields.
- `src/olla/prompts.py` must advertise five tools and teach the D-02 format without changing the existing file/shell examples.

</code_context>

<specifics>
## Specific Ideas

- Exact normal outputs: `remembered: <key>`, `remembered empty: <key>`, `memory is empty: <key>`, and `memory not found: <key>`.
- Exact validation outputs: `invalid remember: key must not be empty`, `invalid remember: expected key on first line and value on remaining lines`, and `invalid recall: key must not be empty`.
- Exact limits: 2,000 characters per value, 32 keys, and 16,000 total value characters.
- Dry-run discloses the key and character count but never echoes note content.

</specifics>

<deferred>
## Deferred Ideas

- MEM-02 context compaction remains a v2 requirement. Phase 4 must not trim or summarize earlier observations when `remember` is called.

</deferred>

---

*Phase: 4-Memory Tool*
*Context gathered: 2026-07-25*
