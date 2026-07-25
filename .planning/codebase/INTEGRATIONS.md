# External Integrations

**Analysis Date:** 2026-07-25

## APIs & External Services

**Local Model Inference:**
- Ollama - Supplies chat completions for the ReAct agent and format-compliance smoke test.
  - SDK/Client: `ollama` 0.6.2, declared in `pyproject.toml` and locked in `uv.lock`.
  - Call site: `call_model()` in `src/olla/loop.py` invokes the synchronous package-level `ollama.chat()` function. `src/olla/smoke.py` reuses that boundary rather than creating a second client.
  - Request contract: `src/olla/loop.py` sends a selected model name, system/user/assistant message history, stop sequences `</args>` and `Observation:`, `num_ctx = 8192`, and a `think` boolean.
  - Response contract: `src/olla/loop.py` reads `response["message"]["content"]`; `src/olla/parser.py` interprets the text as the project’s XML-style `<tool>`, `<args>`, and `<final>` protocol.
  - Endpoint: The application does not construct a URL. The official SDK’s package-level client uses its normal local Ollama endpoint by default and can be redirected with `OLLAMA_HOST`.
  - Auth: None required for the intended local Ollama service. The installed SDK can consume `OLLAMA_API_KEY` for a bearer token, but `src/olla/` does not read or enforce it.
  - Model provisioning: Not managed. `--model` is required by `src/olla/cli.py`; the named model must already be available to the reachable Ollama server.
  - Failure handling: No retry, timeout override, availability probe, or SDK-exception translation is implemented around `ollama.chat()` in `src/olla/loop.py`; client/service exceptions propagate to the CLI.

**Package Registry:**
- Python Package Index - `uv.lock` resolves third-party packages from `https://pypi.org/simple` and records artifacts hosted by Python package infrastructure.
  - SDK/Client: uv/pip-compatible Python packaging metadata in `pyproject.toml` and `uv.lock`.
  - Auth: None configured in the repository. No package-manager credential file is part of the project.
  - Runtime use: Package downloads occur during installation/synchronization, not during an `olla` agent run.

**Host Process Execution:**
- Local operating system executables - The model can request a `shell` tool call, which `src/olla/loop.py` tokenizes with `shlex.split()` and passes through the policy in `src/olla/safety.py`.
  - SDK/Client: Python `subprocess.run(..., shell=False)` in `src/olla/tools/shell.py`.
  - Auth: The child process inherits the current user identity and process environment; the application provides no separate credential boundary.
  - Limits: `src/olla/tools/shell.py` applies a 30-second default timeout and captures stdout/stderr. `src/olla/loop.py` truncates observations before returning them to the model.

## Data Storage

**Databases:**
- Not detected. No database driver, ORM, schema, migration, connection string, or persistence layer appears in `pyproject.toml`, `uv.lock`, or `src/olla/`.

**File Storage:**
- Local filesystem only.
  - Client: Python `pathlib.Path` in `src/olla/tools/files.py`.
  - Reads: `read_file()` reads complete UTF-8 text files and returns content through the shared `ToolResult` shape in `src/olla/tools/base.py`.
  - Writes: `write_file()` replaces the target with UTF-8 text, requires the parent directory to exist, and reports bytes written. `src/olla/loop.py` requires confirmation unless `--yes` is supplied.
  - Scope: Paths are supplied by model output and resolved for display in `src/olla/loop.py`; no application data directory, database file, object-storage bucket, or persistent conversation history is created.

**Caching:**
- None. Conversation state exists only in the in-memory `messages` list inside `src/olla/loop.py` for the duration of one CLI invocation.

## Authentication & Identity

**Auth Provider:**
- No application authentication or identity provider is implemented.
  - Implementation: The `olla` process runs as the invoking operating-system user. Local file and process access in `src/olla/tools/files.py` and `src/olla/tools/shell.py` uses that user’s permissions.
  - Ollama: Intended local use is unauthenticated. Optional SDK-level host/API-key configuration is external to application code and is not validated by `src/olla/`.
  - User authorization: Interactive approval through `rich.prompt.Confirm` in `src/olla/loop.py` is a safety consent gate for tool actions, not authentication.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, OpenTelemetry, hosted monitoring SDK, or error-reporting integration is declared in `pyproject.toml` or imported by `src/olla/`.

**Logs:**
- Console output only.
  - `src/olla/loop.py` prints model final text, tool-step status, tool observations, policy blocks, repeated-call termination, and max-step termination to stdout.
  - `src/olla/smoke.py` prints model compliance summaries and threshold warnings to stdout.
  - `src/olla/tools/shell.py` captures child stdout/stderr into `ToolResult`; `src/olla/loop.py` combines and truncates it before printing and appending it to model history.
  - No log levels, structured logging, persistent log file, metrics, traces, correlation IDs, or remote log sink are present.

## CI/CD & Deployment

**Hosting:**
- None. The repository has no Dockerfile, Compose file, platform manifest, process manager configuration, hosted service adapter, or infrastructure-as-code file.
- The supported delivery form is the local `olla` console script configured in `pyproject.toml`; it requires a separately operated Ollama server.

**CI Pipeline:**
- None detected. There is no tracked `.github/workflows/` pipeline or configuration for another CI provider.
- Tests and linting are local development commands backed by the `dev` extra in `pyproject.toml` and resolved versions in `uv.lock`.

## Environment Configuration

**Required env vars:**
- None are read directly by `src/olla/`.
- `OLLAMA_HOST` - Optional SDK-supported override for the Ollama server endpoint used by the package-level client invoked from `src/olla/loop.py`.
- `OLLAMA_API_KEY` - Optional SDK-supported bearer credential. It is not needed for the intended unauthenticated local Ollama server and is not consumed directly by application code.
- Runtime model selection is not an environment variable: supply the required `--model` option defined in `src/olla/cli.py`.

**Secrets location:**
- Not detected. No `.env` file or repository-managed secret store is present.
- Keep any optional Ollama credential outside the repository and provide it through the process environment; neither `pyproject.toml` nor `src/olla/` defines a secret-loading mechanism.

## Webhooks & Callbacks

**Incoming:**
- None. `src/olla/cli.py` is a local command entry point, not an HTTP server, and no route/callback listener exists under `src/olla/`.

**Outgoing:**
- None. The only network request path is the synchronous Ollama chat request in `src/olla/loop.py`; no webhook, notification, analytics, callback, browser, or arbitrary HTTP integration is implemented.

---

*Integration audit: 2026-07-25*
