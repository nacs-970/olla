# Milestones

## v1.1 Tools Expansion & Interactive REPL (Shipped: 2026-09-22)

**Phases completed:** 3 phases, 7 plans, 15 tasks

**Key accomplishments:**

- `fetch_url(url)` delivered end-to-end: a new boilerplate-stripping, byte-capped, sentence-truncating HTTP text reader wired into `run_loop()` with unconfirmed dispatch and untrusted-tagged observation recording that revokes `--yes` on the next destructive action.
- `search_web(query)` delivered end-to-end: DuckDuckGo Lite HTML parsing with sponsored-row exclusion and uddg-redirect decoding, wired into `run_loop()` with unconfirmed dispatch and untrusted-tagged observation recording, plus the phase's final system-prompt roster bump to "9 tools available".
- `run_loop()` refactored to accept an optional externally-owned `SessionState` (messages/scratchpad/read_snapshots/untrusted_observation_seen); a new `src/olla/repl.py` drives it once per turn from a bare `prompt_toolkit` `PromptSession`, wired end-to-end from `olla` with no TASK argument through to a persisted Scratchpad across two consecutive REPL turns.
- `src/olla/repl.py` expanded from 07-01's bare `prompt_toolkit` tracer into the full REPL-01/REPL-02 UX: `FileHistory`-backed persistent history, explicit `multiline`, `patch_stdout()`-wrapped turns, single/double-Ctrl+C exit semantics at both the idle-prompt and mid-turn interrupt sites, and a `/model`/`/exit`/`/quit`/`/clear` slash-command dispatcher scoped to raw terminal input only.
- New `src/olla/context_trim.py` adds `tiktoken`-based proactive rolling-context trimming — sourced from the previously-dead-code `provider.get_context_length()` — wired into a single chokepoint inside `_stream_model_turn()`, with dropped turns replaced by an LLM-generated digest that is always wrapped in `<untrusted_summary_digest>` so summarized content never re-enters context as unmarked trusted text.
- REPL gains a real Alt+Enter-inserts-newline key binding proven through prompt_toolkit's own key-binding resolution (not a kwarg-presence check), and 07-01's cross-turn stale-read-snapshot prohibition is now directly proven by an automated test with zero production code change.

---

## v1.0 MVP (Shipped: 2026-09-07)

**Phases completed:** 5 phases, 19 plans, 36 tasks  
**Codebase:** 8,509 LOC Python (3,260 LOC src, 5,249 LOC tests) across 154 files  
**Test Suite:** 375 tests passing in 7.11s  
**Git Range:** `ec9303b` -> `85cb025` (296 commits)  
**Verification:** Verified closeout (0 open items, 16/16 requirements satisfied)

**Key accomplishments:**

- Walking-skeleton `olla` CLI: `ollama.chat()`-driven ReAct loop with tolerant XML-tag parsing and `shlex+subprocess(shell=False)` shell execution, verified end-to-end against local Ollama models.
- Format smoke-test `olla --smoke-test --model <name>`: multi-prompt compliance classification with automated warning heuristics.
- Safety gate (`olla.safety`): blocklist with recursive command unwrapping, prompt injection resistance, confirm-before-execute prompt, and `--yes` override.
- Bounded loop control: `--dry-run` single-step preview, `--max-steps` cap, and repetition guard aborting runaway tool thrashing.
- Remote provider integration: OpenAI-compatible endpoint support (OpenAI, OpenRouter) with retry/backoff and streaming tag suppression.
- File tools: safe `read_file(path)` and atomic `write_file(path, content)` with mandatory read-derived overwrite verification, target freshness check, and bounded diff previews.
- Scratchpad memory: atomic invocation-scoped `remember`/`recall` tool with capacity caps and repetition tracking.

---
