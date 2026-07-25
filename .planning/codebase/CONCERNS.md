# Codebase Concerns

**Analysis Date:** 2026-07-25

## Tech Debt

**ReAct loop duplicates tool orchestration:**
- Issue: Shell, `read_file`, and `write_file` repeat signature tracking, repetition checks, result normalization, printing, and observation construction inside one 233-line function.
- Files: `src/olla/loop.py`
- Impact: Every new tool requires edits across dry-run and normal dispatch branches, making safety and behavior drift likely.
- Fix approach: Extract a shared tool-call pipeline and handler registry while preserving shell-specific safety and write-specific confirmation policies.

**Phase 3 validation state is inconsistent:**
- Issue: UAT is marked `testing`, step 4 is blocked, seven tests are skipped, and failed gap records coexist with a completed gap-closure plan.
- Files: `.planning/phases/03-file-tools/03-UAT.md`, `.planning/phases/03-file-tools/03-04-PLAN.md`
- Impact: File-tool unit coverage is strong, but release confidence for the real small-model workflow is unresolved.
- Fix approach: Re-run the full UAT after the prompt/error-message changes and reconcile the UAT totals and gap statuses.

## Known Bugs

**Default pytest collection fails:**
- Symptoms: `.venv/bin/pytest -q` stops during collection with syntax/import errors, while `.venv/bin/pytest tests -q` passes 151 tests.
- Files: `test_fix.py`, `test_replace.py`, `test_temp.py`, `pyproject.toml`, `tests/`
- Trigger: Run pytest from the repository root without an explicit test path.
- Workaround: Run `.venv/bin/pytest tests`; quarantine/remove invalid root artifacts and configure `testpaths = ["tests"]`.

**NUL-containing write path crashes before tool error handling:**
- Symptoms: A `write_file` call whose path contains `\x00` raises `ValueError` from `Path.resolve()` and terminates the loop.
- Files: `src/olla/loop.py`, `src/olla/tools/files.py`, `tests/test_tools/test_files.py`
- Trigger: Model output contains a NUL in the first `write_file` argument line.
- Workaround: Validate/resolve paths inside a caught helper before confirmation; add an end-to-end loop regression test.

**Empty write path produces a misleading target:**
- Symptoms: An empty first line resolves to the repository working directory and can display a write confirmation for a directory.
- Files: `src/olla/loop.py`, `src/olla/tools/files.py`, `.planning/phases/03-file-tools/03-VERIFICATION.md`
- Trigger: Model emits `<args>\ncontent</args>` for `write_file`.
- Workaround: Reject empty or whitespace-only paths before `Path.resolve()` and before confirmation.

**Model and subprocess failures escape as tracebacks:**
- Symptoms: Ollama connection/OOM errors and subprocess errors other than missing executable/timeout are not converted to observations or CLI diagnostics.
- Files: `src/olla/loop.py`, `src/olla/smoke.py`, `src/olla/tools/shell.py`
- Trigger: Ollama is unavailable or killed, or process launch raises `PermissionError`/another `OSError`.
- Workaround: Catch SDK and process-boundary exceptions, print concise diagnostics, and preserve nonzero CLI exit status.

**Parser precedence can discard valid output:**
- Symptoms: A response containing both `write_file` and `<final>` is treated only as a write; uppercase `WRITE_FILE` bypasses the verbatim-content special case.
- Files: `src/olla/parser.py`, `.planning/phases/03-file-tools/03-VERIFICATION.md`
- Trigger: Mixed tag blocks or case-varied tool names in model output.
- Workaround: Normalize tool names, enforce one-block parsing, and define deterministic mixed-block rejection.

## Security Considerations

**Blocklist is bypassable when confirmation is disabled:**
- Risk: Confirmed variants such as `/bin/rm -rf /`, `rm -rf /.`, `env -S "sudo rm -rf /"`, chained `bash -c` content, `/dev/vda`, and `/dev/mmcblk0` classify as `CONFIRM`; `--yes` then executes them unattended.
- Files: `src/olla/safety.py`, `src/olla/loop.py`, `tests/test_safety.py`, `.planning/phases/02-safety-gate-loop-control/02-SECURITY.md`
- Current mitigation: Exact-pattern blocking plus interactive confirmation; project documentation defines the blocklist as a speed bump.
- Recommendations: Treat `--yes` as privileged, normalize executable paths, expand device/root equivalence checks, and prefer an execution allowlist or OS sandbox.

**Filesystem access is unrestricted:**
- Risk: `read_file` can read any accessible UTF-8 file without confirmation, and `write_file --yes` can overwrite any writable path.
- Files: `src/olla/tools/files.py`, `src/olla/loop.py`, `src/olla/prompts.py`
- Current mitigation: Write confirmation shows a resolved path unless `--yes`; reads have no path boundary.
- Recommendations: Add an optional project-root boundary, deny sensitive path classes by default, and require explicit opt-in for paths outside the workspace.

**Write confirmation has a symlink race:**
- Risk: The resolved target shown to the user can change before `Path.write_text()` follows the original path.
- Files: `src/olla/loop.py`, `src/olla/tools/files.py`
- Current mitigation: Path resolution improves disclosure but does not bind the confirmed inode to the write.
- Recommendations: Revalidate immediately before write, reject symlinks where appropriate, and use safe descriptor-based/atomic replacement.

## Performance Bottlenecks

**Truncation happens after full buffering:**
- Problem: Shell stdout/stderr and files are fully loaded into memory before the 2,000-character preview is created.
- Files: `src/olla/tools/shell.py`, `src/olla/tools/files.py`, `src/olla/loop.py`
- Cause: `capture_output=True` and `Path.read_text()` are unbounded.
- Improvement path: Stream or cap reads at the boundary while retaining useful head/tail diagnostics.

**Conversation history is not token-budgeted:**
- Problem: Parsed tool responses, especially `write_file` content, remain in full assistant history even though the model context is fixed at 8,192 tokens.
- Files: `src/olla/loop.py`, `src/olla/parser.py`
- Cause: Only tool observations and unparseable responses are character-truncated.
- Improvement path: Track approximate tokens and compact old/tool payload messages before every model call.

## Fragile Areas

**Regex protocol is model-sensitive:**
- Files: `src/olla/parser.py`, `src/olla/prompts.py`, `src/olla/smoke.py`
- Why fragile: Literal `</args>` truncates file content, multiple blocks pair by first regex match, and format compliance depends on small-model prompting.
- Safe modification: Change parser, stop sequences, prompt examples, and smoke classifications together.
- Test coverage: Parser unit tests exist, but the target 0.6B-4B model matrix remains empirically incomplete in `.planning/phases/01-core-loop-shell-tool-cli/01-AUDIT.md`.

**File writes are destructive and non-atomic:**
- Files: `src/olla/tools/files.py`, `src/olla/loop.py`
- Why fragile: `Path.write_text()` truncates the destination directly; interruption or partial I/O can damage the original with no backup.
- Safe modification: Write to a sibling temporary file, flush, then atomically replace after revalidation.
- Test coverage: `tests/test_tools/test_files.py` covers success/basic errors but not interrupted writes, symlinks, permissions, or atomicity.

## Scaling Limits

**Single-process task execution:**
- Current capacity: One synchronous Ollama request or tool execution at a time, default 15 steps and 30 seconds per shell call.
- Limit: Long model/tool calls block the CLI; timeout handling does not manage descendant process groups.
- Scaling path: Keep the sequential ReAct semantics but add cancellation, process-group cleanup, and configurable bounded timeouts in `src/olla/loop.py` and `src/olla/tools/shell.py`.

## Dependencies at Risk

**Open-ended runtime dependency ranges:**
- Risk: `ollama>=0.6.2` and `rich>=13` permit future breaking major releases for normal pip installs.
- Impact: SDK response shape, `think=` support, or prompt APIs can break `src/olla/loop.py` and `src/olla/smoke.py`.
- Migration plan: Add compatible upper bounds or CI against minimum/latest versions in `pyproject.toml`; keep `uv.lock` refreshed deliberately.

## Missing Critical Features

**Scratchpad memory is absent:**
- Problem: The active v1 requirement for `remember(key, value)` has no implementation.
- Blocks: Cross-turn fact persistence and Phase 4 completion in `.planning/ROADMAP.md`; no memory module exists under `src/olla/`.

**Small-model fallback format is absent:**
- Problem: XML compliance is not validated across the stated smallest models and no fallback protocol exists below the 80% threshold.
- Blocks: Reliable operation on the core 0.6B-4B audience described in `.planning/PROJECT.md` and `.planning/phases/01-core-loop-shell-tool-cli/01-AUDIT.md`.

## Test Coverage Gaps

**Real boundary failures:**
- What's not tested: Ollama unavailable/OOM responses, unexpected SDK shapes, subprocess permission/encoding failures, process descendants after timeout.
- Files: `src/olla/loop.py`, `src/olla/smoke.py`, `src/olla/tools/shell.py`, `tests/test_loop.py`, `tests/test_tools/test_shell.py`
- Risk: Common runtime failures terminate the CLI or leave work running.
- Priority: High

**Filesystem adversarial cases:**
- What's not tested: Loop-level NUL paths, empty paths, symlink swaps, sensitive/out-of-root reads, huge files, and atomic-write failure.
- Files: `src/olla/loop.py`, `src/olla/tools/files.py`, `tests/test_loop.py`, `tests/test_tools/test_files.py`
- Risk: Crashes, misleading approval, unintended target access, memory pressure, or file corruption.
- Priority: High

**End-to-end model behavior:**
- What's not tested: The complete read-modify-write UAT and smoke matrix on the target small models.
- Files: `.planning/phases/03-file-tools/03-UAT.md`, `.planning/phases/01-core-loop-shell-tool-cli/01-AUDIT.md`, `src/olla/prompts.py`
- Risk: Unit tests pass while the intended user workflow remains unreliable.
- Priority: High

---

*Concerns audit: 2026-07-25*
