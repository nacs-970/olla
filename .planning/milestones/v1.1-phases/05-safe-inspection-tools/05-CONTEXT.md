# Phase 5: Safe Inspection Tools - Context

**Gathered:** 2026-09-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Add two read-only inspection tools — `list_dir(path)` and `grep_files(pattern, path, recursive=False)` — that execute without a confirmation prompt. Both are new non-shell tool adapters under `src/olla/tools/`, dispatched from `src/olla/loop.py`, following the existing `read_file`/`write_file` pattern rather than the shell/`safety.check()` pattern.

</domain>

<decisions>
## Implementation Decisions

### list_dir output format
- **D-01:** List a single directory level per call (no recursion). The model recurses by calling `list_dir` again on a subdirectory it wants to explore deeper.
- **D-02:** File sizes shown human-readable (`1.2K`, `3.4M`), matching `ls -lh` convention.
- **D-03:** Entries sorted alphabetically, directories first.
- **D-04:** Symlinks shown as their own type (`[l] name -> target`), never followed/resolved — avoids symlink loops and matches read-only intent.
- **D-05:** Hidden dotfiles (`.env`, `.git`, ...) are shown by default (`ls -a` behavior, not plain `ls`) — they count toward the 50-entry cap.

### grep_files matching semantics
- **D-06:** `grep_files(pattern, path, recursive=False)` — single directory by default; pass `recursive=True` in `<args>` to search subdirectories. New third parameter must be documented in `src/olla/prompts.py`.
- **D-07:** Pattern matching is case-sensitive (Python `re` default semantics, no surprise case-folding).
- **D-08:** Binary file detection via null-byte sniff on the first ~8KB of each candidate file (same heuristic grep/git use) — no file-extension allowlist to maintain. `.git` directory is excluded outright per INSPECT-02.

### Safety dispatch mechanism
- **D-09:** `list_dir`/`grep_files` bypass `safety.check()` entirely — `run_loop()` dispatches straight to their tool adapters, exactly like `read_file` today. No new tool-name branch is added to `src/olla/safety.py`; that module stays scoped to shell argv classification. — **Reversibility:** costly — if a future requirement needs central ALLOW/CONFIRM/BLOCK policy over non-shell tools, this decision would need `safety.check()` to grow a tool-name-aware signature and every existing call site to be revisited.
- **D-10:** No path pre-validation. Let `FileNotFoundError`/`NotADirectoryError` surface as a `ToolResult` error dict, matching the existing `read_file()`/`write_file()` convention in `src/olla/tools/files.py`.

### Truncation & cap behavior
- **D-11:** When results exceed the cap (50 entries for `list_dir`, 25 matches for `grep_files`), truncate and append a trailing note, e.g. `... (+12 more, not shown)`, so the model knows output was cut and can narrow its query.
- **D-12:** Entries/matches kept are the first N in natural scan order (`os.scandir`/`os.walk` order, then sorted per D-03 for `list_dir`) — no extra ranking pass across the full result set.

### Claude's Discretion
- Exact wording of the `(+N more)` truncation note.
- Internal helper structure for the null-byte binary sniff and `.git` exclusion (e.g., shared helper vs inline check) — implementation detail, no user preference expressed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap & requirements
- `.planning/ROADMAP.md` — Phase 5 goal and success criteria (INSPECT-01..03)
- `.planning/REQUIREMENTS.md` — INSPECT-01, INSPECT-02, INSPECT-03 requirement text

### Codebase patterns to follow
- `src/olla/tools/files.py` — pattern for tool adapter shape (`ToolResult` return, caught exceptions become `error` field) that `list_dir`/`grep_files` must follow
- `src/olla/tools/base.py` — shared `ToolResult` contract
- `src/olla/safety.py` — existing `ALLOW`/`CONFIRM`/`BLOCK` classification for shell argv; explicitly NOT extended by this phase (see D-09)
- `.planning/codebase/ARCHITECTURE.md` — "Bypassing the Policy Boundary" anti-pattern section; D-09 is a deliberate, scoped exception for non-shell read-only tools, not a precedent for shell dispatch
- `.planning/codebase/CONVENTIONS.md` — naming, typing, docstring, and import-order conventions to follow for the new tool modules

No external specs — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolResult` (`src/olla/tools/base.py`) — reuse directly as the return contract for `list_dir`/`grep_files`.
- `truncate_output()` (`src/olla/loop.py`) — existing head/tail truncation helper; D-11's cap note is a tool-level concern (separate from this loop-level output truncation) but both feed the same `Observation:` pipeline.

### Established Patterns
- Tool adapters are thin, catch expected exceptions, and return typed dict variants (`{"error": ...}` on failure) rather than raising — `src/olla/tools/files.py` is the direct template.
- `src/olla/loop.py` owns dispatch, confirmation, and observation formatting; adapters stay pure I/O. D-09 preserves this split — `list_dir`/`grep_files` get a new unconfirmed dispatch branch in `loop.py`, same tier as `read_file`.
- Module-private helpers are prefixed with `_` (see `src/olla/safety.py`'s `_blocklist_match`, `_unwrap_env`) — apply the same convention to any binary-sniff/`.git`-exclusion helpers.

### Integration Points
- `src/olla/loop.py` — add dispatch branches for `list_dir` and `grep_files` tool-call types, unconfirmed (no `Confirm.ask()` call), alongside the existing `read_file` branch.
- `src/olla/prompts.py` — document the two new tools' names/args (including `grep_files`'s new `recursive` param) in `SYSTEM_PROMPT` so models know how to call them.
- `src/olla/parser.py` — no change expected; tool dispatch is by tool name, and args are already parsed generically from `<args>`.

</code_context>

<specifics>
## Specific Ideas

No specific UI/output examples given beyond the decisions above — standard `ls -la`-like conventions apply throughout.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 5-Safe Inspection Tools*
*Context gathered: 2026-09-08*
