# Architecture Research: Tools Expansion & Interactive REPL

**Domain:** ReAct loop dispatch, safety gating, and REPL architecture  
**Researched:** 2026-09-07  
**Confidence:** HIGH  

## System Architecture Overview

```
                        +--------------------------------+
                        |           olla CLI             |
                        +--------------------------------+
                                   |           |
                     [One-shot run]            [REPL mode (no args)]
                                   |           |
                                   v           v
                        +--------------------------------+
                        |     Interactive REPL Loop      |
                        |      (prompt_toolkit)          |
                        +--------------------------------+
                                       |
                                       v
                        +--------------------------------+
                        |        ReAct Loop Engine       |
                        |          (run_loop)            |
                        +--------------------------------+
                                       |
                   +-------------------+-------------------+
                   |                   |                   |
                   v                   v                   v
          +-----------------+ +-----------------+ +-----------------+
          |  File Tools     | |   Web Tools     | |   Exec Tools    |
          |  - read_file    | |  - search_web   | |  - shell        |
          |  - write_file   | |  - fetch_url    | +-----------------+
          |  - list_dir     | |  - browse_web   |
          |  - grep_files   | +-----------------+
          +-----------------+
                   |                   |                   |
                   +-------------------+-------------------+
                                       |
                                       v
                        +--------------------------------+
                        |      Safety Gate & Policy      |
                        |  - Read-only: ALLOW            |
                        |  - Destructive: CONFIRM        |
                        |  - Untrusted Flag (Injection)  |
                        +--------------------------------+
```

## Component Details

### 1. Web Tool Layer (`src/olla/tools/web.py`)
- `search_web(query)`: Queries DuckDuckGo via `ddgs`. Returns top 3-5 results formatted as markdown list:
  ```markdown
  1. [Title](url) - Snippet text...
  2. [Title](url) - Snippet text...
  ```
- `fetch_url(url)`: Performs `httpx.get(url, timeout=10.0, follow_redirects=True)` with custom User-Agent. Extracts readable text via `trafilatura`. Hard truncates at 3,000 characters.
- `browse_web(url, action)`: Optional tier. Launches Playwright Chromium with `--headless=shell` and image/font/CSS blocking. Extracts accessibility snapshot or `inner_text`. Truncates at 3,000 characters.

### 2. File Inspection Layer (`src/olla/tools/inspect.py`)
- `list_dir(path)`: Lists directory contents. Output includes item name, type (`[dir]` or `[file]`), and human-readable size. Capped at 50 items.
- `grep_files(pattern, path)`: Recursively searches text files under `path` matching regex `pattern`. Ignores `.git` and binary files. Capped at 25 matching lines.

### 3. Safety Integration
- Read-only tools (`search_web`, `fetch_url`, `browse_web`, `list_dir`, `grep_files`) are classified as `ALLOW` in `safety.check()` — requiring no confirmation prompt.
- Observation tagging: Any output originating from web tools (`search_web`, `fetch_url`, `browse_web`) is marked as `untrusted=True`. If an untrusted observation exists in the turn history, subsequent `shell` or `write_file` calls cannot be auto-approved with `--yes`, enforcing explicit human confirmation against indirect prompt injection.

### 4. REPL Session Engine (`src/olla/repl.py`)
- Invoked when `olla` is run with no positional prompt argument.
- Uses `prompt_toolkit.PromptSession` for command history and multiline input.
- Maintains a persistent `Scratchpad` across conversational turns.
- Automatically handles rolling context truncation to prevent exceeding model `num_ctx`.
