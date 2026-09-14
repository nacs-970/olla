# External Integrations

**Analysis Date:** 2026-09-14

## APIs & External Services

**LLM Providers:**
- Local Ollama server - primary/default model backend
  - SDK/Client: `ollama` Python package, `ollama.chat()` / streaming (`src/olla/providers/ollama.py`)
  - Auth: none (assumes local trusted daemon, typically `http://localhost:11434`)
  - Model selector: unprefixed model name or `ollama/<model>` prefix (`src/olla/providers/__init__.py:86-91`)
- OpenRouter - remote OpenAI-compatible model routing service
  - SDK/Client: raw `httpx` streaming HTTP calls to `{base_url}/chat/completions` and `{base_url}/models` (`src/olla/providers/openai_compat.py`)
  - Default base URL: `https://openrouter.ai/api/v1`
  - Auth: Bearer token via `OPENROUTER_API_KEY` env var, `--api-key` CLI flag, or `config.toml` (`src/olla/providers/__init__.py:22-52`)
  - Model selector: `openrouter/<model>` prefix
  - Sends attribution headers: `HTTP-Referer: https://github.com/olla/olla`, `X-Title: olla CLI Agent` (`src/olla/providers/openai_compat.py:120-123`)
- OpenAI (or OpenAI-compatible endpoint, e.g. self-hosted vLLM) - remote model backend
  - SDK/Client: same `httpx`-based `OpenAICompatProvider` as OpenRouter
  - Default base URL: `https://api.openai.com/v1`
  - Auth: Bearer token via `OPENAI_API_KEY` env var, `--api-key` CLI flag, or `config.toml` (`src/olla/providers/__init__.py:54-84`)
  - Model selector: `openai/<model>` prefix

**Web tools (untrusted external content):**
- DuckDuckGo Lite - web search, scraped via HTML parsing (no API key/official API)
  - Endpoint: `https://lite.duckduckgo.com/lite/` (`src/olla/tools/web.py:23`)
  - Client: `httpx.Client` with browser-spoofed `User-Agent`, capped read (5MB), custom `_DDGResultParser` (HTMLParser subclass) to extract organic (non-sponsored) results
  - Returns up to 5 results, truncated to 3000 chars (`WEB-01`/`WEB-03` requirements)
  - Bot-challenge detection: checks for `anomaly-modal` marker in response and raises a tool error if DuckDuckGo blocks the request
- Arbitrary URL fetch (`fetch_url` tool)
  - Client: `httpx.Client`, same headers/timeout/byte-cap as search, strips `<script>/<style>/<nav>/<header>/<footer>` via `_TextExtractor` (`src/olla/tools/web.py:189-215`)
  - No allowlist/domain restriction - the model can direct fetches to any URL

## Data Storage

**Databases:**
- None - no database, ORM, or persistent data store in the codebase

**File Storage:**
- Local filesystem only, via `olla`'s file tools (`src/olla/tools/files.py`: `read_file`, `write_file`) and inspection tools (`src/olla/tools/inspect.py`: `list_dir`, `grep_files`)
- Config file: `~/.config/olla/config.toml` (XDG) or legacy `~/.olla/config.toml`, read-only (no runtime writes observed)

**Caching:**
- None - no caching layer (each provider/context-length lookup is a live call, e.g. `OpenAICompatProvider.get_context_length()` caches only in-memory per-instance, `src/olla/providers/openai_compat.py:83-104`)

## Authentication & Identity

**Auth Provider:**
- None (no user auth system - this is a local single-user CLI tool)
- Remote-provider API keys (OpenRouter/OpenAI) function as service credentials, not user identity; resolved via CLI flag > env var > per-provider config table > legacy flat config key (`src/olla/providers/__init__.py`)
- Secrets are masked before logging via `mask_secret()` (`src/olla/debug.py`, used in `src/olla/cli.py:47`, `src/olla/loop.py:1027`, `src/olla/providers/openai_compat.py:145`)

## Monitoring & Observability

**Error Tracking:**
- None - no external error-tracking/APM service integrated

**Logs:**
- Local-only debug logging via `debug_log()` (`src/olla/debug.py`), gated behind `--debug` flag, `OLLA_DEBUG` env var, or `debug` config key
- No log shipping, no structured log aggregation

## CI/CD & Deployment

**Hosting:**
- None - not a hosted service; distributed as a pip-installable CLI package

**CI Pipeline:**
- None detected in-repo (no `.github/workflows/`, no other CI config found)

## Environment Configuration

**Required env vars:**
- None required for the default local-Ollama path (no API key needed)
- `OPENROUTER_API_KEY` - required only when using `openrouter/<model>` and no `--api-key`/config value is supplied
- `OPENAI_API_KEY` - required only when using `openai/<model>` and no `--api-key`/config value is supplied

**Optional env vars:**
- `OLLA_CONFIG` - custom config file path
- `OLLA_DEBUG` - enable debug logging
- `OPENROUTER_BASE_URL`, `OPENAI_BASE_URL` - override default provider endpoints
- `XDG_CONFIG_HOME` - relocate default config directory

**Secrets location:**
- User-supplied via `~/.config/olla/config.toml` (git-ignored by nature of being outside the repo), environment variables, or `--api-key` CLI flag
- No `.env` file or in-repo secrets file present in this repository (verified: no `.env*`, `*secret*`, or credential files found at repo root)

## Webhooks & Callbacks

**Incoming:**
- None - `olla` is a CLI tool with no server/listener component

**Outgoing:**
- None (no webhook dispatch); all outbound HTTP is synchronous request/response (chat completions, model listing, web search/fetch)

---

*Integration audit: 2026-09-14*
