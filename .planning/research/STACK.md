# Stack Research: Lightweight Web & Inspection Tools

**Domain:** CLI agent tools & lightweight web access  
**Researched:** 2026-09-07 (Updated)  
**Confidence:** HIGH  

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `curl` / `httpx` | system `curl` / `httpx>=0.27.0` (existing) | Web search & page fetching | Zero new package dependencies. Uses DuckDuckGo Lite HTML endpoint for instant, JS-free search results. |
| Python standard library (`html.parser`, `re`, `urllib`) | standard library | DDG Lite HTML extraction & boilerplate stripping | Lightweight, zero-dependency HTML parsing for titles, links, and snippets. |
| `prompt_toolkit` | ^3.0.40 | Interactive REPL interface | Clean multiline editing, command history, and responsive signal handling. |
| `pathlib` + `os` | standard library | Safe directory inspection (`list_dir`) | Fast POSIX path navigation without shell confirm prompts. |
| `re` + `fnmatch` | standard library | In-file regex search (`grep_files`) | Fast local scanning without spawning external grep processes. |

## What NOT to Use
- **Playwright / Puppeteer / Selenium**: Dropped to avoid heavy binary downloads, Chromium memory overhead (~300-500MB), and host OOM risks.
- **Heavy search client packages (`ddgs`)**: Not needed; DDG Lite HTML provides structured text with simple HTTP/curl queries.
- **Raw HTML passed to LLM**: Always clean and strip tags down to readable plain text or markdown before returning observations.
