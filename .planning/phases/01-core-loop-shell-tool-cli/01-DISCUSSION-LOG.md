# Phase 1: Core Loop + Shell Tool + CLI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 1-Core Loop + Shell Tool + CLI
**Areas discussed:** Args payload format, System prompt design, Step output display, Smoke test mechanics

---

## Args payload format

### Q1: What goes inside `<args>` for the shell tool?

| Option | Description | Selected |
|--------|-------------|----------|
| Raw string | `<args>ls -la /tmp</args>` — parser does `shlex.split()` directly. Zero JSON, matches REQUIREMENTS.md's stated reason for tags over JSON. | ✓ |
| JSON dict | `<args>{"command": "ls -la /tmp"}</args>` — matches ARCHITECTURE.md's draft, but stacks JSON on top of the tag format for a single-field case. | |
| Let Claude decide | Researcher/planner picks based on smoke-test results. | |

**User's choice:** Raw string (Recommended)

### Q2: Does the raw-string convention generalize to future tools, or is it shell-specific?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-tool micro-format | Each tool defines its own simple `<args>` shape. No tool ever needs JSON — locks "no JSON anywhere" as a project-wide principle now. | ✓ |
| Raw string only when single-field | Single-arg tools (shell) get raw string; multi-field tools (future write_file) fall back to JSON. Mixed contract. | |
| Decide later — Phase 1 only needs shell | Lock raw-string for shell now, defer multi-field question to Phase 3. | |

**User's choice:** Per-tool micro-format (Recommended)

---

## System prompt design

### Q1: How much format-teaching goes in the system prompt?

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal + 1 example | Short prose rules per tag + ONE worked example of a full shell tool call. Few-shot helps small-model format-following without big token cost. | ✓ |
| Minimal, no examples | Just prose rules, no example. Cheapest, but Pitfall 1 data suggests sub-4B models need a concrete example. | |
| Multiple examples | Happy path + edge case + counter-example. Best compliance odds, real per-turn token cost. | |

**User's choice:** Minimal + 1 example (Recommended)

### Q2: How is the shell tool's raw-string `<args>` convention taught to the model?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in the worked example | The example IS the teaching — `<tool>shell</tool><args>ls -la</args>` shown directly, no separate prose rule. | ✓ |
| Explicit rule + example | State the rule ("`<args>` contains the raw command...") AND show the example. More tokens, removes ambiguity. | |

**User's choice:** Inline in the worked example (Recommended)

---

## Step output display

### Q1: What prints per step beyond "Step N: running `<cmd>`"?

| Option | Description | Selected |
|--------|-------------|----------|
| + truncated observation | Also print a short preview of the actual command output (same truncation as history). Echoes real output distinctly from model reasoning — catches Pitfall 3 (hallucinated observation) visually. | ✓ |
| Tool call line only | Just the "Step N: running..." line, no output until `<final>`. Cleanest, matches LOOP-05 literally. | |
| + model's raw reasoning text too | Also print prose the model wrote before the tag. Useful for debugging, adds clutter. | |

**User's choice:** + truncated observation (Recommended)

### Q2: For the shell tool, does the step line show raw `<args>` or the resolved command?

| Option | Description | Selected |
|--------|-------------|----------|
| Resolved argv | Show what `shlex.split()` produced / what `subprocess.run` actually executes — "what will actually run" echoing principle. | ✓ |
| Raw `<args>` content | Show exactly what the model wrote, verbatim. | |

**User's choice:** Resolved argv (Recommended)

---

## Smoke test mechanics

### Q1: How is the format-compliance smoke test (success criterion #6) invoked?

| Option | Description | Selected |
|--------|-------------|----------|
| CLI subcommand | `olla --smoke-test [--model X]` runs a fixed prompt set and prints a per-model compliance table. PITFALLS frames this as a "run when trying a new model" user workflow — fits olla's multi-model-switching use case. | ✓ |
| Standalone script | `scripts/smoke_test.py`, dev-only, run manually against the 5 target models. | |
| pytest integration test | `tests/test_smoke.py`, marked slow, requires live Ollama + pulled models. | |

**User's choice:** CLI subcommand (Recommended)

### Q2: If a model scores <80% compliance (PITFALLS threshold), what does Phase 1 do about it?

| Option | Description | Selected |
|--------|-------------|----------|
| Report only | Print/flag the <80% result as a known issue. No fallback format built in Phase 1 — stays within the 8 mapped requirements. Becomes a documented finding for a possible follow-up decimal phase. | ✓ |
| Build fallback format now | Phase 1 also implements + tests an alternate plain-delimiter format as contingency. Expands scope beyond the 8 requirements. | |

**User's choice:** Report only (Recommended)

---

## Claude's Discretion

None — every gray area had a clear user choice.

## Deferred Ideas

None — discussion stayed within Phase 1 scope. ARCHITECTURE.md's `<args>` JSON example is now superseded (see CONTEXT.md canonical_refs note), not deferred.
