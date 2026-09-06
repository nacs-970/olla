---
phase: 04-memory-tool
fixed_at: 2026-07-30T16:49:36Z
review_path: .planning/phases/04-memory-tool/04-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-07-30T16:49:36Z
**Source review:** `.planning/phases/04-memory-tool/04-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### CR-01: Recall's tool-role trust label is not propagated to the confirmation gate

**Status:** fixed: requires human verification
**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** 95dd6b9
**Applied fix:** Made memory execution report whether it emitted an untrusted recall Observation, merged that result into the loop's sticky trust state, and added `yes=True` regressions proving recalled data cannot bypass write or CONFIRM-tier shell prompts.

### WR-01: Valid longer closing Markdown fences leak into unclosed tool arguments

**Status:** fixed
**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** 4e98574
**Applied fix:** Allowed an outer Markdown closing fence to use the same character with a run at least as long as its opener, with coverage for remember, recall, write_file, ordinary tools, and shorter-closer rejection.

### WR-02: Memory-key validation still permits unreachable and context-bloating keys

**Status:** fixed
**Files modified:** `src/olla/tools/memory.py`, `src/olla/loop.py`, `tests/test_tools/test_memory.py`, `tests/test_loop.py`
**Commit:** 2001f92
**Applied fix:** Added shared one-line and 128-character key validation at parser and public scratchpad boundaries, kept failures non-mutating, and bounded executed memory Observations through the existing truncation policy.

## Validation

- Phase-focused suite: 204 passed
- Full maintained suite: 330 passed
- Full-project Ruff: passed
- Source and test compilation: passed
- Cumulative diff and whitespace checks: passed
- All three commits were fast-forwarded to `main` through `2001f92`; the full suite and static gates passed again after integration.

---

_Fixed: 2026-07-30T16:49:36Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
