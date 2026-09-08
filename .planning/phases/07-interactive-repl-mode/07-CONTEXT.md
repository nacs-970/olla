# Phase 7: Interactive REPL Mode - Context

**Gathered:** 2026-09-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Add an interactive terminal REPL: running `olla` with no positional TASK argument launches a multi-turn `prompt_toolkit` session instead of the current required-argument one-shot mode. The REPL preserves Scratchpad memory, file read-snapshots, and full conversation history across turns; applies rolling context trimming to stay within `num_ctx`; and supports mid-session model switching. `run_loop()` is refactored to accept externally-owned session state rather than always creating its own, so the REPL can drive repeated turns through the same ReAct step-loop machinery the one-shot CLI already uses.

</domain>

<decisions>
## Implementation Decisions

### Session architecture
- **D-01:** `run_loop()` is refactored to accept optional pre-existing session state (Scratchpad, messages list, read_snapshots) instead of always constructing its own. `run_loop()` still owns the ReAct step loop; the REPL owns the outer input/session loop and calls `run_loop()` once per turn, injecting/reusing prior state. — **Reversibility:** costly — changes `run_loop()`'s public signature and internal ownership model; every existing call site (CLI one-shot, tests) needs updating to the new optional-param shape.
- **D-02:** Conversation history is one continuous `messages` list across the whole REPL session — system prompt once, then every user turn and its tool observations append to the same list. Rolling trim (D-07..D-10) manages growth, not per-turn resets.
- **D-03:** The repetition guard (`previous_signature`/`repeat_count`) resets at the start of each REPL turn — it only fires on repeats within a single turn's step loop, not across turn boundaries.
- **D-04:** `--max-steps` is a per-turn budget — each user input gets its own fresh allowance (default 50), same semantics as one-shot mode. No cumulative session-wide step cap.
- **D-05:** `read_snapshots` (file-read-before-overwrite safety state) persists across the whole REPL session — a file read in turn 1 still satisfies the read-before-write precondition in a later turn.
- **D-06:** The model provider/client is initialized once per session by default, but the user can switch models mid-session via a `/model <name>` slash command. `/model` is recognized as a control command (not sent to the LLM), re-runs `get_provider()` with the new model, and prints a confirmation. Conversation history transfers to the new model unchanged — `/model` does not reset messages, Scratchpad, read_snapshots, or `untrusted_observation_seen`.

### Rolling context trimming (REPL-03)
- **D-07:** When history nears `num_ctx`, dropped turns are **summarized into a running digest** rather than deleted outright — the digest is appended to context in place of the removed turns' raw content. — **Reversibility:** costly — once a turn is summarized and dropped, its raw content is gone from context; undoing this design means re-adding all removed turn content, which isn't recoverable from the digest alone.
- **D-08:** Only the system prompt and the current in-progress turn are protected from trimming; all prior completed turns are eligible for summarization/removal.
- **D-09:** Context budget is measured via **exact token counting using `tiktoken`** as a new dependency — chosen deliberately over a free char-count proxy or Ollama's own `eval_count` response field, even though this adds a dependency the project's stated constraints call "zero new heavy dependencies." — **Reversibility:** reversible — `tiktoken` is an isolated counting utility; swapping it for another method later doesn't touch call-site contracts. **User confirmed deliberately** after the constraint conflict was explicitly flagged.
- **D-10:** Trimming happens **proactively** — history size is checked and trimmed before every `provider.chat()` call in the REPL loop, never reactively after a context-overflow error.
- **D-11:** Summarization is performed by the **same session model**, via a dedicated short-summary prompt call, not a separate/smaller model. This adds one extra inference call per trim event on the same constrained hardware the project targets. — **User confirmed deliberately** after the extra-latency-cost conflict was flagged; accepted because trimming is expected to be infrequent (only on long sessions).

### REPL UX & controls
- **D-12:** Exiting the REPL: pressing Ctrl+C once interrupts the current turn/generation without ending the session; pressing Ctrl+C twice (double-tap within a short window) exits the session. `/exit` and `/quit` slash commands also exit explicitly.
- **D-13:** `--yes` and `--dry-run` are fixed for the whole session at REPL launch (`olla --yes`) — no in-session slash command to toggle them per-turn.
- **D-14:** Step-by-step tool progress output ("Step N: running `<cmd>`...") prints identically inside REPL turns as in one-shot mode — reuse the existing `_display()`/progress printing unchanged, no REPL-specific formatting.
- **D-15:** Slash command surface for v1: `/model <name>`, `/exit`, `/quit`, and `/clear`. No other commands planned for this phase.

### Scratchpad/session lifecycle edge cases
- **D-16:** `/clear` performs a full session reset: messages history, Scratchpad, read_snapshots, `untrusted_observation_seen`, AND the rolling-context summarization digest (D-07) are all wiped back to fresh-session defaults.
- **D-17:** `/model` (mid-session model switch) leaves all other session state untouched — read_snapshots, `untrusted_observation_seen`, and the summarization digest all survive a model switch unchanged (consistent with D-06's history-transfers decision).

### Claude's Discretion
- Exact prompt wording for the dedicated summarization call (D-11).
- Internal digest format/structure (e.g. single running paragraph vs. per-turn bullet list) as long as it's appended as context the model can read.
- `prompt_toolkit` configuration specifics: history file location, key bindings beyond what's decided (Ctrl+C/Ctrl+D behavior), multiline-editing trigger keys.
- Exact `/model` and `/clear` confirmation message wording.
- Whether `tiktoken`'s `cl100k_base` or another encoding is used as the counting proxy for non-OpenAI models — pick a reasonable default at implementation time since exact per-model tokenizers vary anyway (this is an approximation regardless of encoding choice).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap & requirements
- `.planning/ROADMAP.md` — Phase 7 goal and success criteria (REPL-01..03)
- `.planning/REQUIREMENTS.md` — REPL-01, REPL-02, REPL-03 requirement text

### Codebase patterns to follow
- `src/olla/loop.py` — `run_loop()` (line ~994) owns the ReAct step loop, `messages` list construction, `Scratchpad()` instantiation, `read_snapshots` dict, `previous_signature`/`repeat_count` repetition guard, `untrusted_observation_seen` flag, and the hardcoded `num_ctx: 8192` (line ~514) — all need to become session-injectable per D-01/D-02/D-03/D-05/D-06
- `src/olla/cli.py` — current one-shot entry point; needs a no-TASK-argument branch that launches the REPL instead of raising `UsageError`
- `src/olla/tools/memory.py` — `Scratchpad` class (line 69), currently documented as "lifetime of one owning run-loop invocation" — this docstring/contract changes under D-01/D-05 to session-lifetime, not invocation-lifetime
- `src/olla/loop.py` `truncate_output()` — existing char-based truncation helper; D-09's tiktoken-based measurement is a separate, higher-level context-budget concern, not a replacement for this
- `src/olla/providers/` — `get_provider()` factory used for both initial and `/model`-triggered provider (re)initialization (D-06)
- `.planning/codebase/ARCHITECTURE.md` — existing architecture doc; review for how `run_loop()`'s current one-shot ownership model is documented, since D-01 changes it
- `.planning/codebase/CONVENTIONS.md` — naming, typing, docstring conventions to follow for new REPL module(s)
- `pyproject.toml` — dependency list; `tiktoken` (D-09) and `prompt_toolkit` (REPL-01) are both new additions here

No external specs beyond `.planning/REQUIREMENTS.md` — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_loop()`'s existing ReAct step-loop body (`src/olla/loop.py` ~994-onward) — the REPL calls this once per turn rather than reimplementing step logic.
- `Scratchpad`, `read_snapshots` dict, `previous_signature`/`repeat_count` — existing state containers that just need to be threaded in/out of `run_loop()` as parameters instead of always constructed fresh.
- `get_provider()` (`src/olla/providers/`) — reusable for both initial REPL launch and `/model` mid-session switching.
- `_display()` and existing step-progress printing in `loop.py` — reused unchanged per D-14.

### Established Patterns
- `run_loop()` currently follows a strict one-Scratchpad-per-invocation invariant (Phase 4 decision) specifically to prevent notes crossing between separate `olla` invocations — D-01/D-05 deliberately relax this for the REPL's single continuous process, while the CLI one-shot path keeps the original invariant (each one-shot `olla` call still gets a fresh Scratchpad).
- Module-private helpers prefixed with `_` — apply to any new REPL-internal helpers (slash-command parsing, digest formatting, trim-check logic).

### Integration Points
- `src/olla/cli.py` — new REPL entry branch when `task` is not provided.
- `src/olla/loop.py` — `run_loop()` signature change (optional session-state params); new proactive trim-check + summarization call site before each `provider.chat()`/model-turn call within a REPL-driven turn.
- New module likely needed for REPL-specific concerns (input loop, slash-command dispatch, prompt_toolkit wiring) — planner to decide exact location/naming per `CONVENTIONS.md`.

</code_context>

<specifics>
## Specific Ideas

- Model switching mid-session was raised organically during discussion (not originally scoped as a gray area) — user wants `/model <name>` to work without losing conversation state. This is now D-06/D-17.
- Two decisions (D-09 tiktoken dependency, D-11 same-model summarization call) deliberately override stated project constraints ("zero new heavy dependencies", minimal per-turn token overhead on constrained hardware) — both were explicitly flagged as conflicts during discussion and the user confirmed the choice anyway. Downstream agents should treat these as settled, not re-litigate them, but the planner should note the `pyproject.toml` dependency addition and the extra-latency tradeoff explicitly in the plan.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. `/clear` and `/model` were raised during discussion but fall within REPL-01/REPL-02's existing scope (session control commands), not new capabilities — captured as D-06/D-15/D-16/D-17 rather than deferred.

</deferred>

---

*Phase: 7-Interactive REPL Mode*
*Context gathered: 2026-09-09*
