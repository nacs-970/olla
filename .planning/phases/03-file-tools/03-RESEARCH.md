# Phase 3: File Tools - Research

**Researched:** 2026-06-14
**Domain:** Local file read/write tools for a small-model ReAct agent, integrated with the existing tag-parser, dispatch loop, and confirm-gate
**Confidence:** HIGH (architecture/integration — verified against actual source) / MEDIUM (fence-stripping fix approach and `</args>`-in-content limitation — design decisions, need empirical validation like Phase 1's tag bet)

## Summary

Phase 3 adds two tools — `read_file(path)` and `write_file(path, content)` — to the existing ReAct loop established in Phases 1-2. Both tools are pure-stdlib (`pathlib`, builtin `open`); **no new dependencies are required**. The integration surface is small and well-understood: `loop.py`'s per-step dispatch (currently a single `if parsed["tool"] != "shell"` branch), `prompts.py`'s `SYSTEM_PROMPT` (currently documents only `shell`), and a new `src/olla/tools/files.py` module mirroring `tools/shell.py`'s `ToolResult` contract.

The single highest-risk design decision is **how a two-argument tool (`write_file(path, content)`) is encoded inside the existing single `<args>...</args>` tag**, given that (a) the stop-sequence `</args>` is fixed before the model's tool choice is known, ruling out a separate `<content>` tag, and (b) `parse_response`'s global code-fence-stripping regex and `.strip()` call **actively corrupt file content** that contains backtick fences or relies on a trailing newline. This was verified empirically (see Pitfall 1) — it is a real bug in the current parser that Phase 3 must fix to satisfy Success Criterion 3 (read→modify→write round-trip), not a hypothetical edge case.

A second, **distinct** risk with the same encoding choice is that `</args>` is also the model's stop-sequence (`call_model`, `options={"stop": ["</args>", "Observation:"], ...}`). If the file content the model intends to write contains the literal substring `</args>`, Ollama halts generation at that point — the remaining content is never produced, never reaches the parser, and is silently truncated when written to disk. Unlike Pitfall 1, **no parser fix can recover this** (see Pitfall 5); it is an inherent limitation of the chosen encoding that the planner should document, not "fix."

`write_file` does **not** route through `safety.check()` — that function is a shell-binary allowlist/blocklist classifier (`argv[0]` against `ALLOWLIST`/`_HARD_BLOCKED_BINARIES`/etc.) and has no concept of file paths. Per SAFE-04 (which already names `write_file` explicitly) and the phase success criteria, `write_file` is **always-CONFIRM**: it reuses the `Confirm.ask`/`--yes`/EOFError-decline *mechanism* from `loop.py`, not the `Decision` classifier. `read_file` is read-only and requires no prompt (analogous to the shell ALLOWLIST tier). `Path.resolve()` is used to show the user the real target path at confirm time (symlink/relative-path honesty), not as a containment/sandbox boundary — this project's safety model is "confirm-gate is the boundary," and a path jail would be both inconsistent (shell can already write anywhere) and theater.

**Primary recommendation:** Add `src/olla/tools/files.py` with `read_file(path)` / `write_file(path, content)` returning the existing `ToolResult` shape; encode `write_file`'s two arguments as path-on-first-line / content-is-remainder within a single `<args>` block; fix `parse_response` so file content is not corrupted by fence-stripping or `.strip()`; document (don't attempt to fix) the `</args>`-in-content stop-sequence limitation; dispatch both tools in `run_loop` alongside the existing shell branch, with `write_file` always prompting via `Confirm.ask` (honoring `--yes`) and `read_file` running unprompted with `truncate_output` applied to its result.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tag parsing (extract path/content from `<args>`) | Parser (`parser.py`) | — | Single-file CLI; parser is the only layer that sees raw model text |
| Tool dispatch (route `read_file`/`write_file` to implementations) | Loop (`loop.py`) | — | `run_loop` already owns the shell dispatch branch; file tools are siblings |
| File I/O (open/read/write, error handling) | Tool module (`tools/files.py`) | — | Mirrors `tools/shell.py`'s separation: pure I/O wrapper returning `ToolResult`, no prompting/printing |
| Confirm-gate for writes | Loop (`loop.py`) | — | `Confirm.ask`/`--yes`/EOFError-decline logic already lives in `run_loop`; write_file reuses this mechanism, not `safety.check()` |
| Output truncation (oversized reads) | Loop (`loop.py`) | — | `truncate_output` already lives in `loop.py` and is applied to shell observations; reused for `read_file` results to avoid a circular import (tool importing from loop) |
| Tool-schema documentation for the model | Prompt (`prompts.py`) | — | `SYSTEM_PROMPT` is the model's only "API reference"; must document the new tools, the path/content encoding, and the `</args>`-in-content caveat |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pathlib` (stdlib) | Python >=3.10 (project floor) | Path resolution (`Path(path).resolve()`), existence/type checks (`Path.is_file()`) | Already implicitly used via `os.path` in `safety.py`; `pathlib` is the modern stdlib idiom for path handling and provides `.resolve()` which normalizes `..`/symlinks for honest display, no install needed |
| builtin `open()` (stdlib) | Python >=3.10 | Read/write file contents as text | Simplest possible I/O primitive; matches the project's "no hand-rolled abstraction" philosophy — `open(path, "r", encoding="utf-8")` / `open(path, "w", encoding="utf-8")` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none — no new dependencies) | — | — | — |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pathlib.Path.read_text()`/`write_text()` (one-liners) | `open()` context manager | Both are stdlib and equivalent; `open()` as a context manager is marginally more explicit about encoding/error handling and matches the existing `subprocess.run` try/except style in `tools/shell.py`. Either is fine — pick one and be consistent. `Path.read_text()`/`write_text()` are slightly terser if preferred. |
| First-line-path / rest-is-content encoding (recommended) | A separate `<path>`/`<content>` tag pair | **Incompatible with current stop-sequence wiring.** `call_model` passes `options={"stop": ["</args>", "Observation:"]}` — generation stops at `</args>` regardless of which tool was called, so the model cannot emit content in a tag *after* `</args>`. A second stop-sequence change would require knowing the tool before generation completes, which is impossible in a single-pass chat call. |
| First-line-path / rest-is-content encoding (recommended) | JSON-encode `{"path": ..., "content": ...}` inside `<args>` | Rejected by existing project decision (REQUIREMENTS.md "Out of Scope": "JSON/OpenAI-style function-calling schema — small models (sub-4B) are unreliable at structured JSON"). Asking a 0.6B model to emit valid JSON with escaped newlines/quotes for file content is strictly harder than the tag format the project already validated in Phase 1. |
| `Path.resolve()` for display only | `Path.resolve()` + containment check (`is_relative_to(cwd)`) jail | Rejected — see Pitfall 4. The agent already runs arbitrary confirmed shell commands (`cp`, `tee`, `python -c "open(...).write(...)"`) that bypass any path jail trivially. A jail on `write_file` alone is inconsistent and gives a false sense of sandboxing; REQUIREMENTS.md's Out of Scope explicitly defers sandboxed execution and names "confirm-gate is the safety boundary instead." |

**Installation:**
No new packages — `pathlib` and `open()` are part of the Python standard library already available at the project's `>=3.10` floor.

**Version verification:** N/A — no external packages introduced by this phase.

## Package Legitimacy Audit

> Not applicable — this phase introduces **zero new external packages**. `pathlib` and `open()` are Python standard library, bundled with every CPython >=3.10 install (the project's existing floor, set by `click>=8.1,<9` in `pyproject.toml`). No `pip install` step, no slopcheck run needed, no registry verification needed.

**Packages removed due to slopcheck [SLOP] verdict:** none (no packages evaluated)
**Packages flagged as suspicious [SUS]:** none (no packages evaluated)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FILE-01 | `read_file(path)` tool reads file contents for the model | `tools/files.py::read_file` (Code Examples), dispatch branch in `run_loop` (Architecture Patterns Pattern 2), truncation via existing `truncate_output` (Pitfall 2/Don't Hand-Roll) |
| FILE-02 | `write_file(path, content)` tool writes file contents | Path/content encoding fix in `parser.py` (Pitfall 1, Architecture Patterns Pattern 1), always-CONFIRM dispatch reusing `Confirm.ask`/`--yes`/EOFError pattern (Architecture Patterns Pattern 3), resolved-path display via `Path.resolve()` (Code Examples, Security Domain), `</args>`-in-content limitation documented for the model (Pitfall 5) |
</phase_requirements>

## Architecture Patterns

### System Architecture Diagram

```
Model output (raw text, possibly fenced)
        |
        v  <-- generation halts here if content contains literal "</args>"
        |      (Pitfall 5 — inherent stop-sequence limitation, not a parser bug)
        v
parser.parse_response()  --- FIX NEEDED: fence-strip + .strip() corrupt
        |                     write_file content (Pitfall 1)
        | {"type": "tool", "tool": "read_file"|"write_file"|"shell",
        |  "args_raw": "<path>\n<content...>" or "<path>" or "<cmd>"}
        v
loop.run_loop()  per-step dispatch
        |
        +-- tool == "shell"   -----------> existing safety.check() -> Confirm tier -> tools/shell.run_shell()
        |
        +-- tool == "read_file" ---------> tools/files.read_file(path)
        |                                       |
        |                                       v
        |                                  truncate_output(content)  -- reuse existing helper
        |                                       |
        |                                       v
        |                                  Observation: <truncated content or error>
        |
        +-- tool == "write_file" ---------> resolve path (Path(path).resolve())
                                                  |
                                                  v
                                             Confirm.ask(f"Write to {resolved_path}?")  -- reuse
                                             existing mechanism (declined -> Observation,
                                             EOFError -> decline, --yes skips prompt)
                                                  |
                                                  v (approved)
                                             tools/files.write_file(path, content)
                                                  |
                                                  v
                                             Observation: "wrote N bytes to <resolved_path>"
                                                  or error observation (FileNotFoundError dir,
                                                  PermissionError, etc.)
```

A reader can trace Success Criterion 3 (inspect-then-modify-then-write) end-to-end: model emits `read_file`, loop dispatches to `tools/files.read_file`, truncated content returned as Observation; model emits `write_file` with the modified content, loop resolves the path, prompts (or auto-confirms with `--yes`), and `tools/files.write_file` performs the write, returning a success/error Observation that closes the loop.

### Recommended Project Structure

```
src/olla/
├── loop.py          # add read_file/write_file dispatch branches + write_file confirm-gate
├── parser.py         # FIX: scope fence-stripping / don't .strip() args_raw for write_file content
├── prompts.py        # extend SYSTEM_PROMPT with read_file/write_file schema + path/content encoding example + </args> caveat
└── tools/
    ├── base.py        # ToolResult already generic enough — no change expected, verify during planning
    ├── shell.py        # unchanged
    └── files.py        # NEW: read_file(path) -> ToolResult, write_file(path, content) -> ToolResult
```

### Pattern 1: Path/content encoding inside a single `<args>` tag

**What:** For `write_file`, the model emits `<args>` whose **first line is the file path** and **all remaining text (including embedded newlines, blank lines, and backtick fences) is the file content verbatim**.

**When to use:** Any tool needing more than one "argument" under the current parser/stop-sequence constraints (verified: stop sequence is `</args>`, fixed before the tool name is known — see Alternatives Considered).

**Example (target parser behavior after fix):**
```python
# Source: derived from src/olla/parser.py (read 2026-06-14) + empirical trace
content = (
    "<tool>write_file</tool><args>/tmp/notes.md\n"
    "# Notes\n"
    "\n"
    "Example:\n"
    "```python\n"
    'print("hi")\n'
    "```\n"
    "</args>"
)
parsed = parse_response(content)
# parsed["tool"] == "write_file"
# parsed["args_raw"] should split as:
#   path    = "/tmp/notes.md"
#   content = '# Notes\n\nExample:\n```python\nprint("hi")\n```\n'
# i.e. the embedded ```python fence MUST survive, and the trailing
# newline before </args> SHOULD be preserved for round-trip fidelity.
path, _, file_content = parsed["args_raw"].partition("\n")
```

Splitting `path`/`file_content` via `str.partition("\n")` on the (fixed) `args_raw` is a one-line, dependency-free operation — once `parser.py` stops corrupting the raw text, this split is trivial and belongs in `loop.py`'s dispatch (or `tools/files.py`, either is reasonable; keep it next to where `write_file` is invoked).

**Caveat (Pitfall 5):** this encoding is sound for the overwhelming majority of file content, but content containing the literal substring `</args>` will be truncated at the generation stage, before `parse_response` ever sees it. This is documented as a known limitation, not fixed by this pattern.

### Pattern 2: `read_file` dispatch — no confirm, truncate like shell output

**What:** `read_file` is read-only and side-effect-free, so it dispatches without a confirm prompt — analogous to `safety.ALLOWLIST` shell commands (`cat`, `head`, etc., which already auto-run). Its result is truncated via the **existing** `truncate_output` helper, exactly as shell stdout/stderr is truncated today.

**When to use:** Any new read-only tool that returns potentially-large text into the conversation history.

**Example:**
```python
# Source: pattern mirrors src/olla/loop.py lines 125-136 (shell dispatch, read 2026-06-14)
if parsed["tool"] == "read_file":
    path = parsed["args_raw"].strip()  # single-argument tool: whole args_raw is the path
    result = tools.files.read_file(path)
    if "error" in result:
        preview = result["error"]
    else:
        preview = result["content"]
    preview = truncate_output(preview)
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue
```

Note: for `read_file`, `.strip()` on `args_raw` is safe — a file *path* has no meaningful trailing whitespace, unlike `write_file`'s content. Do not apply the same `.strip()` to `write_file`'s `args_raw`.

### Pattern 3: `write_file` always-CONFIRM, reusing the existing mechanism (not `safety.check()`)

**What:** `write_file` always prompts via `Confirm.ask`, regardless of path — there is no ALLOW/BLOCK tier for file writes in this phase. The mechanism (prompt text, `--yes` bypass, EOFError-as-decline, declined-observation message) is copy-adapted from the shell CONFIRM-tier code already in `run_loop`.

**When to use:** Any tool with a filesystem/state side-effect that SAFE-04 names explicitly.

**Example:**
```python
# Source: pattern mirrors src/olla/loop.py lines 116-123 (shell CONFIRM tier, read 2026-06-14)
if parsed["tool"] == "write_file":
    raw = parsed["args_raw"]  # NOT .strip()'d — see Pattern 1
    path_str, _, file_content = raw.partition("\n")
    path_str = path_str.strip()  # the path line itself can be stripped
    resolved = Path(path_str).resolve()

    if not yes:
        try:
            approved = Confirm.ask(f"Write to `{resolved}`?", default=False)
        except EOFError:
            approved = False
        if not approved:
            messages.append({"role": "user", "content": "Observation: declined by user"})
            continue

    result = tools.files.write_file(path_str, file_content)
    if "error" in result:
        preview = result["error"]
    else:
        preview = f"wrote {len(file_content.encode('utf-8'))} bytes to {resolved}"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue
```

Key point: `safety.check()` is never called for `write_file`. There is no `Decision` dict, no `ALLOW`/`BLOCK` tier — only the prompt-or-skip mechanism.

### Anti-Patterns to Avoid

- **Faking a shell-shaped argv for `write_file` to route through `safety.check()`:** e.g. `check(["write_file", path], yes=yes)`. `safety.check()`'s entire rule table (D-01 ALLOWLIST, D-03 blocklist for `rm`/`dd`/`chmod`/etc.) is meaningless for a file path and either always falls through to `CONFIRM` (harmless but confusing/dead code) or — worse — could accidentally match a blocklist rule if a future rule is path-shaped, producing a nonsensical BLOCK for an unrelated reason. Keep `write_file`'s confirm-gate logic separate and explicit.
- **Building a path-containment "jail" (`is_relative_to(cwd)`) for `write_file`:** gives a false sense of sandboxing in a project whose shell tool can already write anywhere via `tee`/`cp`/redirection-free `python -c`. See Security Domain.
- **Applying the global fence-stripping regex to `write_file` content unchanged:** silently corrupts any file whose legitimate content contains `` ``` ``-delimited blocks (markdown docs, READMEs, code in markdown). See Pitfall 1.
- **Re-using `shlex.split()` on `write_file`'s content:** `write_file`'s second "argument" is free-form file text, not a shell command — `shlex.split` would tokenize it (splitting on whitespace/quotes) and destroy it. Only the path (if anything) should ever be shlex-processed, and even that's unnecessary since paths from `args_raw` don't need shell-quote-unescaping.
- **Treating Pitfall 5 (`</args>`-in-content) as a parser bug fixable alongside Pitfall 1:** a parser fix tested with hand-constructed `parse_response(content)` strings will pass even though real model output containing `</args>` is truncated *before* `content` is ever formed (at the Ollama generation boundary). Don't let a passing parser test create false confidence about this case — see Pitfall 5.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path normalization / symlink resolution | Custom `..`-stripping regex or manual `os.path.normpath` chains | `pathlib.Path(path).resolve()` | stdlib, handles `..`, `.`, symlinks, relative-to-cwd resolution correctly; already the modern idiom, zero dependencies |
| Truncating oversized file content for the model's context | A new truncation function for files | Existing `loop.truncate_output()` (head+tail with `[...truncated N chars...]` marker) | Phase 1 (LOOP-03) already built and tested this exact head+tail truncation for shell output; `read_file` output is the same "potentially large text headed into conversation history" problem — reuse, don't reimplement |
| Confirm-prompt / `--yes` / non-TTY decline mechanics | A new confirm helper for file writes | Existing `Confirm.ask` + `try/except EOFError` + `yes` flag pattern in `run_loop`'s shell CONFIRM branch | Phase 2 (SAFE-04) already solved "prompt, allow --yes override, treat EOFError as decline" — `write_file` is one of the two operations SAFE-04 was written for; the pattern is proven and tested |
| File I/O error handling (missing file, permission denied, etc.) | Custom exception hierarchy / error codes | Plain `try/except (FileNotFoundError, PermissionError, IsADirectoryError, UnicodeDecodeError, OSError)` returning `{"error": "..."}` in the existing `ToolResult` shape | Mirrors `tools/shell.py`'s `FileNotFoundError`/`TimeoutExpired` handling exactly — same `ToolResult["error"]` contract, same "errors become Observations, not exceptions" loop behavior |

**Key insight:** Phase 3 is almost entirely *composition* of Phase 1/2 primitives (`truncate_output`, `Confirm.ask`/`--yes`/EOFError, the `ToolResult` error-as-dict contract, the per-step dispatch `if/elif` chain) applied to a new pair of stdlib I/O calls. The only genuinely new code is the path/content encoding fix in `parser.py` and the two small functions in `tools/files.py`. Pitfall 5 is the one exception: it's not new code at all, but a documentation/acceptance task.

## Common Pitfalls

### Pitfall 1: `parse_response`'s fence-stripping and `.strip()` corrupt `write_file` content

**What goes wrong:** `parser.py` line 16 runs `re.sub(r"```[a-zA-Z]*\n?|```", "", content)` on the **entire raw model output** before extracting `args_raw`, and line 28 calls `.strip()` on the extracted `args_raw`. For `write_file`, `args_raw` *is* the file content (after the path line). Verified empirically (2026-06-14):

- A model emitting `<tool>write_file</tool><args>/tmp/README.md\n# Title\n\`\`\`python\nprint("hi")\n\`\`\`\n</args>` produces `args_raw == '/tmp/README.md\n# Title\nprint("hi")'` — the ` ```python ` / ` ``` ` fence lines are **silently deleted** from the file content that will be written to disk.
- The same input also loses its trailing newline via `.strip()`.

**Why it happens:** The fence-stripping regex was added (Phase 1) to handle models that wrap their *entire tool-call response* in a markdown code block (a real and common small-model behavior) — it was never designed for a tool whose payload is itself markdown/code containing fences.

**How to avoid:** Scope the fix to `write_file` specifically. Two viable approaches (planner should pick one and document the choice):
1. **Targeted unwrap, not global strip:** Before the regex runs, detect if the *entire* `content` string is wrapped in a single leading/trailing ` ``` ` fence pair (the Phase-1 case) and strip only those two delimiter lines — leave all *interior* fences (the write_file-content case) untouched. This requires restructuring `parse_response` so the unwrap happens once at the boundary, not via a global `re.sub`.
2. **Bypass fence-stripping entirely for `write_file`:** Extract `args_raw` for `write_file` from the *original* `content` (pre-`re.sub`), only applying fence-stripping/trimming logic to the `tool`/path-line portion, never to the content portion.

Either way, **do not `.strip()` the `file_content` portion of `args_raw`** — only `.strip()` the path line (first line). This is an MVP-acceptable but real fence-handling tradeoff; flag it in the plan as something to spot-check against actual small-model output (mirrors Phase 1's empirical tag-compliance validation).

**Note:** This pitfall is about content that *is present* in `content` but mangled by `parse_response`. It is fixable by changing the parser. Contrast with Pitfall 5, where content is truncated *before* `content` is even formed — not fixable by the parser at all.

**Warning signs:** A round-trip test (`read_file` a markdown file containing a fenced code block, ask the model to make a trivial edit, `write_file` it back) produces a file missing its code fences or missing its trailing newline.

### Pitfall 2: Hard-coded `if parsed["tool"] != "shell"` rejects new tools in both the normal loop and `--dry-run`

**What goes wrong:** `loop.py` has **two** places that gate on `parsed["tool"]`:
- Line 49 (`--dry-run` branch): `if parsed["tool"] != "shell": print(f"Model would call unknown tool '{parsed['tool']}'"); return`
- Line 84 (normal loop): `if parsed["tool"] != "shell": ... continue` (treats anything non-shell as "unknown tool")

If only the normal-loop branch is updated to recognize `read_file`/`write_file`, `--dry-run` will report `read_file`/`write_file` as "unknown tool" even after they're fully implemented — a regression in `--dry-run`'s usefulness (SAFE-01) for the new tools.

**Why it happens:** Both branches were written when `shell` was the only tool; the equality check was a reasonable shortcut at the time but doesn't scale to a tool dispatch table.

**How to avoid:** Update both branches. For `--dry-run`, add previews for `read_file` (e.g., "Step 1 would read: \<path\>") and `write_file` (e.g., "Step 1 would write to \<resolved path\> — would prompt for confirmation" / "auto-approved with --yes"), reusing the same path-resolution logic as the real dispatch so the preview is accurate.

**Warning signs:** `olla --dry-run "edit foo.py"` on a model that correctly emits `<tool>write_file</tool>...` prints "Model would call unknown tool 'write_file'" instead of a useful preview.

### Pitfall 3: Repetition guard's signature is shell-shaped (`("shell", tuple(argv))`)

**What goes wrong:** `loop.py` line 97: `sig = ("shell", tuple(argv))` — the repetition-guard signature is hard-coded to the shell tuple shape. If `read_file`/`write_file` dispatch branches are added as separate `elif` blocks *without* updating the signature logic, repeated identical `read_file(same_path)` or `write_file(same_path, same_content)` calls (a realistic small-model failure mode — re-reading the same file in a loop, or re-writing because it misjudged confirm-decline) won't be caught by LOOP-04's repetition guard.

**Why it happens:** The signature was written for the single-tool (shell) case; `("shell", tuple(argv))` was never intended as a general "tool call fingerprint."

**How to avoid:** Generalize the signature to `(tool_name, args_raw)` or `(tool_name, normalized_args)` computed once per step regardless of which tool branch executes, and check/update `prev_sig`/`repeat_count` before the tool-specific dispatch (or at a point common to all tool branches).

**Warning signs:** A small model stuck in a loop repeatedly calling `read_file(/tmp/x)` (e.g., misinterpreting its own output) runs for the full `--max-steps` instead of being caught by the 3x repetition guard.

### Pitfall 5: `</args>` as a stop-sequence means `write_file` can never produce content containing `</args>` — this is an inherent limitation, not a parser bug

**What goes wrong:** `call_model` passes `options={"stop": ["</args>", "Observation:"], "num_ctx": 8192}` (verified, `loop.py` line 26). Ollama's stop-sequence handling halts generation **the moment the model emits the `</args>` token sequence** — any content the model "intended" to write after that point is **never generated and never returned** to olla at all. This is a generation-time truncation, upstream of `parse_response` entirely.

This is a **distinct failure mode from Pitfall 1**: Pitfall 1's fence-stripping/`.strip()` corrupts content that *is* present in `content` but mangled by the parser — fixable by changing `parse_response`. This pitfall truncates content **before it exists** — no parser fix, however careful, can recover bytes the model was never allowed to generate. If the file the model is writing legitimately contains the literal 7-character substring `</args>` anywhere in its intended content, everything from that point onward is silently dropped, and `write_file` will write a truncated file with no error.

**Why it happens:** `</args>` was chosen as the stop-sequence so the model can't keep generating past a tool call and hallucinate its own `Observation:`/`<final>` (LOOP-02). This is correct and necessary for `shell`'s single-line command argument, where `</args>` appearing mid-content is essentially impossible. It becomes a hazard once `<args>` is overloaded to carry arbitrary multi-line file content (Pattern 1) — a payload type where `</args>` is no longer guaranteed absent.

**Prevalence note:** `</args>` is not a common substring in real-world files — HTML/XML use tags like `</div>`/`</body>`, not `</args>`. The realistic triggers are: (a) a file that documents olla's own tag format (e.g., this RESEARCH.md, or a README describing the `<args>`/`</args>` convention), (b) coincidental occurrence in generated/templated text, or (c) a model hallucinating/echoing the tag syntax into file content it's asked to write. Low-to-moderate frequency, but when it happens the failure is **silent and unrecoverable** — no error observation, just a truncated file written to disk after user confirmation of what looked like a normal write.

**Confidence note:** The literal `stop` list configuration is `[VERIFIED: codebase]` (HIGH — `loop.py` line 26). The generation-time halt mechanism itself is reasoned from Ollama's documented stop-sequence semantics and was NOT independently confirmed via a live model trace in this session — tag as MEDIUM confidence for the exact halt behavior, HIGH confidence that *some* truncation occurs given the stop list includes `</args>`.

**How to avoid:** This is a **design-level limitation of the chosen encoding/stop-sequence combination**, not something `parser.py` can fix. Real remedies are planner/discuss-phase decisions, not code tasks for this phase alone:

1. **Accept and document the limitation** (recommended for MVP): note in `prompts.py`/developer docs that `write_file` content must not contain the literal substring `</args>`; this is a narrow edge case unlikely to affect typical code/config/doc files.
2. **Detect truncation heuristically and warn:** no reliable "generation stopped early" signal is exposed by this client usage (`response["message"]["content"]` gives no indication of *why* generation stopped) — likely not worth building for v1.
3. **Rework the stop-sequence/encoding scheme** (out of scope for this phase, costly): e.g., a different closing delimiter for `write_file` specifically — but this reintroduces the "model doesn't know its own tool before generation completes" problem (Alternatives Considered), and changing `</args>` removes the LOOP-02 protection for `shell`.

**Recommendation for this phase:** option 1 (accept + document) is the pragmatic choice — add a one-line caveat to `prompts.py` or developer docs. Do not attempt a parser-side fix for this specific issue; conflating it with Pitfall 1's fix would give false confidence (a parser fix tested against hand-constructed `parse_response(content)` strings would pass, while the real failure occurs at the Ollama generation boundary, before `content` exists, and is invisible to such tests).

**Warning signs:** A `write_file` call succeeds (no error observation) but the written file is shorter than expected, cut off exactly at or before a point where `</args>` would have appeared in the intended content. Round-trip tests using hand-constructed `parse_response` inputs (as used to verify Pitfall 1) will NOT catch this — they bypass `call_model`/Ollama entirely and thus can't reproduce the generation-time truncation.

### Pitfall 4: Treating `Path.resolve()` as a security boundary instead of a display aid

**What goes wrong:** It's tempting — especially given ASVS V12/path-traversal guidance from general web sources — to add a containment check (`resolved.is_relative_to(Path.cwd())`, or a "jail" directory) and BLOCK/refuse writes outside it. This would be **inconsistent** with the project's existing safety model: the shell tool (already shipped, Phase 1-2) can write anywhere on the filesystem the user can (via `tee /etc/foo`, `cp`, `python3 -c "open('/etc/foo','w').write(...)"`, etc.), gated only by the same confirm prompt. A `write_file`-only path jail would block `write_file(/etc/foo)` while `<tool>shell</tool><args>tee /etc/foo</args>` (CONFIRM tier, not even blocklisted) sails through — security theater that confuses users about what's actually protected.

**Why it happens:** Generic "prevent path traversal" guidance (the top web-search results for this topic) assumes a web-server context where the file tool is the *only* filesystem access surface. That assumption doesn't hold here — `write_file` is one of several ways the agent can touch the filesystem, and the others are already covered by the confirm-gate.

**How to avoid:** Use `Path(path).resolve()` purely to **show the user the real target** in the confirm prompt (so `write_file(../../etc/foo)` displays as `/etc/foo`, not the literal relative string) — this is disclosure, satisfying SC2 ("resolved path shown in the prompt"), not enforcement. Do not add a BLOCK/refuse path for "outside cwd" or similar. The confirm prompt *is* the boundary, exactly as REQUIREMENTS.md's Out of Scope section states for the project as a whole.

**Warning signs:** A plan task says "validate the resolved path is within the project directory" or "reject writes outside `cwd`" — this contradicts the project's stated safety model and should be flagged in plan review.

## Code Examples

### `tools/files.py` — read_file and write_file (new module)

```python
# Source: mirrors src/olla/tools/shell.py error-handling style (read 2026-06-14);
# pathlib API per Python 3.10+ stdlib docs (docs.python.org/3/library/pathlib.html)
"""File tools: read/write text files via pathlib, errors-as-dict per ToolResult."""

from pathlib import Path

from olla.tools.base import ToolResult


def read_file(path: str) -> ToolResult:
    """Read a text file's full contents.

    Returns {"content": str} on success, or {"error": str} if the file
    does not exist, is a directory, or cannot be decoded as UTF-8.
    Truncation for large files is the caller's (loop.py's) responsibility,
    mirroring how shell stdout/stderr truncation is applied in run_loop.
    """
    p = Path(path)
    try:
        content = p.read_text(encoding="utf-8")
        return {"content": content}
    except FileNotFoundError:
        return {"error": f"file not found: {path}"}
    except IsADirectoryError:
        return {"error": f"is a directory, not a file: {path}"}
    except PermissionError:
        return {"error": f"permission denied: {path}"}
    except UnicodeDecodeError:
        return {"error": f"cannot decode as UTF-8 (binary file?): {path}"}


def write_file(path: str, content: str) -> ToolResult:
    """Write `content` to `path`, creating the file (or overwriting it).

    Returns {"bytes_written": int, "path": str} on success, or {"error": str}
    on PermissionError / parent-directory-missing / etc. Caller (loop.py) is
    responsible for the confirm-gate -- this function performs the write
    unconditionally once called.
    """
    p = Path(path)
    try:
        p.write_text(content, encoding="utf-8")
        return {"bytes_written": len(content.encode("utf-8")), "path": str(p.resolve())}
    except FileNotFoundError:
        return {"error": f"parent directory does not exist: {path}"}
    except IsADirectoryError:
        return {"error": f"is a directory, not a file: {path}"}
    except PermissionError:
        return {"error": f"permission denied: {path}"}
```

Note: `ToolResult` (in `tools/base.py`) is `TypedDict, total=False` with fields `argv, returncode, stdout, stderr, error` — `content`, `bytes_written`, `path` are new fields not currently declared. The planner should extend `ToolResult` (or define a file-tool-specific TypedDict) to keep type hints accurate; `total=False` makes this additive and non-breaking.

### `prompts.py` — extended SYSTEM_PROMPT (illustrative, planner should tune wording for token budget)

```python
# Source: extends src/olla/prompts.py (read 2026-06-14), encoding per Pattern 1 above
SYSTEM_PROMPT = """You are a helpful assistant that completes tasks using tools.

Available tools:

- shell: <tool>shell</tool><args>the raw shell command to run</args>
- read_file: <tool>read_file</tool><args>/path/to/file</args>
- write_file: <tool>write_file</tool><args>/path/to/file
the full new file contents go here, on the lines after the path
</args>

For write_file, the FIRST LINE of <args> is the file path; everything after
the first newline is the exact file content to write. Do not include the
literal text "</args>" anywhere in the file content -- it will cut off the
write early.

When you have the final answer, respond with:
<final>your answer text here</final>

Only output one tag block per turn.
"""
```

The exact wording is a planner/discuss-phase concern (token-budget tuning for 0.6B-4B models per the project's core value), but the **encoding rule and the `</args>` caveat must be stated explicitly and with an example**, since for small models the prompt is the only "schema" they have.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.path.join`/`os.path.normpath` string manipulation for paths | `pathlib.Path` object-oriented API (`.resolve()`, `.read_text()`, `.write_text()`) | `pathlib` since Python 3.4 (2014); now the unambiguous stdlib default | `tools/files.py` should use `pathlib` throughout — `safety.py` already mixes `os.path.normpath` (for slash-normalization edge cases) and could stay as-is, but new file-tool code should prefer `pathlib` |

**Deprecated/outdated:** Nothing in this domain is deprecated — `pathlib`/`open()` are stable, current stdlib APIs with no pending changes affecting this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Path-on-first-line / content-is-remainder is the best encoding for `write_file`'s two arguments within the existing `<args>` tag and `</args>` stop-sequence constraints | Architecture Patterns Pattern 1, Alternatives Considered, Pitfall 5 | **Elevated from "Low" given Pitfall 5's concrete failure case:** any encoding that uses `</args>` as both the closing delimiter AND the stop-sequence has a hard edge where file content containing the literal substring `</args>` is silently truncated at generation time. This is not unique to the first-line-path encoding — any single-`<args>`-block encoding shares it. An alternative encoding (e.g., a sentinel delimiter line like `---CONTENT---` between path and content) does NOT remove this edge, since `</args>` is still the stop-sequence regardless of internal structure. Residual risk is therefore inherent to the `</args>`-stop-sequence + single-tag-payload combination, not specific to A1's chosen split point. Low-to-moderate real-world frequency (see Pitfall 5 prevalence note), but the failure mode is silent — recommend documenting (Pitfall 5 option 1) rather than treating A1 itself as wrong. |
| A2 | Targeted fence-unwrap (Pitfall 1, option 1 or 2) is feasible to implement in `parser.py` without breaking Phase 1's existing fence-stripping behavior for `shell`/`final` tags | Pitfall 1 | If the fix is harder than expected (e.g., models emit inconsistent/nested fence patterns), the planner may need to scope Phase 3 to "best-effort" fence handling and document the limitation, similar to Phase 1's tag-compliance smoke test approach (empirical validation against real small models recommended). |
| A3 | `read_file`/`write_file` are single-`<args>`-block tools (no second tag needed) is achievable given the current `["</args>", "Observation:"]` stop-sequence — verified by reading `loop.py`'s `call_model`, not just assumed | Architecture Patterns Pattern 1 | Low risk — this is `[VERIFIED: codebase]`, not assumed. Listed here only because the *consequence* (single-`<args>` encoding) is the load-bearing design choice this whole phase depends on, and that same load-bearing choice is what makes Pitfall 5 reachable. |

**Note:** A1 and A2 are design recommendations with MEDIUM confidence (no external authority validates "best" small-model tool-encoding — this is project-specific). A3 is HIGH confidence (verified against `loop.py` source). Neither A1 nor A2 represents a hallucinated package/API — both concern in-repo design choices the planner/discuss-phase should confirm or adjust based on early testing against the project's target models (mirrors Phase 1's SC6 empirical validation pattern).

## Open Questions

1. **How should `parse_response` be restructured to fix Pitfall 1 (fence-stripping/`.strip()` corruption of `write_file` content) without regressing Phase 1's fence-tolerance for `shell`/`final` tags?**
   - What we know: the current global `re.sub` and `.strip()` are verified (empirically, 2026-06-14) to corrupt `write_file` content containing fences or relying on trailing whitespace/newlines.
   - What's unclear: whether a single targeted-unwrap regex is sufficient, or whether `parse_response` needs a tool-aware branch (extract `args_raw` differently for `write_file` vs. `shell`/other tools).
   - Recommendation: planner should design this as its own task with explicit before/after test cases (a markdown file with embedded fences, a file requiring a trailing newline), and treat it as the phase's highest-risk *code* task — possibly sequenced first since `read_file`/`write_file` dispatch and the system prompt both depend on the encoding being correct.

2. **What size threshold should trigger `read_file` truncation, and should it match `MAX_OBSERVATION_CHARS` (2000) exactly, or differ for file content vs. shell output?**
   - What we know: `loop.py`'s `truncate_output(text, limit=MAX_OBSERVATION_CHARS)` defaults to 2000 chars, head+tail split.
   - What's unclear: whether 2000 chars is appropriate for file content (often more line-structured/predictable than shell output) — e.g., a head+tail split of a 500-line Python file may produce a confusing "head of file ... tail of file" view that omits the middle entirely, vs. shell output where head+tail of a long log is more naturally useful.
   - Recommendation: reuse `truncate_output` with the existing constant for MVP consistency (Don't Hand-Roll); if the planner wants file-specific truncation (e.g., "first N lines + last N lines" instead of "first N chars + last N chars"), that's a reasonable v2 refinement but adds complexity not required by FILE-01's stated success criterion ("truncated if oversized so it cannot blow the context window" — char-based truncation already satisfies this).

3. **Should `write_file` create missing parent directories, or fail with an error observation?**
   - What we know: `Path.write_text()` raises `FileNotFoundError` if the parent directory doesn't exist (verified: this is standard `pathlib`/`open()` behavior, not olla-specific).
   - What's unclear: whether the project wants `write_file` to `mkdir(parents=True)` automatically (convenience, but a write_file call could now create an arbitrary directory tree as a side effect of a single confirm) or surface the error and let the model retry (e.g., emit a `shell` `mkdir -p` call first, which would itself go through the shell CONFIRM gate).
   - Recommendation: fail with an error observation (`{"error": "parent directory does not exist: ..."}`) for MVP — this is the smaller, more auditable side effect, and is consistent with "every action the user sees in the confirm prompt is the action that happens" (auto-creating directories as a side-effect of a file-write confirm could surprise the user). The model can recover by issuing a `shell` `mkdir -p` command, which gets its own confirm prompt.

4. **Is the `</args>`-in-content stop-sequence truncation (Pitfall 5) something the project is willing to accept for v1, or does it need to be surfaced to the user during `/gsd:discuss-phase`?**
   - What we know: `loop.py`'s `call_model` literally passes `</args>` as a stop-sequence (HIGH confidence, verified). Content containing that substring will be truncated at generation time (MEDIUM confidence on the exact mechanism — reasoned from Ollama's documented stop-sequence semantics, not live-traced).
   - What's unclear: whether this needs a live-model trace to confirm before planning proceeds, or whether documenting-and-accepting (option 1) is sufficient to unblock the plan.
   - Recommendation: treat as accept-and-document for v1 (add the caveat to `SYSTEM_PROMPT`/docs as shown in Code Examples). If `/gsd:discuss-phase` surfaces this and the user wants stronger guarantees, that's a scope decision affecting the stop-sequence design (LOOP-02) more broadly, not just Phase 3 — flag for cross-phase awareness rather than blocking Phase 3 planning.

## Environment Availability

Not applicable — this phase has no external dependencies (no new packages, no external services/CLIs beyond what Phases 1-2 already established). `pathlib`/`open()` are part of the Python interpreter itself.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 (already a dev dependency, per `pyproject.toml`) |
| Config file | none — pytest auto-discovers `tests/` (existing convention: `tests/test_*.py`, `tests/test_tools/test_*.py`) |
| Quick run command | `pytest tests/test_tools/test_files.py tests/test_loop.py -x` |
| Full suite command | `pytest` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FILE-01 | `read_file(path)` returns file contents | unit | `pytest tests/test_tools/test_files.py::test_read_file_success -x` | Wave 0 |
| FILE-01 | Oversized file content is truncated before reaching model context | unit | `pytest tests/test_loop.py::test_run_loop_read_file_truncates_large_output -x` | Wave 0 |
| FILE-01 | `read_file` on missing/unreadable file returns an error Observation, not an exception | unit | `pytest tests/test_tools/test_files.py::test_read_file_not_found -x` | Wave 0 |
| FILE-02 | `write_file(path, content)` writes content to disk only after confirm approval | unit/integration | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_approved -x` | Wave 0 |
| FILE-02 | `write_file` confirm prompt shows the resolved path (SC2) | unit | `pytest tests/test_loop.py::test_run_loop_write_file_shows_resolved_path -x` | Wave 0 |
| FILE-02 | Declining the `write_file` confirm prompt performs no write | unit | `pytest tests/test_loop.py::test_run_loop_write_file_confirm_declined -x` | Wave 0 |
| FILE-02 | `--yes` skips the `write_file` confirm prompt | unit | `pytest tests/test_loop.py::test_run_loop_write_file_yes_skips_prompt -x` | Wave 0 |
| FILE-02 | `write_file` content survives parser round-trip (fences, trailing newline) — Pitfall 1 fix | unit | `pytest tests/test_parser.py::test_write_file_args_preserve_fences_and_newline -x` | Wave 0 |
| SC3 (read->modify->write end-to-end) | A `read_file` then `write_file` sequence completes via `run_loop` | integration | `pytest tests/test_loop.py::test_run_loop_read_then_write_end_to_end -x` | Wave 0 |
| `--dry-run` for new tools (Pitfall 2 regression) | `--dry-run` previews `read_file`/`write_file` instead of "unknown tool" | unit | `pytest tests/test_loop.py::test_dry_run_previews_read_file` / `test_dry_run_previews_write_file -x` | Wave 0 |
| Repetition guard generalization (Pitfall 3) | Repeated identical `read_file`/`write_file` calls trigger the 3x guard | unit | `pytest tests/test_loop.py::test_run_loop_repetition_guard_covers_file_tools -x` | Wave 0 |

**Note on Pitfall 5:** no automated test can validate the `</args>`-in-content generation-time truncation without a live Ollama call (mocked `ollama.chat` responses bypass the stop-sequence mechanism entirely). This is documented as a known limitation (prompt caveat), not a tested behavior — do not add a Wave 0 gap for it.

### Sampling Rate

- **Per task commit:** `pytest tests/test_tools/test_files.py tests/test_parser.py tests/test_loop.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tools/test_files.py` — new file, covers FILE-01/FILE-02 unit tests for `tools/files.py::read_file`/`write_file` (use `tmp_path` fixture, mirroring `tests/test_tools/test_shell.py`'s style)
- [ ] Extend `tests/test_parser.py` — add cases for `write_file` path/content split, fence preservation, trailing-newline preservation (Pitfall 1)
- [ ] Extend `tests/test_loop.py` — add `read_file`/`write_file` dispatch tests mirroring the existing shell CONFIRM-tier tests (`mocker.patch("olla.loop.Confirm.ask", ...)`, `mocker.patch("olla.tools.files.read_file"/"write_file", ...)` or real `tmp_path` I/O — planner's choice), plus `--dry-run` and repetition-guard coverage for the new tools
- [ ] No new fixtures/conftest needed — `tmp_path` (pytest builtin) and `mocker` (`pytest-mock`, already a dev dependency) cover all new test needs

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` (from `.planning/config.json`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — local single-user CLI, no auth surface |
| V3 Session Management | No | N/A — no sessions |
| V4 Access Control | No | N/A — no multi-user access control; OS file permissions are the only access boundary, already enforced by the kernel regardless of olla |
| V5 Input Validation | Yes | `read_file`/`write_file` paths are passed to `pathlib.Path`/`open()` without shell interpretation (no `shlex`/`subprocess` involved for file tools — eliminates injection vectors that apply to `SHELL-01`). `Path(path).resolve()` normalizes the path for **display** before the confirm prompt (SC2), satisfying "show the user what will actually happen" without claiming to be a containment boundary (see Pitfall 4). |
| V6 Cryptography | No | N/A — no crypto operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal (`write_file(../../etc/cron.d/evil)`) leading to writes outside the intended directory | Tampering | `Path.resolve()` shown in the confirm prompt (SC2) so the user sees the *true* target before approving; the confirm-gate is the boundary (not a path jail — see Pitfall 4), consistent with the project's existing shell-tool safety model |
| Symlink-based write redirection (`write_file(innocuous_name)` where `innocuous_name` is a symlink to a sensitive file) | Tampering | `Path.resolve()` follows symlinks, so the confirm prompt shows the real symlink target, giving the user the information needed to decline |
| Overwriting an existing file without the user realizing it's an overwrite vs. a new file | Tampering / Repudiation | Optional enhancement (not required by FILE-02's stated success criteria): the confirm prompt could note "(overwriting existing file)" vs "(new file)" by checking `Path(path).exists()` before prompting — low cost, improves disclosure. Planner's discretion; not a blocker. |
| Model-driven write to a `.py`/shell-config file later executed by the shell tool (write-then-exec chain) | Elevation of Privilege | Out of scope for Phase 3 specifically — this is the general "agent can write a script and then ask to run it" pattern already implicitly possible via `shell` + `tee`/`cat heredoc` even before `write_file` exists. The confirm-gate on *both* the write and the subsequent `shell` execution (SAFE-04, already shipped) is the existing mitigation; Phase 3 doesn't change this risk profile, only makes the write step more ergonomic for the model. |
| Silent content truncation at the `</args>` stop-sequence boundary (Pitfall 5) causing an incomplete file to be written without error | Tampering (unintentional) / Repudiation | Document the `</args>` caveat in `SYSTEM_PROMPT` (Code Examples); no code-level mitigation available within this phase's scope (see Pitfall 5) |

## Sources

### Primary (HIGH confidence)
- `/home/nacs/Documents/git/olla/src/olla/loop.py` (read 2026-06-14) — `run_loop`, `call_model` stop-sequence wiring (`options={"stop": ["</args>", "Observation:"], "num_ctx": 8192}`, line 26), `truncate_output`, existing shell CONFIRM/ALLOW/BLOCK dispatch, `--dry-run` branch
- `/home/nacs/Documents/git/olla/src/olla/safety.py` (read 2026-06-14) — `Decision` TypedDict, `check()` signature and rule table (confirmed shell-argv-only, no path concept)
- `/home/nacs/Documents/git/olla/src/olla/parser.py` (read 2026-06-14) — `parse_response`, fence-stripping regex, `.strip()` on `args_raw`, and `ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)` — empirical traces (Bash, 2026-06-14) confirming (a) corruption of `write_file`-style content by fence-stripping/`.strip()` (Pitfall 1), and (b) `ARGS_RE`'s non-greedy match stops at the first `</args>` in a hand-constructed string (informs but does not by itself establish Pitfall 5 — the generation-time mechanism is the primary cause; `ARGS_RE`'s behavior on a hypothetically-fed full string is secondary/incidental)
- `/home/nacs/Documents/git/olla/src/olla/tools/shell.py` and `src/olla/tools/base.py` (read 2026-06-14) — `ToolResult` contract, error-as-dict pattern
- `/home/nacs/Documents/git/olla/tests/test_loop.py` and `/home/nacs/Documents/git/olla/tests/test_tools/test_shell.py` (read 2026-06-14) — existing test patterns for CONFIRM-tier dispatch (`mocker.patch("olla.loop.Confirm.ask", ...)`) and tool-result assertions
- `/home/nacs/Documents/git/olla/.planning/REQUIREMENTS.md` (read 2026-06-14) — FILE-01/FILE-02 wording, SAFE-04's explicit mention of `write_file`, Out-of-Scope items (JSON tool schema, sandboxing) that constrain the design
- Python 3 stdlib docs, `pathlib` (`docs.python.org/3/library/pathlib.html`) — `Path.resolve()` behavior on nonexistent paths (verified via Bash, 2026-06-14: returns an absolute normalized path without requiring the target to exist), `is_relative_to` availability (3.9+, within project's 3.10 floor)

### Secondary (MEDIUM confidence)
- WebSearch "python pathlib resolve path traversal prevent agent file write safety check" — general containment-check guidance (`is_relative_to`), used here only to identify and **reject** the path-jail approach as inconsistent with this project's existing safety model (Pitfall 4); the guidance itself is sound for its intended (web-server) context but doesn't transfer directly
- Ollama stop-sequence semantics (training knowledge of `options.stop` halting generation at the matched sequence) — used for Pitfall 5's generation-time mechanism. Not independently re-verified via live Ollama call or official docs fetch in this session; flagged MEDIUM confidence accordingly (see Pitfall 5 Confidence note and Open Question 4).

### Tertiary (LOW confidence)
- None — no unverified claims used in final recommendations without an explicit confidence flag

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib-only, no version/availability uncertainty
- Architecture: HIGH — dispatch points, stop-sequence constraint, and `ToolResult`/`Confirm.ask` patterns all verified against actual source files read in this session
- Pitfalls: HIGH for Pitfalls 2-4 (verified against source); MEDIUM for Pitfall 1's *fix* (the corruption itself is empirically verified HIGH, but the best fix approach is a design choice — flagged in Assumptions Log A2); MEDIUM for Pitfall 5 (the stop-sequence config is HIGH/verified, but the exact generation-time halt mechanism is reasoned, not live-traced — flagged in Open Question 4)

**Research date:** 2026-06-14
**Valid until:** Effectively indefinite for the stdlib portions (pathlib/open are stable); the parser-fix design (Pitfall 1) and the stop-sequence limitation (Pitfall 5) should be revisited if Phase 1's smoke-test (01-02) is re-run against new target models, since both fence-handling and stop-sequence-truncation behavior are model-dependent
