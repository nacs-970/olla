# Milestones

## v1.0 MVP (Shipped: 2026-09-07)

**Phases completed:** 5 phases, 19 plans, 36 tasks  
**Codebase:** 8,509 LOC Python (3,260 LOC src, 5,249 LOC tests) across 154 files  
**Test Suite:** 375 tests passing in 7.11s  
**Git Range:** `ec9303b` -> `85cb025` (296 commits)  
**Verification:** Verified closeout (0 open items, 16/16 requirements satisfied)

**Key accomplishments:**

- Walking-skeleton `olla` CLI: `ollama.chat()`-driven ReAct loop with tolerant XML-tag parsing and `shlex+subprocess(shell=False)` shell execution, verified end-to-end against local Ollama models.
- Format smoke-test `olla --smoke-test --model <name>`: multi-prompt compliance classification with automated warning heuristics.
- Safety gate (`olla.safety`): blocklist with recursive command unwrapping, prompt injection resistance, confirm-before-execute prompt, and `--yes` override.
- Bounded loop control: `--dry-run` single-step preview, `--max-steps` cap, and repetition guard aborting runaway tool thrashing.
- Remote provider integration: OpenAI-compatible endpoint support (OpenAI, OpenRouter) with retry/backoff and streaming tag suppression.
- File tools: safe `read_file(path)` and atomic `write_file(path, content)` with mandatory read-derived overwrite verification, target freshness check, and bounded diff previews.
- Scratchpad memory: atomic invocation-scoped `remember`/`recall` tool with capacity caps and repetition tracking.

---
