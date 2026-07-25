# Codebase Structure

**Analysis Date:** 2026-07-25

## Directory Layout

```text
olla/
├── src/
│   └── olla/                    # Installable application package
│       ├── cli.py               # Click composition root
│       ├── loop.py              # ReAct orchestration
│       ├── parser.py            # Model-response protocol parser
│       ├── prompts.py           # Compact system prompt
│       ├── safety.py            # Shell safety policy
│       ├── smoke.py             # Model-format smoke test
│       └── tools/               # Host I/O adapters and result contract
├── tests/
│   ├── test_cli.py              # CLI routing tests
│   ├── test_loop.py             # Controller behavior tests
│   ├── test_parser.py           # Protocol parser tests
│   ├── test_safety.py           # Safety policy tests
│   ├── test_smoke.py            # Smoke classifier/runner tests
│   └── test_tools/              # Tool adapter tests
├── .planning/
│   ├── codebase/                # Generated current-state codebase maps
│   ├── phases/                  # Phase plans, reviews, and verification
│   ├── quick/                   # Quick-task planning artifacts
│   ├── research/                # Project research documents
│   ├── PROJECT.md               # Product/constraint context
│   ├── REQUIREMENTS.md          # Requirement inventory
│   ├── ROADMAP.md               # Phase roadmap
│   └── STATE.md                 # Current workflow state
├── .claude/
│   └── worktrees/               # Tool-managed worktree location
├── .venv/                       # Local generated Python environment
├── pyproject.toml               # Package, dependency, build, and script config
├── uv.lock                      # Resolved dependency lockfile
├── CLAUDE.md                    # Aggregated repository guidance
└── .gitignore                   # Generated Python artifact exclusions
```

The repository uses a conventional Python `src/` layout. Installable code is
under `src/olla/`; tests live in a separate mirrored `tests/` hierarchy.
Planning and delivery artifacts are kept beside the code in `.planning/`.

The root also currently contains non-package scratch artifacts:
`final_replace.py`, `read_and_replace.py`, `read_and_replace.sh`,
`test_fix.py`, `test_replace.py`, `test_temp.py`, and `test.txt`. These files
are outside `src/olla/`, outside `tests/`, and are not tracked by git. Do not use
them as patterns or destinations for application code.

## Directory Purposes

**`src/olla/`:**

- Purpose: Contains all shipped Python application code.
- Contains: CLI wiring, application orchestration, model protocol, safety
  policy, diagnostics, and the `tools` package.
- Key files: `src/olla/cli.py`, `src/olla/loop.py`,
  `src/olla/parser.py`, `src/olla/prompts.py`,
  `src/olla/safety.py`, `src/olla/smoke.py`

**`src/olla/tools/`:**

- Purpose: Contains concrete host I/O adapters and their shared return
  contract.
- Contains: One module per tool concern plus an empty package initializer.
- Key files: `src/olla/tools/base.py`, `src/olla/tools/files.py`,
  `src/olla/tools/shell.py`, `src/olla/tools/__init__.py`

**`tests/`:**

- Purpose: Contains pytest coverage for application modules and cross-layer
  orchestration behavior.
- Contains: Flat test modules mirroring top-level `src/olla/*.py` modules and a
  nested `test_tools/` package mirroring `src/olla/tools/`.
- Key files: `tests/test_cli.py`, `tests/test_loop.py`,
  `tests/test_parser.py`, `tests/test_safety.py`, `tests/test_smoke.py`

**`tests/test_tools/`:**

- Purpose: Exercises adapter success/error behavior independently of the
  controller.
- Contains: Shell and filesystem adapter tests.
- Key files: `tests/test_tools/test_shell.py`,
  `tests/test_tools/test_files.py`

**`.planning/`:**

- Purpose: Stores GSD project state, roadmap context, implementation plans,
  reviews, audits, and codebase reference documents.
- Contains: Project-level Markdown/JSON files plus phase-, quick-task-,
  research-, and codebase-specific subdirectories.
- Key files: `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`,
  `.planning/ROADMAP.md`, `.planning/STATE.md`,
  `.planning/config.json`, `.planning/HANDOFF.json`

**`.planning/phases/`:**

- Purpose: Groups implementation artifacts by zero-padded phase number and
  kebab-case phase slug.
- Contains: `PLAN`, `SUMMARY`, `RESEARCH`, `REVIEW`, `SECURITY`, `VALIDATION`,
  `VERIFICATION`, and `UAT` documents where applicable.
- Key files: `.planning/phases/01-core-loop-shell-tool-cli/01-01-PLAN.md`,
  `.planning/phases/02-safety-gate-loop-control/02-PATTERNS.md`,
  `.planning/phases/03-file-tools/03-VERIFICATION.md`

**`.planning/research/`:**

- Purpose: Holds design-time ecosystem and architecture research.
- Contains: Stack, feature, pitfall, architecture, summary documents.
- Key files: `.planning/research/ARCHITECTURE.md`,
  `.planning/research/STACK.md`, `.planning/research/SUMMARY.md`

**`.planning/codebase/`:**

- Purpose: Holds current-state maps consumed by planning and execution
  workflows.
- Contains: Uppercase Markdown documents organized by analysis focus.
- Key files: `.planning/codebase/ARCHITECTURE.md`,
  `.planning/codebase/STRUCTURE.md`

**`.claude/worktrees/`:**

- Purpose: Reserved for tool-managed isolated worktrees.
- Contains: No project source files in the current repository state.
- Key files: Not applicable

**`.venv/`:**

- Purpose: Local Python runtime and installed dependency environment.
- Contains: Generated interpreter, packages, and scripts.
- Key files: Not applicable; never add application code here.

## Key File Locations

**Entry Points:**

- `pyproject.toml`: Declares `olla = "olla.cli:main"` as the installed console
  script.
- `src/olla/cli.py`: Defines the single Click command and routes normal versus
  smoke-test execution.
- `src/olla/loop.py`: Defines the normal task runner used by the CLI.
- `src/olla/smoke.py`: Defines the diagnostic runner selected by
  `--smoke-test`.

**Configuration:**

- `pyproject.toml`: Owns package name/version, Python floor, runtime/dev
  dependencies, Hatchling build configuration, and console entry point.
- `uv.lock`: Pins the complete resolved dependency graph for local/reproducible
  development.
- `.gitignore`: Excludes virtual environments, bytecode, egg metadata, and
  pytest caches.
- `CLAUDE.md`: Aggregates project, stack, workflow, and repository guidance.
- `.planning/config.json`: Stores GSD workflow configuration.

**Core Logic:**

- `src/olla/loop.py`: ReAct state machine, model calls, confirmation gates, and
  tool dispatch.
- `src/olla/parser.py`: XML-like response parsing and write-payload
  preservation.
- `src/olla/prompts.py`: Model-facing tool protocol.
- `src/olla/safety.py`: Shell command policy.
- `src/olla/tools/base.py`: Cross-adapter `ToolResult` shape.
- `src/olla/tools/shell.py`: Shell execution adapter.
- `src/olla/tools/files.py`: File read/write adapters.
- `src/olla/smoke.py`: Model protocol compatibility diagnostics.

**Testing:**

- `tests/test_cli.py`: CLI validation and argument forwarding.
- `tests/test_loop.py`: Model/tool conversation flow, safety integration,
  dry-run, truncation, repetition, and max-step behavior.
- `tests/test_parser.py`: Parser tolerance and payload preservation.
- `tests/test_safety.py`: Safety policy and wrapper-bypass regression cases.
- `tests/test_smoke.py`: Response classification and smoke summary behavior.
- `tests/test_tools/test_shell.py`: Subprocess adapter behavior.
- `tests/test_tools/test_files.py`: Filesystem adapter behavior.

## Naming Conventions

**Files:**

- Use lowercase `snake_case.py` for application modules:
  `src/olla/parser.py`, `src/olla/safety.py`.
- Use `test_<module>.py` for tests that mirror one top-level module:
  `tests/test_parser.py`, `tests/test_safety.py`.
- Mirror nested source packages in the test tree:
  `src/olla/tools/files.py` → `tests/test_tools/test_files.py`.
- Keep package markers named `__init__.py`:
  `src/olla/__init__.py`, `src/olla/tools/__init__.py`.
- Use uppercase semantic names for project-wide planning artifacts:
  `.planning/PROJECT.md`, `.planning/ROADMAP.md`,
  `.planning/codebase/ARCHITECTURE.md`.
- Prefix phase artifacts with their zero-padded phase or plan number:
  `.planning/phases/02-safety-gate-loop-control/02-03-PLAN.md`.

**Directories:**

- Use lowercase package names without separators: `src/olla/`.
- Use source-mirroring lowercase test packages: `tests/test_tools/`.
- Use kebab-case for multiword phase and quick-task directories:
  `.planning/phases/01-core-loop-shell-tool-cli/`.
- Use concise plural nouns for code groupings: `src/olla/tools/`,
  `.planning/phases/`, `.planning/research/`.

**Symbols:**

- Use `snake_case` for functions, parameters, and local state:
  `parse_response`, `run_loop`, `repeat_count`.
- Use `PascalCase` for typed dictionary contracts:
  `Decision` in `src/olla/safety.py`, `ToolResult` in
  `src/olla/tools/base.py`.
- Use uppercase `SNAKE_CASE` for protocol/policy constants:
  `SYSTEM_PROMPT`, `ALLOWLIST`, `MAX_OBSERVATION_CHARS`.
- Prefix private implementation helpers with `_`:
  `_blocklist_match`, `_unwrap_env`, `_normalize_slash_target` in
  `src/olla/safety.py`.

## Where to Add New Code

**New User-Facing Feature:**

- Primary code: Put task lifecycle behavior in `src/olla/loop.py`; put only CLI
  declaration, validation, and routing in `src/olla/cli.py`.
- Tests: Add CLI surface cases to `tests/test_cli.py` and lifecycle cases to
  `tests/test_loop.py`.
- Model contract: Update `src/olla/prompts.py` and parser coverage in
  `tests/test_parser.py` whenever the feature changes model-visible syntax.

**New Tool:**

- Implementation: Add `src/olla/tools/<tool_name>.py`; keep it focused on host
  I/O and return `ToolResult`-compatible dictionaries from
  `src/olla/tools/base.py`.
- Dispatch: Add explicit execution, observation, repetition, and confirmation
  handling in `src/olla/loop.py`.
- Prompting: Teach the exact tool and argument format in
  `src/olla/prompts.py`.
- Tests: Add `tests/test_tools/test_<tool_name>.py` for adapter behavior and
  integration cases to `tests/test_loop.py`.
- Contract: Extend `src/olla/tools/base.py` only when the new adapter requires
  reusable result fields; do not mix parser or policy fields into
  `ToolResult`.

**New Shell Safety Rule:**

- Primary code: Add private matching helpers/constants and route them through
  `_blocklist_match()` in `src/olla/safety.py`.
- Tests: Add direct decision cases to `tests/test_safety.py` and a controller
  integration case to `tests/test_loop.py` when the rule affects `--yes`,
  prompting, or execution.

**New Model Response Form:**

- Implementation: Extend tolerant decoding in `src/olla/parser.py`; preserve
  the `final`/`tool`/`none` discriminator expected by
  `src/olla/loop.py`.
- Tests: Add focused parsing cases to `tests/test_parser.py` and end-to-end
  conversation behavior to `tests/test_loop.py`.
- Prompt: Keep emitted examples synchronized in `src/olla/prompts.py`.

**New Diagnostic/Smoke Check:**

- Implementation: Add classifiers or scenarios to `src/olla/smoke.py`.
- CLI routing: Extend the existing diagnostic branch in `src/olla/cli.py`
  unless the project gains multiple subcommands.
- Tests: Add deterministic model-boundary cases to `tests/test_smoke.py`.

**New Component/Module:**

- Implementation: Place shipped modules under `src/olla/`; use a subpackage
  only for a cohesive family such as `src/olla/tools/`.
- Imports: Use absolute package imports in application code, matching
  `from olla.parser import parse_response` in `src/olla/loop.py`.
- Tests: Mirror module ownership under `tests/`.

**Utilities:**

- Shared helpers: No generic utility module exists. Keep a helper private in
  the owning module, as in `src/olla/safety.py`, until two or more production
  modules share the same semantic responsibility.
- Shared contracts: Put adapter result types in
  `src/olla/tools/base.py`; keep policy types beside policy in
  `src/olla/safety.py`.

**Planning and Documentation:**

- Current-state architecture maps: `.planning/codebase/`
- Up-front technical research: `.planning/research/`
- Phase-specific plans/reviews: `.planning/phases/<NN>-<phase-slug>/`
- Quick-task records: `.planning/quick/<date-or-id>-<task-slug>/`

## Special Directories

**`src/`:**

- Purpose: Separates installable Python packages from repository tooling and
  tests.
- Generated: No
- Committed: Yes

**`tests/`:**

- Purpose: Houses pytest suites outside the installed package.
- Generated: No
- Committed: Yes

**`.planning/`:**

- Purpose: Persists GSD project context and delivery artifacts.
- Generated: Partly workflow-generated and partly authored
- Committed: Yes

**`.planning/codebase/`:**

- Purpose: Stores codebase mapper output used by future plans and execution.
- Generated: Yes
- Committed: Intended to be committed with the planning corpus

**`.venv/`:**

- Purpose: Local dependency environment.
- Generated: Yes
- Committed: No; excluded by `.gitignore`

**`__pycache__/`:**

- Purpose: CPython bytecode caches under `src/olla/` and `tests/`.
- Generated: Yes
- Committed: No; excluded by `.gitignore`

**`.pytest_cache/`:**

- Purpose: Pytest's local run metadata.
- Generated: Yes
- Committed: No; excluded by `.gitignore`

**`.ruff_cache/`:**

- Purpose: Ruff's local analysis cache.
- Generated: Yes
- Committed: No

**`.claude/worktrees/`:**

- Purpose: Tool-managed location for isolated repository worktrees.
- Generated: Yes
- Committed: No files detected

**`.agents/` and `.codex/`:**

- Purpose: Reserved repository-local agent/skill configuration roots.
- Generated: Environment-managed
- Committed: No files detected

---

*Structure analysis: 2026-07-25*
