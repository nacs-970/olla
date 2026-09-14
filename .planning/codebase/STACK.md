# Technology Stack

**Analysis Date:** 2026-09-14

## Languages

**Primary:**
- Python >=3.10 (per `pyproject.toml` `requires-python`) - entire codebase (`src/olla/`, `tests/`)

**Secondary:**
- TOML - configuration file format (`~/.config/olla/config.toml`), parsed via `config.py`

## Runtime

**Environment:**
- CPython >=3.10 (project targets 3.10+; dev/CI environment observed running 3.14, per compiled `__pycache__/*.cpython-314.pyc` artifacts)
- Uses stdlib `tomllib` on Python >=3.11; falls back to the `tomli` backport on 3.10 (`src/olla/config.py:7-10`)

**Package Manager:**
- `uv` (evidenced by `uv.lock` at repo root, 72KB lockfile)
- `pip` also supported directly (README installs via `python -m pip install .`)
- Lockfile: present (`uv.lock`)

## Frameworks

**Core:**
- `click` >=8.1,<9 - CLI argument parsing and entry point (`src/olla/cli.py`)
- `ollama` >=0.6.2 (official Python client) - talks to local Ollama server for `chat()`/`generate()`/streaming (`src/olla/providers/ollama.py`)
- `httpx` >=0.27.0 - HTTP client used for OpenAI-compatible remote providers and web tools (`src/olla/providers/openai_compat.py`, `src/olla/tools/web.py`)
- `rich` >=13 - terminal output styling and confirm prompts (`src/olla/loop.py` uses `rich.prompt.Confirm`, `rich.text.Text`)

**Testing:**
- `pytest` >=8 - test runner (`tests/`, config in `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]`)
- `pytest-mock` >=3.14 - mocking convenience fixture, used to mock `ollama.chat`/`httpx` calls in tests

**Build/Dev:**
- `hatchling` - build backend (`[build-system]` in `pyproject.toml`)
- `ruff` - linting (declared as a `dev` optional dependency; no `[tool.ruff]` configuration section present in `pyproject.toml`, so defaults apply)

## Key Dependencies

**Critical:**
- `ollama` >=0.6.2 - primary local-model integration; the entire ReAct loop depends on its `chat()`/`stream_chat()` behavior (`src/olla/providers/ollama.py`)
- `httpx` >=0.27.0 - transitively required by `ollama` and directly used for remote OpenAI-compatible providers and the web-fetch/search tools
- `click` >=8.1,<9 - defines the whole CLI surface (`olla` console-script entry point maps to `olla.cli:main`)

**Infrastructure:**
- `tomli` >=1.1.0 (conditional: `python_version < '3.11'`) - TOML config parsing backport for Python 3.10
- `pydantic` / `pydantic-core` - transitive dependencies pulled in by the `ollama` client (not used directly in project code; no Pydantic models written in `olla`'s own source, per `uv.lock`)

## Configuration

**Environment:**
- `OLLA_CONFIG` - overrides the config file path (`src/olla/config.py:26-29`)
- `OLLA_DEBUG` - enables debug logging when set to `1`/`true`/`yes` (`src/olla/cli.py:36`)
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` - OpenRouter provider credentials/endpoint override (`src/olla/providers/__init__.py:27,35`)
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` - OpenAI-compatible provider credentials/endpoint override (`src/olla/providers/__init__.py:59,67`)
- `XDG_CONFIG_HOME` - honored for the default config path resolution (`src/olla/config.py:15-17`)

**Config file resolution order** (`src/olla/config.py`, `find_config_path`):
1. `--config`/explicit custom path (if passed)
2. `OLLA_CONFIG` env var
3. `$XDG_CONFIG_HOME/olla/config.toml` (or `~/.config/olla/config.toml` if unset)
4. Legacy fallback: `~/.olla/config.toml`
5. Returns `{}` if none found (no hard failure)

**Config keys read (from TOML or env, layered with CLI flags taking priority):**
- `default_model` / `model`, `api_key`, `base_url`, `debug`
- Provider-scoped tables: `[openrouter]` (`base_url`, `api_key`), `[openai]` (`base_url`, `api_key`)
- Legacy flat keys also supported: `openrouter_base_url`, `openrouter_api_key`, `openai_base_url`, `openai_api_key`

**Build:**
- `pyproject.toml` - single source of build/dependency/tooling configuration; no separate `setup.py`/`setup.cfg`
- `[tool.hatch.build.targets.wheel]` packages `src/olla`

## Platform Requirements

**Development:**
- POSIX operating system only (`classifiers = ["Operating System :: POSIX"]` in `pyproject.toml`) - not intended for Windows
- A running local Ollama installation with at least one model pulled (for local-model workflows)
- Python virtualenv (`python -m venv .venv`) per README

**Production:**
- No server/deployment target - `olla` is a local CLI tool installed via `pip install .`, invoked as the `olla` console script
- Optional remote model providers (OpenRouter, OpenAI-compatible APIs) require network access and an API key

---

*Stack analysis: 2026-09-14*
