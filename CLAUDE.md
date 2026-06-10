<!-- GSD:project-start source:PROJECT.md -->

## Project

**olla**

A lightweight Python CLI agent that wraps local Ollama models in a tight ReAct (reason → act → observe) loop. Run agentic tasks — shell commands, file edits — against small local LLMs (0.6B-7B range) without the overhead of frameworks like LangChain or heavyweight agent CLIs.

**Core Value:** Stay fast and accurate on small local models. Minimal per-turn token overhead so 2-4B models on constrained hardware remain responsive and don't drift into wrong answers under a bloated context.

### Constraints

- **Hardware**: Must run well on a resource-constrained laptop — minimize per-turn token overhead, avoid heavy framework dependencies.
- **Models**: Model-agnostic. User switches between multiple local Ollama models (0.6B-7B range); no hardcoded default model.
- **Dependencies**: Minimal — `ollama` (Python client), `rich`, `click` only. No LangChain, Pydantic, or vector DBs.
- **Distribution**: pip install via `pyproject.toml`, single `olla` console-script entry point.
- **Safety**: Agent executes arbitrary shell commands and writes files — blocklist, confirm-gating, and dry-run are non-negotiable from v1.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | >=3.10 | Runtime | Matches `click` 8.4's minimum (3.10+) and is the realistic floor for any 2026 CLI; Arch Linux ships 3.12+ by default so no compatibility tax. Using `match` statements and modern typing (`X \| Y`) keeps the ~500-line codebase terse. |
| `ollama` (official Python client) | >=0.6.2 | Talk to local Ollama server (`chat`, `generate`, streaming) | Official, actively maintained client (latest 0.6.2, Apr 2026). Thin wrapper over Ollama's HTTP API — exactly the "near-zero abstraction" fit for this project. Supports both sync `Client`/top-level functions and `AsyncClient`; v1 should use the **sync** top-level `chat()`/`generate()` since the ReAct loop is inherently sequential (think → act → observe, one step at a time). |
| `click` | >=8.1,<9 | CLI argument parsing, console-script entry point | Industry-standard for Python CLIs (38%+ of CLI projects per 2025 surveys), explicitly named in PROJECT.md constraints, decorator-based API keeps a single-file CLI readable, and `click.confirm()` / `click.prompt()` map directly onto the required "confirm before shell/write_file" UX. Pin `<9` to avoid an unplanned major-version jump mid-project; 8.4.1 (released May 2026) is current. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich` | >=13,<14 | Pretty console output (streaming tokens, step headers, diffs before confirm) | **Reconcile with PROJECT.md first** — see "Conflict to resolve" below. If kept: use only `rich.console.Console` for streaming print + `rich.prompt.Confirm` for the confirm-gate. Avoid `rich.progress`/tables/panels — that's the "polish" PROJECT.md explicitly defers. A minimal `rich` usage (one `Console` instance, plain `.print()` calls) costs ~1 import and adds negligible startup latency. |
| (stdlib) `argparse` | bundled | Fallback if you decide to drop `click` | Only relevant if you want **zero third-party deps**. For ~500 lines with one subcommand-free entry point (`olla "task"` + flags), argparse is entirely sufficient and ships with Python — see "Alternatives Considered." Not recommended here only because PROJECT.md already commits to `click`, and `click`'s decorator style + built-in `confirm`/`prompt`/`echo` save boilerplate for this project's safety-gating UX. |
| (stdlib) `subprocess` | bundled | Shell tool execution | Use `subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=...)` with the command pre-split (`shlex.split`), **not** `shell=True`. See PITFALLS-adjacent notes below — this is a security-critical default, not a style preference. |
| (stdlib) `shlex` | bundled | Safely tokenize/quote shell command strings | Use `shlex.split()` to turn the model's `<args>command</args>` string into an argv list before passing to `subprocess.run(..., shell=False)`. Also useful for blocklist matching (match against the parsed argv[0]/args, not raw substring matching on the full string, to reduce bypass via quoting tricks). |
| (stdlib) `re` | bundled | Tool-call tag parser (`<tool>`/`<args>`/`<final>`) | A simple regex-based or incremental-scan parser is sufficient for XML-style tags from small models. No XML parser library needed — the tags are not real XML (models often emit malformed/unbalanced tags), so a forgiving regex/state-machine parser is more robust than `xml.etree` (which will throw on malformed input). |
| (stdlib) `pathlib` | bundled | File read/write tool implementations | Standard for path handling; pairs naturally with confirm-gating (`Path(p).resolve()` to check the resolved path before write). |
| `pytest` | >=8 | Test runner | De facto standard; needed for the testing strategy below. |
| `pytest-mock` | >=3.14 | Convenience wrapper over `unittest.mock` for mocking `ollama.chat`/`generate` | Optional — `unittest.mock.patch` from stdlib is sufficient, but `pytest-mock`'s `mocker` fixture reduces boilerplate when mocking the same `ollama.chat` call across many test cases (one per parser/loop scenario). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` | Unit + integration tests | Structure: `tests/test_parser.py` (XML tag parsing — pure functions, no mocking needed), `tests/test_tools.py` (shell/file tools, mock `subprocess.run` and use `tmp_path` fixture for file I/O), `tests/test_loop.py` (ReAct loop, mock `ollama.chat` to return canned XML responses and assert on step transitions/max-steps/dry-run behavior). |
| `ruff` | Linting + formatting (replaces flake8/black/isort) | Single fast tool, zero-config-friendly, widely adopted as of 2025/2026. Add as a dev dependency only (`[dependency-groups.dev]` or `[project.optional-dependencies.dev]`); does not affect runtime install. |
| `hatchling` (build backend) | Build the wheel/sdist for `pip install` | See packaging section below — recommended over `setuptools` for a clean, modern `pyproject.toml`-only setup. |
| `uv` (optional, dev workflow) | Fast venv/dependency management during development | Not a project dependency — a recommendation for *your* dev loop (`uv venv`, `uv pip install -e .`, `uv run pytest`). Does not appear in `pyproject.toml`. |

## Installation

# Core runtime dependencies

# Optional (only if PROJECT.md constraint is updated to keep rich — see conflict note)

# Dev dependencies

### `pyproject.toml` skeleton

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `click` | `argparse` (stdlib) | If you want **literally zero third-party dependencies** beyond `ollama` itself. For a ~500-line single-command CLI with flags like `--model`, `--dry-run`, `--max-steps`, `--yes`, argparse is fully capable and ships with Python. The only loss is `click`'s built-in `confirm()`/`prompt()`/`echo()` helpers (trivial to replace with `input()` and `print()`). Recommended to switch to this **only if** the project later wants to drop the `click` dependency entirely; otherwise `click` is fine and already decided in PROJECT.md. |
| `click` | `typer` | Typer is excellent for multi-subcommand CLIs with type-hint-driven parsing, but it's built **on top of click** and adds its own dependency surface (plus optionally `rich` for its help formatting). For a single-command, flag-only CLI, typer adds abstraction without payoff — `click` (or argparse) is simpler and matches PROJECT.md's existing decision. |
| `ollama` official client | Raw `requests`/`httpx` calls to `http://localhost:11434/api/*` | If you want to shave the `httpx`+`pydantic` transitive dependency tree (see conflict note below) to an absolute minimum. The Ollama HTTP API is simple JSON-over-HTTP and `/api/chat` with `"stream": true` returns newline-delimited JSON — easy to consume with stdlib `urllib.request` + `json.loads` per line. **Not recommended for v1**: you'd be reimplementing connection handling, error mapping, and streaming parsing that the official client already provides correctly, for a project whose stated goal is *not* "build everything from scratch." Revisit only if the `pydantic` dependency becomes a real problem (it currently is not — see below). |
| Regex/state-machine XML-tag parser | `lxml` / `xml.etree.ElementTree` | Real XML parsers reject malformed/unbalanced markup, which small models *will* produce (unclosed tags, stray text before/after tags, nested angle brackets in shell commands). A tolerant custom parser (regex for `<tool>...</tool>`, `<args>...</args>`, `<final>...</final>` with greedy/non-greedy tuning, plus fallback handling for unclosed final tags) is both simpler and more robust here. Don't add an XML dependency for this. |
| Native Ollama `tools=` parameter | XML-tag prompting (PROJECT.md's chosen approach) | Already decided, and research **supports this decision** — see Sources/notes below. Native tool-calling is appropriate if/when the project later targets only models >=7-8B that have been specifically tuned for tool use (e.g., Llama 3.1 8B, Qwen3-Coder), and you're willing to handle Ollama's known tool-calling bugs (malformed JSON on truncation → HTTP 500 in some Qwen3 cases). |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `subprocess.run(cmd, shell=True)` | Passes the model-generated command string straight to `/bin/sh -c`, enabling shell metacharacter injection (`;`, `|`, `` ` ``, `$()`) even after blocklist checks on the literal string — a blocklist on `"rm -rf /"` does nothing against `"rm -rf /tmp/x; rm -rf /"` style chaining if shell interpretation is allowed implicitly elsewhere, and `shell=True` is the single highest-risk default in this codebase given the agent runs **arbitrary model-suggested commands**. | `subprocess.run(shlex.split(cmd), shell=False, capture_output=True, text=True, timeout=N)`. Still apply the blocklist, but on the parsed argv, not the raw string. |
| `ollama.create()` for "system prompt" | `create()` builds a **persistent custom Modelfile-based model variant** on the Ollama server — it's for publishing a new named model, not for per-request system prompts. Using it per-invocation would pollute the user's local Ollama model list and add significant overhead per turn. | Pass `messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": ...}, ...]` to `chat()` — system prompt is just the first message with `role: "system"`, no model creation needed. |
| Native `tools=` schema as the *only* tool-invocation path for v1 | Confirmed via Ollama's own issue tracker: tool-call JSON from Qwen3 models can be truncated/malformed and Ollama returns HTTP 500 instead of a graceful partial result; tool definitions for some templates aren't reliably serialized to JSON. This directly corroborates PROJECT.md's existing rationale for XML tags on small models — native tool calling is **not** a safe fallback to lean on for 0.6B-4B models. | Stick with the XML `<tool>/<args>/<final>` prompting approach already decided. Optionally, keep native tool-calling as an experiment behind a flag for larger models (gemma 7B+) later, but don't make it load-bearing for v1. |
| `LangChain`, `LlamaIndex`, or any agent framework | PROJECT.md explicitly excludes these, and research confirms the rationale: these frameworks assume JSON/structured tool-calling as the primary interface, add large dependency trees (10s of transitive packages), and add per-turn prompt overhead (system prompts often 1-2k+ tokens) that directly fights the stated goal of minimizing per-turn token overhead on constrained hardware. | The hand-rolled ~500-line ReAct loop already planned. |
| `pydantic` as a *direct* project dependency | PROJECT.md constraints say "No... Pydantic." Be aware this is **already unavoidable transitively** — `ollama>=0.6.2` depends on `pydantic>=2.9` for its response models (`ChatResponse`, `Message`, etc.). This is not a violation of the spirit of the constraint (no Pydantic *models to write/maintain in olla's own code*), but worth noting so it's not a surprise when `pip install ollama` pulls in `pydantic` + `pydantic-core` + `httpx` + `httpcore` + `anyio` + others. | Don't write any Pydantic models in olla's own code (use plain dataclasses/dicts/TypedDict if structure is needed). Accept the transitive dependency from `ollama` itself — it's the cost of using the official client and is reasonable. |
| `requests` library | Not needed — `ollama` client already bundles `httpx` for HTTP, and you shouldn't be making raw HTTP calls in v1 per the alternatives analysis above. | `ollama` client's `chat()`/`generate()`. |

## Stack Patterns by Variant

- Drop `click`, use stdlib `argparse` for `--model`, `--dry-run`, `--max-steps`, `--yes`, and the positional task string.
- Drop `rich`, use plain `print()` with `sys.stdout.write()` for streaming token output (flush after each chunk) and stdlib `input()` for the confirm prompt.
- This still pulls in `pydantic`/`httpx` transitively via `ollama`, which is unavoidable without reimplementing the HTTP layer.
- Use `click` for the entry point and flag parsing as the primary CLI surface.
- Use `rich.console.Console` *only* for: (1) streaming the model's thinking/output token-by-token with `console.print(token, end="")`, and (2) `rich.prompt.Confirm.ask(...)` for the shell/write_file confirm gate. Do not build tables, panels, progress bars, or syntax-highlighted diffs in v1 — that's the explicitly deferred "polish."
- This is the recommended path: it matches PROJECT.md's stated dependency list, and a minimal `rich` usage genuinely improves the UX of a streaming agent loop (distinguishing "thinking" output from tool results from final answers via simple color/style) at near-zero cost.
- Use `ollama.chat(model=..., messages=..., tools=[...])` with Python functions passed directly (the SDK auto-converts function signatures + docstrings to tool schemas).
- Keep this behind a `--native-tools` experimental flag; do not replace the XML-tag path, since the project is explicitly model-agnostic across 0.6B-7B and the XML approach is the only one proven reliable across that whole range.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `ollama>=0.6.2` | Python >=3.8 (package floor) | No conflict with the recommended >=3.10 floor (driven by `click` 8.4.x). If you instead pin `click==8.1.*` for a 3.7+ floor, `ollama` is still compatible. |
| `ollama>=0.6.2` | `pydantic>=2.9`, `httpx>=0.27` (transitive) | Both are modern, actively maintained, no known conflicts with `click`/`rich`/`pytest`. Do not pin these yourself — let `ollama`'s own constraints resolve them. |
| `click>=8.1,<9` | `rich>=13,<14` | No interaction; both can coexist freely. If you later migrate to `typer`, note typer itself depends on `click` and optionally `rich`, so the combination is well-trodden. |
| `hatchling` (build backend) | `pyproject.toml`-only projects, `src/` layout | No `setup.py`/`setup.cfg` needed. Works cleanly with `pip install -e .` (editable installs) for local development. |
| `pytest>=8` | Python >=3.9 | Comfortably covers the >=3.10 floor. |

## Conflict to Resolve (flag for roadmap/PROJECT.md)

- If `rich` is a declared dependency, it should be doing *something* (otherwise it's dead weight) — minimal use (streaming console + confirm prompt) is recommended above and is cheap.
- If "no rich output" is the real intent for v1, drop `rich` from the dependency list entirely and use stdlib `print()`/`input()` — the CLI still works fine, just with plain text.

## Sources

- https://github.com/ollama/ollama-python — current version (0.6.2, Apr 2026), `chat()`/`generate()`/`AsyncClient` API shape, streaming via `stream=True`. MEDIUM-HIGH confidence (WebFetch of repo + PyPI, not Context7 — Context7 CLI unavailable in this session due to sandbox policy).
- https://pypi.org/project/ollama/ — version 0.6.2, Python >=3.8 requirement. HIGH confidence (official package index).
- https://docs.ollama.com/capabilities/tool-calling — tools parameter schema, streaming tool-call accumulation behavior, `role: "tool"` response messages. HIGH confidence (official docs).
- https://github.com/ollama/ollama/issues/14601 and https://github.com/ollama/ollama/issues/14570 — Qwen3 tool-calling reliability issues (malformed tool definitions, HTTP 500 on truncated JSON). MEDIUM confidence (GitHub issue tracker, real bug reports but issue status/fix-state not independently re-verified at time of writing) — directly supports PROJECT.md's XML-tag design decision.
- https://pypi.org/project/click/ — click 8.4.1 (May 2026), Python >=3.10 requirement. HIGH confidence (official package index).
- WebSearch: "click vs typer vs argparse small CLI pyproject.toml" — click ~38.7% adoption share among Python CLI projects as of 2025, argparse recommended for zero-dependency lightweight tools. MEDIUM confidence (aggregated WebSearch summary, multiple consistent sources but not a single authoritative benchmark).
- WebSearch: "hatchling vs setuptools pyproject.toml minimal Python package 2025" — hatchling recommended as the modern default for pure-Python `pyproject.toml`-only projects (PEP 621-native, no `setup.py` needed, reproducible builds, git-aware file inclusion). MEDIUM-HIGH confidence (consistent across Hatch's own docs and independent comparison articles).
- WebSearch: "python subprocess command safety blocklist library shell agent sandbox" — confirms `shell=False` + `shlex.split()` as the standard mitigation for command injection in agent-executed shell tools; allowlist preferred over blocklist in general security guidance (though PROJECT.md's blocklist approach for v1 is a reasonable pragmatic floor, not a full security boundary). MEDIUM confidence.
- WebSearch: "testing python CLI agent mocking ollama chat responses pytest tool call parser" — confirms the pattern of mocking the LLM client call (`ollama.chat`) at the boundary and testing the parser/loop logic deterministically with canned responses; pytest fixtures for "fake LLM response" objects are the standard approach. MEDIUM confidence (aggregated from multiple blog/community sources, no single canonical reference).

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
