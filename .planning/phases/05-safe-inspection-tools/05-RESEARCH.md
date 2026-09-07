# Phase 5: Safe Inspection Tools - Research

**Researched:** 2026-09-08
**Domain:** Read-only filesystem inspection tools (directory listing + regex grep) for a small-model ReAct CLI agent, dispatched without confirmation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**list_dir output format**
- D-01: List a single directory level per call (no recursion). The model recurses by calling `list_dir` again on a subdirectory it wants to explore deeper.
- D-02: File sizes shown human-readable (`1.2K`, `3.4M`), matching `ls -lh` convention.
- D-03: Entries sorted alphabetically, directories first.
- D-04: Symlinks shown as their own type (`[l] name -> target`), never followed/resolved — avoids symlink loops and matches read-only intent.
- D-05: Hidden dotfiles (`.env`, `.git`, ...) are shown by default (`ls -a` behavior, not plain `ls`) — they count toward the 50-entry cap.

**grep_files matching semantics**
- D-06: `grep_files(pattern, path, recursive=False)` — single directory by default; pass `recursive=True` in `<args>` to search subdirectories. New third parameter must be documented in `src/olla/prompts.py`.
- D-07: Pattern matching is case-sensitive (Python `re` default semantics, no surprise case-folding).
- D-08: Binary file detection via null-byte sniff on the first ~8KB of each candidate file (same heuristic grep/git use) — no file-extension allowlist to maintain. `.git` directory is excluded outright per INSPECT-02.

**Safety dispatch mechanism**
- D-09: `list_dir`/`grep_files` bypass `safety.check()` entirely — `run_loop()` dispatches straight to their tool adapters, exactly like `read_file` today. No new tool-name branch is added to `src/olla/safety.py`; that module stays scoped to shell argv classification. — **Reversibility:** costly — if a future requirement needs central ALLOW/CONFIRM/BLOCK policy over non-shell tools, this decision would need `safety.check()` to grow a tool-name-aware signature and every existing call site to be revisited.
- D-10: No path pre-validation. Let `FileNotFoundError`/`NotADirectoryError` surface as a `ToolResult` error dict, matching the existing `read_file()`/`write_file()` convention in `src/olla/tools/files.py`.

**Truncation & cap behavior**
- D-11: When results exceed the cap (50 entries for `list_dir`, 25 matches for `grep_files`), truncate and append a trailing note, e.g. `... (+12 more, not shown)`, so the model knows output was cut and can narrow its query.
- D-12: Entries/matches kept are the first N in natural scan order (`os.scandir`/`os.walk` order, then sorted per D-03 for `list_dir`) — no extra ranking pass across the full result set.

### Claude's Discretion
- Exact wording of the `(+N more)` truncation note.
- Internal helper structure for the null-byte binary sniff and `.git` exclusion (e.g., shared helper vs inline check) — implementation detail, no user preference expressed.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INSPECT-01 | `list_dir(path)` tool lists directory entries with `[d]`/`[f]` indicator, names, and sizes, capped at 50 entries | See "Standard Stack", "Architecture Patterns: list_dir", "Code Examples" |
| INSPECT-02 | `grep_files(pattern, path)` tool performs regex search across text files (ignoring `.git` and binary files), returning up to 25 matches with file:line | See "Architecture Patterns: grep_files", "Common Pitfalls", "Code Examples" |
| INSPECT-03 | `safety.check()` classifies inspection tools as `ALLOW`, executing without interactive confirmation prompts | Confirmed as D-09: dispatch bypasses `safety.check()` entirely rather than adding an ALLOW branch there — see "Architecture Patterns: Safety Dispatch" for why this still satisfies the requirement's intent |

</phase_requirements>

## Summary

This phase is **pure Python standard library** — `os`, `pathlib`, `re`, `stat`. No new third-party dependency is introduced, so the Package Legitimacy Gate and version-pinning steps are not applicable this phase. The two new tools follow the exact adapter shape already established by `src/olla/tools/files.py` (`ToolResult`-returning, exception-catching, no raising) and are dispatched from `src/olla/loop.py` exactly like `read_file` — unconfirmed, no `safety.check()` involvement.

The one design gap CONTEXT.md leaves open is the **wire format** for `grep_files`'s three arguments (`pattern`, `path`, `recursive`). `src/olla/parser.py` only special-cases opaque multi-line payloads for `{"write_file", "remember", "recall"}`; every other tool name (including `read_file`, `shell`, and — unless a parser change is made — `grep_files`) goes through the generic branch, which requires exactly one `<tool>`/`<args>` pair and returns `args_raw.strip()` with internal newlines intact [VERIFIED: src/olla/parser.py:159-164 — `args_raw = content[args_open.end() : args_end]\n    return {\n        "type": "tool",\n        "tool": tool,\n        "args_raw": args_raw.strip(),\n    }`]. This means a **line-based** format (line 1 = pattern, line 2 = path, optional line 3 = `recursive=true`) parses correctly today with **zero parser changes for the tag-detection logic** — but `str.strip()` only trims whitespace from the very start and end of the *entire* `args_raw` string, not per-line. Since `pattern` would sit on line 1 (the start of the string), any regex the model writes with meaningful **leading** whitespace (e.g. `    return` to match an indented line) would have that leading whitespace silently stripped before `grep_files` ever sees it — a real limitation, not a hypothetical one, and it is unresolved by CONTEXT.md. See Pitfall 4 and Open Question 1 for the two ways to handle it. A space/comma-delimited single-line format is fragile for a different reason (grep patterns and paths routinely contain spaces). This research recommends the line-based format as the better of the two, but flags the whitespace-stripping caveat as something the planner must explicitly decide how to handle, not something "no change expected" fully covers.

The other cross-cutting insight from the existing codebase (`_execute_read_file`'s `untrusted_observation_seen` return value, `_record_file_observation`'s untrusted-content tagging) is that **directory names and grep match content are attacker-influenceable data**, exactly like file content read via `read_file`. D-09 only says these tools skip the *execute-confirmation* gate (`safety.check()`); it does not exempt their *output* from the project's existing untrusted-observation tagging that revokes `--yes` auto-bypass on the next destructive shell/write action. The plan should wire `list_dir`/`grep_files` results through the same untrusted-observation path `read_file` already uses, not the plain `_record_observation` path used for memory/shell-blocked messages.

**Primary recommendation:** Add `src/olla/tools/inspect.py` (or two focused modules) with `list_dir(path)` and `grep_files(pattern, path, recursive=False)` following the exact `ToolResult`/exception-catching shape of `read_file`; dispatch both from `run_loop()`/`_prepare_action()` as new unconfirmed branches parallel to `read_file`, using `_resolve_file_path()` for path resolution and the existing untrusted-observation recording path for output.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Directory entry listing (`list_dir`) | Tool Infrastructure (`src/olla/tools/`) | — | Pure host-filesystem I/O; must stay a thin adapter per the existing "Tool Infrastructure" layer boundary (ARCHITECTURE.md) |
| Regex file search (`grep_files`) | Tool Infrastructure (`src/olla/tools/`) | — | Same as above; no policy or confirmation logic belongs in the adapter |
| Dispatch / no-confirm routing | Application Orchestration (`src/olla/loop.py`) | — | `run_loop()` already owns all tool dispatch, confirmation-skip, and observation formatting; new tools plug into `_prepare_action()`/execute-branch structure, not a new layer |
| "Is this tool auto-approved?" classification | Policy (bypassed, per D-09) | — | D-09 deliberately keeps `src/olla/safety.py` scoped to shell argv; INSPECT-03's "ALLOW" intent is satisfied by loop.py's dispatch choice, not a new safety.py branch |
| Protocol documentation (tool names/args) | Model Protocol (`src/olla/prompts.py`) | — | `SYSTEM_PROMPT` is the single source of truth teaching the model the tag contract; must be updated for both new tools including the new `recursive` param |
| Untrusted-output tagging | Application Orchestration (`src/olla/loop.py`) | — | `untrusted_observation_seen` bookkeeping is loop-local state; the tool adapters must not themselves decide trust status |

## Standard Stack

### Core
No third-party packages. Everything below is Python standard library, already available given the project's `>=3.10` floor (`pyproject.toml` `requires-python = ">=3.10"`) [VERIFIED: pyproject.toml:8 — `requires-python = ">=3.10"`].

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `os` (stdlib) | bundled | `os.scandir()` for single-level directory listing, `os.walk()` for recursive grep traversal, `os.DirEntry` type-checking | Fastest, allocation-light directory iteration API; `DirEntry.is_dir()/is_file()/stat()` default to `follow_symlinks=True` and must be called with `follow_symlinks=False` to inspect the entry itself [CITED: docs.python.org/3/library/os.html#os.scandir — "DirEntry.is_dir(): ... follow_symlinks parameter default: True ... If follow_symlinks is False, return True only if this entry is a directory (without following symlinks)."] |
| `pathlib` (stdlib) | bundled | Already the project's path-handling convention (`Path(path).resolve()` in `loop.py`) | Matches `_resolve_file_path()`'s existing pattern [VERIFIED: src/olla/loop.py:111-117 — `def _resolve_file_path(path: str) -> tuple[Path | None, str | None]: ... return Path(path).resolve(), None`] |
| `re` (stdlib) | bundled | Regex compilation and line matching for `grep_files` | D-07 locks case-sensitive default `re` semantics; no flags needed |
| `stat` (stdlib) | bundled | `stat.S_ISDIR`/`stat.S_ISREG` mode-bit checks, already imported in `src/olla/tools/files.py` | Reuse the existing convention rather than introducing `os.path.isdir`/`isfile` (which follow symlinks implicitly and would violate D-04) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | — | No new supporting libraries required this phase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `os.scandir()` + manual type/size formatting | `Path.iterdir()` + `Path.stat()` | `iterdir()`/`Path.stat()` is more idiomatic pathlib but issues a fresh `lstat`/`stat` syscall per entry per property access (no caching like `DirEntry`); for a 50-entry cap this is a negligible cost either way, so this is a style choice — `os.scandir()` is recommended only because the size/mode reasoning is simpler with `DirEntry.stat(follow_symlinks=False)` returning a single cached `os.stat_result` reused for both mode and size. |
| Python `re` module | Third-party `regex` package | Not needed: `re` fully covers D-07's semantics (plain Python regex, case-sensitive). Adding `regex` would be an unnecessary dependency for a project whose STACK.md already commits to minimal deps. |
| Manual binary-sniff via null-byte check | `python-magic` / `filetype` (MIME sniffing libraries) | D-08 explicitly locks the null-byte heuristic ("no file-extension allowlist to maintain"); a MIME-sniffing library is heavier, adds a dependency, and doesn't match D-08's stated rationale. Do not introduce. |

**Installation:** None — no new dependencies to install this phase.

**Version verification:** N/A — no external packages. All APIs used (`os.scandir`, `os.walk`, `os.DirEntry`, `re`, `stat`) are part of Python's standard library and unaffected by the project's `>=3.10` floor.

## Package Legitimacy Audit

**Not applicable this phase.** `list_dir` and `grep_files` are implemented entirely with Python standard library modules (`os`, `pathlib`, `re`, `stat`). No `pip install` / `pyproject.toml` dependency changes occur — the existing `dev` dependency group [VERIFIED: pyproject.toml:23-28 — `[project.optional-dependencies]\ndev = [\n    "pytest>=8",\n    "pytest-mock>=3.14",\n    "ruff",\n]`] is unaffected. The Package Legitimacy Gate protocol is skipped because there are no external packages to check.

**Packages removed due to [SLOP] verdict:** none (N/A — no packages evaluated)
**Packages flagged as suspicious [SUS]:** none (N/A — no packages evaluated)

## Architecture Patterns

### System Architecture Diagram

```text
Model output (XML tags)
        │
        ▼
parse_response()  [src/olla/parser.py — UNCHANGED]
  generic branch: exactly one <tool>/<args> pair,
  args_raw.strip() (internal newlines preserved)
        │
        ▼
_prepare_action()  [src/olla/loop.py]
  new branches: tool == "list_dir" | "grep_files"
  resolve path(s) via _resolve_file_path() (D-10: resolve only, no existence check)
  for grep_files: split args_raw on "\n" → pattern / path / recursive flag
        │
        ▼
run_loop() dispatch  [src/olla/loop.py]
  D-09: NO safety.check() call — straight to adapter, same tier as read_file
        │
        ├──────────────┐
        ▼              ▼
_execute_list_dir   _execute_grep_files   [NEW, loop.py — parallel to _execute_read_file]
        │              │
        ▼              ▼
list_dir(path)      grep_files(pattern, path, recursive)   [NEW, src/olla/tools/inspect.py]
  os.scandir(path)      os.scandir(path)  (recursive=False)
  sort: dirs first,     or os.walk(path, followlinks=False)  (recursive=True),
    then alpha (D-03)     pruning ".git" from dirnames in place
  cap 50 (D-11/D-12)    per-file: null-byte sniff first ~8KB (D-08)
  → ToolResult           regex search matching lines, cap 25 (D-11/D-12)
        │              │
        ▼              ▼
        Host filesystem (read-only: os.scandir/os.walk/open(rb))
        │              │
        └──────┬───────┘
               ▼
_record_file_observation() [REUSE, loop.py]
  tags output as <untrusted_file_content>, sets untrusted_observation_seen=True
  (directory/file names and grep match text are attacker-influenceable, same as read_file content)
        │
        ▼
messages.append({"role": "tool", "content": "Observation: <untrusted_file_content>...})
        │
        ▼
Next model turn
```

### Recommended Project Structure
```
src/olla/
├── tools/
│   ├── inspect.py       # NEW — list_dir() and grep_files() adapters (or split into
│   │                    #   list_dir.py + grep_files.py if the plan prefers one
│   │                    #   concern per file; either satisfies CONVENTIONS.md's
│   │                    #   "focused modules under tools/" rule)
│   ├── base.py           # ToolResult — reuse as-is, no new fields required
│   ├── files.py          # UNCHANGED — pattern reference only
│   └── shell.py          # UNCHANGED
├── loop.py                # add _prepare_action branches, _execute_list_dir,
│                           #   _execute_grep_files, dispatch in run_loop()
├── prompts.py              # document list_dir/grep_files tag contract + recursive param
└── parser.py               # UNCHANGED (generic branch already handles both tools)
```

### Pattern 1: Single-level directory listing with cached-stat type checks
**What:** Use `os.scandir()` once per call; for each `DirEntry`, resolve type via `is_symlink()` first (checked before `is_dir()`/`is_file()`, since those default to `follow_symlinks=True` and would misclassify a symlink), then `stat(follow_symlinks=False)` for the mode/size actually shown.
**When to use:** `list_dir(path)` implementation.
**Example:**
```python
# Pattern derived from stdlib os.scandir/os.DirEntry semantics
# [CITED: docs.python.org/3/library/os.html#os.scandir — "DirEntry.is_dir():
#  ... follow_symlinks parameter default: True ... DirEntry.stat(): ...
#  This method follows symbolic links by default. ... If follow_symlinks is
#  False, the stat is taken on the symlink itself rather than the file it
#  points to."]
import os
import stat

def _entry_kind(entry: os.DirEntry) -> str:
    if entry.is_symlink():
        return "l"
    # is_dir()/is_file() default to follow_symlinks=True — must pass False
    # explicitly or a symlink-to-dir would be misclassified as "d" (violates D-04).
    if entry.is_dir(follow_symlinks=False):
        return "d"
    return "f"

def _entry_size(entry: os.DirEntry) -> int:
    # follow_symlinks=False: reuse the already-cached lstat, and never resolve
    # the symlink target (D-04 — "never followed/resolved").
    return entry.stat(follow_symlinks=False).st_size
```

### Pattern 2: `.git`-pruned recursive walk
**What:** Prune `.git` from `dirnames` **in place** (not by rebinding the name) so `os.walk()`'s own traversal skips descending into it — a rebind (`dirnames = [...]`) has no effect on `os.walk`'s internal recursion.
**When to use:** `grep_files(..., recursive=True)`.
**Example:**
```python
# [ASSUMED — sourced from WebSearch of third-party os.walk() explainers, not
#  a directly-fetched docs.python.org quote this session (the os.walk anchor
#  fetch returned a truncated page). Consistent with widely-documented, stable
#  stdlib behavior: os.walk()'s topdown-mode traversal only respects in-place
#  slice-assignment mutation of dirnames, not a rebind of the name.]
import os

def _walk_excluding_git(root: str):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        yield dirpath, filenames
```

### Pattern 3: Null-byte binary sniff (git/grep heuristic)
**What:** Read the first ~8KB of a candidate file in binary mode; treat presence of `\x00` as "binary, skip."
**When to use:** Before running the regex line-search on any file in `grep_files`.
**Example:**
```python
# git's own binary-detection constant is FIRST_FEW_BYTES = 8000 (8KB)
# [CITED: WebSearch summary of git internals (no primary git source file
#  fetched this session) — "Git detects files as binary if they contain a
#  null byte (\0) in the first 8000 bytes, using a buffer size constant of
#  FIRST_FEW_BYTES set to 8000."]
def _is_binary(path: str, sniff_size: int = 8192) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sniff_size)
    except OSError:
        return True  # unreadable — treat as skip, not a crash
    return b"\x00" in chunk
```
D-08 says "first ~8KB" — git's actual constant is 8000 bytes, not 8192; either is a reasonable interpretation of "~8KB" and this is a Claude's Discretion-level implementation detail, but note the discrepancy so the planner can pick one deliberately rather than by accident.

### Pattern 4: Sort-then-cap for `list_dir`, scan-order-cap for `grep_files`
**What:** D-12 distinguishes the two tools' ordering: `list_dir` sorts the **entire** listing (dirs first, then alphabetical — D-03) and only then takes the first 50; `grep_files` does **not** get an extra ranking pass — matches are kept in raw `os.scandir`/`os.walk` order, capped at the first 25 encountered.
**When to use:** Both tools, but with different ordering semantics — do not accidentally apply D-03's sort to `grep_files` matches.
**Example:**
```python
def _sorted_capped(entries: list[os.DirEntry], cap: int = 50):
    ordered = sorted(
        entries,
        key=lambda e: (not e.is_dir(follow_symlinks=False), e.name),
    )
    return ordered[:cap], max(0, len(ordered) - cap)
```

### Anti-Patterns to Avoid
- **Adding a `list_dir`/`grep_files` branch to `src/olla/safety.py`:** D-09 explicitly rejects this. `safety.py` stays scoped to shell argv classification (ARCHITECTURE.md's own "Bypassing the Policy Boundary" anti-pattern section describes the *opposite* failure — routing shell calls around `safety.check()` — but the same file's stated purpose is shell-only; adding a non-shell tool-name branch there would blur that boundary in the other direction).
- **Treating `list_dir`/`grep_files` output as trusted (`_record_observation` instead of `_record_file_observation`):** would silently defeat the existing `untrusted_observation_seen` re-confirmation mechanism for any destructive action the model takes immediately after inspecting attacker-influenced filenames or file content.
- **Using `os.path.isdir()`/`Path.is_dir()` for type classification:** both follow symlinks by default with no way to opt out short of manual `os.path.islink()` checks first — `os.DirEntry.is_dir(follow_symlinks=False)` is simpler and avoids a duplicate syscall.
- **Rebinding `dirnames` instead of slice-assigning it in the `.git`-pruning walk:** `dirnames = [...]` does not affect `os.walk`'s subsequent recursion; only `dirnames[:] = [...]` (in-place mutation) does [ASSUMED — WebSearch-sourced, not a directly-fetched primary-source quote; see Pattern 2].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Human-readable byte sizes (`1.2K`, `3.4M`) | A generic "smart" size-unit library | A small local `_human_size()` helper (~10 lines, binary/1024-based units matching `ls -lh`) | This is a two-branch, well-bounded formatting problem; pulling in a dependency (e.g. `humanize`) for one function violates the project's "minimal dependencies" constraint (CLAUDE.md) for negligible benefit |
| Binary/text file detection | A MIME-sniffing library (`python-magic`, `filetype`) | The null-byte-in-first-8KB heuristic (D-08, matches git's own approach) | D-08 already locked this decision specifically to avoid a file-extension allowlist *and*, implicitly, a heavier sniffing dependency |
| Recursive directory traversal with exclusions | A custom recursive-descent walker | `os.walk()` with in-place `dirnames` pruning | Stdlib already solves symlink-loop avoidance (`followlinks=False` default) and directory-skip semantics; a hand-rolled walker would have to reimplement both correctly |

**Key insight:** Every problem in this phase already has a direct, well-tested standard-library answer. The only "custom" code needed is small glue (size formatting, cap/truncation bookkeeping) explicitly called out in CONTEXT.md as Claude's Discretion — there is no case here for reaching outside stdlib.

## Common Pitfalls

### Pitfall 1: Forgetting `follow_symlinks=False` on `DirEntry.is_dir()`/`is_file()`/`stat()`
**What goes wrong:** A symlink pointing at a directory gets classified and sized as if it were a real directory (or a symlink to a file gets read for its target's size), directly violating D-04 ("never followed/resolved").
**Why it happens:** `DirEntry.is_dir()`, `is_file()`, and `stat()` all default to `follow_symlinks=True` — the opposite of what this phase needs — because that's the more common use case for general directory walking.
**How to avoid:** Always pass `follow_symlinks=False` explicitly in this phase's type/size logic; check `is_symlink()` first, before `is_dir()`/`is_file()`.
**Warning signs:** A test creating a symlink to a directory shows `[d]` instead of `[l] name -> target` in `list_dir` output.

### Pitfall 2: `.git` exclusion applied to `list_dir` by mistake
**What goes wrong:** D-05 (list_dir shows hidden dotfiles including `.git` as a visible entry) and D-08 (`.git` excluded outright from `grep_files` traversal) are easy to conflate into one blanket "always hide `.git`" rule, which would violate D-05.
**Why it happens:** Both decisions mention `.git` and sit in the same CONTEXT.md document, tempting a shared helper that over-applies the exclusion.
**How to avoid:** Keep the `.git`-exclusion helper scoped to `grep_files`'s traversal only; `list_dir` must list `.git` like any other directory entry (subject to the 50-entry cap same as everything else).
**Warning signs:** A test listing a directory containing `.git` doesn't see it in `list_dir` output — that's a bug per D-05, not a feature.

### Pitfall 3: Pruning `dirnames` by rebinding instead of in-place mutation
**What goes wrong:** `dirnames = [d for d in dirnames if d != ".git"]` silently does nothing — `os.walk()` still descends into `.git` and burns time/matches scanning packed git objects (which will also all fail the binary sniff as binary garbage, wasting cap slots on non-matches or, worse, matching binary-looking regex noise if the null-byte check has a gap).
**Why it happens:** Both forms look identical at a glance; the in-place requirement is a `os.walk()`-specific contract, not general Python list behavior.
**How to avoid:** Use slice assignment: `dirnames[:] = [...]`.
**Warning signs:** A test with a nested `.git/objects/...` structure still shows matches or scanned files from inside `.git`.

### Pitfall 4: Wire format ambiguity for `grep_files`'s three arguments — and a whitespace trap in the recommended fix
**What goes wrong (delimiter choice):** If the plan picks a single-line, space/comma-delimited args format (`pattern, path, recursive=True`), any pattern or path containing a space, comma, or the delimiter character breaks parsing — and grep patterns very commonly contain spaces (e.g. `def foo(`, `TODO: fix`).
**What goes wrong (line-based fix, if chosen naively):** Putting `pattern` on line 1 of a line-based format walks into a second trap: `parse_response()`'s generic branch calls `args_raw.strip()` on the **whole** captured string [VERIFIED: src/olla/parser.py:159-164 — `args_raw = content[args_open.end() : args_end]\n    return {\n        "type": "tool",\n        "tool": tool,\n        "args_raw": args_raw.strip(),\n    }`], which strips leading whitespace from line 1 only (not internal lines). A regex the model writes with meaningful leading whitespace (`    return`, `\tif `) would silently lose it before `grep_files` ever sees the pattern.
**Why it happens:** CONTEXT.md's D-06 specifies the tool's Python-level signature (`grep_files(pattern, path, recursive=False)`) but does not lock the model-facing `<args>` wire format — this is a genuine gap left for planning, and the whitespace-stripping behavior of the *existing, unmodified* generic parser branch is easy to miss since it only manifests for leading-whitespace patterns.
**How to avoid:** Two viable fixes — pick one explicitly (see Open Question 1): (a) accept the limitation and document it in `prompts.py` (patterns needing significant leading whitespace won't round-trip exactly — a narrow, documentable constraint), or (b) add `"grep_files"` to `parse_response()`'s special-cased opaque-payload set alongside `write_file`/`remember`/`recall`, which skips the whole-string `.strip()` and preserves pattern whitespace exactly — a small, targeted `parser.py` change that contradicts CONTEXT.md's "no change expected" framing but may be worth it.
**Warning signs:** A grep pattern containing a literal space or comma silently searches the wrong path or fails to parse (delimiter trap); a grep pattern intended to match indented code never matches anything (whitespace-stripping trap).

### Pitfall 5: ReDoS / catastrophic backtracking from a model-supplied regex
**What goes wrong:** Python's `re` module (backtracking engine) can hang on pathological patterns (e.g. nested quantifiers like `(a+)+b`) applied to adversarial or even accidentally-long input lines, freezing the whole CLI session (no other work happens while `re` backtracks).
**Why it happens:** `grep_files`'s pattern argument comes from the model, which itself may be echoing text from an untrusted file observation (indirect prompt injection) or simply produce a bad pattern.
**How to avoid:** At minimum, wrap `re.compile()` in a `try/except re.error` and return a `ToolResult` error (required regardless, since a model can trivially emit a syntactically invalid pattern). A stricter mitigation (regex complexity limits, per-line/per-file timeout) is not required by any locked decision and would add complexity beyond this phase's stated scope — flag as an accepted risk consistent with the project's existing threat model (single-user local CLI, not a multi-tenant service; `src/olla/safety.py`'s shell blocklist accepts a comparable class of "local footgun" risk already).
**Warning signs:** `olla` appears to hang indefinitely on a `grep_files` call with no CPU-bound `subprocess` in flight.

## Code Examples

### list_dir adapter skeleton (matches `read_file`'s ToolResult/exception-catching shape)
```python
# Source: pattern derived from src/olla/tools/files.py's read_file() shape
# [VERIFIED: src/olla/tools/files.py:288-328 — "def read_file(path: str) -> ToolResult:
#  ... except FileNotFoundError: result = {"path": path, "error": f"file not found: {path}"}
#  except IsADirectoryError: result = {"path": path, "error": f"is a directory: {path}"}"]
import os
from olla.tools.base import ToolResult

def list_dir(path: str) -> ToolResult:
    """List one directory level: type, name, human-readable size, sorted
    dirs-first alphabetically, capped at 50 entries. Never raises."""
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except FileNotFoundError:
        return {"path": path, "error": f"directory not found: {path}"}
    except NotADirectoryError:
        return {"path": path, "error": f"not a directory: {path}"}
    except OSError as e:
        return {"path": path, "error": f"could not list {path}: {e}"}

    ordered = sorted(
        entries,
        key=lambda e: (not e.is_dir(follow_symlinks=False), e.name),
    )
    shown, remaining = ordered[:50], max(0, len(ordered) - 50)
    # ... format each entry per Pattern 1/4, append "(+N more, not shown)" if remaining
    return {"path": path, "content": "..."}  # final line format is Claude's Discretion
```

### grep_files adapter skeleton
```python
# Source: pattern combines D-06/D-07/D-08 with Pattern 2/3 above.
import os
import re
from olla.tools.base import ToolResult

def grep_files(pattern: str, path: str, recursive: bool = False) -> ToolResult:
    """Regex search text files under path, ignoring .git and binary files,
    up to 25 matching lines. Never raises."""
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return {"path": path, "error": f"invalid regex {pattern!r}: {e}"}

    matches: list[str] = []
    truncated = False

    def _scan_file(file_path: str) -> None:
        nonlocal truncated
        if len(matches) >= 25:
            truncated = True
            return
        # os.walk(followlinks=False) only stops descent into symlinked
        # *directories* — a symlinked *file* still appears in `filenames`.
        # Check explicitly here so both the recursive and non-recursive
        # branches skip symlinked files consistently (A2: never search
        # through a symlink, matching D-04's "never followed/resolved").
        if os.path.islink(file_path):
            return
        if _is_binary(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, start=1):
                    if len(matches) >= 25:
                        truncated = True
                        return
                    if compiled.search(line):
                        matches.append(f"{file_path}:{lineno}:{line.rstrip()}")
        except OSError:
            return  # unreadable mid-scan — skip, don't crash the whole call

    try:
        if recursive:
            for dirpath, filenames in _walk_excluding_git(path):
                for name in filenames:
                    _scan_file(os.path.join(dirpath, name))
        else:
            with os.scandir(path) as it:
                for entry in it:
                    # entry.is_file(follow_symlinks=False) already excludes
                    # symlinked files here; the os.path.islink() check inside
                    # _scan_file is what gives the recursive branch above the
                    # same guarantee, since os.walk() filenames are plain
                    # strings with no per-entry symlink flag.
                    if entry.is_file(follow_symlinks=False):
                        _scan_file(entry.path)
    except (FileNotFoundError, NotADirectoryError) as e:
        return {"path": path, "error": f"could not search {path}: {e}"}

    # ... append "(+N more, not shown)" note if truncated
    return {"path": path, "content": "\n".join(matches)}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A | N/A | N/A | This is a small, stable stdlib domain — there is no "old vs. new" API churn to track for `os.scandir`/`os.walk`/`re` in the relevant Python version range (3.10+). |

**Deprecated/outdated:** None applicable.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `grep_files`'s model-facing `<args>` wire format should be line-based (pattern / path / optional `recursive=true`), not space/comma-delimited on one line | Summary, Pitfall 4 | If the planner instead picks a delimited single-line format, patterns/paths containing the delimiter character will silently mis-parse; low blast radius (caught quickly in testing) but worth locking explicitly before implementation rather than leaving to per-task improvisation |
| A2 | `grep_files` should skip symlinked files/directories entirely (never search through them), by analogy to D-04's "never followed/resolved" for `list_dir` | Architecture Patterns (Pattern 2), Code Examples | D-04 is scoped to `list_dir` output format only; if the intent was actually to search *through* symlinked files, skipping them would under-report matches. Low risk either way since `os.walk(followlinks=False)` is also the safer default against symlink loops |
| A3 | `list_dir`/`grep_files` output should be recorded via the existing untrusted-observation path (`_record_file_observation`-equivalent, setting `untrusted_observation_seen=True`), not the plain `_record_observation` path | Summary, Anti-Patterns | If unconfirmed, a future destructive action immediately following a `list_dir`/`grep_files` call would incorrectly skip the re-confirmation gate under `--yes`, since directory/file names and grep match text can carry attacker-influenced content (e.g. a maliciously named file, or a prompt-injection string embedded in matched file content) |
| A4 | Directories should still show a (mostly meaningless) `os.stat().st_size` in the size column, matching `ls -lh`'s own behavior of showing a nonzero size for directories | Architecture Patterns (Pattern 1) | Cosmetic only — if wrong, directories might instead show `-` or omit size; no functional impact |

**If this table is empty:** N/A — see entries above; all are implementation-detail gaps in an otherwise fully-decided phase, not open compliance/retention/security-standard questions.

**Confirmed, not assumed (kept out of this table on purpose):** "up to 25 matches" (INSPECT-02/ROADMAP.md) counts matching **lines**, not individual regex sub-matches within a line, matching grep's default (non-`-o`) behavior. ROADMAP.md's success criterion explicitly says "capped at 25 **matching lines**" [VERIFIED: .planning/ROADMAP.md:38 — "`grep_files(pattern, path)` tool performs regex search over text files, ignoring `.git` and binary files, capped at 25 matching lines."] — this resolves CONTEXT.md's own D-11 phrasing ("25 matches"), which is ambiguous in isolation, so it does not belong in the assumptions table above (it needs no user confirmation).

## Open Questions

1. **Exact model-facing wire format for `grep_files`'s three arguments, and how to handle the leading-whitespace-in-pattern trap**
   - What we know: The Python-level signature (`grep_files(pattern, path, recursive=False)`) is locked by D-06; `parser.py`'s generic branch preserves internal newlines but strips leading/trailing whitespace from the *whole* `args_raw` string, which would clip a leading-whitespace pattern on line 1 of a line-based format (see Pitfall 4).
   - What's unclear: CONTEXT.md does not lock the exact serialization the model must emit inside `<args>...</args>`, nor whether the whitespace-stripping edge case is acceptable.
   - Recommendation: Adopt the line-based format from A1 above and document it precisely in `src/olla/prompts.py` with a worked example (mirroring the existing `write_file`/`remember` examples in the system prompt), including how `recursive` is signaled when omitted (default `False`) vs. present. Separately and explicitly decide between: (a) documenting the leading-whitespace limitation as a known constraint (no parser change, matches CONTEXT.md's expectation), or (b) adding `"grep_files"` to `parse_response()`'s special-cased opaque-payload set in `src/olla/parser.py` (a small, targeted parser change that preserves exact pattern whitespace but contradicts "no change expected"). This research recommends (a) unless the planner has reason to believe leading-whitespace regex patterns are a realistic, common use case for this tool.
   - **RESOLVED (05-01-PLAN.md):** Line-based wire format adopted — `<args>` line 1 is the raw `pattern`, line 2 (stripped) is `path`, an optional line 3 equal to exactly `"recursive=true"` (case-insensitive) enables recursion; any other/absent third line is `recursive=False`. Option (a) chosen for the whitespace trap: the leading-whitespace-stripping limitation is accepted and documented via a code comment at the `_prepare_action()` `grep_files` branch in `loop.py`; `parser.py` is left unmodified (no opaque-payload special-case added).

2. **Exact output line format for `list_dir` and `grep_files`**
   - What we know: `list_dir` needs `[d]`/`[f]`/`[l]` markers, name, human-readable size, sorted dirs-first-then-alpha, capped at 50 with a trailing note; `grep_files` needs `file:line` (this research recommends also including the matched line text, matching conventional grep output and ROADMAP.md's framing of "matches" as something meaningfully returned to the model).
   - What's unclear: The precise column/delimiter layout (CONTEXT.md defers "exact wording of the `(+N more)` truncation note" to Claude's Discretion, implying the rest of the format is also open unless explicitly worded elsewhere).
   - Recommendation: Follow `ls -la`-style single-line-per-entry text (not a table/JSON structure) to stay consistent with the plain-text `Observation:` convention every other tool already uses; keep it terse given `MAX_OBSERVATION_CHARS = 2000` in `src/olla/loop.py` truncates long observations anyway.
   - **RESOLVED (05-01-PLAN.md):** `list_dir` emits one line per entry: `"[d]"`/`"[f]"` + name + human-readable size (`ls -lh` style, e.g. `1.2K`), or `"[l] name -> target"` for symlinks (no size shown); sorted directories-first-then-alphabetical, capped at 50 with a trailing "not shown" note when truncated. `grep_files` emits one line per match: `"{file_path}:{lineno}:{line_text}"` (trailing newline stripped), in scan order (no extra ranking pass), capped at 25 with a trailing truncation note when cut. Exact truncation-note wording remains Claude's Discretion per CONTEXT.md.

## Environment Availability

Not applicable — this phase has no external tool/service/runtime dependencies beyond the Python interpreter and local filesystem already required by the rest of the project. No new CLI tools, databases, or network services are introduced.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8 [VERIFIED: pyproject.toml:23-28 — `[project.optional-dependencies]\ndev = [\n    "pytest>=8",\n    "pytest-mock>=3.14",\n    "ruff",\n]`] |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options] testpaths = ["tests"]` [VERIFIED: pyproject.toml:33-34 — `[tool.pytest.ini_options]\ntestpaths = ["tests"]`] |
| Quick run command | `pytest tests/test_tools/test_inspect.py -x` (new test file — see Wave 0 Gaps) |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| INSPECT-01 | `list_dir` returns `[d]`/`[f]`/`[l]` entries, sizes, sorted dirs-first-alpha, capped at 50, `.git` shown | unit | `pytest tests/test_tools/test_inspect.py -k list_dir -x` | ❌ Wave 0 |
| INSPECT-02 | `grep_files` regex-matches text files, skips `.git`/binary, caps at 25 lines, `file:line` output, `recursive` flag toggles traversal depth | unit | `pytest tests/test_tools/test_inspect.py -k grep_files -x` | ❌ Wave 0 |
| INSPECT-03 | `list_dir`/`grep_files` dispatch executes without a confirmation prompt (loop-level, not safety.py) | unit/integration | `pytest tests/test_loop.py -k "list_dir or grep_files" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_tools/test_inspect.py tests/test_loop.py -x` (fast, scoped)
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tools/test_inspect.py` — new file covering both `list_dir()` and `grep_files()` adapter behavior (mirrors `tests/test_tools/test_files.py`'s structure: `tmp_path` fixture, one test per success/error/edge-case scenario)
- [ ] `tests/test_loop.py` additions — new tests for the `_prepare_action`/dispatch branches for `list_dir`/`grep_files`, following the existing `test_run_loop_...read_file...` naming convention, specifically covering (a) no confirmation prompt is triggered, (b) `untrusted_observation_seen` is set on success per A3 above
- [ ] `tests/test_prompts.py` additions — assert the new tools' names and the `recursive` parameter appear in `SYSTEM_PROMPT`, mirroring existing assertions for `read_file`/`write_file`
- Framework install: none needed — `pytest`/`pytest-mock` are already dev dependencies [VERIFIED: pyproject.toml:23-28]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Single-user local CLI; no auth boundary exists anywhere in the project (per ARCHITECTURE.md's own "Authentication: Not applicable" note) |
| V3 Session Management | no | No session concept beyond one `run_loop()` invocation |
| V4 Access Control | no | No access-control boundary; the model runs with the OS user's own filesystem permissions, same as every existing tool |
| V5 Input Validation | yes | `re.compile()` wrapped in `try/except re.error` (invalid regex from the model must not crash the loop); path arguments are resolved via `_resolve_file_path()` but **not** existence-validated per D-10 (matches `read_file`'s existing convention) |
| V6 Cryptography | no | No cryptographic operations in this phase |
| V12 Files and Resources | yes | Path traversal (CWE-22): `list_dir`/`grep_files` accept arbitrary paths with no containment boundary, same as `read_file`/`write_file`/`shell` today. This is a documented existing project posture, not a new gap: [VERIFIED: .planning/codebase/ARCHITECTURE.md:312-314 — "**Working directory:** Relative shell and file paths inherit the process working directory. Path resolution in `src/olla/loop.py` is for disclosure in confirmation/preview text, not a containment check."]. No new mitigation is introduced or required by this phase's locked decisions (D-10 explicitly chooses no path pre-validation) — flagged here as an accepted, pre-existing risk rather than a phase-introduced one. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Path traversal via `list_dir("/etc")` or `grep_files(pattern, "/")` | Information Disclosure | None added this phase (accepted risk, consistent with `read_file` precedent); a future phase could add an opt-in project-root containment check without touching this phase's scope |
| ReDoS via a pathological model-supplied regex (CWE-1333) | Denial of Service | Catch `re.error` for invalid patterns (required); full backtracking-complexity mitigation is out of scope this phase (see Common Pitfalls #5) — accepted risk given the single-user local threat model |
| Indirect prompt injection via file/directory names or grep match content | Tampering (of the model's subsequent reasoning) | Tag `list_dir`/`grep_files` observations as untrusted (`_record_file_observation`-equivalent), preserving the `untrusted_observation_seen` re-confirmation gate for any destructive action that follows, exactly as `read_file` already does |
| `.git` internal object scanning leaking packed/compressed binary blobs into grep output | Information Disclosure / noise | D-08 already locks `.git` exclusion from `grep_files` traversal; `list_dir` intentionally still shows `.git` as an entry (D-05) — do not conflate the two (Common Pitfall #2) |

## Sources

### Primary (HIGH confidence)
- `src/olla/tools/files.py`, `src/olla/tools/base.py`, `src/olla/loop.py`, `src/olla/safety.py`, `src/olla/parser.py`, `src/olla/prompts.py`, `pyproject.toml` — read directly this session (via `Read`, with line numbers); all `[VERIFIED: path:lines]` citations above quote these exact files verbatim.
- `.planning/phases/05-safe-inspection-tools/05-CONTEXT.md` — user decisions, read directly this session.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` (including the success-criteria lines cited for INSPECT-01/02/03), `.planning/STATE.md`, `.planning/config.json` — read directly this session.
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONVENTIONS.md` — read directly this session.
- WebFetch of `docs.python.org/3/library/os.html#os.scandir` — this fetch returned a usable, directly-quotable description of `DirEntry.is_dir()`/`is_file()`/`is_symlink()`/`stat()` and their `follow_symlinks` defaults; treated as `[CITED]` where quoted above.

### Secondary (MEDIUM confidence)
- WebSearch "python os.walk followlinks default prune directories in place dirnames" — confirmed `followlinks` defaults to not following symlinks, and that `dirnames[:] = [...]` (in-place slice assignment) is required to affect `os.walk`'s recursion, while rebinding `dirnames` does not. A follow-up WebFetch of `docs.python.org/3/library/os.html#os.walk` was attempted to upgrade this to `[CITED]` but returned a truncated page with no usable quote — this claim stays at WebSearch-sourced `[ASSUMED]`/MEDIUM rather than being presented as docs-fetched, despite being well-established, stable stdlib behavior.
- WebSearch "git binary file detection null byte heuristic first bytes buffer" — confirmed git's own binary-detection heuristic uses a `FIRST_FEW_BYTES` constant of 8000 bytes and a null-byte presence check, directly supporting D-08's "same heuristic grep/git use" framing. No primary git source file was fetched this session, so this is WebSearch-sourced, not `[VERIFIED]` against git's source.

### Tertiary (LOW confidence)
- None used as load-bearing sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pure stdlib, no version-sensitivity, directly verified against the repo's own `pyproject.toml` floor
- Architecture: HIGH — derived directly from reading `loop.py`, `parser.py`, `safety.py`, `files.py`, `base.py`, and the project's own ARCHITECTURE.md/CONVENTIONS.md this session
- Pitfalls: HIGH for stdlib-behavior pitfalls (DirEntry follow_symlinks, os.walk dirnames pruning — both externally confirmed); MEDIUM for the ReDoS/wire-format pitfalls, which are reasoned inferences rather than locked decisions (see Assumptions Log)

**Research date:** 2026-09-08
**Valid until:** Effectively unbounded for the stdlib API surface (no near-term deprecation risk); re-verify only if the project's Python floor changes materially above 3.10, or if CONTEXT.md is amended with a different wire-format/output-format decision.
