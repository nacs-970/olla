# Project Research Summary

**Project:** olla  
**Domain:** Lightweight web search, page fetching, file inspection, and REPL  
**Researched:** 2026-09-07 (Updated)  
**Confidence:** HIGH  

## Executive Summary

Milestone v1.1 expands `olla` with lightweight web intelligence, unprompted file inspection tools, and an interactive REPL mode.

Per user requirements, heavy browser automation (Playwright/Chromium) is completely dropped. Web access relies entirely on `curl` / `httpx` querying DuckDuckGo Lite (`lite.duckduckgo.com`) for web search, and fetching/stripping HTML text for page reads. This achieves zero new heavy dependencies, near-zero RAM footprint, and fast execution.

All web outputs are strictly bounded to 3,000 characters to prevent context window saturation, and untrusted web observation tracking ensures indirect prompt injection defenses remain active.

## Key Findings

### Recommended Stack

- `curl` / `httpx`: Zero-dependency web queries against DuckDuckGo Lite HTML and direct webpage content fetching.
- `html.parser` / regex: Fast extraction of search snippets and readable webpage text without external DOM libraries.
- `prompt_toolkit`: Terminal REPL loop supporting input history, multiline editing, and signal handling.
- `pathlib` / standard library: Safe directory and regex file search for unprompted inspection.

### Expected Features

**Must have (table stakes):**
- `search_web(query)`: DuckDuckGo Lite search returning top 3-5 snippet cards via curl/httpx.
- `fetch_url(url)`: Fast HTTP/curl page reader delivering cleaned text/markdown.
- `list_dir(path)` & `grep_files(pattern, path)`: Read-only inspection tools bypassing confirmation gates.
- `olla` interactive REPL: Multi-turn prompt loop with preserved scratchpad memory.

### Critical Pitfalls

1. **Context Window Saturation**: Never pass raw HTML to models. Clean and hard-truncate all web observations to <= 3,000 characters.
2. **Indirect Prompt Injection**: Web content cannot be trusted. Tag web observations and enforce human confirmation on subsequent shell or write actions.
3. **Network Timeouts**: Enforce 10s connect/read timeouts on all external requests.

## Implications for Roadmap

- **Phase 05: Safe Inspection Tools (`list_dir`, `grep_files`)** — Immediate low-risk win to unblock read-only code exploration without shell prompts.
- **Phase 06: Lightweight Web Search & Fetch (`search_web`, `fetch_url`)** — Zero-dependency curl/httpx DuckDuckGo Lite search and page reading.
- **Phase 07: Interactive REPL Mode (`olla`)** — Multi-turn conversation loop, persistent session scratchpad, and rolling context management.
