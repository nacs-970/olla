---
phase: 01-core-loop-shell-tool-cli
plan: 01
subsystem: agent-loop
tags: [ollama, click, shlex, subprocess, react-loop, cli, xml-parsing]

requires: []

provides:
  - "olla CLI: TASK argument + --model (required, no hardcoded default) + --max-steps (default 15, functional) + --dry-run/--yes (accepted no-op stubs for Phase 2)"
  - "run_loop(): ReAct step loop calling ollama.chat() with options={'stop': ['</args>','Observation:'], 'num_ctx': 8192}, think=False on every step"
  - "parse_response(): tolerant <tool>/<args>/<final> extraction handling markdown fences, surrounding prose, and unclosed tags"
  - "run_shell(): shlex.split() + subprocess.run(shell=False) with timeout and missing-command error handling"
  - "truncate_output(): head+tail truncation shared identically between printed step preview and Observation: history entry"
  - "ToolResult TypedDict (total=False) shared tool-result contract for future Phase 3 file tools"

affects: [02-safety-gating, 03-file-tools]

tech-stack:
  added: ["ollama>=0.6.2", "click>=8.1,<9", "pytest>=8", "pytest-mock>=3.14", "ruff"]
  patterns:
    - "ReAct loop: messages list (system/user/assistant), one ollama.chat() call per step"
    - "Tolerant regex parsing via (?:</tag>|$) alternation to handle stop-sequence-truncated model output"
    - "shlex.split + subprocess.run(shell=False) for safe argv execution (no shell metacharacter interpretation)"
    - "Single truncate_output() call feeds both the printed preview and the history-appended Observation (LOOP-03 guarantee)"

key-files:
  created:
    - pyproject.toml
    - src/olla/__init__.py
    - src/olla/cli.py
    - src/olla/loop.py
    - src/olla/parser.py
    - src/olla/prompts.py
    - src/olla/tools/__init__.py
    - src/olla/tools/base.py
    - src/olla/tools/shell.py
    - tests/__init__.py
    - tests/test_parser.py
    - tests/test_loop.py
    - tests/test_cli.py
    - tests/test_tools/__init__.py
    - tests/test_tools/test_shell.py
  modified: []

key-decisions:
  - "T-01-SC supply-chain checkpoint approved: ollama, click, pytest, pytest-mock, ruff all verified as legitimate PyPI packages (no typosquats); pip install -e \".[dev]\" succeeded"
  - "Task 7 e2e checkpoint approved: real ollama.chat() run (model=tripolskypetr/gemma4-uncensored-aggressive:latest) verified both the no-tool <final> path ('what is 1+1' -> '2', clean) and the tool-calling path ('list the files in the current directory' -> Step 1: running ['ls', '-F']... with real directory listing preview, then a final-answer line); --model-required usage error confirmed via 'olla \"do something\"' -> 'Error: --model is required (no hardcoded default model, CLI-01)'"

patterns-established:
  - "ToolResult TypedDict (total=False) as the shared tool-result shape — Phase 3 file tools should return this same shape"
  - "SYSTEM_PROMPT = short prose + exactly ONE worked <tool>/<final> example, zero JSON — proven to elicit correctly-tagged output from a small (uncensored gemma) local model"

requirements-completed: [LOOP-01, LOOP-02, LOOP-03, LOOP-05, SHELL-01, CLI-01, CLI-02, CLI-03]

duration: ~30min active (Tasks 1-6: 26min on 2026-06-11 07:23-07:49 +07; Task 7 + summary: 2026-06-11, after a session-pause checkpoint)
completed: 2026-06-11
---

# Phase 1: core-loop-shell-tool-cli Summary

**Walking-skeleton `olla` CLI: ollama.chat()-driven ReAct loop with tolerant XML-tag parsing and shlex+subprocess(shell=False) shell execution, verified end-to-end against a real local Ollama model**

## Performance

- **Duration:** ~30 min active work (split across two sessions; Task 7 paused for human-verify checkpoint)
- **Started:** 2026-06-11T00:23:18Z (Task 1 commit)
- **Completed:** 2026-06-11T08:12:42Z (this summary)
- **Tasks:** 7 (6 auto/tdd + 1 blocking human-verify checkpoint)
- **Files modified:** 15 (all new)

## Accomplishments
- Full vertical slice (CLI -> loop -> ollama.chat -> parser -> shell tool -> printed final answer) verified against a real local Ollama model, both with and without a tool call
- Tolerant `<tool>/<args>/<final>` parser handles markdown-fenced, prose-wrapped, AND unclosed-tag model output (7/7 parser tests)
- Safe shell execution via `shlex.split()` + `subprocess.run(shell=False)` with timeout and missing-command handling (5/5 shell tests)
- ReAct loop enforces stop-sequences (`</args>`, `Observation:`), `num_ctx=8192`, `think=False` on every step, and truncates large outputs identically for display and history (6/6 loop tests)
- CLI requires `--model` (no hardcoded default, CLI-01), `--max-steps` is functional (default 15), `--dry-run`/`--yes` accepted as no-op stubs for Phase 2 (4/4 cli tests)
- `pip install -e ".[dev]"` exposes a working `olla` console-script

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffold (pyproject.toml + package skeleton)** - `c35df81` (feat)
2. **Task 2: Verify pip install before building on the package** - approved (T-01-SC), no separate commit (verification-only checkpoint)
3. **Task 3: System prompt + tag parser** - `62d71f0` (feat, tdd)
4. **Task 4: Shell tool** - `dcdeb00` (feat, tdd)
5. **Task 5: ReAct loop (truncation, stop-sequences, step output)** - `5fea05f` (feat, tdd)
6. **Task 6: CLI wiring + manual end-to-end verification** - `228e392` (feat, tdd)
7. **Task 7: End-to-end run against a real local Ollama model** - approved, no separate commit (verification-only checkpoint)

**Plan metadata:** this commit (docs: complete plan 01-01)

## Files Created/Modified
- `pyproject.toml` - hatchling src-layout config, `olla` console-script entry point, runtime + dev deps
- `src/olla/__init__.py` - package marker
- `src/olla/cli.py` - click entry point `main()`: TASK + --model (required) + --max-steps + --dry-run/--yes
- `src/olla/loop.py` - `run_loop()`, `call_model()`, `truncate_output()`, `MAX_OBSERVATION_CHARS`
- `src/olla/parser.py` - `parse_response()`, `FINAL_RE`, `TOOL_RE`, `ARGS_RE`
- `src/olla/prompts.py` - `SYSTEM_PROMPT` (prose + one worked example, no JSON)
- `src/olla/tools/__init__.py` - tools subpackage marker
- `src/olla/tools/base.py` - `ToolResult` TypedDict (total=False)
- `src/olla/tools/shell.py` - `run_shell()` via shlex + subprocess(shell=False)
- `tests/__init__.py`, `tests/test_tools/__init__.py` - package markers
- `tests/test_parser.py` - 7 parser tests
- `tests/test_loop.py` - 6 loop tests (mocked ollama.chat)
- `tests/test_tools/test_shell.py` - 5 shell tests
- `tests/test_cli.py` - 4 CLI tests

## Decisions Made
- T-01-SC (supply-chain) approved after spot-checking all 5 declared packages on PyPI — no typosquats, install succeeded.
- Task 7 e2e checkpoint approved: real-model run confirmed both the no-tool `<final>` path and the tool-calling path (`Step 1: running ['ls', '-F']...` + real directory listing preview), and the `--model`-required usage error fires before any model call. Both pass criteria from `01-01-PLAN.md` Task 7 `<how-to-verify>` (steps 3-6) satisfied.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Session-process note (not a code issue): a checkpoint instruction containing a literal `--model <your-model>` placeholder caused a zsh parse error (`zsh: parse error near \n`) because zsh interprets bare `<`/`>` as redirection. Resolved by giving the real model name inline in all subsequent checkpoint commands. No code change required; tracked as a process anti-pattern in `.continue-here.md` for future sessions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Walking skeleton complete and verified end-to-end against a real local Ollama model (both no-tool and tool-calling paths).
- 22/22 unit tests pass (7 parser + 5 shell + 6 loop + 4 cli).
- Ready for Plan 01-02 (`--smoke-test` flag, depends_on 01-01) — same modules, formalizes this same compliance check across more models/think-modes.
- Phase 2 (safety gating: SAFE-01..04 — blocklist, confirm-before-execute, `--dry-run` enforcement) builds directly on `run_shell()`/`run_loop()`/the existing `--dry-run`/`--yes` CLI stubs.
- No blockers carried forward.

---
*Phase: 01-core-loop-shell-tool-cli*
*Completed: 2026-06-11*

## Self-Check: PASSED
22/22 tests pass (7 parser + 5 shell + 6 loop + 4 cli); all 5 acceptance-criteria greps return >=1; all 15 key files present; `import olla` succeeds; `olla "do something"` correctly errors with "Error: --model is required (no hardcoded default model, CLI-01)".
