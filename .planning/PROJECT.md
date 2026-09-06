# olla

## What This Is

A lightweight Python CLI agent that wraps local Ollama models and remote OpenAI-compatible providers in a tight ReAct (reason → act → observe) loop. Run agentic tasks — shell commands, file edits, scratchpad memory notes — against small local LLMs (0.6B-7B range) or remote endpoints without framework bloat or heavyweight dependencies.

## Core Value

Stay fast and accurate on small local models. Minimal per-turn token overhead so 2-4B models on constrained hardware remain responsive and don't drift into wrong answers under a bloated context.

## Requirements

### Validated

- ✓ ReAct loop core: think → act → observe cycle, tolerant XML-tag parsing (`<tool>`, `<args>`, `<final>`) — v1.0
- ✓ Stop-sequences passed to chat client to prevent hallucinated observations — v1.0
- ✓ Explicit context sizing (`num_ctx`) and tool output truncation — v1.0
- ✓ Repetition guard: aborts loop on 2-3 repeated identical calls — v1.0
- ✓ Visible step-by-step progress output ("Step N: running `<cmd>`...") — v1.0
- ✓ Shell tool: `subprocess.run(shlex.split(cmd), shell=False)` — v1.0
- ✓ Safety: `--dry-run` single-step preview — v1.0
- ✓ Safety: shell command blocklist speed bump with recursive unwrapping — v1.0
- ✓ Safety: `--max-steps` cap (default 15) to prevent infinite loops — v1.0
- ✓ Safety: confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes` — v1.0
- ✓ File tools: `read_file(path)` and atomic `write_file(path, content)` with read-derived overwrite checks and diff preview — v1.0
- ✓ Scratchpad memory tool: `remember`/`recall` for cross-turn notes — v1.0
- ✓ CLI: `--model` flag targeting any local or remote model without hardcoded default — v1.0
- ✓ CLI: One-shot mode `olla "task description"` — v1.0
- ✓ CLI: Pip-installable via `pyproject.toml` console-script entry point — v1.0
- ✓ Provider: Remote OpenAI-compatible API support (`--api-base`, `--api-key`, OpenRouter) — v1.0

### Active

- [ ] Interactive/REPL mode: multi-turn conversational session
- [ ] Per-tool allowlist (`--tools`/`-t`) to restrict session to read-only tools
- [ ] Token/context usage indicator (e.g., "~1.2k/4k tokens used this turn")
- [ ] Context-compaction on `remember()`: prune redundant tool observations

### Out of Scope

- Config file (`~/.olla/config.toml`) — CLI flags and env vars sufficient for now
- Web search / browser automation — heavy dependency, large token cost; not core to local-first agent loop
- Rich colored/decorative output — keep output minimal and clean; `rich` scoped to prompts and progress

## Context

- Shipped v1.0 with ~8,500 LOC Python (3,260 LOC src, 5,249 LOC tests).
- 375 automated unit and integration tests passing.
- Tech stack: Python 3.10+, `ollama`, `rich`, `click`, `httpx`.
- Local Ollama models tested: `JOSIEFIED-Qwen3` (0.6b/1.7b/4b), `gemma4:e2b`, `gemma4-uncensored-aggressive`.
- Remote providers: OpenAI-compatible endpoints including OpenRouter with automated retry and backoff.
- Prompt format uses XML-style tags (`<tool>`, `<args>`, `<final>`) rather than JSON function-calling schemas, keeping token overhead minimal.

## Constraints

- **Hardware**: Must run well on resource-constrained hardware — minimize per-turn token overhead, avoid heavy framework dependencies.
- **Models**: Model-agnostic. Support both local Ollama models and remote OpenAI-compatible endpoints; no hardcoded default model.
- **Dependencies**: Minimal — `ollama`, `rich`, `click`, `httpx`. No LangChain, Pydantic, or vector DBs.
- **Distribution**: pip install via `pyproject.toml`, single `olla` console-script entry point.
- **Safety**: Agent executes arbitrary shell commands and writes files — blocklist, confirm-gating, read-derived overwrites, and dry-run are non-negotiable.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| ReAct loop with XML-style tags, no JSON tool schema | Small models (0.6-4B) are unreliable at JSON function calling; tag-based output parses reliably and keeps prompts short | ✓ Good |
| No hardcoded default model | User runs multiple models day-to-day, needs flexibility via `--model` | ✓ Good |
| pip/pyproject distribution with console-script entry point | Standard CLI install pattern, clean `olla` command on PATH | ✓ Good |
| Multi-layer safety gate (blocklist + confirm prompt + dry-run) | Defense-in-depth against prompt injection and accidental destructive actions | ✓ Good |
| Read-derived overwrite prerequisite for file editing | Prevents small models from hallucinating file replacements without inspecting contents | ✓ Good |
| Invocation-scoped scratchpad memory (`remember`/`recall`) | Allows intermediate state without context bloating or persistent database overhead | ✓ Good |
| Pluggable provider abstraction (Ollama + OpenAI-compatible) | Seamless switching between local inference and remote models | ✓ Good |

---
*Last updated: 2026-09-07 after v1.0 milestone*
