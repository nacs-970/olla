# Phase 7: Interactive REPL Mode - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-09
**Phase:** 7-Interactive REPL Mode
**Areas discussed:** Session architecture — run_loop reuse, Rolling context trimming — REPL-03, REPL UX & controls, Scratchpad/session lifecycle edge cases

---

## Session architecture — run_loop reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Refactor run_loop to accept session state | run_loop() gains optional params (existing Scratchpad, messages, read_snapshots) so REPL wrapper can call it once per turn injecting/reusing prior session state | ✓ |
| Extract inner step-loop into a reusable function | Pull the for-step ReAct loop body into a session-scoped helper; run_loop becomes a thin one-shot wrapper | |
| Keep run_loop untouched, wrap Scratchpad externally | REPL calls run_loop fresh each turn, new session-lifetime Scratchpad threaded in via light param at call boundary | |

**User's choice:** Refactor run_loop to accept session state
**Notes:** run_loop still does the ReAct step loop; REPL owns the outer input/session loop.

| Option | Description | Selected |
|--------|-------------|----------|
| One continuous messages list | System prompt once, every turn + tool observations append to same list | ✓ |
| Reset messages per turn, carry only Scratchpad | Fresh system+task list each turn; only Scratchpad persists | |

**User's choice:** One continuous messages list

| Option | Description | Selected |
|--------|-------------|----------|
| Reset each turn | New user turn is a fresh intent; guard only fires within a turn's step loop | ✓ |
| Persist across whole session | Guard state carries across turns | |

**User's choice:** Reset each turn

| Option | Description | Selected |
|--------|-------------|----------|
| Per-turn budget | Each user input gets fresh --max-steps allowance | ✓ |
| One running budget for whole session | --max-steps consumed cumulatively across all turns | |

**User's choice:** Per-turn budget

| Option | Description | Selected |
|--------|-------------|----------|
| Persist across session | File read in turn 1 satisfies read-before-write in turn 3 | ✓ |
| Reset each turn | Every turn requires its own fresh read_file before write_file | |

**User's choice:** Persist across session

| Option | Description | Selected |
|--------|-------------|----------|
| Once per session | get_provider() runs once when REPL starts, reused for every turn | |
| Re-initialize per turn | get_provider() called fresh each turn | |
| (free text) | User: "can change model while in session" | ✓ |

**User's choice:** Free text — wants ability to switch model mid-session (led to follow-up questions below)

| Option | Description | Selected |
|--------|-------------|----------|
| Slash command `/model <name>` | REPL recognizes leading `/model` line as control command, re-runs get_provider(), keeps session state intact | ✓ |
| Restart provider silently on model change via flag | No in-REPL command; user must exit and restart with different --model | |

**User's choice:** Slash command `/model <name>`

| Option | Description | Selected |
|--------|-------------|----------|
| History transfers | New model receives same accumulated messages list | ✓ |
| History resets on switch | Clean messages list on switch | |

**User's choice:** History transfers

---

## Rolling context trimming — REPL-03

| Option | Description | Selected |
|--------|-------------|----------|
| Drop oldest full turns | Remove complete oldest turns until under budget | |
| Drop oldest tool observations first | Strip large old Observation blocks first | |
| Summarize dropped turns into a running digest | Condense old turns into a short summary appended to context | ✓ |

**User's choice:** Summarize dropped turns into a running digest
**Notes:** Adds complexity and an extra summarization call, but user picked deliberately.

| Option | Description | Selected |
|--------|-------------|----------|
| System prompt + current turn only | Only system prompt and in-progress turn protected | ✓ |
| System prompt + last N full turns | Guarantee a fixed window of recent turns always intact | |

**User's choice:** System prompt + current turn only

| Option | Description | Selected |
|--------|-------------|----------|
| Character-count proxy | Estimate tokens via char count | |
| Exact tokenizer count per model | Use model's actual tokenizer for precise counting | ✓ |

**User's choice:** Exact tokenizer count per model
**Notes:** Flagged as conflicting with "zero new heavy dependencies" constraint — user confirmed deliberately.

| Option | Description | Selected |
|--------|-------------|----------|
| Proactive, before each model call | Estimate size before every provider.chat() call, trim preemptively | ✓ |
| Reactive, only after overflow error | Let call fail on overflow, then trim and retry | |

**User's choice:** Proactive, before each model call

**Flagged conflict follow-up 1** — Summarization needs an LLM call:
| Option | Description | Selected |
|--------|-------------|----------|
| Same session model, dedicated short-summary call | Reuse active model with small dedicated prompt | ✓ |
| Accept the cost — confirm intentional | Confirm extra per-trim call acceptable | |

**User's choice:** Same session model, dedicated short-summary call

**Flagged conflict follow-up 2** — Exact token counting needs a tokenizer library:
| Option | Description | Selected |
|--------|-------------|----------|
| Ollama's own token-count API/response field | Use eval_count/usage.total_tokens, no new dependency | |
| Add a lightweight tokenizer dependency | Pull in a small tokenizer lib purely for estimation | ✓ |

**User's choice:** Add a lightweight tokenizer dependency
**Notes:** Deliberate override of "zero new heavy dependencies" constraint after conflict was flagged.

| Option | Description | Selected |
|--------|-------------|----------|
| tiktoken | Widely used, fast, prebuilt wheels | ✓ |
| Claude's discretion at research time | Let researcher evaluate current options | |

**User's choice:** tiktoken

---

## REPL UX & controls

| Option | Description | Selected |
|--------|-------------|----------|
| Ctrl+D and /exit or /quit | EOF exits cleanly; /exit and /quit as alternatives; Ctrl+C interrupts current turn | |
| Ctrl+C exits, Ctrl+D ignored | Single-key exit convention | |
| (free text) | User: "ctrl+c 2 times, /exit /quit" | ✓ |

**User's choice:** Free text — Ctrl+C twice (double-tap) exits session; single Ctrl+C interrupts current turn; /exit and /quit also exit.

| Option | Description | Selected |
|--------|-------------|----------|
| Per-session only, set at launch | --yes/--dry-run set once at REPL launch, govern every turn | ✓ |
| Toggleable via slash command mid-session | e.g. /yes on, /dry-run toggle | |

**User's choice:** Per-session only, set at launch

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, identical output | Reuse exact same _display()/progress printing unchanged | ✓ |
| Condensed/different output for REPL | More compact progress indicator | |

**User's choice:** Yes, identical output

| Option | Description | Selected |
|--------|-------------|----------|
| None else needed | /model, /exit, /quit cover REPL-01/02 scope | |
| Add /clear (reset session state) | Resets messages, Scratchpad, read_snapshots without restarting process | ✓ |

**User's choice:** Add /clear (reset session state)

---

## Scratchpad/session lifecycle edge cases

| Option | Description | Selected |
|--------|-------------|----------|
| Reset by /clear | Full session reset covers messages, Scratchpad, read_snapshots, and untrusted_observation_seen | ✓ |
| Sticky for whole process, /clear doesn't reset it | Untrusted-exposure consequence persists across /clear | |

**User's choice:** Reset by /clear

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, /clear wipes the digest | Consistent with /clear being a full state reset | ✓ |
| Digest persists across /clear | Digest treated as separate long-lived session memory | |

**User's choice:** Yes, /clear wipes the digest

| Option | Description | Selected |
|--------|-------------|----------|
| Leave untouched | /model only swaps provider/model, all other state stays as-is | ✓ |
| Reset safety-related state on switch | Treat model switch as a trust boundary, reset read_snapshots and untrusted flag | |

**User's choice:** Leave untouched

---

## Claude's Discretion

- Exact prompt wording for the dedicated summarization call.
- Internal digest format/structure.
- `prompt_toolkit` configuration specifics: history file location, key bindings beyond Ctrl+C/Ctrl+D behavior, multiline-editing trigger keys.
- Exact `/model` and `/clear` confirmation message wording.
- Which `tiktoken` encoding to use as the counting proxy for non-OpenAI models.

## Deferred Ideas

None — discussion stayed within phase scope.
