# Technology Stack

**Analysis Date:** 2026-07-25

## Languages

**Primary:**
- Python >=3.10 - All installable application code, CLI behavior, tool implementations, and tests live under `src/olla/` and `tests/`; the supported floor is declared in `pyproject.toml`.
- The repository does not pin a specific Python minor release. The checked-out development environment currently uses Python 3.14.6, while compatibility must remain at the `pyproject.toml` floor of Python 3.10.

**Secondary:**
- TOML - Package metadata, dependency declarations, build configuration, and the resolver lock are in `pyproject.toml` and `uv.lock`.
- Bash - `read_and_replace.sh` is an untracked, repository-root auxiliary script and is not part of the packaged `olla` runtime.
- Markdown/JSON - Project planning and workflow state are maintained under `.planning/`; these files do not execute in the application runtime.

## Runtime

**Environment:**
- CPython >=3.10, declared by `requires-python = ">=3.10"` in `pyproject.toml`.
- The application is a synchronous, one-shot command-line process. `src/olla/cli.py` enters `src/olla/loop.py`, performs sequential model/tool turns, and exits after a final response or the configured step limit.
- A separately running Ollama server and at least one locally available model are operational runtime requirements for every non-mocked model call in `src/olla/loop.py`.

**Package Manager:**
- uv - `uv.lock` is present and locks the complete runtime/dev dependency graph. The repository does not pin the uv executable version; the current workstation has uv 0.11.31.
- Lockfile: present at `uv.lock` (format version 1, revision 3).
- Use the versions resolved in `uv.lock` for reproducible development. Do not infer the environment from the currently installed `.venv/`, which is ignored by `.gitignore` and can lag behind the lock.

## Frameworks

**Core:**
- Click 8.4.1 locked - Decorator-based CLI parsing, positional task input, and `--model`, `--dry-run`, `--max-steps`, `--yes`, and `--smoke-test` flags in `src/olla/cli.py`.
- No web, API-server, ORM, agent orchestration, or UI framework is used. The ReAct loop is implemented directly in `src/olla/loop.py`, with the protocol prompt in `src/olla/prompts.py` and parser in `src/olla/parser.py`.

**Testing:**
- pytest 9.1.0 locked - Test runner for the suite under `tests/`.
- pytest-mock 3.15.1 locked - Mocking support, especially for isolating `ollama.chat` calls exercised through `src/olla/loop.py`.

**Build/Dev:**
- Hatchling, version not pinned - PEP 517 build backend declared in `pyproject.toml`; builds the `src/olla` package into wheels/sdists.
- Ruff 0.15.17 locked - Development linting/formatting dependency declared in the `dev` extra in `pyproject.toml`. No repository-specific Ruff rules are configured.
- uv, version not pinned - Environment creation, dependency synchronization, and command execution are represented by `uv.lock`; uv is a development tool rather than a project dependency.

## Key Dependencies

**Critical:**
- `ollama` 0.6.2 locked (`>=0.6.2` declared) - Official Python client used by `src/olla/loop.py` to send synchronous chat requests to the Ollama service.
- `click` 8.4.1 locked (`>=8.1,<9` declared) - Defines the public `olla` command in `src/olla/cli.py`; the console-script mapping is declared in `pyproject.toml`.
- `rich` 15.0.0 locked (`>=13` declared) - Supplies `rich.prompt.Confirm` for shell and file-write approval gates in `src/olla/loop.py`.

**Infrastructure:**
- `httpx` 0.28.1 locked - Transitive transport used by `ollama`; application code does not call `httpx` directly. The dependency chain is recorded in `uv.lock`.
- `pydantic` 2.13.4 locked - Transitive Ollama response-model dependency; application-owned structured results use `typing.TypedDict` in `src/olla/tools/base.py`, not Pydantic models.
- Python standard library - `pathlib` provides UTF-8 filesystem access in `src/olla/tools/files.py`; `subprocess` runs argv without a shell in `src/olla/tools/shell.py`; `shlex` tokenizes commands in `src/olla/loop.py`; `re` implements response parsing in `src/olla/parser.py` and smoke classification in `src/olla/smoke.py`.

## Configuration

**Environment:**
- Application behavior is configured through command-line arguments in `src/olla/cli.py`; no application configuration file or `.env` file is present.
- `--model` is mandatory and is forwarded unchanged from `src/olla/cli.py` to `ollama.chat()` in `src/olla/loop.py`; there is no hardcoded model default.
- `--max-steps` defaults to 15, `--yes` bypasses confirmation prompts allowed by policy, `--dry-run` executes one model call without tools, and `--smoke-test` checks model output-format compliance in `src/olla/smoke.py`.
- Every chat call in `src/olla/loop.py` sets stop sequences to `</args>` and `Observation:`, sets `num_ctx` to 8192, and passes an explicit `think` boolean.
- The top-level Ollama SDK client can honor `OLLAMA_HOST` and `OLLAMA_API_KEY`, but the application does not read, validate, or document these variables itself. No environment variables are required by `src/olla/`.

**Build:**
- `pyproject.toml` contains the PEP 621 project metadata, Hatchling backend, runtime/dev dependencies, console script, and `src/olla` wheel target.
- `uv.lock` pins the resolved install set for Python >=3.10.
- `src/olla/__init__.py` exposes application version `0.1.0`, matching `pyproject.toml` and the local project block in `uv.lock`.
- No `setup.py`, `setup.cfg`, `requirements.txt`, `tox.ini`, `pytest.ini`, dedicated Ruff config, or Python-version file is present.

## Platform Requirements

**Development:**
- Install CPython >=3.10 and a package installer; use `uv.lock` with uv for the repository’s reproducible environment.
- Install the development extra declared in `pyproject.toml` to obtain pytest, pytest-mock, and Ruff.
- Run an Ollama server reachable by the official client and install/pull the model named with `olla --model`; model availability is not provisioned by this repository.
- Shell tool behavior in `src/olla/tools/shell.py` requires the requested executable to exist on the host `PATH`; commands execute in the current working directory with the caller’s OS permissions.
- Filesystem behavior in `src/olla/tools/files.py` requires UTF-8 text and existing parent directories for writes.

**Production:**
- No hosted production target, container image, service unit, or deployment manifest is detected.
- Distribution is a pip-installable wheel/sdist built from `pyproject.toml`, exposing the `olla` console script as `olla.cli:main`.
- Deploy as a local foreground CLI on any platform supporting Python >=3.10, the locked Python dependencies, and network access to an Ollama server. The project does not provide daemonization, background execution, sandbox/container isolation, or Ollama provisioning.

---

*Stack analysis: 2026-07-25*
