# Stack Research: Web Search, Browsing, and Inspection Tools

**Domain:** CLI agent tools & lightweight browser automation  
**Researched:** 2026-09-07  
**Confidence:** HIGH  

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `ddgs` (duckduckgo_search) | ^7.0.0 | Web search queries | No API key required, fast JSON results (title, href, snippet), zero daemon overhead. |
| `httpx` | >=0.27.0 (existing) | Fast HTTP web fetching | Already a dependency in olla; supports sync/async requests, timeouts, and redirect handling. |
| `trafilatura` | ^2.0.0 | HTML text/markdown extraction | High-precision boilerplate removal (ads, navigation, footers); lightweight compared to full DOM parsers. |
| `playwright` | ^1.45.0 (optional) | Headless browser execution | Ships with `chromium-headless-shell`; supports route request abortion for images/fonts/css; robust JS execution. |
| `prompt_toolkit` | ^3.0.40 | Interactive REPL interface | Industry standard for Python interactive CLIs; history navigation, multiline editing, clean signal handling. |

### Supporting / Standard Library

| Module | Purpose | Notes |
|--------|---------|-------|
| `pathlib` + `os` | Directory inspection (`list_dir`) | Standard library, zero dependency, fast POSIX/Windows path handling. |
| `re` + `fnmatch` | In-file regex search (`grep_files`) | Fast local scanning without invoking external `grep` subprocess. |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `ddgs` | Google Custom Search / Tavily / Bing | When official paid API guarantees are required; undesirable for olla's zero-config local philosophy. |
| `trafilatura` | `beautifulsoup4` + `markdownify` | When custom DOM tag filtering is needed; `trafilatura` is better at automated boilerplate extraction. |
| `playwright` (headless-shell) | `selenium` / raw Puppeteer | Selenium is heavier and requires separate chromedriver installs; Playwright manages headless shell cleanly. |
| `prompt_toolkit` | built-in `cmd` / `readline` | `readline` has platform quirks on Windows and lacks multiline editing or modern styling. |

## What NOT to Use
- **LangChain / CrewAI web tools**: Massive dependency graph, opinionated abstractions, high memory footprint.
- **Full Chromium desktop browser**: Avoid default desktop headless mode; consumes 300-500MB RAM. Use `chromium-headless-shell` with asset blocking.
- **Raw HTML passing to LLM**: Never feed raw HTML into 2-4B models; destroys token limits and confuses reasoning.
