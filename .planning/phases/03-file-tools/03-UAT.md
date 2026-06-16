---
status: partial
phase: 03-file-tools
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md
started: 2026-06-16T02:47:00Z
updated: 2026-06-16T02:47:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 12
name: "[testing complete]"
expected: |
  [testing complete]
awaiting: user response

## Tests

### 1. User-Flow Step 1 - Run olla with a read/write task
expected: Start olla with a prompt like `olla "read test.txt, replace 'foo' with 'bar', and write it back"`. The loop starts.
result: issue
reported: "User ran command with `--model qwen3.5:0.8b-256k`. It resulted in `error: could not parse command: No closing quotation` and the model falsely claimed it was successful without calling read_file or writing anything."
severity: major

### 2. User-Flow Step 2 - Observe read_file tool call
expected: The model calls `read_file` on `test.txt`. You should see the tool execution output in the console.
result: pass

### 3. User-Flow Step 3 - Observe write_file confirm prompt
expected: The model calls `write_file` to update `test.txt`. You should see a confirm prompt that displays the resolved absolute path of the file.
result: issue
reported: "User created test.txt, but the model (qwen3.5:2b-256k) hallucinated shell commands and bad read_file paths, eventually hitting max steps (15) without ever calling write_file."
severity: blocker

### 4. User-Flow Step 4 - Confirm the write and assert outcome
expected: Type 'y' to confirm. The loop finishes. Open `test.txt` and verify the content is updated successfully.
result: blocked
blocked_by: prior-phase
reason: "what do you want me to do? again?"

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
passed: 1
issues: 2
pending: 0
skipped: 7
blocked: 1

## Gaps

- truth: "Start olla with a prompt like `olla \"read test.txt, replace 'foo' with 'bar', and write it back\"`. The loop starts."
  status: failed
  reason: "User reported: User ran command with `--model qwen3.5:0.8b-256k`. It resulted in `error: could not parse command: No closing quotation` and the model falsely claimed it was successful without calling read_file or writing anything."
  severity: major
  test: 1

- truth: "The model calls `write_file` to update `test.txt`. You should see a confirm prompt that displays the resolved absolute path of the file."
  status: failed
  reason: "User reported: User created test.txt, but the model (qwen3.5:2b-256k) hallucinated shell commands and bad read_file paths, eventually hitting max steps (15) without ever calling write_file."
  severity: blocker
  test: 3
