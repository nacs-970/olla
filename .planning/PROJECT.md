# olla

## What This Is

A lightweight Python CLI agent that wraps local Ollama models in a tight ReAct (reason → act → observe) loop. Run agentic tasks — shell commands, file edits — against small local LLMs (0.6B-7B range) without the overhead of frameworks like LangChain or heavyweight agent CLIs.

## Core Value

Stay fast and accurate on small local models. Minimal per-turn token overhead so 2-4B models on constrained hardware remain responsive and don't drift into wrong answers under a bloated context.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] ReAct loop core: think → act → observe cycle, parse `<tool>`/`<args>`/`<final>` XML-style tags from model output, tolerant of markdown fences/whitespace/minor formatting drift
- [ ] Stop-sequences passed to `ollama.chat()` so the model can't keep generating past a tool call and hallucinate its own observation/final
- [ ] Explicit `num_ctx` set on every Ollama request; large tool outputs truncated before being appended to history (prevents silent context-window truncation dropping the system prompt)
- [ ] Repetition guard: abort the loop with a diagnostic if the same tool+args is called 2-3 times in a row
- [ ] Visible step-by-step progress output ("Step N: running `<cmd>`...") as the loop executes
- [ ] Shell tool: `subprocess.run(shlex.split(cmd), shell=False)` — captures stdout/stderr, returned to model. No pipes/redirects/chaining in v1 (shell=False)
- [ ] File tools: `read_file(path)`, `write_file(path, content)`
- [ ] Scratchpad memory tool: `remember(key, value)` for cross-turn notes
- [ ] `--dry-run` flag: single-step preview — show the next planned tool call without executing it or any side effects, then stop (can't honestly preview steps beyond the first without a real observation)
- [ ] Safety: shell command blocklist (`rm -rf /`, `sudo`, `dd`, etc.) — speed-bump layer, not the primary boundary
- [ ] Safety: `--max-steps` cap (default 15) to prevent infinite loops
- [ ] Safety: confirm prompt (via `rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`
- [ ] `--model` flag: target any local Ollama model, no hardcoded default
- [ ] One-shot mode: `olla "task description"` runs loop to completion
- [ ] pip-installable via `pyproject.toml` (hatchling, src layout), `olla` console-script entry point

### Out of Scope

- Interactive/REPL mode — adds complexity, deferred to v2 (v0.3 in original roadmap)
- Config file (`~/.olla/config.toml`) — CLI flags sufficient for v1
- Web search (SearXNG tool) — not core to local-first agent loop, defer to v2
- Rich colored terminal output — nice-to-have polish, not core functionality
- Per-project tool toggles — defer until config file lands

## Context

- User runs Arch Linux laptop with constrained hardware.
- Local Ollama models available: `JOSIEFIED-Qwen3` (0.6b/1.7b/4b), `gemma4:e2b` (7.2GB), `gemma4-uncensored-aggressive` (3GB).
- Prior experience: Ollama + Claude Code combo was too slow and gave wrong answers on this hardware — motivated building something purpose-built for small models.
- Prompt format uses XML-style tags (`<tool>`, `<args>`, `<final>`) rather than JSON function-calling schemas, since small instruction-tuned models (0.6B-4B) are unreliable at structured JSON tool calls but handle simple tag-based output well.

## Constraints

- **Hardware**: Must run well on a resource-constrained laptop — minimize per-turn token overhead, avoid heavy framework dependencies.
- **Models**: Model-agnostic. User switches between multiple local Ollama models (0.6B-7B range); no hardcoded default model.
- **Dependencies**: Minimal — `ollama` (Python client), `rich`, `click` only. No LangChain, Pydantic, or vector DBs.
- **Distribution**: pip install via `pyproject.toml`, single `olla` console-script entry point.
- **Safety**: Agent executes arbitrary shell commands and writes files — blocklist, confirm-gating, and dry-run are non-negotiable from v1.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| ReAct loop with XML-style tags, no JSON tool schema | Small models (0.6-4B) are unreliable at JSON function calling; tag-based output parses reliably and keeps prompts short | — Pending |
| No hardcoded default model | User runs multiple local models day-to-day, needs flexibility via `--model` | — Pending |
| pip/pyproject distribution with console-script entry point | Standard CLI install pattern, clean `olla` command on PATH | — Pending |
| v1 scope = core loop + shell/file tools + memory + dry-run (v0.1-v0.2 of original sketch) | Ship a minimal working agent first, validate the loop before layering interactive mode, config, or web search | — Pending |

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
*Last updated: 2026-06-10 after initialization*
