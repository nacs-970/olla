---
phase: 04-memory-tool
fixed_at: 2026-07-30T16:22:43Z
review_path: /home/nacs/Documents/git/olla/.planning/phases/04-memory-tool/04-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-07-30T16:22:43Z
**Source review:** `.planning/phases/04-memory-tool/04-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: Recall promotes potentially untrusted data to a user instruction

**Files modified:** `src/olla/loop.py`, `src/olla/prompts.py`, `tests/test_loop.py`, `tests/test_prompts.py`
**Commit:** 3cc3870
**Status:** fixed
**Applied fix:** Recalled values now use a dedicated tool-role Observation wrapped in an explicit untrusted-memory envelope, while terminal rendering remains verbatim. The system prompt identifies recalled notes as untrusted data, and a read → remember → recall regression proves attacker-controlled bytes never reappear with the `user` role.

### WR-01: Suffix-final recovery treats payload finals as outer answers

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** 6b5b3a0
**Status:** fixed: requires human verification
**Applied fix:** Final openings are counted independently outside opaque args spans, and special-tool suffixes containing additional protocol structure are rejected before a tool call is accepted. Regressions cover a final inside a second args block and multiple outer finals following an unclosed payload final.

### WR-02: An outer Markdown fence becomes part of an unclosed memory value

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** a56c6f1
**Status:** fixed: requires human verification
**Applied fix:** A single matching outer backtick or tilde fence is removed before protocol parsing without stripping interior payload fences. Combined fenced-plus-unclosed regressions cover `remember`, `recall`, and an ordinary shell tool.

### WR-03: Public scratchpad methods bypass the declared key contract

**Files modified:** `src/olla/tools/memory.py`, `tests/test_tools/test_memory.py`
**Commit:** 58c629c
**Status:** fixed
**Applied fix:** Public scratchpad methods now trim keys, reject empty or whitespace-only keys with the parser's exact errors, and consistently use the normalized key for storage, lookup, acknowledgments, and missing-key diagnostics. Direct-boundary regressions cover invalid and whitespace-surrounded keys.

### WR-04: Ollama request failures escape and abort the CLI

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 426c653
**Status:** fixed
**Applied fix:** Normal and dry-run model calls now catch Ollama request and response errors at the loop boundary, print a terminal-safe diagnostic with recovery guidance, and return cleanly. Regressions exercise both client exception types in both execution modes.

## Skipped Issues

None.

## Verification

- Focused per-finding tests passed before each atomic commit.
- Scoped Phase 4 suite: 187 passed.
- Full maintained suite: 313 passed.
- Ruff: all maintained source and test files passed with `--no-cache`.
- Python compilation: all maintained source and test modules passed.
- Cumulative `git diff --check`: passed.
- Cumulative diff contains only the eight reviewed production and test files.
- Isolated worktree source status was clean; this report remained uncommitted for the orchestrator.
- All five commits were fast-forwarded to `main` through `426c653`; the full suite and static gates passed again after integration.

---

_Fixed: 2026-07-30T16:22:43Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
