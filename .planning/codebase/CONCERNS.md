# Codebase Concerns

**Analysis Date:** 2026-09-14

## Tech Debt

**Monolithic `loop.py` carries most control flow:**
- Issue: `src/olla/loop.py` is 1,178 lines and owns action parsing (`_prepare_action`), dry-run preview rendering (`_preview_action`), per-tool execution (`_execute_shell`, `_execute_read_file`, `_execute_write_file`, `_execute_list_dir`, `_execute_grep_files`, `_execute_fetch_url`, `_execute_search_web`, `_execute_memory`), streaming, and the `run_loop` state machine, all in one module.
- Files: `src/olla/loop.py`
- Impact: Any change to the action protocol (adding a tool, changing confirmation policy) touches `_Action`, `_prepare_action`, `_preview_action`, and a new `_execute_*` function plus the dispatch `if/elif` chain in `run_loop` (lines 1104-1175) — five edit sites per tool addition, increasing the chance of an inconsistent change (e.g. forgetting to update `untrusted_observation_seen` propagation for a new tool).
- Fix approach: Extract a tool-registry pattern (dict of tool name -> parse/preview/execute callables) so adding a tool is one registration instead of five scattered edits.

**Duplicated per-tool "error short-circuit" boilerplate:**
- Issue: Every `_execute_*` function in `src/olla/loop.py` (e.g. `_execute_read_file:707-709`, `_execute_list_dir:882-884`, `_execute_grep_files:905-907`, `_execute_fetch_url:929-931`) repeats the same `if action.error is not None: _record_observation(...); return False` guard.
- Files: `src/olla/loop.py:648-991`
- Impact: Low risk today (mechanical and consistent), but any future tool that forgets this guard would execute on already-invalid `_Action` state.
- Fix approach: Factor the guard into a decorator or a shared dispatch wrapper that checks `action.error` once before calling the tool-specific body.

**Root-level stray script outside the package/tests layout:**
- Issue: `test_connection.py` (tracked in git, 7.9K) lives at the repo root rather than under `tests/` or `src/olla/`, despite its `test_` prefix suggesting a pytest file; it is not collected by `pytest` (`testpaths = ["tests"]` in `pyproject.toml`) and appears to be a manual diagnostics script (commit message: "add test_connection.py script to verify API keys and models").
- Files: `test_connection.py`
- Impact: Confusing naming — looks like a test but isn't one; not covered by CI/lint scope definitions; risks accidental collection if `testpaths` is ever loosened.
- Fix approach: Rename to something like `scripts/check_connection.py` or move under a `scripts/` directory, and drop the `test_` prefix.

**Orphaned root `__pycache__` directory with no matching source:**
- Issue: `./__pycache__/test_fix.cpython-314.pyc`, `test_replace.cpython-314.pyc`, and `test_temp.cpython-314.pyc` exist with no corresponding `test_fix.py`/`test_replace.py`/`test_temp.py` source files anywhere in the repo (only `test_connection.cpython-314.pyc` has a live source).
- Files: `./__pycache__/`
- Impact: Harmless (already `.gitignore`d), but indicates ad hoc scratch scripts were created and deleted locally without cleanup; a minor sign of untracked exploratory work outside the git history.
- Fix approach: `rm -rf __pycache__` locally; no repo change needed since the directory is already ignored.

## Known Bugs

No reproducible bugs identified. The full test suite (431 tests across `tests/`) passes, and `ruff check src/ tests/` reports no issues as of this analysis.

## Security Considerations

**`fetch_url`/`search_web` have no host/scheme allowlist and execute unconfirmed:**
- Risk: `src/olla/tools/web.py` (`fetch_url`, `search_web`) accepts any model-supplied URL and fetches it via `httpx` with no restriction on scheme, host, or IP range. `src/olla/loop.py:_execute_fetch_url` (923-940) and `_execute_search_web` (943-960) invoke these tools directly with no `safety.check()` gate and no `Confirm.ask` prompt — this is a deliberate design choice (documented in `src/olla/prompts.py:21-27` as "runs immediately without asking for confirmation" and tracked as `WEB-01`..`WEB-04` in `.planning/REQUIREMENTS.md`), but it means a model (or content injected into a prior tool observation) can direct outbound requests to internal/link-local addresses (e.g. cloud metadata endpoints at `169.254.169.254`, or `localhost`-bound services like the Ollama server itself on `11434`) without any confirmation gate.
- Files: `src/olla/tools/web.py`, `src/olla/loop.py:923-960`
- Current mitigation: `WEB-04` (`.planning/REQUIREMENTS.md`) revokes `--yes` auto-bypass for *subsequent* destructive actions once any untrusted observation (including a web fetch) has been seen, and observations are wrapped in `<untrusted_web_content>` tags with an explicit system-prompt instruction not to follow embedded requests (`src/olla/prompts.py:7-9`). Output is truncated to 3,000 chars (`_truncate_to_sentence`) and response bodies are capped at 5MB (`_MAX_RESPONSE_BYTES`).
- Recommendations: Add an opt-in host/IP denylist (RFC 1918, loopback, link-local, and the Ollama server's own bind address) before dispatching `fetch_url`/`search_web` requests, or at minimum surface the resolved IP in the tool-call preview so a `--yes`-less user sees where the request is actually going.

**Shell safety gate is a blocklist, not an allowlist, for unknown binaries:**
- Risk: `src/olla/safety.py` classifies any binary not in `ALLOWLIST` (10 read-only commands) or `_HARD_BLOCKED_BINARIES` (6 binaries) as `CONFIRM` rather than `BLOCK`. This is intentional (per the module docstring and `D-04`: "yes does not change the gate decision; it only affects whether loop.py prompts"), but it means the safety net for a model going off-script relies entirely on the user reading and approving the `Confirm.ask("Proceed?")` prompt in `src/olla/loop.py:_execute_shell` (669-685) — there is no secondary technical control once a human approves.
- Files: `src/olla/safety.py`, `src/olla/loop.py:648-697`
- Current mitigation: Comprehensive blocklist covering `rm` dangerous targets, `dd`/`mkfs*` on raw block devices, fork bombs, `chmod`/`chown -R /`, and recursive unwrapping of `env`, `find -exec`, and `bash/sh/zsh -c` wrappers (`src/olla/safety.py:158-251`), all well covered by `tests/test_safety.py` (373 lines).
- Recommendations: None required for the stated threat model (human-in-the-loop confirm is the intended boundary); document this explicitly for users relying on `--yes` unattended runs, since `--yes` bypasses the `CONFIRM` prompt for anything not on the blocklist.

**`--yes` unattended mode trusts model output for any non-blocklisted command:**
- Risk: When `--yes` is passed, every shell command classified `CONFIRM` (i.e., everything except the 10-command read-only allowlist and the explicit blocklist) runs without a human prompt, as long as no untrusted observation has been seen yet in the run (`untrusted_observation_seen` gate in `src/olla/loop.py:669-676`). A small local model producing a plausible-looking but destructive command (e.g. `mv`, arbitrary `rm` of a non-dangerous-looking path, `curl | sh`-style download-and-execute if split across two shell calls) would execute unattended.
- Files: `src/olla/loop.py:648-697`, `src/olla/safety.py`
- Current mitigation: `untrusted_observation_seen` correctly revokes the `--yes` bypass once any file/shell/web/memory observation has been recorded, forcing a confirm prompt for the *next* action — this narrows the unattended-execution window to the very first action of a run.
- Recommendations: This is a documented tradeoff for the project's "small models, minimal overhead" goal; no change needed unless the project wants a stricter default (e.g. requiring `--yes` to also pass an explicit `--i-understand-the-risk` flag).

**Config file secrets loaded without permission checks:**
- Risk: `src/olla/config.py:load_config` reads `~/.config/olla/config.toml` (or legacy `~/.olla/config.toml`) which can contain `api_key` for remote providers (`src/olla/providers/__init__.py:33-39,65-71`), with no check on file permissions (e.g. world-readable config).
- Files: `src/olla/config.py`, `src/olla/providers/__init__.py`
- Current mitigation: `mask_secret` (`src/olla/debug.py:21-27`) prevents secrets from being printed in full in debug logs.
- Recommendations: Low priority for a single-user local CLI; consider warning if the config file's mode bits are group/world-readable.

## Performance Bottlenecks

No significant bottlenecks identified. The ReAct loop is inherently sequential (one model call per step, per `AGENTS.md`/stack decisions), and file/shell/web tools all have explicit size/time caps: `MAX_OBSERVATION_CHARS = 2000` (`src/olla/loop.py:37`), `_MAX_RESPONSE_BYTES = 5_000_000` and 3,000-char truncation for web content (`src/olla/tools/web.py:18,59-70`), a 30-second default shell timeout (`src/olla/tools/shell.py:8`), and a 50-entry cap on `list_dir` / 25-match cap on `grep_files` (`src/olla/tools/inspect.py:38,69`).

## Fragile Areas

**`write_file`'s atomic-replace path in `src/olla/tools/files.py` is intricate and platform-narrow:**
- Files: `src/olla/tools/files.py:249-677` (`_exchange_files`, `perform_write`)
- Why fragile: Overwriting an existing file uses `renameat2`/`RENAME_EXCHANGE` (Linux) or `renameatx_np`/`RENAME_SWAP` (macOS) via raw `ctypes.CDLL` calls (`_exchange_files:249-285`) to get a race-free atomic swap, with manual rollback logic if post-exchange verification fails (`perform_write:566-590`). `_validate_backend_support()` (`src/olla/tools/files.py:20-67`) runs at **import time** and raises `RuntimeError` if the runtime lacks `fcntl.flock`, `O_NOFOLLOW`/`O_DIRECTORY`, or `dir_fd` support — meaning the whole `olla` package fails to import on non-POSIX systems (e.g. native Windows) rather than degrading gracefully.
- Safe modification: Any change to `perform_write`, `_exchange_files`, or `_copy_and_verify_metadata` should be validated against the existing `tests/test_tools/test_files.py` (784 lines) before merging, since the race-condition and metadata-preservation guarantees are easy to silently break (e.g. reordering the `fstat`/`flock`/digest-verify sequence in `perform_write:405-597`).
- Test coverage: Strong (784-line test file specifically for this module), but the platform-specific `ctypes` FFI path (`_exchange_files`) is inherently harder to exercise across all target platforms (Linux vs. macOS syscall numbers) in a single CI run.

**Parser's positional/ordering-based tag disambiguation in `src/olla/parser.py`:**
- Files: `src/olla/parser.py:45-165`
- Why fragile: `parse_response` distinguishes valid single tool calls from malformed/duplicated ones purely through regex `.finditer()` position counting and nested nested branching (e.g. the special-cased `write_file`/`remember`/`recall` payload-opacity handling at lines 77-122, layered on top of the generic ordered-pair logic at lines 124-164). Small models are known to emit malformed tags (unbalanced, extra, or out-of-order), so this parser's correctness depends on exhaustive edge-case enumeration rather than a formal grammar.
- Safe modification: Change only via the existing 292-line `tests/test_parser.py`, adding a new test case for any new malformed-input scenario before touching the regex logic.
- Test coverage: Good relative to module size (292 test lines vs. 164 source lines), but any new special-cased tool (beyond `write_file`/`remember`/`recall`) will require re-verifying the payload-opacity branch at lines 77-122.

## Scaling Limits

**In-process, per-invocation memory only:**
- Current capacity: `Scratchpad` (`src/olla/tools/memory.py`) caps notes at `MAX_KEYS = 32`, `MAX_VALUE_CHARS = 2_000`, `MAX_TOTAL_CHARS = 16_000`, and exists only for the lifetime of one `run_loop()` call (`src/olla/loop.py:1046`) — there is no persistence across CLI invocations.
- Limit: Not a bug (the interactive REPL that would need cross-turn persistence is `REPL-02`, tracked as pending in `.planning/REQUIREMENTS.md`), but any workflow expecting memory to survive between separate `olla` invocations will silently lose it.
- Scaling path: `REPL-01`/`REPL-02`/`REPL-03` (`.planning/REQUIREMENTS.md`, Phase 7, status `pending`) are the planned path to multi-turn sessions with rolling context management.

**Fixed `num_ctx=8192` for local Ollama models:**
- Current capacity: `src/olla/loop.py:call_model` (514) and `src/olla/providers/ollama.py` (13,27,46) hardcode `num_ctx=8192` regardless of the model's actual supported context window.
- Limit: Models with larger native context (e.g. 32k+) are artificially capped; models that can't handle 8192 well may degrade. `MAX_OBSERVATION_CHARS = 2000` per tool observation is tuned against this fixed budget.
- Scaling path: Make `num_ctx` configurable via `config.toml`/CLI flag, or query the model's actual context window the way `OpenAICompatProvider.get_context_length()` (`src/olla/providers/openai_compat.py:83-104`) already does for remote providers.

## Dependencies at Risk

No dependencies currently at risk. Runtime dependencies (`ollama>=0.6.2`, `click>=8.1,<9`, `rich>=13`, `httpx>=0.27.0`, `tomli` for `<3.11` only) are all actively maintained with no known deprecation notices at analysis time. See `.planning/codebase/STACK.md` for full version detail if present.

## Missing Critical Features

**Interactive REPL not yet implemented:**
- Problem: `REPL-01`/`REPL-02`/`REPL-03` (`.planning/REQUIREMENTS.md`, Phase 7 "Interactive REPL Mode", status `pending` in `.planning/state.json`) are not built — `olla` currently only supports single-shot `TASK` invocations (`src/olla/cli.py:65-66` requires a `task` argument).
- Blocks: Any workflow needing a persistent multi-turn conversational session with retained `Scratchpad` state across turns.

**No per-tool allowlist / restricted-tool sessions:**
- Problem: `CLI-04` ("Per-tool allowlist (`--tools`/`-t`) to restrict a session to read-only tools") is listed under "Future Requirements" in `.planning/REQUIREMENTS.md` and not implemented — every `olla` invocation exposes all 9 tools (`shell`, `read_file`, `write_file`, `list_dir`, `grep_files`, `fetch_url`, `search_web`, `remember`, `recall`) with no way to run a read-only-only session.
- Blocks: Safer restricted-scope usage (e.g. "only let this model read and search, never write or run shell").

**No context/token usage indicator:**
- Problem: `CLI-05` ("Token/context usage indicator") is listed under "Future Requirements" and not implemented.
- Blocks: Users cannot see how close a long-running task is to the fixed `num_ctx=8192` budget before truncation/drift issues occur.

## Test Coverage Gaps

No significant gaps identified for the current feature set — every `src/olla/` module has a corresponding test file (`tests/test_*.py` or `tests/test_tools/test_*.py`), and the largest source module (`loop.py`, 1,178 lines) has by far the largest test file (`test_loop.py`, 2,913 lines). `ruff check` and the full 431-test suite both pass cleanly at analysis time.

**Platform-specific atomic-write path (`_exchange_files`) is harder to fully exercise:**
- What's not tested: The `renameat2`/`renameatx_np` `ctypes` FFI branch in `src/olla/tools/files.py:249-285` depends on the actual OS syscall being available; CI running on a single platform (e.g. Linux only) cannot directly exercise the macOS `renameatx_np` branch or the `NotImplementedError` fallback path for unsupported platforms in the same run.
- Files: `src/olla/tools/files.py:249-285`
- Risk: A regression in the macOS-specific branch could go undetected if CI only runs on Linux.
- Priority: Low (the project's own `_validate_backend_support` already refuses to run at all on unsupported platforms, narrowing the blast radius).

---

*Concerns audit: 2026-09-14*
