---
status: diagnosed
phase: 03-file-tools
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md
started: 2026-06-16T02:47:00Z
updated: 2026-07-28T14:28:59+07:00
---

## Current Test

[testing complete]

## Tests

### 1. User-Flow Step 1 - Run olla with a read/write task
expected: Start olla with a prompt like `olla "read test.txt, replace 'foo' with 'bar', and write it back"`. The loop starts.
result: pass

### 2. User-Flow Step 2 - Observe read_file tool call
expected: The model calls `read_file` on `test.txt`. You should see the tool execution output in the console.
result: pass

### 3. User-Flow Step 3 - Observe write_file confirm prompt
expected: The model calls `write_file` to update `test.txt`. You should see a confirm prompt that displays the resolved absolute path of the file.
result: pass

### 4. User-Flow Step 4 - Confirm the write and assert outcome
expected: Type 'y' to confirm. The loop finishes. Open `test.txt` and verify the content is updated successfully.
result: issue
reported: "it read and write but it do it wrong, since i not sure is the model is too small or something else"
severity: major
evidence: |
  qwen3.5:2b-256k sometimes returned a final answer without using a tool, confused file contents with scratchpad memory, and hallucinated file contents.
  On the edit attempt it called write_file before read_file, overwrote trash.md with 148 unrelated bytes after confirmation, then called recall for a key that had never been remembered.

### 5. read_file missing file error
expected: Ask olla to read a non-existent file. The loop should not crash; it should receive a "not found" observation and continue.
result: skipped
reason: User-flow failed

### 6. write_file missing parent directory
expected: Ask olla to write a file to a non-existent directory. It should display the confirm prompt, and upon confirmation, the loop should not crash but receive an error observation about the missing directory.
result: skipped
reason: User-flow failed

### 7. write_file preserves exact content
expected: Ask olla to write a markdown code block to a file. The resulting file should contain the exact markdown fences and newlines, unmodified by the parser.
result: skipped
reason: User-flow failed

### 8. write_file dry-run preview
expected: Run a task involving `write_file` with `--dry-run`. It should preview the write tool call and stop without actually prompting for confirmation or writing the file.
result: skipped
reason: User-flow failed

### 9. Repetition guard for file tools
expected: Force the model into a loop where it calls the same `read_file` or `write_file` repeatedly. The repetition guard should abort the run after 3 identical calls with a "model likely stuck" message.
result: skipped
reason: User-flow failed

### 10. write_file no-newline refusal
expected: If the model emits a `write_file` call with just the path and no newline/content, the tool should unconditionally refuse to execute (with a clear observation) BEFORE presenting the confirm prompt.
result: skipped
reason: User-flow failed

### 11. Coverage Check (Goal-Backward)
expected: Verify that the user can "inspect and update project files to complete the task" by checking that `src/olla/tools/files.py` implements both `read_file` and `write_file` tools, and `src/olla/loop.py` dispatches them appropriately with a confirm gate for `write_file`.
result: skipped
reason: User-flow failed

## Summary

total: 11
passed: 3
issues: 1
pending: 0
skipped: 7
blocked: 0

## Gaps

- gap_id: G-03-1
  truth: "Start olla with a prompt like `olla \"read test.txt, replace 'foo' with 'bar', and write it back\"`. The loop starts."
  status: resolved
  resolved_by: "03-04-PLAN.md and passing UAT retest"
  resolved_at: 2026-07-28
  reason: "User reported: User ran command with `--model qwen3.5:0.8b-256k`. It resulted in `error: could not parse command: No closing quotation` and the model falsely claimed it was successful without calling read_file or writing anything."
  severity: major
  test: 1
  root_cause: "The `shlex.split()` call in `loop.py` raises `ValueError: No closing quotation` when a small model hallucinates a shell command with an unbalanced quote. Small models fail to understand this parser error and falsely output `<final>`."
  artifacts:
    - path: "src/olla/loop.py"
      issue: "shlex.split ValueError exposes cryptic error message to model"
  missing:
    - "Catch ValueError from shlex.split and return a clearer, model-friendly error observation"
  debug_session: ".planning/debug/parser-error-no-closing-quotation.md"

- gap_id: G-03-3
  truth: "The model calls `write_file` to update `test.txt`. You should see a confirm prompt that displays the resolved absolute path of the file."
  status: resolved
  resolved_by: "03-04-PLAN.md and passing UAT retest"
  resolved_at: 2026-07-28
  reason: "User reported: User created test.txt, but the model (qwen3.5:2b-256k) hallucinated shell commands and bad read_file paths, eventually hitting max steps (15) without ever calling write_file."
  severity: blocker
  test: 3
  root_cause: "The `SYSTEM_PROMPT` gives `shell` equal prominence to file tools without negative constraints. Small models default to familiar shell commands (cat/sed/echo) which fail silently due to subprocess.run(shell=False). Also, the prompt uses literal absolute paths as examples, causing hallucinated invalid paths."
  artifacts:
    - path: "src/olla/prompts.py"
      issue: "SYSTEM_PROMPT does not forbid shell for file I/O and uses absolute paths in examples"
  missing:
    - "Update SYSTEM_PROMPT to explicitly restrict shell for file I/O"
    - "Demote shell below file tools in examples"
    - "Update file tool examples to use relative paths"
  debug_session: ".planning/debug/hallucinated-shell-commands-max-steps.md"

- gap_id: G-03-4
  truth: "After confirmation, the requested edit is applied to the existing file without replacing it with unrelated model-generated content."
  status: failed
  reason: "User reported: it read and write but it do it wrong, since i not sure is the model is too small or something else"
  severity: major
  test: 4
  root_cause: "AND-gated failure: qwen3.5:2b-256k selected a semantically invalid write-before-read plan, while olla accepted the full-file replacement after confirming only the path. The prompt lacks an explicit same-file read-before-edit workflow and does not distinguish scratchpad recall from file contents; the runtime tracks no successful same-target read, snapshot freshness, content provenance, or proposed-content preview. Model size increases the failure rate, but the actionable data-loss cause is the missing prompt/runtime edit contract."
  artifacts:
    - path: "src/olla/prompts.py"
      issue: "No existing-file read-before-write or file-versus-scratchpad rule; the standalone write example teaches direct overwrite."
    - path: "src/olla/loop.py"
      issue: "Any syntactically valid write_file payload can replace an existing file after a path-only confirmation."
    - path: "src/olla/tools/files.py"
      issue: "write_file correctly performs a complete replacement, making missing upstream edit guards destructive."
    - path: "tests/test_loop.py"
      issue: "No regression requires a successful same-target read or preservation of unrelated content before overwrite."
  missing:
    - "Teach a compact same-file read -> Observation -> write edit transcript and prohibit memory as a substitute for file contents."
    - "Require a successful same-target read before overwriting an existing file and reject stale snapshots."
    - "Show create-versus-overwrite plus a locally computed diff or content preview at confirmation."
    - "Add model-independent regressions for premature writes, stale reads, and preservation of unrequested content."
  debug_session: ".planning/debug/file-edit-wrong-content.md"
