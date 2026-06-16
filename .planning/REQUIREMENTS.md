# Requirements: olla

**Defined:** 2026-06-10
**Core Value:** Stay fast and accurate on small local models — minimal per-turn token overhead so 2-4B models on constrained hardware remain responsive and don't drift into wrong answers under a bloated context.

## v1 Requirements

### Loop

- [x] **LOOP-01**: ReAct loop parses `<tool>`/`<args>`/`<final>` tags from model output, tolerant of markdown fences, whitespace, and minor formatting drift
- [x] **LOOP-02**: Stop-sequences passed to `ollama.chat()` so the model can't generate past a tool call and hallucinate its own observation/final
- [x] **LOOP-03**: Explicit `num_ctx` set on every Ollama request; large tool outputs truncated before being appended to history
- [x] **LOOP-04**: Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3 times in a row
- [x] **LOOP-05**: Visible step-by-step progress output ("Step N: running `<cmd>`...") as the loop executes

### Shell

- [x] **SHELL-01**: Shell tool runs `subprocess.run(shlex.split(cmd), shell=False)`, captures stdout/stderr, returns to model — no pipes/redirects/chaining in v1

### Files

- [x] **FILE-01**: `read_file(path)` tool reads file contents for the model
- [x] **FILE-02**: `write_file(path, content)` tool writes file contents

### Memory

- [ ] **MEM-01**: `remember(key, value)` scratchpad tool for cross-turn notes

### Safety

- [x] **SAFE-01**: `--dry-run` flag previews the next planned tool call without executing it or any side effects, then stops
- [x] **SAFE-02**: Shell command blocklist (`rm -rf /`, `sudo`, `dd`, etc.) as a speed-bump layer, not the primary safety boundary
- [x] **SAFE-03**: `--max-steps` cap (default 15) prevents infinite loops
- [x] **SAFE-04**: Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes`

### CLI

- [x] **CLI-01**: `--model` flag targets any local Ollama model, no hardcoded default
- [x] **CLI-02**: One-shot mode — `olla "task description"` runs the loop to completion
- [x] **CLI-03**: Pip-installable via `pyproject.toml` (hatchling, src layout), `olla` console-script entry point

## v2 Requirements

### CLI

- **CLI-04**: Per-tool allowlist (`--tools`/`-t`) to restrict a session to read-only tools
- **CLI-05**: Token/context usage indicator (e.g., "~1.2k/4k tokens used this turn")

### Memory

- **MEM-02**: Context-compaction — `remember()` calls trigger trimming/summarizing the corresponding tool observation from rolling context

## Out of Scope

| Feature | Reason |
|---------|--------|
| Interactive/REPL mode | Adds session-state complexity; deferred to v2 once one-shot loop is validated |
| Config file (`~/.olla/config.toml`) | CLI flags sufficient for v1; defer until flag patterns stabilize |
| Web search / browser automation | Heavy dependency, large token cost; not core to local-first agent loop |
| Rich colored/decorative output (panels, tables, syntax highlighting) | Pure polish, zero functional risk in deferring; `rich` scoped to `Confirm.ask` + step progress only |
| Per-project tool toggles | Defer until config file lands |
| JSON/OpenAI-style function-calling schema | Small models (sub-4B) are unreliable at structured JSON; tag-based format chosen specifically to avoid this failure mode |
| Sandboxed/containerized execution (Docker, bubblewrap) | Heavyweight, platform-specific, conflicts with "pip install, runs anywhere Ollama runs"; confirm-gate is the safety boundary instead |
| Diff/patch-based file editing | Structured patch output is exactly the multi-field reliability problem the tag format avoids; full-file `write_file` rewrite chosen instead |
| Persistent autonomous/background operation | Conflicts with confirm-gating and `--max-steps` safety model; one-shot only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LOOP-01 | Phase 1 | Complete |
| LOOP-02 | Phase 1 | Complete |
| LOOP-03 | Phase 1 | Complete |
| LOOP-05 | Phase 1 | Complete |
| SHELL-01 | Phase 1 | Complete |
| CLI-01 | Phase 1 | Complete |
| CLI-02 | Phase 1 | Complete |
| CLI-03 | Phase 1 | Complete |
| LOOP-04 | Phase 2 | Complete |
| SAFE-01 | Phase 2 | Complete |
| SAFE-02 | Phase 2 | Complete |
| SAFE-03 | Phase 2 | Complete |
| SAFE-04 | Phase 2 | Complete |
| FILE-01 | Phase 3 | Complete |
| FILE-02 | Phase 3 | Complete |
| MEM-01 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-10*
*Last updated: 2026-06-10 after roadmap creation (LOOP-04 reassigned Phase 1 → Phase 2: repetition guard is loop-control, pairs with max-steps in the safety/control phase)*
