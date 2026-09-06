# Phase 1: Core Loop + Shell Tool + CLI - Research

**Researched:** 2026-06-10
**Domain:** Python ReAct agent loop over local Ollama models, custom XML-tag tool-call protocol, shell execution, click CLI, hatchling packaging
**Confidence:** MEDIUM-HIGH (API mechanics HIGH; tag-format-compliance behavior on target models LOW until smoke test runs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Args/Tag Format (LOOP-01)
- **D-01:** `<args>` content for the shell tool is a **raw string**, e.g. `<args>ls -la /tmp</args>`. Parser extracts the content and runs `shlex.split()` on it directly. No JSON anywhere in the tag contract.
- **D-02:** **Per-tool micro-format principle, locked project-wide now**: each tool defines its own simple `<args>` shape (shell = raw command string). No tool uses JSON, even when future tools (Phase 3 file tools) need multiple fields — they get their own delimiter convention, not a JSON fallback.

#### System Prompt (LOOP-01, CLI-02)
- **D-03:** Minimal format-teaching — short prose rule per tag (`<tool>`, `<args>`, `<final>`) plus **exactly ONE worked example** showing a complete shell tool call followed by a `<final>` answer. No multi-example or "what not to do" blocks — token-budget takes priority over extra compliance margin.
- **D-04:** The worked example is the **sole teaching mechanism** for the args-raw-string convention — no separate prose rule saying "`<args>` contains the raw command text." Show, don't explain.

#### Step Output Display (LOOP-05)
- **D-05:** Each step prints `Step N: running <resolved argv>...` using the **post-`shlex.split()`** command — what will actually execute — not the raw `<args>` string verbatim.
- **D-06:** After execution, also print a **truncated preview of the actual command output**, using the same truncation rule that applies to history (LOOP-03). Shown distinctly from any model reasoning/prose text, so hallucinated-observation bugs (Pitfall 3) are visible immediately.

#### Smoke Test / Format Validation (Success Criterion #6)
- **D-07:** Implemented as **`olla --smoke-test [--model NAME]`** — a CLI subcommand (not a separate script, not pytest-only) that runs a fixed prompt set against the target model and prints a per-model tag-compliance table. Matches PITFALLS' framing of this as a "run when trying a new model" user workflow.
- **D-08:** A model scoring **<80%** (PITFALLS Pitfall 1 threshold) is **reported/flagged in the output as a known issue**. Phase 1 does **not** build a fallback delimiter format — that becomes a documented finding for a possible follow-up decimal phase (e.g. 1.1) if the smoke test surfaces it.

### Claude's Discretion
None — every gray area had a clear user choice (all "Recommended" options accepted as-is).

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within Phase 1 scope. (One correction, not a deferral: ARCHITECTURE.md's JSON `<args>` example is now superseded per D-01/D-02 — flagged in canonical_refs so the planner doesn't carry it forward by accident.)

### Canonical References (downstream agents MUST read before planning/implementing)

#### Project & Requirements
- `.planning/PROJECT.md` — core value, constraints, key decisions (XML tags over JSON, `shell=False`, no hardcoded default model)
- `.planning/REQUIREMENTS.md` — LOOP-01, LOOP-02, LOOP-03, LOOP-05, SHELL-01, CLI-01, CLI-02, CLI-03 definitions for Phase 1
- `.planning/ROADMAP.md` §Phase 1 — success criteria including the smoke-test requirement (#6) and the `<80%` fallback-format trigger

#### Research (load-bearing for Phase 1)
- `.planning/research/PITFALLS.md` — Pitfall 1 (tag-compliance validation, the smoke test's reason for existing), Pitfall 2 (lenient/tolerant parsing), Pitfall 3 (stop-sequence + hallucinated-observation, buffer-then-truncate-then-parse), Pitfall 6 (output truncation + explicit `num_ctx`)
- `.planning/research/ARCHITECTURE.md` — loop/parser/prompt structure (Patterns 2-4), Build Order Slice 1. **Note:** its `<args>{"command": "..."}` JSON example is **superseded by D-01/D-02 above** — use the raw-string per-tool format instead, everywhere this doc shows JSON args.

### Existing Code Insights
Repo is empty (no `src/`, no `pyproject.toml` yet) — Phase 1 is a from-scratch build. `.planning/research/ARCHITECTURE.md` "Recommended Project Structure" (`src/olla/{cli,loop,parser,prompts}.py` + `tools/shell.py`) is the only existing structural guidance; nothing to reuse, nothing to integrate with.

### Specific Ideas
- Shell tool's `<args>` is the literal command string, fed straight to `shlex.split()` — e.g. model writes `<args>ls -la /tmp</args>`, parser runs `shlex.split("ls -la /tmp")`.
- System prompt ships with exactly one worked example (one shell call + one `<final>`), nothing more.
- Per-step terminal output: `Step N: running <resolved argv>...` then a truncated preview of real stdout/stderr.
- `olla --smoke-test --model <name>` runs the fixed compliance prompt set and prints a table; <80% on any model is flagged but does not block Phase 1 or trigger building an alternate format.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-01 | ReAct loop parses `<tool>`/`<args>`/`<final>` tags from model output, tolerant of markdown fences, whitespace, and minor formatting drift | Architecture Pattern 3 (tolerant regex parser, `(?:</tag>|$)` alternation, fence-stripping, `<final>` priority); Pitfall 2 (brittle parsing); Pitfall 5 (unclosed-`<args>` is the EXPECTED case given LOOP-02's stop config, not an edge case) |
| LOOP-02 | Stop-sequences passed to `ollama.chat()` so the model can't generate past a tool call and hallucinate its own observation/final | Pattern 1 (`options={"stop":["</args>","Observation:"]}`, `Options.stop` field VERIFIED via ollama-python `_types.py`); Pitfall 3 (hallucinated observations, buffer-then-parse); Pitfall 5 (stop-on-`</args>` interaction with parser tolerance) |
| LOOP-03 | Explicit `num_ctx` set on every Ollama request; large tool outputs truncated before being appended to history | Pattern 1 (`options={"num_ctx":8192}`, `Options.num_ctx` field VERIFIED); Pattern 5 (`truncate_output()` helper, head/tail truncation with marker); Pitfall 6 (silent context truncation drops system prompt first) |
| LOOP-05 | Visible step-by-step progress output ("Step N: running `<cmd>`...") as the loop executes | Pattern 4 + D-05 (print resolved argv, post-`shlex.split()`); Pattern 5 + D-06 (truncated output preview shown distinctly from model prose); Code Examples "Minimal Loop Skeleton" |
| SHELL-01 | Shell tool runs `subprocess.run(shlex.split(cmd), shell=False)`, captures stdout/stderr, returns to model — no pipes/redirects/chaining in v1 | Pattern 4 (`run_shell()` example, `shlex.split` + `subprocess.run(shell=False, capture_output=True, text=True, timeout=N)`, `FileNotFoundError`/`TimeoutExpired` handling); Security Domain V5 (shell=False as command-injection mitigation) |
| CLI-01 | `--model` flag targets any local Ollama model, no hardcoded default | Pattern 6 (click skeleton, `--model` required with `click.UsageError` if absent — "no hardcoded default" enforced at CLI layer) |
| CLI-02 | One-shot mode — `olla "task description"` runs the loop to completion | Pattern 6 (positional `task` argument, `run_loop()` invocation); Code Examples "Minimal Loop Skeleton" (full one-shot iteration to `<final>` or `max_steps`) |
| CLI-03 | Pip-installable via `pyproject.toml` (hatchling, src layout), `olla` console-script entry point | Code Examples "pyproject.toml Skeleton" (hatchling build-backend, `src/olla` package, `[project.scripts] olla = "olla.cli:main"`, versions verified against PyPI) |

</phase_requirements>

## Summary

Phase 1 builds a from-scratch Python package (`src/olla/`) implementing a single-file-feeling ReAct loop: `cli.py` (click entry point) → `loop.py` (iterative `for step in range(max_steps)` over `ollama.chat()`) → `parser.py` (tolerant regex extraction of `<tool>`/`<args>`/`<final>`) → `tools/shell.py` (`subprocess.run(shlex.split(...), shell=False)`). The `ollama` Python client (>=0.6.2, confirmed current on PyPI as of this session) exposes `Options.stop` and `Options.num_ctx` directly — both LOOP-02 and LOOP-03 are first-class, documented fields, not workarounds. `<args>` content is a **raw string** (D-01/D-02, locked) — `shlex.split()` directly, no JSON anywhere in the tag contract; this supersedes the `json.loads(...)` example in `ARCHITECTURE.md`'s parser pattern.

The single biggest open risk remains Pitfall 1 (tag-format compliance on 0.6B-4B models), and this research surfaced two NEW mechanistic findings that sharpen — but do not resolve — that risk: (1) Qwen3-family models (which JOSIEFIED-Qwen3 is built on) ship "thinking mode" ON by default in Ollama, splitting output into `message.thinking` vs `message.content`, and separately have been **fine-tuned to emit a native `<tool_call>{"name":...,"arguments":{...}}</tool_call>` JSON-in-XML format** that competes with olla's custom raw-string `<tool>/<args>/<final>` contract; (2) gemma3-family tool-tuned variants show the same pattern — native `<tool>{"name":...,"parameters":{...}}</tool>` JSON-wrapped-in-XML format from their own fine-tuning. Both findings mean the smoke test (D-07/D-08) must check not just "did the model emit `<tool>/<args>/<final>` at all" but "did it revert to its OWN trained tool format instead of olla's prompted format" — this is the dominant failure mode the existing PITFALLS.md doesn't name explicitly.

**Primary recommendation:** Build the four-file vertical slice (`cli.py`, `loop.py`, `parser.py`, `tools/shell.py`, `prompts.py`) exactly per `ARCHITECTURE.md` Build Order Slice 1, but with `<args>` as raw-string (`shlex.split`, never JSON) per D-01/D-02; pass `think=False` explicitly in the `chat()` call as the default (token-budget + avoids think/stop interaction risk — see Pitfall 4 below), and design the `--smoke-test` to detect THREE outcomes per model: (a) compliant olla-format tags, (b) reversion to the model's own native tool-call format, (c) no recognizable tags at all.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI argument parsing & entry point | CLI (click) | — | `--model`/task-string/`--smoke-test` are pure argv concerns; click owns this exclusively |
| ReAct loop orchestration (step counter, message history) | Application core (`loop.py`) | — | Stateful sequencing of chat→parse→dispatch→observe; not owned by Ollama (stateless API) or click (no business logic) |
| Prompt construction (system prompt, worked example) | Application core (`prompts.py`) | — | Static string assembly, no I/O; kept separate so prompt tuning doesn't touch loop logic |
| Ollama API call (chat, streaming, options) | External service client (`ollama` package) | Application core (wiring `stop`/`num_ctx`/`think`) | Olla owns *which options to pass*; the `ollama` client owns *how the HTTP/JSON exchange happens* |
| Tag/output parsing (`<tool>`/`<args>`/`<final>`) | Application core (`parser.py`) | — | Pure-function regex transforms on `message.content`; no side effects, fully unit-testable in isolation |
| Shell command execution | Tool layer (`tools/shell.py`) | OS (`subprocess`/kernel) | Olla owns argv construction (`shlex.split`) and result capture; the OS/subprocess owns actual process execution |
| Step progress / output display | CLI (via `rich.Console` or `click.echo`) | Application core (formats the strings) | Loop produces step data; CLI layer renders it — keeps loop testable without capturing stdout |
| Format-compliance smoke test | CLI subcommand (`--smoke-test`) | Application core (reuses `loop.py`'s chat-call wiring) | A thin harness around the same `chat()` call path, with a different prompt set and a compliance-table renderer |
| Packaging / distribution | Build tooling (hatchling, `pyproject.toml`) | — | No runtime code; purely build-system configuration |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ollama` | 0.6.2 [VERIFIED: PyPI `pip index versions ollama` — current is 0.6.2] | Python client for local Ollama server (`chat()`, streaming, `Options`) | Official client; `Options` dataclass exposes `stop`, `num_ctx`, `think` as documented fields — exactly the mechanisms LOOP-02/LOOP-03 require, no hand-rolled HTTP needed [VERIFIED: ollama-python GitHub `ollama/_types.py` source via WebFetch] |
| `click` | >=8.1,<9 (8.3.3 installed locally; 8.4.1 latest on PyPI) [VERIFIED: PyPI `pip index versions click`] | CLI argument parsing, console-script entry point | Already locked in CLAUDE.md/STACK.md; `click.echo`, positional arg + `--model`/`--dry-run`/`--max-steps`/`--yes` flags, and a `--smoke-test` flag all map directly onto click decorators |
| `rich` | **>=13** (no upper pin recommended — see note) | `Console` for step-progress output; `Confirm.ask` reserved for Phase 2 | `pip index versions rich` shows latest is **15.0.0**, and 15.0.0 is what's installed locally [VERIFIED: PyPI]. STACK.md's `>=13,<14` pin is now STALE — `Console.print()` and `rich.prompt.Confirm.ask` are stable, long-standing APIs unaffected by the 13→15 major bumps for this minimal usage. Recommend `rich>=13` or `rich>=13,<16` to avoid blocking on a future major bump without testing. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (stdlib) `subprocess` | bundled | Shell tool execution | `subprocess.run(shlex.split(cmd), shell=False, capture_output=True, text=True, timeout=N)` per SHELL-01 |
| (stdlib) `shlex` | bundled | Tokenize raw `<args>` string into argv | `shlex.split(args_content)` — the ONLY place argv is constructed; same tokens used for both execution and the `Step N: running ...` display (D-05) |
| (stdlib) `re` | bundled | Tag parser (`<tool>`/`<args>`/`<final>`) | Tolerant regex with `re.DOTALL`, handles markdown fences, prose, and unclosed tags via `(?:</tag>|$)` alternation (see Pitfall 5 below) |
| (stdlib) `pathlib` | bundled | Not used directly in Phase 1 (file tools are Phase 3) | N/A this phase — included in `pyproject.toml` deps list only as stdlib (no install needed) |
| `pytest` | >=8 (9.0.3 latest/installed) [VERIFIED: PyPI] | Test runner | `tests/test_parser.py`, `tests/test_tools/test_shell.py`, `tests/test_loop.py` |
| `pytest-mock` | >=3.14 (3.15.1 latest/installed) [VERIFIED: PyPI] | Mock `ollama.chat` / `subprocess.run` | Optional convenience over `unittest.mock.patch` |
| `ruff` | latest | Lint/format | Dev-only, zero-config |
| `hatchling` | latest (1.30.1 on PyPI) [VERIFIED: PyPI] | Build backend | `pyproject.toml`-only, `src/` layout, `[project.scripts]` entry point |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom regex tag parser | `xml.etree.ElementTree` | Real XML parser rejects malformed/unbalanced tags (unclosed `<args>`, stray prose) that small models WILL produce — already decided against in STACK.md, reaffirmed here |
| `think=False` default | `think=True` (Ollama's default for Qwen3) | Thinking mode may *improve* tag compliance for the smallest models (0.6B) by giving them a scratchpad before committing to the tag format — but costs tokens/latency and risks `stop`-sequence interaction (Pitfall 4). Smoke test should measure both. |
| `subprocess.run(..., shell=False)` | `shell=True` | Already resolved in STATE.md in favor of `shell=False` — reaffirmed, no change |

**Installation:**
```bash
pip install "ollama>=0.6.2" "click>=8.1,<9" "rich>=13"
```

**Version verification:** All four core/supporting packages confirmed present and current via `pip index versions <pkg>` against the live PyPI index during this research session (see Package Legitimacy Audit below for full table). `ollama` 0.6.2 matches CLAUDE.md's existing pin exactly — no drift. `rich` 15.0.0 is newer than CLAUDE.md's `<14` ceiling — recommend updating that ceiling.

## Package Legitimacy Audit

> slopcheck could not be installed in this session — the sandbox's auto-mode classifier blocked `pip install slopcheck --break-system-packages` as an unrelated, agent-chosen package install with supply-chain risk. Per the Package Legitimacy Gate's graceful-degradation rule, **all packages below are tagged `[ASSUMED]`** and the planner must gate each install behind a `checkpoint:human-verify` task, even though PyPI registry presence and current versions were independently confirmed.

| Package | Registry | Age (approx, from training knowledge) | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|------|-----------|--------------|-----------|-------------|
| `ollama` | PyPI | ~3 yrs (since Ollama's Python client launch 2023) | very high (millions/month) | github.com/ollama/ollama-python | not run — `[ASSUMED]` | Approved, gate behind checkpoint |
| `click` | PyPI | ~15 yrs | extremely high (one of top Python CLI libs) | github.com/pallets/click | not run — `[ASSUMED]` | Approved, gate behind checkpoint |
| `rich` | PyPI | ~6 yrs | extremely high | github.com/Textualize/rich | not run — `[ASSUMED]` | Approved, gate behind checkpoint |
| `hatchling` | PyPI | ~5 yrs | high (default backend for `hatch`) | github.com/pypa/hatch | not run — `[ASSUMED]` | Approved, gate behind checkpoint |
| `pytest` | PyPI | ~15+ yrs | extremely high | github.com/pytest-dev/pytest | not run — `[ASSUMED]` | Approved, gate behind checkpoint |
| `pytest-mock` | PyPI | ~10 yrs | high | github.com/pytest-dev/pytest-mock | not run — `[ASSUMED]` | Approved, gate behind checkpoint |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck did not run)
**Packages flagged as suspicious [SUS]:** none (slopcheck did not run)

*All packages above are tagged `[ASSUMED]` because slopcheck was unavailable. All six are well-established, multi-year, high-download packages that any Python developer would recognize by name — the practical risk is low — but per protocol the planner must still insert a `checkpoint:human-verify` before the `pip install` step (a single combined checkpoint covering all six is reasonable given they're all uncontroversial, widely-known packages already named in the project's own CLAUDE.md).*

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │  User: olla "task description" --model X │
                    └───────────────────┬───────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │  cli.py (click)      │
                              │  - parse args/flags  │
                              │  - build system      │
                              │    prompt (prompts)  │
                              └──────────┬───────────┘
                                         │ messages=[system, user]
                                         ▼
              ┌──────────────────────────────────────────────────────┐
              │  loop.py: for step in range(max_steps):               │
              │                                                        │
              │   ┌─────────────┐    chat(model, messages,            │
              │   │ ollama.chat │◄───  options={stop,num_ctx},         │
              │   │   (HTTP)    │      think=False)                    │
              │   └──────┬──────┘                                      │
              │          │ message.content                             │
              │          ▼                                             │
              │   ┌─────────────────┐                                  │
              │   │ parser.py        │  regex: <final>? <tool>+<args>? │
              │   │ extract tags     │  unclosed-tag tolerant          │
              │   └──────┬──────────┘                                  │
              │          │                                             │
              │   ┌──────┴───────┐                                     │
              │   │  <final>?     │── yes ──► print final, EXIT loop   │
              │   └──────┬───────┘                                     │
              │          │ no, <tool>+<args> found                     │
              │          ▼                                             │
              │   ┌─────────────────────┐                              │
              │   │ tools/shell.py       │  shlex.split(args) →        │
              │   │ subprocess.run(      │  argv; print "Step N:       │
              │   │  argv, shell=False)  │  running <argv>..."         │
              │   └──────┬──────────────┘                              │
              │          │ stdout/stderr (truncated)                   │
              │          ▼                                             │
              │   append assistant msg (raw) + user msg                │
              │   ("Observation: <truncated output>")                  │
              │   to `messages`, loop continues                        │
              │                                                        │
              │   (no tags found → corrective re-prompt,               │
              │    counts toward max_steps)                            │
              └──────────────────────────────────────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │  --smoke-test mode:  │
                              │  reuses chat() call  │
                              │  with fixed prompts, │
                              │  prints compliance   │
                              │  table per model     │
                              └─────────────────────┘
```

### Recommended Project Structure
```
src/olla/
├── __init__.py
├── cli.py           # click entry point: --model, --dry-run, --max-steps, --yes, --smoke-test, positional task
├── loop.py          # ReAct loop: step counter, messages list, dispatch to parser/tools
├── parser.py        # tolerant regex extraction: <tool>, <args>, <final>
├── prompts.py       # system prompt template + ONE worked example (D-03/D-04)
└── tools/
    ├── __init__.py
    ├── base.py      # minimal tool interface/registry (just shell for Phase 1)
    └── shell.py      # subprocess.run(shlex.split(...), shell=False, timeout=...)
tests/
├── test_parser.py
├── test_loop.py
└── test_tools/
    └── test_shell.py
pyproject.toml
```

### Pattern 1: ReAct Loop with Stop-Sequence and Explicit Context Size
**What:** Each iteration calls `ollama.chat()` with `messages` (full history resent — Ollama is stateless), `options={"stop": [...], "num_ctx": N}`, and `think=False`.
**When to use:** Every chat call in `loop.py` and in the `--smoke-test` harness.
**Example:**
```python
# Source: ollama-python GitHub ollama/_types.py (Options class) [VERIFIED via WebFetch]
# Options fields confirmed present: stop: Optional[Sequence[str]], num_ctx: Optional[int]
import ollama

response = ollama.chat(
    model=model_name,
    messages=messages,             # full history, list[dict] with role/content
    options={
        "stop": ["</args>", "Observation:"],   # LOOP-02: prevent hallucinated observation
        "num_ctx": 8192,                          # LOOP-03: explicit, prevents silent truncation
    },
    think=False,                    # avoid thinking-mode token overhead + stop-interaction risk (Pitfall 4)
)
content = response["message"]["content"]
```

### Pattern 2: Raw-String `<args>` Parsing — shlex, NOT JSON (D-01/D-02)
**What:** `<args>` content is fed directly to `shlex.split()`. ARCHITECTURE.md's `json.loads(args_match.group(1))` example is **superseded** — do not use it.
**When to use:** `parser.py` extraction step, immediately before dispatch to `tools/shell.py`.
**Example:**
```python
# Per CONTEXT.md D-01/D-02 — raw string, no JSON, ever
import shlex

args_content = args_match.group(1).strip()   # e.g. "ls -la /tmp"
argv = shlex.split(args_content)              # ['ls', '-la', '/tmp']
# argv is used BOTH for execution AND for the "Step N: running <argv>..." display (D-05)
```

### Pattern 3: Tolerant Tag Parser — Unclosed Tags, Markdown Fences, `<final>` Wins
**What:** Regex-based extraction that handles (a) markdown code fences around tags, (b) missing closing tags (especially likely given `stop=["</args>"]` — see Pitfall 5), (c) `<final>` taking priority if both `<final>` and `<tool>` appear.
**When to use:** `parser.py`, called once per `chat()` response on the FULL buffered `message.content` (never streamed-and-parsed simultaneously — see PITFALLS.md Integration Gotchas).
**Example:**
```python
# Adapted from ARCHITECTURE.md Pattern 4, with D-01/D-02 raw-string args
# and unclosed-tag tolerance (end-of-buffer as implicit close)
import re

FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_RE  = re.compile(r"<tool>(.*?)(?:</tool>|$)", re.DOTALL | re.IGNORECASE)
ARGS_RE  = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)

def parse_response(content: str) -> dict:
    # Strip markdown code fences if present (models often wrap tags in ```)
    content = re.sub(r"```[a-zA-Z]*\n?|```", "", content)

    final_match = FINAL_RE.search(content)
    if final_match:
        # <final> wins even if <tool> also present (Pitfall 2)
        return {"type": "final", "text": final_match.group(1).strip()}

    tool_match = TOOL_RE.search(content)
    args_match = ARGS_RE.search(content)
    if tool_match and args_match:
        return {
            "type": "tool",
            "tool": tool_match.group(1).strip(),
            "args_raw": args_match.group(1).strip(),
        }

    # Neither tag found — corrective re-prompt path (counts toward max_steps)
    return {"type": "none", "raw": content}
```

**Critical note (NEW finding from this session):** Because `options={"stop": ["</args>", ...]}` is set per LOOP-02, Ollama will likely **stop generation before emitting `</args>`** if `</args>` is the matched stop string — meaning `message.content` ends with `...<args>ls -la` and NO closing tag. The `(?:</args>|$)` alternation above is REQUIRED, not optional, to handle this — a strict `<args>(.*?)</args>` regex would fail on the model's most common, "successful" output. This directly ties Success Criterion #2's "unclosed tags" requirement to LOOP-02's stop-sequence config — they are not independent.

### Pattern 4: Shell Tool — `shlex.split` + `subprocess.run(shell=False)`
**What:** SHELL-01's exact mechanism.
**When to use:** `tools/shell.py`, the only tool in Phase 1.
**Example:**
```python
# Source: stdlib subprocess docs + STACK.md "What NOT to Use" (shell=True rejected)
import subprocess
import shlex

def run_shell(args_raw: str, timeout: int = 30) -> dict:
    argv = shlex.split(args_raw)
    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError:
        return {"argv": argv, "error": f"command not found: {argv[0]}"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "error": f"command timed out after {timeout}s"}
```

### Pattern 5: Output Truncation Before History Append (LOOP-03 + D-06)
**What:** Truncate large stdout/stderr BEFORE constructing the "Observation: ..." message appended to `messages`, with a `[...truncated...]` marker. Same truncation feeds both the history AND the terminal preview (D-06).
**When to use:** `loop.py`, after every tool dispatch, before appending to `messages`.
**Example:**
```python
# Source: PITFALLS.md Pitfall 6 (canonical, Phase 1 load-bearing)
MAX_OBSERVATION_CHARS = 2000   # tunable; should scale with num_ctx

def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2):]
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"
```

### Pattern 6: click CLI Skeleton with `--smoke-test` Subcommand-Style Flag (D-07)
**What:** Single-command click app; `--smoke-test` short-circuits to the compliance-table path instead of the normal loop.
**When to use:** `cli.py` entry point.
**Example:**
```python
# Pattern follows click's standard single-command decorator style
# (click >=8.1,<9 confirmed via PyPI; API stable across 8.x)
import click

@click.command()
@click.argument("task", required=False)
@click.option("--model", required=False, help="Ollama model name (no default)")
@click.option("--dry-run", is_flag=True, help="Preview next tool call without executing")
@click.option("--max-steps", default=15, show_default=True, type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation prompts")
@click.option("--smoke-test", is_flag=True, help="Run format-compliance check against --model")
def main(task, model, dry_run, max_steps, yes, smoke_test):
    if smoke_test:
        if not model:
            raise click.UsageError("--smoke-test requires --model")
        run_smoke_test(model)
        return

    if not task:
        raise click.UsageError("TASK argument required (or use --smoke-test)")
    if not model:
        raise click.UsageError("--model is required (no hardcoded default, CLI-01)")

    run_loop(task=task, model=model, max_steps=max_steps, dry_run=dry_run, auto_yes=yes)

if __name__ == "__main__":
    main()
```
**Note on `--dry-run`/`--yes`:** These flags' underlying gating logic (SAFE-01/SAFE-04) is Phase 2. Recommend Phase 1 accept these flags at the CLI layer (so the surface is stable and Phase 2 doesn't need a CLI signature change) but treat them as **no-ops or pass-through stubs** in `loop.py` for now — see Open Questions.

### Anti-Patterns to Avoid
- **Streaming + simultaneous parsing:** Don't call `chat(..., stream=True)` and try to regex-match tags incrementally — buffer the full response first, then parse (PITFALLS.md Integration Gotchas; reaffirmed).
- **`json.loads()` on `<args>` content:** Explicitly superseded by D-01/D-02. If you see this pattern in ARCHITECTURE.md, it is WRONG for Phase 1 — use `shlex.split()`.
- **Recursive loop instead of iterative `for` with step counter:** Already flagged in ARCHITECTURE.md Anti-Pattern 3 — recursion risks Python stack limits and makes `--max-steps` enforcement awkward.
- **Native `tools=` schema as primary path:** Already excluded per STACK.md "What NOT to Use" — confirmed still correct; Qwen3/gemma3 native tool formats are a *risk to detect*, not a *feature to adopt*, in Phase 1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stop-sequence enforcement | Manual string-scanning during streaming to cut off generation | `options={"stop": [...]}` passed to `ollama.chat()` | Ollama's server enforces this server-side (llama.cpp `stop` param); reimplementing client-side is strictly worse — model has already generated (and been billed in latency for) the extra tokens |
| Context window sizing | Computing token counts manually and trimming `messages` | `options={"num_ctx": N}` + truncate tool OUTPUT before append | `num_ctx` is a model-load-time parameter Ollama already manages; truncating large observations is the actual lever Phase 1 needs (per Pitfall 6) — don't build a token-counting library for this |
| XML/tag parsing | `xml.etree.ElementTree` or a hand-rolled state machine with full grammar | Two/three regex patterns with `re.DOTALL` and `(?:</tag>|$)` alternation | Real grammars reject malformed input that small models routinely produce; a 3-regex tolerant parser is simpler AND more robust here (already established in ARCHITECTURE.md/PITFALLS.md, reaffirmed) |
| CLI argument parsing | Custom `sys.argv` parsing | `click` | Already locked; `click.option`/`click.argument`/`click.UsageError` cover all of CLI-01/02/03's surface |
| Shell argv tokenization | Custom string-splitting (handling quotes, escapes manually) | `shlex.split()` | stdlib, handles quoting/escaping correctly per POSIX shell rules — exactly what's needed to turn a raw `<args>` string into a safe argv list |

**Key insight:** Every "don't hand-roll" item in this phase has a stdlib or already-adopted-library solution that is BOTH simpler AND more correct than a custom implementation — there is no tradeoff here, just adoption of existing, documented APIs.

## Common Pitfalls

### Pitfall 1: Tag-Format Compliance Is Unvalidated, and the Failure Mode Is "Reverts to Trained Format," Not Just "No Tags"
**What goes wrong:** A model trained/fine-tuned for tool use (JOSIEFIED-Qwen3 is Qwen3-based; some gemma3 variants are tool-tuned) may ignore olla's prompted `<tool>/<args>/<final>` convention entirely and instead emit ITS OWN trained tool-call format.
**Why it happens:** Qwen3's chat template and fine-tuning corpus teach `<tool_call>{"name": "...", "arguments": {...}}</tool_call>` (JSON-in-XML) [CITED via WebSearch, multiple sources discussing Qwen3 tool-calling format — MEDIUM confidence, not independently re-verified against JOSIEFIED's specific Modelfile/template in this session]. Similarly, gemma3 tool-tuned variants reportedly emit `<tool> {"name": "...", "parameters": {...}} </tool>` [CITED: WebSearch result summarizing gemma3 tool-calling chat template, referencing https://ollama.com/orieg/gemma3-tools and https://docs.ollama.com/capabilities/tool-calling — MEDIUM confidence]. Both are SUPERFICIALLY similar to olla's tags (same `<tool>` wrapper) but carry JSON inside — which `shlex.split()` would mangle if parsed as a raw command string.
**How to avoid:** The `--smoke-test` (D-07) must check for THREE patterns per response, not two:
  1. olla's expected format: `<tool>NAME</tool><args>raw string</args>` or `<final>...</final>`
  2. the model's own native format: `<tool_call>{"name":...}</tool_call>` (Qwen3-style) or `<tool>{"name":...,"parameters":{...}}</tool>` (gemma3-tool-tuned style)
  3. neither (free text / no tags)
  Pattern (2) should be reported as a DISTINCT compliance-failure category from pattern (3) — it indicates the worked example (D-03/D-04) is being overridden by the model's own training, which is actionable information different from "model doesn't understand tags at all."
**Warning signs:** Smoke-test output containing `<tool_call>` or JSON (`{"name":`, `"parameters":`, `"arguments":`) inside `<tool>`/`<args>` tags.

### Pitfall 2: Brittle Parsing (canonical, reaffirmed)
**What goes wrong:** Strict regex (`<tool>(.*?)</tool>`) fails on markdown-fenced or unclosed tags.
**Why it happens:** Small models wrap output in ` ```xml ... ``` ` fences or get cut off by `stop` before closing tags.
**How to avoid:** Strip fences first; use `(?:</tag>|$)` alternation; `<final>` wins if both present; corrective re-prompt on no-match counts toward `--max-steps`.
**Warning signs:** Loop appears to "hang" on step 1 with no tool execution and no final answer — likely a parse failure being silently swallowed.

### Pitfall 3: Hallucinated Observations (canonical, reaffirmed)
**What goes wrong:** Model generates its own fake "Observation: ..." text after a tool call, without waiting for real execution.
**Why it happens:** Model has seen ReAct-style transcripts in training data where Observation follows immediately.
**How to avoid:** `options={"stop": ["</args>", "Observation:"]}` — belt-and-suspenders: stop sequence PLUS the parser only ever looks at content up to (and not past) the first `<tool>+<args>` or `<final>` match, ignoring any trailing text.
**Warning signs:** `message.content` containing the literal string "Observation:" followed by output that doesn't match what the shell tool actually returned.

### Pitfall 4: `think=True` (Ollama's Default for Qwen3) May Interact Badly with `stop` Sequences
**What goes wrong:** Ollama enables "thinking mode" by default for Qwen3-family models [CITED: docs.ollama.com/capabilities/thinking — HIGH confidence, official docs]. Response splits into `message.thinking` (reasoning trace) and `message.content` (final answer). If the model's REASONING (inside the thinking block) happens to contain the stop string (e.g., it reasons "...I should use </args> to close the tag..."), generation could abort mid-thought, before `message.content` is even produced.
**Why it happens:** `stop` sequences are typically applied to the raw token stream by the inference backend, not selectively to `message.content` after template-based splitting — but this interaction is **not independently verified in this session** [ASSUMED — see Assumptions Log].
**How to avoid:** Pass `think=False` explicitly in `chat()` calls for the main loop AND the smoke test. This is a clean default for two independent reasons: (1) avoids the unverified think/stop interaction risk entirely, (2) reduces per-turn token cost — directly serving olla's core value of "minimal per-turn token overhead" on 0.6-4B models. The smoke test SHOULD also run a `think=True` pass for comparison, since thinking *might* improve format compliance for the smallest models (a real tradeoff, not a clear win — flag as Open Question).
**Warning signs:** `message.content` is empty/truncated while `message.thinking` is non-empty and long; loop appears to terminate after 1 step with a parse failure on an empty string.

### Pitfall 5: Stop-Sequence on `</args>` Guarantees Unclosed `<args>` Tags
**What goes wrong:** If `stop=["</args>"]` and Ollama EXCLUDES the stop string from returned content (typical for llama.cpp-family backends [ASSUMED — not independently verified against ollama-python's specific behavior in this session]), then EVERY successful tool-call response will have `message.content` ending in `...<args>ls -la /tmp` with NO closing tag — by design, not as an edge case.
**Why it happens:** This is the intended mechanism of LOOP-02 (stop generation at the tool-call boundary) — but it directly produces the "unclosed tags" scenario named in Success Criterion #2.
**How to avoid:** The parser's `<args>(.*?)(?:</args>|$)` pattern (Pattern 3 above) MUST treat end-of-string as an implicit close. Do not write a parser that requires `</args>` to be present — that parser would fail on the MOST COMMON successful case, not just a degraded one.
**Warning signs:** Parser unit tests that only test `<args>foo</args>` (with closing tag) will pass while the real loop fails 100% of the time on real model output — write a test case for the no-closing-tag form FIRST.

### Pitfall 6: Context Window Blowup (canonical, reaffirmed)
**What goes wrong:** Ollama's default `num_ctx` (~2048-4096) silently truncates oldest tokens, dropping the system prompt first.
**Why it happens:** Default context size is small; truncation is silent (no error).
**How to avoid:** Always pass explicit `num_ctx` (e.g., 8192) in `options`; truncate large tool OUTPUTS before appending to `messages` (Pattern 5 above) — this is the primary lever, since `num_ctx` alone doesn't prevent a single huge `ls -la /` output from consuming the whole window.
**Warning signs:** Model "forgets" its tag-format instructions after 2-3 tool calls with large outputs (e.g., `cat` on a big file).

## Code Examples

### Full chat() Call Wiring (LOOP-02 + LOOP-03 + Pitfall 4)
```python
# Source: ollama-python GitHub ollama/_types.py Options class [VERIFIED via WebFetch]
# Confirmed fields: stop: Optional[Sequence[str]], num_ctx: Optional[int]
# think param confirmed on Client.chat() signature [VERIFIED via WebFetch of ollama/_client.py-equivalent]
import ollama

def call_model(model: str, messages: list[dict]) -> str:
    response = ollama.chat(
        model=model,
        messages=messages,
        options={
            "stop": ["</args>", "Observation:"],
            "num_ctx": 8192,
        },
        think=False,
    )
    return response["message"]["content"]
```

### Minimal Loop Skeleton
```python
# Source: ARCHITECTURE.md Pattern 1, adapted with D-01/D-02 raw-string args
# and Pattern 5 truncation
def run_loop(task: str, model: str, max_steps: int, system_prompt: str):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for step in range(1, max_steps + 1):
        content = call_model(model, messages)
        parsed = parse_response(content)
        messages.append({"role": "assistant", "content": content})

        if parsed["type"] == "final":
            print(parsed["text"])
            return

        if parsed["type"] == "tool":
            argv = shlex.split(parsed["args_raw"])
            print(f"Step {step}: running {argv}...")
            result = run_shell(parsed["args_raw"])
            preview = truncate_output(result.get("stdout", "") + result.get("stderr", ""))
            print(preview)
            messages.append({"role": "user", "content": f"Observation: {preview}"})
            continue

        # parsed["type"] == "none" — corrective re-prompt, counts toward max_steps
        messages.append({
            "role": "user",
            "content": "No <tool> or <final> tag found. Respond using <tool>/<args> or <final> only."
        })

    print(f"Reached max steps ({max_steps}) without a <final> answer.")
```

### Smoke Test Compliance Check (D-07/D-08)
```python
# Detects THREE outcomes per Pitfall 1 above
import re

NATIVE_QWEN_RE = re.compile(r"<tool_call>\s*\{", re.IGNORECASE)
NATIVE_GEMMA_RE = re.compile(r"<tool>\s*\{", re.IGNORECASE)  # JSON inside <tool>, not olla's plain-name format
OLLA_TOOL_RE = re.compile(r"<tool>(?!\s*\{)([^<]+)</tool>\s*<args>", re.IGNORECASE)
OLLA_FINAL_RE = re.compile(r"<final>", re.IGNORECASE)

def classify_response(content: str) -> str:
    if OLLA_FINAL_RE.search(content) or OLLA_TOOL_RE.search(content):
        return "compliant"
    if NATIVE_QWEN_RE.search(content) or NATIVE_GEMMA_RE.search(content):
        return "reverted_to_native_format"
    return "non_compliant"

def run_smoke_test(model: str):
    fixed_prompts = [
        "List the files in the current directory.",
        "What is 2 + 2? Answer directly.",
        # ... small fixed set per D-07
    ]
    results = {"compliant": 0, "reverted_to_native_format": 0, "non_compliant": 0}
    for prompt in fixed_prompts:
        content = call_model(model, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        results[classify_response(content)] += 1

    total = len(fixed_prompts)
    compliance_pct = results["compliant"] / total * 100
    print(f"{model}: {compliance_pct:.0f}% compliant "
          f"({results['compliant']}/{total}), "
          f"{results['reverted_to_native_format']} reverted to native format, "
          f"{results['non_compliant']} non-compliant")
    if compliance_pct < 80:
        print(f"  WARNING: {model} below 80% threshold (D-08) — flagged for follow-up")
```

### pyproject.toml Skeleton (CLI-03)
```toml
# Source: STACK.md, version numbers refreshed against PyPI this session
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "olla"
version = "0.1.0"
description = "Lightweight ReAct agent CLI for local Ollama models"
requires-python = ">=3.10"
dependencies = [
    "ollama>=0.6.2",
    "click>=8.1,<9",
    "rich>=13",
]

[project.scripts]
olla = "olla.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-mock>=3.14", "ruff"]

[tool.hatch.build.targets.wheel]
packages = ["src/olla"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `<args>{"command": "ls -la"}</args>` (JSON args, ARCHITECTURE.md original example) | `<args>ls -la</args>` (raw string, `shlex.split`) | D-01/D-02, this phase's CONTEXT.md, 2026-06-10 | Parser code in ARCHITECTURE.md Pattern 4 must be rewritten — `json.loads()` removed entirely from Phase 1's parser |
| `rich>=13,<14` pin (STACK.md) | `rich>=13` (no upper pin, or `<16`) | This research session | `rich` 15.0.0 is current/installed; `Console`/`Confirm.ask` APIs unaffected for this minimal usage scope |
| Thinking mode assumed "off unless requested" | Thinking mode ON BY DEFAULT for Qwen3/GPT-OSS/DeepSeek in Ollama | docs.ollama.com/capabilities/thinking (current) | Must explicitly pass `think=False` or accept `message.thinking`/`message.content` split + token overhead |

**Deprecated/outdated:**
- ARCHITECTURE.md's JSON `<args>` parser example: superseded by D-01/D-02, do not implement as written.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | JOSIEFIED-Qwen3 specifically (a community fine-tune of Qwen3) inherits Qwen3's native `<tool_call>{"name":...}</tool_call>` tool-call format and thinking-mode-by-default behavior | Pitfall 1, Pitfall 4 | If JOSIEFIED's Modelfile strips/disables these (some "uncensored"/fine-tuned variants modify the chat template), the smoke test's "reverted to native format" detection logic for Qwen-family models may never trigger (false negative) — but the detection code is harmless if it never matches, so risk is LOW (smoke test simply reports "compliant" or "non_compliant" only) |
| A2 | gemma3 tool-tuned variants emit `<tool>{"name":...,"parameters":{...}}</tool>` (JSON inside `<tool>` tags) | Pitfall 1, smoke-test classifier | gemma4:e2b / gemma4-uncensored-aggressive are NOT confirmed to be the same family/tuning as the `orieg/gemma3-tools` variant referenced in the WebSearch result — if olla's gemma4 targets behave differently, the `NATIVE_GEMMA_RE` pattern in the smoke test may be a no-op (harmless — same false-negative-only risk as A1) |
| A3 | Ollama's `stop` sequences are applied to the raw generation stream and EXCLUDE the matched stop string from `message.content` (llama.cpp-family default behavior) | Pitfall 5 | If Ollama INCLUDES the stop string in output instead, `<args>...</args>` would actually be present in most responses — the `(?:</args>|$)` alternation in the parser is still CORRECT either way (it matches both with and without the closing tag), so this assumption being wrong does not break the parser, only changes which branch fires more often |
| A4 | `think=True`'s reasoning trace could trigger a `stop` sequence mid-thought, aborting generation before `message.content` is produced | Pitfall 4 | If this interaction doesn't actually occur (Ollama may scope `stop` to `message.content` generation only, after thinking completes), then `think=False` is still a safe, conservative default (token-budget rationale alone justifies it) — risk of being wrong here is LOW since the recommendation doesn't depend on this assumption being true |
| A5 | All six packages (`ollama`, `click`, `rich`, `hatchling`, `pytest`, `pytest-mock`) are legitimate, non-hallucinated packages | Package Legitimacy Audit | slopcheck unavailable; risk is LOW given these are extremely well-known, multi-year-old packages already named in the project's own CLAUDE.md prior to this research — but planner must still add the checkpoint per protocol |

**If this table is empty:** N/A — see entries above. All five assumptions are LOW-risk-if-wrong because either (a) the recommended code/design is correct regardless of which way the assumption resolves, or (b) the failure mode is a harmless false-negative in smoke-test classification, not a broken loop.

## Open Questions (RESOLVED)

1. **Should `--dry-run`/`--yes` be functional or stubbed in Phase 1?**
   - What we know: Phase 1's requirement IDs are LOOP-01/02/03/05, SHELL-01, CLI-01/02/03 — none of these are SAFE-01 (dry-run) or SAFE-04 (confirm/--yes), which are explicitly Phase 2 (REQUIREMENTS.md traceability table). However, the orchestrator's additional_context describes "a minimal click-based CLI with `--model`/`--dry-run`/`--max-steps`/`--yes` flags" as part of this phase's scope.
   - What's unclear: whether the planner should (a) implement these flags as fully no-op/accepted-but-ignored in Phase 1 (stable CLI surface, Phase 2 adds behavior), or (b) omit `--dry-run`/`--yes` from Phase 1's CLI entirely and add them in Phase 2's plan.
   - Recommendation: Include `--max-steps` as a REAL, functional flag in Phase 1 (the loop needs SOME termination condition regardless of SAFE-03's repetition-guard refinement — `range(max_steps)` is already in the Pattern 1/skeleton above and is load-bearing for LOOP-01/05). For `--dry-run` and `--yes`: accept them at the click layer as no-op stubs (so Phase 2 doesn't need a CLI signature change) but do NOT build any gating/confirm logic around them in Phase 1 — document this explicitly in the plan so it's not mistaken for SAFE-01/04 being "done."
   - RESOLVED: Adopted as recommended in 01-01-PLAN.md Task 6 — `--max-steps` is functional (default 15, threaded into `run_loop`); `--dry-run`/`--yes` are accepted as no-op click flags for Phase 2 CLI-surface stability, with an explicit note that no SAFE-01/04 gating logic is implemented.

2. **Does `think=True` improve tag-compliance enough on the 0.6B model to be worth the token cost?**
   - What we know: thinking mode gives the model a scratchpad before committing to output; the smallest models (0.6B) are most likely to benefit from this, per the general intuition that CoT improves small-model task-following.
   - What's unclear: whether this benefit, if real, outweighs (a) token/latency cost (core-value tension) and (b) the unverified think/stop interaction risk (Pitfall 4 / A4).
   - Recommendation: smoke test should run BOTH `think=False` (default) and `think=True` passes for the Qwen3-family models specifically (gemma3 may not support `think` at all per docs.ollama.com — verify per-model), and report both compliance numbers. This turns an assumption into an empirical finding the user can act on.
   - RESOLVED: Adopted in 01-02-PLAN.md Task 1 — `call_model` gains a `think: bool = False` parameter, and `run_smoke_test` runs both `think=False` and `think=True` passes per model, printing a separate compliance line for each (Tests 6-8).

3. **Will the `--smoke-test`'s "reverted to native format" detection (Pitfall 1) actually fire for JOSIEFIED-Qwen3 / gemma4 variants, or is this purely theoretical?**
   - What we know: Qwen3's base chat template and gemma3-tool-tuned variants are documented (via WebSearch, MEDIUM confidence) to use `<tool_call>{...}` / `<tool>{...}</tool>` JSON-wrapped formats when given tool definitions via Ollama's native `tools=` parameter.
   - What's unclear: olla does NOT use the native `tools=` parameter (explicitly excluded per STACK.md) — it only uses prompted instructions. It's possible the native tool-call format ONLY activates when `tools=[...]` is passed to `chat()`, in which case this entire failure mode may not manifest at all when olla calls `chat()` without `tools=`.
   - Recommendation: this is exactly what the smoke test is FOR — build the three-way classifier (Pattern in Code Examples) regardless, since it's cheap to implement and provides real signal either way. If "reverted_to_native_format" never fires across all 5 models, that's a useful negative result (Pitfall 1's risk profile shifts entirely to "non_compliant" / no-tags-at-all).
   - RESOLVED: Adopted in 01-02-PLAN.md Task 1 — `classify_response()` implements the three-way classifier (compliant / reverted_to_native_format / non_compliant), with olla-tag checks ordered first (Tests 3-4).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ | 3.14.5 (exceeds `>=3.10` requirement) | — |
| pip | packaging/install | ✓ | present | — |
| `ollama` CLI | running models for smoke test, manual testing | ✓ (binary present) | unknown (warned "could not connect to a running Ollama instance") | — |
| Ollama server (daemon) | ALL runtime testing — loop, shell tool integration, smoke test | ✗ (not running: `curl http://localhost:11434/api/version` empty) | — | User must start `ollama serve` before running olla or the smoke test |
| Target models (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive) | smoke test (D-07/D-08) | ✗ (`ollama list` returns empty — server down, can't enumerate) | unknown | User must `ollama pull <model>` for each target before running `--smoke-test` |
| `ollama` Python package | runtime import | ✗ (not yet installed — greenfield) | target 0.6.2 | `pip install` step in Phase 1 plan |

**Missing dependencies with no fallback:**
- None that block WRITING Phase 1's code — the loop/parser/shell-tool/CLI can be fully implemented and unit-tested (with mocked `ollama.chat`) without a running Ollama server.

**Missing dependencies with fallback:**
- Ollama server + target models: required for END-TO-END manual testing and the `--smoke-test` subcommand's actual execution. Fallback: Phase 1 ships the smoke-test CODE; the user runs it locally once Ollama is running and models are pulled (this matches D-07/D-08's framing of the smoke test as a "run when trying a new model" user workflow, not a CI-gated check). This is EXPECTED, not a gap — the smoke test is *designed* in Phase 1 and *executed* by the user on their hardware.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Local CLI, single-user, no network-facing auth surface |
| V3 Session Management | No | Stateless one-shot CLI invocation; no sessions |
| V4 Access Control | No | Single local user, no multi-tenancy or privilege boundaries within olla itself |
| V5 Input Validation | **Yes** | Model-generated `<args>` content is parsed via `shlex.split()` (NOT raw shell string) and executed via `subprocess.run(argv, shell=False)` — this is the standard control for command-injection prevention when input originates from an untrusted/unpredictable source (the LLM). `shell=False` + argv-list form means shell metacharacters (`;`, `|`, `` ` ``, `$()`, `&&`) in the model's output are NOT interpreted by a shell — they become literal arguments to whatever `argv[0]` is (which will typically just fail or be a no-op argument), not command-chaining operators. |
| V6 Cryptography | No | No secrets, tokens, or cryptographic operations in Phase 1 scope |

### Known Threat Patterns for Local CLI + LLM-Driven Shell Execution

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell metacharacter / command injection via model-generated `<args>` | Tampering | `shlex.split()` (tokenize) + `subprocess.run(argv, shell=False)` (no shell interpretation) — Phase 1's chosen mechanism. **Important scope note:** this prevents *shell-level injection* (`;`, `|`, backticks becoming control operators) but does NOT prevent the model from choosing to run a genuinely destructive single command (e.g., `rm -rf /tmp/important`) — that's SAFE-02 (blocklist, Phase 2), explicitly out of scope here. |
| Resource exhaustion / runaway process (model requests a long-running or interactive command) | Denial of Service | `subprocess.run(..., timeout=N)` — Phase 1's `run_shell()` example includes `timeout` parameter; recommend a conservative default (e.g., 30s) so a hung command (e.g., model emits `<args>tail -f /var/log/syslog</args>`) doesn't hang the entire loop indefinitely |
| Infinite/runaway loop (model never emits `<final>`, repeats same tool call) | Denial of Service | `--max-steps` cap (already in Phase 1's loop skeleton per Open Question #1) — full repetition-detection (LOOP-04) is Phase 2, but the hard step-count ceiling is a Phase 1 baseline that prevents unbounded execution |
| Sensitive data exposure via tool output echoed into model context / terminal | Information Disclosure | Out of scope for Phase 1 (no secrets-handling requirements in LOOP-01..05/SHELL-01/CLI-01..03); NOTE for awareness only — if a user runs olla in a directory containing secrets and asks it to `cat .env`, that content flows into `messages` (sent to local Ollama server) and stdout. This is consistent with the project's stated trust model (local-only, single-user) but worth noting as a non-mitigated pattern, should NOT be silently expanded in scope without a user decision |

**Flagged tension (per advisor review, not a contradiction to silently resolve):** PROJECT.md states "blocklist, confirm-gating, and dry-run are non-negotiable from v1" as a constraint, while ROADMAP.md/REQUIREMENTS.md explicitly assign SAFE-01/02/04 to Phase 2 and Phase 1's Build-Order-Slice-1 description says "no safety, confirm-skip" for the first vertical slice. **This research does not attempt to resolve this tension** — it is a roadmap-level sequencing decision already made (Phase 1 → Phase 2 dependency chain), and overriding it would contradict the locked CONTEXT.md/ROADMAP.md. However, the planner and `security_block_on: "high"` gate should be aware: **Phase 1's shell tool, as specified, executes arbitrary model-chosen commands with `shell=False` argv-safety as the ONLY control** — no blocklist, no confirm prompt, no dry-run gating. This is "unsafe by design" for Phase 1 in isolation, by explicit project sequencing (the safety gate is Phase 2's entire purpose). If `security_block_on: "high"` flags this during plan-check, the correct resolution is "documented and deferred to Phase 2 per ROADMAP.md," not "expand Phase 1 scope to include SAFE-*."

## Sources

### Primary (HIGH confidence)
- ollama-python GitHub `ollama/_types.py` (raw source via WebFetch) — `Options` class fields: `stop: Optional[Sequence[str]]`, `num_ctx: Optional[int]`, confirmed present
- ollama-python GitHub `examples/chat.py`, `examples/chat-stream.py` (via WebFetch) — minimal `chat()`/streaming usage patterns
- https://docs.ollama.com/capabilities/thinking (via WebFetch) — `think` param (bool or "low"/"medium"/"high"), thinking-enabled-by-default for Qwen3/GPT-OSS/DeepSeek, `message.thinking` vs `message.content` split
- PyPI `pip index versions <pkg>` for `ollama` (0.6.2), `click` (8.4.1, 8.3.3 installed), `rich` (15.0.0, installed), `hatchling` (1.30.1), `pytest` (9.0.3, installed), `pytest-mock` (3.15.1, installed) — direct registry queries this session
- `.planning/config.json` — `nyquist_validation: false`, `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: "high"` (read directly)

### Secondary (MEDIUM confidence)
- WebSearch "JOSIEFIED Qwen3 ollama tool calling XML tags small model format compliance" — Qwen3 native `<tool_call>{"name":...,"arguments":{...}}</tool_call>` format; not independently re-verified against JOSIEFIED's specific Modelfile
- WebSearch "gemma3 ollama tool calling format chat template thinking" — gemma3-tool-tuned variants emit `<tool>{"name":...,"parameters":{...}}</tool>`; sources: https://ollama.com/orieg/gemma3-tools, https://docs.ollama.com/capabilities/tool-calling, https://github.com/ollama/ollama/issues/9941
- WebSearch "Qwen3 ollama think tag thinking mode disable enable_thinking chat template" — `think=False`/`enable_thinking=False` mitigation pattern

### Tertiary (LOW confidence)
- A3/A4 (stop-sequence inclusion/exclusion behavior, think/stop interaction) — not found in any source this session, flagged in Assumptions Log as low-risk-if-wrong because recommended code is correct either way

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified directly against live PyPI registry this session
- Architecture: HIGH — Patterns 1-6 build directly on canonical ARCHITECTURE.md/PITFALLS.md with one corrective change (D-01/D-02 raw-string args) already mandated by locked CONTEXT.md decisions
- Pitfalls: MEDIUM — Pitfalls 1,2,3,6 are canonical/reaffirmed (HIGH); Pitfalls 4,5 are NEW findings from this session, mechanically sound but with LOW-confidence sub-claims (A1-A4) that the smoke test will resolve empirically

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (30 days — Ollama API surface for `Options`/`think` is stable; model-specific tag-compliance behavior (Pitfall 1) should be re-validated whenever target model versions change, via the smoke test itself rather than re-research)
