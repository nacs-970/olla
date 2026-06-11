---
status: complete
phase: 01-core-loop-shell-tool-cli
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-06-11T00:00:00Z
updated: 2026-06-11T00:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CLI requires --model
expected: |
  Run: olla "do something"
  Output includes: Error: --model is required (no hardcoded default model, CLI-01)
  Exit code is non-zero.
result: pass

### 2. CLI requires TASK
expected: |
  Run: olla (no arguments)
  Output is a usage error mentioning TASK (e.g. "TASK argument is required").
  Exit code is non-zero.
result: pass

### 3. --dry-run prints inert notice
expected: |
  Run: olla "echo hi" --model YOUR_MODEL --dry-run
  Before the agent loop starts, output includes:
  "Note: --dry-run is not yet enforced (Phase 2); the agent may execute real commands."
  The agent loop still runs after the notice (real commands execute).
result: pass

### 4. --yes prints inert notice
expected: |
  Run: olla "echo hi" --model YOUR_MODEL --yes
  Before the agent loop starts, output includes:
  "Note: --yes is not yet enforced (Phase 2); confirmation prompts are not implemented yet."
result: pass

### 5. End-to-end no-tool answer
expected: |
  Run: olla "what is 1+1?" --model YOUR_MODEL
  Model responds with a <final> answer; CLI prints just the final text (e.g. "2"),
  with no "Step N: running [...]" line (no shell command executed).
result: pass

### 6. End-to-end tool-calling
expected: |
  Run: olla "list the files in the current directory" --model YOUR_MODEL
  CLI prints "Step 1: running ['ls', ...]..." followed by a real directory
  listing, then prints a final answer summarizing the result.
result: pass

### 7. --smoke-test compliance check
expected: |
  Run: olla --smoke-test --model YOUR_MODEL
  CLI runs the fixed prompts under think=False and think=True, printing
  per-mode compliance percentages (compliant / reverted-to-native /
  non-compliant counts). If think=False compliance is below 80%, a line
  starting with a D-08 WARNING is printed.
result: pass

### 8. --smoke-test without --model
expected: |
  Run: olla --smoke-test
  Output is a usage error mentioning --model.
  Exit code is non-zero.
result: pass

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
