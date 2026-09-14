# Roadmap: olla

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-09-07)
- 🚧 **v1.1 Tools Expansion & Interactive REPL** — Phases 5-7 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-4) — SHIPPED 2026-09-07</summary>

- [x] Phase 1: Core Loop + Shell Tool + CLI (2/2 plans) — completed 2026-06-11
- [x] Phase 2: Safety Gate + Loop Control (8/8 plans) — completed 2026-06-13
- [x] Phase 02.1: API Connect with olla (Remote Providers) (2/2 plans) (INSERTED) — completed 2026-09-07
- [x] Phase 3: File Tools (5/5 plans) — completed 2026-06-15
- [x] Phase 4: Memory Tool (2/2 plans) — completed 2026-09-07

</details>

### Phase 5: Safe Inspection Tools

- [x] **Phase 5: Safe Inspection Tools** - Read-only `list_dir` and `grep_files` tools executing without confirmation prompts (completed 2026-09-08)
  - **Plans:** 1/1 plans complete
  - Plans:
    - [x] 05-01-PLAN.md — list_dir + grep_files end-to-end, unconfirmed dispatch, untrusted tagging

### Phase 6: Lightweight Web Search & Fetch

- [x] **Phase 6: Lightweight Web Search & Fetch** - DuckDuckGo Lite search and HTML webpage reading via curl/httpx with truncation and untrusted tagging (completed 2026-09-09)
  - **Plans:** 2/2 plans complete
  - Plans:
    - [x] 06-01-PLAN.md — fetch_url end-to-end (web.py adapter, loop.py wiring, untrusted tagging, truncation)
    - [x] 06-02-PLAN.md — search_web end-to-end (DDG Lite parsing, loop.py wiring, prompt roster finalization)

### Phase 7: Interactive REPL Mode

- [ ] **Phase 7: Interactive REPL Mode** - Multi-turn terminal REPL with prompt_toolkit, persistent scratchpad memory, and rolling context management
  - **Plans:** 4/4 plans executed
- [x] 07-04-PLAN.md
  - Plans:
    - [x] 07-01-PLAN.md — SessionState refactor + minimal REPL tracer (run_loop() session injection, cli.py dispatch, dependency checkpoint)
    - [x] 07-02-PLAN.md — Full REPL UX (FileHistory, multiline, double-Ctrl+C, /model /exit /quit /clear)
    - [x] 07-03-PLAN.md — Rolling context trimming (tiktoken counting, summarization digest, untrusted tagging)

## Phase Details

### Phase 5: Safe Inspection Tools

**Goal**: As a user running tasks with olla, I want the model to list directory contents and grep across files without safety confirmation prompts, so that discovery is fast and frictionless.
**Depends on**: Phase 4 (v1.0 complete)
**Requirements**: INSPECT-01, INSPECT-02, INSPECT-03
**Success Criteria**:

1. `list_dir(path)` tool returns directory tree with file types (`[d]`/`[f]`), names, and sizes, capped at 50 items.
2. `grep_files(pattern, path)` tool performs regex search over text files, ignoring `.git` and binary files, capped at 25 matching lines.
3. Both tools execute with no interactive confirmation prompt: `run_loop()` dispatches `list_dir`/`grep_files` straight to their tool adapters, bypassing `safety.check()` entirely (D-09) — `safety.py` is not modified or given a tool-name branch.

### Phase 6: Lightweight Web Search & Fetch

**Goal**: As a user running tasks requiring online information, I want olla to query DuckDuckGo and fetch webpage text using curl/httpx, so that the model can research topics without heavy browser dependencies.
**Depends on**: Phase 5
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04
**Success Criteria**:

1. `search_web(query)` returns top 3-5 snippet cards (title, URL, summary) parsed from DuckDuckGo Lite.
2. `fetch_url(url)` retrieves webpage content and extracts cleaned text with HTML markup stripped.
3. Web observation outputs are strictly hard-truncated to 3,000 characters before appending to context.
4. Web observations tag turn state as `untrusted`, revoking `--yes` auto-bypass on subsequent destructive actions.

### Phase 7: Interactive REPL Mode

**Goal**: As a user working iteratively, I want to run `olla` without arguments to enter an interactive conversation session, so that I can refine tasks across multiple turns while preserving intermediate scratchpad notes.
**Depends on**: Phase 6
**Requirements**: REPL-01, REPL-02, REPL-03
**Success Criteria**:

1. Running `olla` with no positional prompt argument launches an interactive `prompt_toolkit` terminal REPL with multiline editing and history.
2. Scratchpad memory values persist across conversational turns within the same session.
3. Rolling context window management automatically trims older turns to stay within the model's `num_ctx`.
