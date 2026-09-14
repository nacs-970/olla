# Codebase Structure

**Analysis Date:** 2026-09-14

## Directory Layout

```
olla/
├── src/olla/                  # Application package (installed as `olla`)
│   ├── __init__.py             # Empty/near-empty package marker
│   ├── cli.py                  # click entry point (`olla` console script)
│   ├── config.py               # TOML config loader (~/.config/olla/config.toml)
│   ├── debug.py                # --debug / OLLA_DEBUG tracing
│   ├── loop.py                 # ReAct loop orchestrator (largest file, 1178 lines)
│   ├── parser.py                # <tool>/<args>/<final> tag parser
│   ├── prompts.py               # SYSTEM_PROMPT string
│   ├── safety.py                # Shell argv ALLOW/CONFIRM/BLOCK classifier
│   ├── smoke.py                 # Model format-compliance smoke test
│   ├── providers/                # LLM backend abstraction
│   │   ├── __init__.py            # get_provider() factory + re-exports
│   │   ├── base.py                # Provider Protocol, StreamChunk, ProviderError
│   │   ├── ollama.py              # Local Ollama daemon provider
│   │   └── openai_compat.py       # OpenRouter/OpenAI-compatible HTTP provider
│   └── tools/                     # Individual tool implementations
│       ├── __init__.py             # Empty
│       ├── base.py                 # ToolResult / FileSnapshot shared types
│       ├── files.py                # read_file / write_file (TOCTOU-safe)
│       ├── inspect.py              # list_dir / grep_files
│       ├── memory.py               # Scratchpad (remember / recall)
│       ├── shell.py                # run_shell (subprocess wrapper)
│       └── web.py                  # fetch_url / search_web
├── tests/                      # pytest suite, mirrors src/olla/ layout
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_debug.py
│   ├── test_loop.py             # Largest test file (103K) — full loop scenarios
│   ├── test_parser.py
│   ├── test_prompts.py
│   ├── test_providers.py
│   ├── test_safety.py
│   ├── test_smoke.py
│   └── test_tools/               # Mirrors src/olla/tools/
│       ├── test_files.py
│       ├── test_inspect.py
│       ├── test_memory.py
│       ├── test_shell.py
│       └── test_web.py
├── .planning/                  # GSD workflow state (requirements, roadmap, phase plans, codebase docs)
├── test_connection.py           # Standalone manual connectivity script (repo root, not in tests/)
├── pyproject.toml               # hatchling build, deps, [project.scripts] entry point, pytest config
├── uv.lock                      # uv-managed lockfile
├── README.md
└── CLAUDE.md                    # Project-specific instructions for Claude Code
```

## Directory Purposes

**`src/olla/`:**
- Purpose: The entire application — flat package, no sub-packages beyond `providers/` and `tools/`
- Contains: Orchestration (`loop.py`), CLI (`cli.py`), support modules (`config.py`, `debug.py`, `prompts.py`, `smoke.py`), parser (`parser.py`), safety gate (`safety.py`)
- Key files: `loop.py` (core logic, 1178 lines), `cli.py` (thin wiring layer)

**`src/olla/providers/`:**
- Purpose: Isolate all LLM-backend-specific code behind a common `Provider` Protocol
- Contains: One module per backend family (`ollama.py` for local Ollama, `openai_compat.py` for any OpenAI-compatible HTTP API used by both `openrouter/` and `openai/` model prefixes) plus the shared `base.py` types and the `__init__.py` routing factory
- Key files: `__init__.py` (`get_provider()` — the only way callers obtain a provider)

**`src/olla/tools/`:**
- Purpose: One module per tool family exposed to the model via the tag protocol
- Contains: `shell.py` (process execution), `files.py` (filesystem read/write with staleness protection), `inspect.py` (read-only directory/grep tools), `memory.py` (in-run scratchpad), `web.py` (network fetch/search), `base.py` (shared result/snapshot types consumed by all of the above)
- Key files: `base.py` defines the contract every other file in this directory implements

**`tests/`:**
- Purpose: pytest suite; structure mirrors `src/olla/` 1:1 (`tests/test_X.py` tests `src/olla/X.py`; `tests/test_tools/test_Y.py` tests `src/olla/tools/Y.py`)
- Contains: Unit tests per module plus `test_loop.py`, which is by far the largest test file and covers full multi-step loop scenarios (safety confirmation, write staleness, repetition detection, provider streaming)
- Committed: Yes

**`.planning/`:**
- Purpose: GSD workflow artifacts — requirements, roadmap, phase plans/summaries, research notes, and this `codebase/` doc set
- Contains: `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `milestones/`, `phases/`, `research/`, `codebase/`
- Generated: Partially (research cache files under `.cache/` are generated; most `.md` files are hand/agent-authored)
- Committed: Yes (except `.planning/tmp/` and `.planning/research/.cache/` per typical GSD conventions — verify against `.gitignore` before assuming)

## Key File Locations

**Entry Points:**
- `src/olla/cli.py`: `main()` — the `olla` console-script target (`pyproject.toml` `[project.scripts]`)
- `src/olla/loop.py`: `run_loop()` — the programmatic core entry point invoked by `cli.py`

**Configuration:**
- `pyproject.toml`: dependencies, build backend (hatchling), console script, pytest config
- `src/olla/config.py`: runtime TOML config resolution (`~/.config/olla/config.toml`, `OLLA_CONFIG` env override, legacy `~/.olla/config.toml` fallback)
- `.ruff_cache/`, `.pytest_cache/`: tool caches, not hand-edited

**Core Logic:**
- `src/olla/loop.py`: ReAct step cycle, action dispatch, safety/confirmation wiring
- `src/olla/parser.py`: model-output tag parsing
- `src/olla/safety.py`: shell command risk classification

**Testing:**
- `tests/`: pytest suite; run via `pytest` (uses `[tool.pytest.ini_options] testpaths = ["tests"]` from `pyproject.toml`)
- `tests/test_tools/`: tool-specific tests mirroring `src/olla/tools/`

## Naming Conventions

**Files:**
- Module names are singular, lowercase, underscores only when needed: `loop.py`, `parser.py`, `safety.py`, `config.py`
- Provider modules named after the backend they wrap: `ollama.py`, `openai_compat.py` (compat suffix signals it serves multiple `*_compat` model prefixes, not just OpenAI itself)
- Test files always `test_<module>.py`, one-to-one with the source module they cover

**Directories:**
- Plural nouns for collections of same-shaped modules: `providers/`, `tools/`
- `tests/test_tools/` mirrors `src/olla/tools/` exactly — when adding a new tool module, add its test in the matching subdirectory

## Where to Add New Code

**New Tool (e.g. a new model-callable capability):**
- Implementation: new module in `src/olla/tools/` implementing functions that return `ToolResult` (see `src/olla/tools/base.py`)
- Wire-up required in `src/olla/parser.py` (if the tag shape needs special-casing, following the `write_file`/`remember`/`recall` precedent), `src/olla/loop.py` (`_prepare_action` branch, new `_execute_*` function, dispatch chain in `run_loop()` and `_preview_action()`), and `src/olla/prompts.py` (document the new tag in `SYSTEM_PROMPT`)
- Tests: `tests/test_tools/test_<name>.py` plus loop-level scenario coverage in `tests/test_loop.py`

**New Provider (e.g. a new remote model backend):**
- Implementation: new module in `src/olla/providers/` implementing the `Provider` Protocol (`chat`, `stream_chat`, `get_context_length`) from `src/olla/providers/base.py`
- Wire-up required in `src/olla/providers/__init__.py` (`get_provider()` prefix-routing logic)
- Tests: `tests/test_providers.py`

**Safety Rule Changes:**
- All shell-risk logic lives in `src/olla/safety.py` only — do not duplicate allowlist/blocklist checks elsewhere
- Tests: `tests/test_safety.py`

**Utilities:**
- Shared helpers with no natural tool/provider home go directly in `src/olla/` (e.g. `debug.py`, `config.py`) rather than a generic `utils.py` — this codebase has no catch-all utility module

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow state (requirements, roadmap, phase history, research, codebase docs)
- Generated: Mixed (agent-authored docs; `.cache/` subfolders are generated research caches)
- Committed: Yes (verify `.gitignore` for `.planning/tmp/` exclusions)

**`.pytest_cache/`, `.ruff_cache/`:**
- Purpose: Tool caches for pytest and ruff
- Generated: Yes
- Committed: No (present in working tree but excluded via `.gitignore`)

**`.gsd/`:**
- Purpose: GSD tooling working state (untracked at time of analysis)
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-09-14*
