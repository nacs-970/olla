---
phase: 03-file-tools
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/olla/tools/base.py
  - src/olla/tools/files.py
  - src/olla/parser.py
  - src/olla/loop.py
  - src/olla/prompts.py
  - tests/test_tools/test_files.py
  - tests/test_parser.py
  - tests/test_loop.py
findings:
  critical: 3
  warning: 3
  info: 1
  total: 7
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Reviewed the read_file/write_file tool implementations, the new write_file-aware
parser branch, and the loop.py dispatch/confirm-gate wiring. All 146 existing
tests pass, but every finding below represents an UNTESTED edge case or gap
in the existing suite — none are regressions, all are real.

The most serious issue is **CR-A**: both `read_file` and `write_file` violate
their own "Never raises" docstring contract — a path string containing a null
byte (`\x00`) causes an uncaught `ValueError` that crashes the entire CLI
process, not just the tool call. This is directly reachable from model output
(`<tool>read_file</tool><args>some\x00path</args>`) and is a process-crash
risk, not merely a bad-observation risk.

**CR-B** is a parser-level truncation bug: `ARGS_RE`'s non-greedy `.search()`
will terminate a write_file `<args>` capture at the FIRST `</args>` substring
it finds — including one that appears literally inside the file content being
written (e.g., the model is writing a file that itself contains `<tool>/<args>`
examples). This silently truncates the file content and the trailing real
`</args>` closer, undermining the entire verbatim-preservation goal of the
write_file parser branch.

**CR-C** is a data-loss bug: if the model emits `<args>` for write_file with no
newline (just a bare path, no file content), `partition("\n")` yields an empty
`file_content`, the confirm prompt gives no indication the write is empty, and
approving it **silently truncates an existing file to 0 bytes**.

Three warnings cover an inconsistency in `<final>` vs write_file precedence in
the parser, a misleading confirm-prompt path when `args_raw` has no path
component (resolves to CWD), and a documented-but-violated spec deviation in
`read_file`'s empty-content handling.

## Critical Issues

### CR-01: `read_file` and `write_file` crash on null-byte paths despite "Never raises" contract

**File:** `src/olla/tools/files.py:15-23` (read_file), `src/olla/tools/files.py:33-40` (write_file)

**Issue:** Both functions' docstrings explicitly promise "Never raises," but
neither except-clause includes `ValueError`. `Path(...).read_text()` /
`Path(...).write_text()` raise `ValueError: embedded null byte` for any path
string containing `\x00` (via the underlying `os` call), which is NOT a
subclass of `OSError` and therefore not caught by `except (UnicodeDecodeError,
OSError) as e` (read_file, line 22) or `except OSError as e` (write_file, line
39).

Verified for `read_file`:
```python
>>> read_file('a\x00b')
ValueError: embedded null byte   # uncaught, propagates out of parse loop
```

Verified for `write_file` (parent directory exists, filename contains `\x00`):
```python
>>> write_file('/tmp/xxx/file\x00name', 'content')
ValueError: embedded null byte   # uncaught — p.parent.exists() passes,
                                  # crash happens at p.write_text()
```

A model emitting a malformed path containing a stray null byte (e.g. from
garbled tokenization) crashes the entire `olla` CLI process rather than
producing an error Observation the model could recover from. This is a
crash/availability issue reachable purely from model output, with no user
confirmation step in front of it for `read_file`.

**Fix:** Add `ValueError` to both except tuples:
```python
# files.py, read_file
    except (UnicodeDecodeError, OSError, ValueError) as e:
        return {"path": path, "error": f"could not read {path}: {e}"}

# files.py, write_file
    try:
        p.write_text(content, encoding="utf-8")
        return {"path": path, "bytes_written": len(content.encode("utf-8"))}
    except (OSError, ValueError) as e:
        return {"path": path, "error": f"could not write {path}: {e}"}
```

---

### CR-02: Parser truncates write_file `<args>` at first literal `</args>` inside file content

**File:** `src/olla/parser.py:7` (`ARGS_RE`), used at `src/olla/parser.py:25-29`

**Issue:** `ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)`
is non-greedy and uses `.search()`. For the write_file special-case branch
(lines 21-29), this regex is matched against the ORIGINAL `content` (not the
fence-stripped version), so if the file content being written contains the
literal substring `</args>` anywhere — for example, the model is writing a
markdown file or Python script that itself documents/contains
`<tool>...</tool><args>...</args>` examples — the capture group stops at that
first inner `</args>`, silently dropping everything after it, including the
real closing `</args>` of the outer write_file call.

Verified:
```python
content = "<tool>write_file</tool><args>/tmp/code.py\nprint('<tool>shell</tool><args>ls</args>')\n</args>"
parse_response(content)
# -> {'type': 'tool', 'tool': 'write_file',
#     'args_raw': "/tmp/code.py\nprint('<tool>shell</tool><args>ls"}
```

The file would be written with truncated, syntactically-broken content
(`print('<tool>shell</tool><args>ls`), and the user/model has no signal this
happened — `write_file` succeeds and reports `bytes_written` for the truncated
content. This directly undermines the documented goal of the write_file parser
branch ("file content must be preserved verbatim... legitimate file content
may contain code fences").

**Fix:** For the write_file branch, match the LAST `</args>` in the content
(or the outermost balanced pair) instead of the first. A pragmatic fix: use
`rfind` on the literal string rather than the non-greedy regex for the
write_file case, since the tag positions for `<tool>`/`<args>` are known to
precede the content:

```python
if raw_tool_match and raw_tool_match.group(1).strip() == "write_file":
    args_start_match = re.search(r"<args>", content, re.IGNORECASE)
    if args_start_match:
        start = args_start_match.end()
        end = content.rfind("</args>")
        if end == -1 or end < start:
            args_raw = content[start:]
        else:
            args_raw = content[start:end]
        return {"type": "tool", "tool": "write_file", "args_raw": args_raw}
```

This greedily captures up to the LAST `</args>` in the content, which is far
more likely to be the actual closing tag than the first occurrence. Add a
regression test asserting that file content containing a literal `</args>`
substring is preserved verbatim (not truncated).

---

### CR-03: No-newline write_file args silently truncate existing files to empty (data loss)

**File:** `src/olla/loop.py:181-203` (normal loop), `src/olla/loop.py:71-75` (dry-run)

**Issue:** When `parsed["args_raw"]` for write_file contains no `\n` (i.e., the
model emits only a path, no file content — e.g.
`<tool>write_file</tool><args>/tmp/existing.txt</args>`), `partition("\n")`
(line 181) returns `path="/tmp/existing.txt"`, `file_content=""`. The confirm
prompt at line 187 (`f"Write to \`{resolved}\`?"`) gives NO indication that the
content to be written is empty — it looks identical to a normal write
confirmation. If the user approves (or `--yes` is set), `write_file(path, "")`
is called and — verified via REPL — **silently truncates an existing file to 0
bytes**:

```python
open(p, 'w').write('IMPORTANT DATA')
write_file(p, '')          # -> {'path': p, 'bytes_written': 0}
open(p).read()              # -> ''  (data destroyed)
```

A malformed/incomplete model response (model forgets to include file content
after the path, or generation gets cut off before the newline) causes silent
destruction of any existing file at that path, with a confirm prompt that does
not surface the empty-content fact before the user approves.

**Fix:** Detect the no-newline / empty-content case before showing the confirm
prompt and either refuse to proceed or make the emptiness explicit in the
prompt:

```python
path, sep, file_content = parsed["args_raw"].partition("\n")
path = path.strip()
resolved = Path(path).resolve()

if not sep:
    # No newline in args_raw — model sent a path with no content.
    preview = "write_file refused: no file content provided (missing newline after path)"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue

if not yes:
    prompt = f"Write to `{resolved}`?"
    if not file_content:
        prompt = f"Write EMPTY content to `{resolved}` (existing content will be erased)?"
    try:
        approved = Confirm.ask(prompt, default=False)
    except EOFError:
        approved = False
    ...
```

Apply the equivalent "no sep" guard in the dry-run branch (lines 71-75) as
well, so dry-run output also flags this case.

## Warnings

### WR-01: write_file always wins over `<final>` in parser, inconsistent with documented precedence

**File:** `src/olla/parser.py:21-32`

**Issue:** The write_file special-case branch (lines 21-29) executes and
`return`s unconditionally, BEFORE the `<final>` check (lines 34-38) is ever
reached. If a model response contains both a write_file tool call and a
`<final>` tag (in either order), the write_file branch always wins.

Verified:
```python
content = "<final>done</final><tool>write_file</tool><args>/tmp/x\ncontent</args>"
parse_response(content)
# -> {'type': 'tool', 'tool': 'write_file', 'args_raw': '/tmp/x\ncontent'}
# (write_file wins even though <final> appears first)
```

This contradicts the precedent established by `test_final_wins_over_tool`,
which asserts `<final>` takes priority over `<tool>` for shell (and by
extension, presumably all tools). The write_file special case introduces an
undocumented exception to this precedence rule — a model that emits both a
completed write and a final answer in the same turn will have its final answer
silently discarded in favor of re-running the write.

**Fix:** Check for `<final>` (against the fence-stripped content) before
entering the write_file special case, or restructure so the write_file branch
only fires when no `<final>` tag is present:

```python
stripped = re.sub(r"```[a-zA-Z]*\n?|```", "", content)
final_match = FINAL_RE.search(stripped)
if final_match:
    return {"type": "final", "text": final_match.group(1).strip()}

raw_tool_match = TOOL_RE.search(content)
raw_args_match = ARGS_RE.search(content)
if (
    raw_tool_match
    and raw_args_match
    and raw_tool_match.group(1).strip() == "write_file"
):
    return {"type": "tool", "tool": "write_file", "args_raw": raw_args_match.group(1)}
...
```

Add a test mirroring `test_final_wins_over_tool` but for `write_file`.

---

### WR-02: Empty/whitespace write_file args resolve to CWD, producing misleading confirm/dry-run output

**File:** `src/olla/loop.py:71-75` (dry-run), `src/olla/loop.py:181-184` (normal loop)

**Issue:** If `parsed["args_raw"]` is empty or has no usable path before the
first `\n` (e.g. `<tool>write_file</tool><args></args>` or
`<tool>write_file</tool><args>\ncontent</args>`), `path.strip()` evaluates to
`""`. `Path("").resolve()` resolves to the **current working directory of the
olla process** (verified: `Path("").resolve()` -> `/home/nacs/Documents/git/olla`,
the project root).

The dry-run preview (`f"Step 1 would write to {resolved} — would prompt for
confirmation"`) and the normal-loop confirm prompt (`f"Write to \`{resolved}\`?"`)
then display the project's own working directory as the target path, which is
confusing/alarming — it looks like olla is about to overwrite something in its
own root, when actually the model emitted malformed/empty args.

In the normal-loop case this does not currently cause data loss: a subsequent
`write_file("", file_content)` call returns
`{'path': '', 'error': "could not write : [Errno 21] Is a directory: '.'"}` (no
write occurs, `IsADirectoryError` is caught as `OSError`). But the misleading
confirm-prompt UX remains, and a user who reflexively approves a prompt showing
their own project directory could be alarmed or could approve based on
incorrect information.

**Fix:** Validate that `path` is non-empty before resolving/prompting:

```python
path, _, file_content = parsed["args_raw"].partition("\n")
path = path.strip()
if not path:
    preview = "write_file refused: no path provided in <args>"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue
resolved = Path(path).resolve()
```

Apply the same `if not path` guard in the dry-run branch.

---

### WR-03: `read_file`'s "(no output)" fallback for empty file content contradicts plan spec and is untested

**File:** `src/olla/loop.py:162-164`

**Issue:**
```python
combined = result.get("content", "")
if not combined:
    combined = "(no output)"
```
03-01-PLAN.md explicitly specifies that `read_file` should NOT have this
fallback: *"Apply `truncate_output(combined)`... (no `(no output)` fallback
needed — empty file content is valid and meaningful, unlike empty shell
stdout+stderr)"*. The implementation adds the fallback anyway, so reading a
genuine 0-byte file produces the Observation `"(no output)"` — identical to
what a model would see for an empty shell command's stdout/stderr. This can
mislead a small local model into believing the read failed, the file doesn't
exist, or the tool call did nothing, when in fact the file legitimately exists
and is empty (a meaningful, common state — e.g. a freshly-created/truncated
file, an empty `__init__.py`, etc.).

No test in `tests/test_tools/test_files.py` or `tests/test_loop.py` covers
reading an empty file's content through the loop (`grep -rn "content.*\"\"\|empty"`
returns no matches for this scenario), so this deviation from the documented
spec is currently untested and unnoticed.

**Fix:** Remove the fallback for read_file, distinguishing it from the
shell-stdout case, per the plan:

```python
elif parsed["tool"] == "read_file":
    ...
    if "error" in result:
        combined = result["error"]
    else:
        combined = result.get("content", "")
    preview = truncate_output(combined)
```

Add a test: writing an empty file then dispatching `read_file` on it produces
an Observation that is the truncated empty string (or whatever
`truncate_output("")` returns), not `"(no output)"`.

## Info

### IN-01: write_file does not create missing parent directories — confirm prompt is shown before this check fails

**File:** `src/olla/loop.py:181-198`, `src/olla/tools/files.py:33-35`

**Issue:** The confirm prompt (`Write to \`{resolved}\`?`) is shown and the
user must approve BEFORE `write_file()` is called and discovers the parent
directory doesn't exist (line 34-35 of files.py). The user experience is:
approve a write, then immediately see
`"parent directory does not exist: <dir>"` as the Observation. This is not a
bug (the never-raise contract is honored, and no data loss occurs), but it's a
minor UX rough edge — the confirm-gate could pre-check `p.parent.exists()` and
either skip the prompt or note the issue in the prompt itself, sparing the user
an unnecessary confirmation for a write that's guaranteed to fail.

**Fix (optional, low priority):**
```python
resolved = Path(path).resolve()
if not resolved.parent.exists():
    preview = f"parent directory does not exist: {resolved.parent}"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue
```
placed before the confirm-gate, mirroring the early-exit already present in
`write_file()` itself.

---

_Reviewed: 2026-06-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
