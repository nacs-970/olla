# Features Research: Tools Expansion & Interactive REPL

**Domain:** Agent tool capabilities & REPL UX  
**Researched:** 2026-09-07  
**Confidence:** HIGH  

## Feature Breakdown

### Table Stakes

| Feature | User Value | Complexity | Small-Model Constraint |
|---------|------------|------------|------------------------|
| `search_web(query)` | Retrieve current web information | Low | Cap at 5 results; truncate each snippet to 200 chars. Total payload < 1,500 chars. |
| `fetch_url(url)` | Read webpage contents as markdown | Low | Strip navigation/boilerplate; truncate to 3,000 chars. |
| `list_dir(path)` | Inspect directory hierarchy without shell gating | Low | List up to 50 items with type (`[d]`/`[f]`) and size; avoid infinite tree walks. |
| `grep_files(pattern, path)` | Find code occurrences across files without shell gating | Medium | Respect `.gitignore`, cap matches at 25 lines with filename and line numbers. |
| Interactive REPL | Continuous multi-turn dialogue | Medium | Keep conversation rolling window within model `num_ctx`; maintain scratchpad memory across turns. |

### Differentiators

| Feature | Description | Complexity | Value Add |
|---------|-------------|------------|-----------|
| **Tiered Web Fetching** | Fast HTTP reader (`fetch_url`) is default; `browse_web` only when JS/DOM interaction requested | Medium | 90% of requests run in <100ms with zero browser RAM overhead. |
| **Lightweight Headless Engine** | Playwright with `--headless=shell` and image/font/CSS blocking | High | Enables JS rendering in <80MB RAM on resource-constrained laptops. |
| **Unprompted Read-Only Tools** | `list_dir`, `grep_files`, `search_web`, `fetch_url` bypass Confirm prompts | Low | Fluid investigation without repetitive user confirmation prompts. |
| **Indirect Injection Protection** | Web observations automatically mark observation state as untrusted | Medium | Revokes `--yes` confirmation bypass for destructive actions following web reads. |

### Anti-Features (What We Avoid)
- **Full DOM dumps**: Never output raw HTML or full DOM trees to the model.
- **Persistent browser daemon**: Do not keep browser running in the background indefinitely; close or idle-timeout browser contexts to reclaim RAM.
- **Unbounded file searching**: Prevent grep/list tools from walking virtual mounts (`/proc`, `/sys`) or enormous `node_modules` without depth/entry bounds.
