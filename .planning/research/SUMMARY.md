# Project Research Summary

**Project:** olla  
**Domain:** Agent tool capabilities, web browsing, inspection, and REPL  
**Researched:** 2026-09-07  
**Confidence:** HIGH  

## Executive Summary

Milestone v1.1 expands `olla` from an offline shell/file manipulation loop into an agent capable of gathering online intelligence, safely inspecting files without confirmation fatigue, and maintaining interactive sessions across multiple conversational turns.

To succeed on small local models (0.6B-7B) on resource-constrained hardware (7.1GB RAM), web capabilities must follow a strict tiered approach: zero-key DuckDuckGo search queries returning concise snippet cards, fast HTTP HTML-to-markdown text extraction via `trafilatura` for 90% of reading tasks, and an optional stripped-down Playwright `chromium-headless-shell` with heavy assets blocked (images/fonts/css) to keep memory footprint under 80MB.

All web outputs are strictly bounded to prevent context window saturation, and untrusted observations automatically trigger indirect prompt injection safeguards before any destructive action can execute.

## Key Findings

### Recommended Stack

- `ddgs` (^7.0.0): Zero-config DuckDuckGo search returning top titles, links, and snippets without requiring API keys.
- `trafilatura` (^2.0.0): Industry-standard HTML text and article extraction that removes navigation headers, footers, and sidebars.
- `playwright` (^1.45.0): Headless browser integration with `chromium-headless-shell`, request abortion for media/CSS, and accessibility snapshots.
- `prompt_toolkit` (^3.0.40): Clean terminal REPL loop supporting input history, multiline editing, and responsive signal handling.
- `pathlib` / standard library: Safe directory and regex file search for unprompted inspection.

### Expected Features

**Must have (table stakes):**
- `search_web(query)`: Top 3-5 snippet search results, strictly character-capped.
- `fetch_url(url)`: Fast HTTP reader delivering cleaned, readable markdown.
- `list_dir(path)` & `grep_files(pattern, path)`: Read-only inspection tools bypassing confirmation gates.
- `olla` interactive REPL: Multi-turn prompt loop with preserved scratchpad memory.

**Should have (competitive):**
- `browse_web(url, action)`: Lightweight headless browser for dynamic JavaScript pages.
- Indirect prompt injection defense: untrusted web observation tracking revoking `--yes` bypass.

### Architecture Approach

The architecture retains the proven single ReAct execution engine in `run_loop`. Tools are grouped cleanly into:
1. `olla.tools.web`: `search_web`, `fetch_url`, optional `browse_web`
2. `olla.tools.inspect`: `list_dir`, `grep_files`
3. `olla.tools.files`: `read_file`, `write_file`
4. `olla.tools.shell`: `run_shell`
5. `olla.tools.memory`: `remember`, `recall`

Read-only tools are designated `ALLOW` in `safety.check()`, eliminating confirmation prompt friction.

### Critical Pitfalls

1. **Host RAM OOM**: Avoid full desktop Chromium. Use `chromium-headless-shell` with image/font/CSS blocking.
2. **Context Window Saturation**: Never pass raw HTML to models. Clean and hard-truncate all web observations to <= 3,000 characters.
3. **Indirect Prompt Injection**: Web content cannot be trusted. Tag web observations and enforce human confirmation on subsequent shell or write actions.
4. **Hanging Network Requests**: Enforce 10s connect/read timeouts on all external requests.

## Implications for Roadmap

- **Phase 05: Safe Inspection Tools (`list_dir`, `grep_files`)** — Immediate low-risk win to unblock read-only code exploration without shell prompts.
- **Phase 06: Web Search & Fast Content Reader (`search_web`, `fetch_url`)** — Zero-browser web intelligence with DDGS and Trafilatura.
- **Phase 07: Lightweight Headless Browser (`browse_web`)** — Playwright headless shell integration with asset blocking and context safety.
- **Phase 08: Interactive REPL Mode (`olla`)** — Multi-turn conversation loop, persistent session scratchpad, and rolling context management.

## Sources
- Playwright documentation on `chromium-headless-shell` and route abort optimization.
- DuckDuckGo Search (`ddgs`) Python library specification.
- Trafilatura documentation for HTML-to-text extraction.
- Prompt Toolkit documentation for interactive CLI session handling.
