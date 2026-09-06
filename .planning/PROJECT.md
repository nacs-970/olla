# olla

## What This Is

A lightweight Python CLI agent that wraps local Ollama models and remote OpenAI-compatible providers in a tight ReAct (reason → act → observe) loop. Run agentic tasks — shell commands, file edits, scratchpad memory notes, web search/reading via curl/httpx, and file inspection — against small local LLMs (0.6B-7B range) or remote endpoints without framework bloat or heavyweight dependencies.

## Core Value

Stay fast and accurate on small local models. Minimal per-turn token overhead so 2-4B models on constrained hardware remain responsive and don't drift into wrong answers under a bloated context.

## Current Milestone: v1.1 Tools Expansion & Interactive REPL

**Goal:** Expand olla with lightweight curl/httpx web search and page fetching, safe read-only inspection tools, and an interactive REPL mode, while preserving strict small-model token budgets and near-zero memory overhead.

**Target features:**
- Web Search Tool (`search_web`): DuckDuckGo Lite snippet search via curl/httpx.
- Web Content Reader (`fetch_url`): Lightweight HTTP/curl HTML text extractor.
- Safe File Inspection Tools (`list_dir`, `grep_files`): Unprompted read-only filesystem discovery.
- Interactive REPL Mode: Multi-turn conversational session with preserved tool context.

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

- [ ] **SEARCH-01**: Web search tool `search_web(query)` using curl/httpx against DuckDuckGo Lite returning top 3-5 snippets
- [ ] **WEB-01**: Webpage text reader `fetch_url(url)` using curl/httpx with boilerplate stripping and 3,000-char truncation
- [ ] **WEB-02**: Untrusted observation tagging for web results revoking `--yes` auto-bypass on subsequent destructive actions
- [ ] **INSPECT-01**: Read-only directory listing tool `list_dir(path)` with type/size info, capped at 50 entries
- [ ] **INSPECT-02**: Read-only regex search tool `grep_files(pattern, path)` capped at 25 matches
- [ ] **INSPECT-03**: Unprompted execution for inspection tools under `safety.check()`
- [ ] **REPL-01**: Interactive REPL mode `olla` (without task argument) supporting multiline editing via `prompt_toolkit`
- [ ] **REPL-02**: Multi-turn session state preserving Scratchpad memory across turns
- [ ] **REPL-03**: Rolling conversation context truncation to fit within model `num_ctx`

### Out of Scope

- Heavy browser automation (Playwright/Chromium) — rejected to preserve host RAM and avoid binary dependencies
- Config file (`~/.olla/config.toml`) — CLI flags and env vars sufficient for now
- Rich colored/decorative output — keep output minimal and clean; `rich` scoped to prompts and progress

## Context

- Shipped v1.0 with ~8,500 LOC Python (3,260 LOC src, 5,249 LOC tests).
- 375 automated unit and integration tests passing.
- Tech stack: Python 3.10+, `ollama`, `rich`, `click`, `httpx`.
- Local Ollama models tested: `JOSIEFIED-Qwen3` (0.6b/1.7b/4b), `gemma4:e2b`, `gemma4-uncensored-aggressive`.
- Remote providers: OpenAI-compatible endpoints including OpenRouter with automated retry and backoff.
- Prompt format uses XML-style tags (`<tool>`, `<args>`, `<final>`) rather than JSON function-calling schemas, keeping token overhead minimal.

## Constraints

- **Hardware**: Must run well on resource-constrained hardware (e.g. 7.1GB RAM host) — near-zero memory footprint for web tools.
- **Models**: Model-agnostic. Support both local Ollama models and remote OpenAI-compatible endpoints; no hardcoded default model.
- **Dependencies**: Zero new heavy dependencies — use system `curl` / `httpx` for web queries.
- **Distribution**: pip install via `pyproject.toml`, single `olla` console-script entry point.
- **Safety**: Unprompted tools must be strictly read-only; destructive operations continue to require confirmation.

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
| Lightweight curl/httpx web search over heavy browser | Eliminates 300-500MB browser RAM bloat and extra binary dependencies on 7.1GB RAM host | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-07 for v1.1 milestone kickoff*
