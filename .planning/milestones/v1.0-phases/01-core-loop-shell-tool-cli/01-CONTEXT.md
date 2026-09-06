# Phase 1: Core Loop + Shell Tool + CLI - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A user runs `olla "task description" --model <name>` and watches a reason-act-observe loop drive a shell command to a `<final>` answer, parsing `<tool>/<args>/<final>` tags from any local Ollama model. Phase 1 also ships the `olla` console-script and a smoke test that measures tag-compliance across the 5 target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive).

</domain>

<decisions>
## Implementation Decisions

### Args/Tag Format (LOOP-01)
- **D-01:** `<args>` content for the shell tool is a **raw string**, e.g. `<args>ls -la /tmp</args>`. Parser extracts the content and runs `shlex.split()` on it directly. No JSON anywhere in the tag contract.
- **D-02:** **Per-tool micro-format principle, locked project-wide now**: each tool defines its own simple `<args>` shape (shell = raw command string). No tool uses JSON, even when future tools (Phase 3 file tools) need multiple fields — they get their own delimiter convention, not a JSON fallback.

### System Prompt (LOOP-01, CLI-02)
- **D-03:** Minimal format-teaching — short prose rule per tag (`<tool>`, `<args>`, `<final>`) plus **exactly ONE worked example** showing a complete shell tool call followed by a `<final>` answer. No multi-example or "what not to do" blocks — token-budget takes priority over extra compliance margin.
- **D-04:** The worked example is the **sole teaching mechanism** for the args-raw-string convention — no separate prose rule saying "`<args>` contains the raw command text." Show, don't explain.

### Step Output Display (LOOP-05)
- **D-05:** Each step prints `Step N: running <resolved argv>...` using the **post-`shlex.split()`** command — what will actually execute — not the raw `<args>` string verbatim.
- **D-06:** After execution, also print a **truncated preview of the actual command output**, using the same truncation rule that applies to history (LOOP-03). Shown distinctly from any model reasoning/prose text, so hallucinated-observation bugs (Pitfall 3) are visible immediately.

### Smoke Test / Format Validation (Success Criterion #6)
- **D-07:** Implemented as **`olla --smoke-test [--model NAME]`** — a CLI subcommand (not a separate script, not pytest-only) that runs a fixed prompt set against the target model and prints a per-model tag-compliance table. Matches PITFALLS' framing of this as a "run when trying a new model" user workflow.
- **D-08:** A model scoring **<80%** (PITFALLS Pitfall 1 threshold) is **reported/flagged in the output as a known issue**. Phase 1 does **not** build a fallback delimiter format — that becomes a documented finding for a possible follow-up decimal phase (e.g. 1.1) if the smoke test surfaces it.

### Claude's Discretion
None — every gray area had a clear user choice (all "Recommended" options accepted as-is).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — core value, constraints, key decisions (XML tags over JSON, `shell=False`, no hardcoded default model)
- `.planning/REQUIREMENTS.md` — LOOP-01, LOOP-02, LOOP-03, LOOP-05, SHELL-01, CLI-01, CLI-02, CLI-03 definitions for Phase 1
- `.planning/ROADMAP.md` §Phase 1 — success criteria including the smoke-test requirement (#6) and the `<80%` fallback-format trigger

### Research (load-bearing for Phase 1)
- `.planning/research/PITFALLS.md` — Pitfall 1 (tag-compliance validation, the smoke test's reason for existing), Pitfall 2 (lenient/tolerant parsing), Pitfall 3 (stop-sequence + hallucinated-observation, buffer-then-truncate-then-parse), Pitfall 6 (output truncation + explicit `num_ctx`)
- `.planning/research/ARCHITECTURE.md` — loop/parser/prompt structure (Patterns 2-4), Build Order Slice 1. **Note:** its `<args>{"command": "..."}` JSON example is **superseded by D-01/D-02 above** — use the raw-string per-tool format instead, everywhere this doc shows JSON args.

</canonical_refs>

<code_context>
## Existing Code Insights

Repo is empty (no `src/`, no `pyproject.toml` yet) — Phase 1 is a from-scratch build. `.planning/research/ARCHITECTURE.md` "Recommended Project Structure" (`src/olla/{cli,loop,parser,prompts}.py` + `tools/shell.py`) is the only existing structural guidance; nothing to reuse, nothing to integrate with.

</code_context>

<specifics>
## Specific Ideas

- Shell tool's `<args>` is the literal command string, fed straight to `shlex.split()` — e.g. model writes `<args>ls -la /tmp</args>`, parser runs `shlex.split("ls -la /tmp")`.
- System prompt ships with exactly one worked example (one shell call + one `<final>`), nothing more.
- Per-step terminal output: `Step N: running <resolved argv>...` then a truncated preview of real stdout/stderr.
- `olla --smoke-test --model <name>` runs the fixed compliance prompt set and prints a table; <80% on any model is flagged but does not block Phase 1 or trigger building an alternate format.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope. (One correction, not a deferral: ARCHITECTURE.md's JSON `<args>` example is now superseded per D-01/D-02 — flagged above in canonical_refs so the planner doesn't carry it forward by accident.)

</deferred>

---

*Phase: 1-Core Loop + Shell Tool + CLI*
*Context gathered: 2026-06-10*
