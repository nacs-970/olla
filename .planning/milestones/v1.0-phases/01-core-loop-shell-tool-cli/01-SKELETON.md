# Walking Skeleton — olla

**Phase:** 1
**Generated:** 2026-06-10

## Capability Proven End-to-End

A user runs `olla "list the files in /tmp" --model <local-ollama-model>` and watches a reason-act-observe loop call a real local Ollama model, parse its `<tool>/<args>/<final>` tags, execute a real shell command via `shlex.split()` + `subprocess.run(shell=False)`, print step-by-step progress with truncated output previews, and print the model's final answer — all from a `pip install -e .`-installed `olla` console-script.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| CLI framework | `click` (`@click.command()`, single command, no subcommands in Plan 1) | Decorator-based parsing maps directly onto `TASK` argument + `--model`/`--dry-run`/`--max-steps`/`--yes` flags; `click.UsageError` gives free CLI-01 enforcement (no hardcoded default model). Locked in PROJECT.md/CLAUDE.md. |
| Model interface | `ollama` official Python sync client, `ollama.chat()` only (no native `tools=` schema) | XML-tag prompting (`<tool>/<args>/<final>`) over JSON function-calling, per PROJECT.md and D-01/D-02 — small models (0.6B-4B) are unreliable at JSON tool schemas; the official client's `chat()` is a thin wrapper sufficient for sync, sequential ReAct steps. |
| Agent loop | Hand-rolled ReAct loop in `src/olla/loop.py` (`run_loop`, `call_model`, `truncate_output`) — no LangChain/LlamaIndex/agent framework | ~30-40 line loop is simpler, has near-zero per-turn token overhead, and avoids frameworks whose JSON-first assumptions and large dependency trees directly fight the "minimal overhead on constrained hardware" core value. |
| Tag/data format | Per-tool raw-string micro-format (e.g. shell's `<args>` = literal command string, fed straight to `shlex.split()`); regex-based tolerant parser (`FINAL_RE`/`TOOL_RE`/`ARGS_RE` with `(?:</tag>|$)`), NOT a real XML parser | D-01/D-02 lock this project-wide: no JSON anywhere in the tag contract, every tool defines its own simple `<args>` shape. A real XML parser (`lxml`/`ElementTree`) would reject the malformed/unbalanced tags small models routinely produce (especially with `stop=["</args>"]` truncating output mid-tag) — a tolerant regex parser is required. |
| "Data layer" | None — in-memory `messages: list[dict]` (OpenAI/Ollama chat-message shape: `{"role": ..., "content": ...}`) passed by reference through the loop, no persistence | Phase 1 is single-shot/one-process; no DB, no cross-run state. Phase 4 (Memory Tool) will add persistent scratchpad notes — deliberately NOT built here. |
| Shell execution | `subprocess.run(shlex.split(args_raw), shell=False, capture_output=True, text=True, timeout=30)` in `src/olla/tools/shell.py` | `shell=False` + `shlex.split()` is the load-bearing security control (see threat model T-01-01 in 01-01-PLAN.md): shell metacharacters in model-generated `<args>` become literal argv tokens, never interpreted by a shell. No pipes/redirects/chaining in v1 (SHELL-01). |
| Tool result contract | `ToolResult` `TypedDict(total=False)` in `src/olla/tools/base.py` with `argv`/`returncode`/`stdout`/`stderr`/`error` keys | Shared shape every tool returns (shell now, file read/write in Phase 3). No registry/dispatch class built yet — only one tool exists; `loop.py` calls `run_shell()` directly. Phase 3 should introduce a registry only if/when a second tool's dispatch needs it. |
| Context sizing & loop safety | Explicit `num_ctx=8192` and `stop=["</args>", "Observation:"]` on every `ollama.chat()` call (`think=False` always); `truncate_output()` (head+tail, `MAX_OBSERVATION_CHARS=2000`) applied identically to the printed preview AND the history-appended `Observation:` message; `--max-steps` (default 15) hard-caps the loop | LOOP-02/LOOP-03: prevents the model hallucinating its own `Observation:`/`<final>` past a tool call, prevents large tool output from silently evicting the system prompt from context, and guarantees the loop terminates even if the model never emits `<final>`. |
| Packaging / distribution | `hatchling` build backend, `src/` layout, `pyproject.toml`-only (no `setup.py`), `[project.scripts] olla = "olla.cli:main"`, `pip install -e ".[dev]"` for local dev | CLI-03. Modern, reproducible, zero legacy packaging files. `[dependency-groups.dev]`/optional-dependencies keeps `pytest`/`pytest-mock`/`ruff` out of the runtime install. |
| Directory layout | `src/olla/{__init__.py, cli.py, loop.py, parser.py, prompts.py, tools/{__init__.py, base.py, shell.py}}`, mirrored by `tests/{test_parser.py, test_loop.py, test_cli.py, test_tools/test_shell.py}` | One module per concern (CLI parsing / loop orchestration / tag parsing / prompt text / tool implementations), matching the vertical slice CLI -> loop -> parser/tools. Sets the pattern Phase 2 (safety gate module), Phase 3 (file tools under `tools/`), and Phase 4 (memory tool under `tools/`) will extend without restructuring. |

## Stack Touched in Phase 1

- [x] Project scaffold — `pyproject.toml` (hatchling, src layout), `ruff` + `pytest` configured as dev extras
- [x] CLI entry point — `olla "task" --model <name>` is the one real "route"; `--dry-run`/`--yes`/`--max-steps` flags accepted (only `--max-steps` functional in Plan 1)
- [x] Model integration — at least one real read (`ollama.chat()` against a live local model) AND the loop's "write" equivalent (executing a real shell command and feeding its output back into message history)
- [x] Terminal UI — step-by-step progress (`Step N: running [...]`), truncated output previews, and final-answer printing (the "interactive element wired to the API")
- [x] Local run — `pip install -e ".[dev]"` + `olla "task" --model <name>` is the documented full-stack run command (no separate deployment target; this is a local CLI tool)

## Out of Scope (Deferred to Later Slices)

- Command blocklist, confirm-before-execute prompts, `--dry-run` enforcement, repetition guard (Phase 2 — SAFE-01, SAFE-02, SAFE-03, SAFE-04, LOOP-04). `--dry-run`/`--yes` exist only as no-op CLI flags in Plan 1 for surface stability.
- `--smoke-test` tag-compliance table across the 5 target models (Plan 2 of this phase, success criterion 6 / D-07/D-08).
- A tool registry/dispatch abstraction — only `run_shell()` exists; `loop.py` calls it directly. Revisit only when a second tool (Phase 3 file tools) needs shared dispatch.
- File read/write tools (Phase 3 — FILE-01, FILE-02).
- Cross-turn memory/scratchpad tool (Phase 4 — MEM-01).
- Native `tools=` JSON function-calling as an alternative path (explicitly rejected per PROJECT.md/D-01/D-02 for the 0.6B-7B target range; XML tags are the only supported format).
- Pipes, redirects, command chaining (`|`, `>`, `&&`, `;`) in the shell tool — SHELL-01 v1 scope is single-command argv only.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 1, Plan 2: `olla --smoke-test [--model NAME]` — runs a fixed prompt set against a target model and prints a tag-compliance table, reusing `parser.py`/`loop.py` from Plan 1; flags any model scoring <80% as a known issue (D-08) without building a fallback format.
- Phase 2: Safety gate (blocklist + confirm-before-execute + `--dry-run` enforcement + repetition guard) inserted at the parse-to-dispatch boundary in `loop.py`, between `parse_response()` and `run_shell()`.
- Phase 3: File read/write tools (`tools/file.py`, reusing the `ToolResult` contract from `tools/base.py`), gated through Phase 2's safety gate.
- Phase 4: Memory/scratchpad tool (`tools/memory.py`) for cross-turn note persistence within a single run.
