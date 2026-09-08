# Phase 6: Lightweight Web Search & Fetch - Context

**Gathered:** 2026-09-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Add two network-facing tools — `search_web(query)` and `fetch_url(url)` — implemented via `httpx` (already a direct dependency), executing without a confirmation prompt. Both are new non-shell tool adapters under `src/olla/tools/`, dispatched from `src/olla/loop.py`, following the `list_dir`/`grep_files` unconfirmed-dispatch pattern (INSPECT-03/D-09 precedent) rather than the shell/`safety.check()` pattern. Their outputs must be tagged untrusted (WEB-04), reusing the existing `_record_*_observation` wiring in `loop.py`.

</domain>

<decisions>
## Implementation Decisions

### Confirmation dispatch
- **D-01:** `search_web`/`fetch_url` bypass `safety.check()` entirely and dispatch unconfirmed, same tier as `list_dir`/`grep_files` — `run_loop()` routes straight to their tool adapters. No new tool-name branch added to `src/olla/safety.py`. — **Reversibility:** costly — if a future requirement needs central ALLOW/CONFIRM/BLOCK policy over web tools, this needs `safety.check()` to grow a tool-name-aware signature and every call site revisited (same shape as Phase 5's D-09).

### URL safety (fetch_url)
- **D-02:** `fetch_url` applies no host or scheme restrictions — no SSRF guardrails (no blocking of localhost, private IP ranges, or the cloud metadata endpoint `169.254.169.254`), no scheme allowlist. Same trust posture as other unconfirmed tools. — **Reversibility:** reversible — a validation layer can be added later without breaking the tool's public contract. — **User confirmed deliberately** after the SSRF exposure was explicitly flagged (unconfirmed dispatch + arbitrary model-chosen URL could reach internal/metadata endpoints).

### fetch_url content extraction & truncation
- **D-03:** Boilerplate-aware extraction using stdlib `html.parser` (`HTMLParser` subclass) — always drop `script`, `style`, `nav`, `header`, `footer` tags before extracting text. No aggressive stripping of `aside`/`form`/`iframe`/`svg`/`noscript`.
- **D-04:** Truncation at WEB-03's 3,000-char cap trims back to the last sentence boundary (`.`, `!`, `?`) at or under the limit, not a hard mid-word/mid-sentence slice. Append a truncation note when cut (matches Phase 5 D-11's cap-note convention).

### search_web output format
- **D-05:** DuckDuckGo Lite results parsed via stdlib `html.parser`, not regex — consistent parsing approach with `fetch_url`'s extraction (D-03), more robust to markup than targeted regex.
- **D-06:** Snippet cards shown to the model as a numbered list, 3 lines each: `N. <title>` / `   <url>` / `   <summary>` — matches `list_dir`/`grep_files`' plain-text convention, easy for small models to reference by number.

### Claude's Discretion
- Exact wording of the truncation note for `fetch_url` (analogous to Phase 5's `(+N more, not shown)`).
- `httpx.Client` timeout value and retry/backoff policy for both tools (follow `src/olla/providers/openai_compat.py`'s existing `httpx.Client(timeout=...)` pattern; no user preference expressed).
- Internal helper structure for the `HTMLParser` subclass(es) — shared base between `search_web` and `fetch_url` parsing vs. separate implementations.
- Exact tag name for untrusted wrapping of web observations (e.g. `<untrusted_web_content>`), following the `<untrusted_file_content>`/`<untrusted_shell_output>`/`<untrusted_memory_content>` naming precedent in `src/olla/loop.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap & requirements
- `.planning/ROADMAP.md` — Phase 6 goal and success criteria (WEB-01..04)
- `.planning/REQUIREMENTS.md` — WEB-01, WEB-02, WEB-03, WEB-04 requirement text

### Codebase patterns to follow
- `src/olla/tools/base.py` — `ToolResult` contract, reuse for `search_web`/`fetch_url` returns
- `src/olla/tools/inspect.py` — Phase 5 precedent for unconfirmed-dispatch tool adapter shape (`list_dir`/`grep_files`); `search_web`/`fetch_url` follow the same shape
- `src/olla/loop.py` — `_record_file_observation`/`_record_memory_observation`/`_record_shell_observation` and the `untrusted_observation_seen` flag threading through `run_loop()`; a new `_record_web_observation`-style wiring is needed for WEB-04
- `src/olla/providers/openai_compat.py` — existing `httpx.Client(timeout=...)` usage and exception handling (`httpx.HTTPError`, `httpx.TimeoutException`, `httpx.TransportError`) to follow for `search_web`/`fetch_url`'s own HTTP calls
- `.planning/codebase/ARCHITECTURE.md` — "Bypassing the Policy Boundary" section; confirms `safety.check()` stays shell-argv-scoped, consistent with D-01
- `.planning/codebase/CONVENTIONS.md` — naming, typing, docstring, and import-order conventions for the new tool modules

No external specs beyond `.planning/REQUIREMENTS.md` — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolResult` (`src/olla/tools/base.py`) — reuse directly as the return contract for `search_web`/`fetch_url`.
- `httpx` is already a direct dependency (`pyproject.toml`) and already used via `httpx.Client(timeout=...)` in `src/olla/providers/openai_compat.py` — no new dependency needed for WEB-01/02 despite requirements' "curl/httpx" wording; `httpx.Client` is the natural fit, no need to shell out to a `curl` subprocess.
- `truncate_output()` (`src/olla/loop.py`) — existing loop-level head/tail truncation helper; WEB-03's 3,000-char cap (D-04) is a tool-level concern, separate from this but feeding the same `Observation:` pipeline.

### Established Patterns
- Tool adapters are thin, catch expected exceptions, and return typed dict variants (`{"error": ...}` on failure) rather than raising — `src/olla/tools/files.py` and `src/olla/tools/inspect.py` are the direct templates.
- `src/olla/loop.py` owns dispatch, confirmation, and observation formatting; adapters stay pure I/O. D-01 preserves this split.
- Untrusted-observation wrapping precedent: `_record_file_observation`/`_record_memory_observation`/`_record_shell_observation` in `loop.py` wrap content in `<untrusted_X_content>` tags and set `untrusted_observation_seen = True`, which later forces re-confirmation on a CONFIRM-tier action even under `--yes` (proven by Phase 5's gate-consequence tests). WEB-04 needs the same wiring for both `search_web` and `fetch_url` results.
- Module-private helpers prefixed with `_` (`safety.py`'s `_blocklist_match`, `_unwrap_env`) — apply the same convention to any HTML-parsing/extraction helpers.

### Integration Points
- `src/olla/loop.py` — add unconfirmed dispatch branches for `search_web`/`fetch_url` tool-call types (D-01), alongside the existing `list_dir`/`grep_files` branches; wire untrusted tagging (WEB-04).
- `src/olla/prompts.py` — document `search_web(query)` and `fetch_url(url)` tool contracts in `SYSTEM_PROMPT`.
- `src/olla/parser.py` — no change expected; tool dispatch is by tool name, args already parsed generically from `<args>`.

</code_context>

<specifics>
## Specific Ideas

No specific UI/output examples given beyond the decisions above — numbered-list snippet cards and boilerplate-stripped plain text apply throughout.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (SSRF guardrails were considered and explicitly declined — see D-02 — not deferred, decided.)

</deferred>

---

*Phase: 6-Lightweight Web Search & Fetch*
*Context gathered: 2026-09-09*
