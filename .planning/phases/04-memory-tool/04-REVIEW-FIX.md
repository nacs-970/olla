---
phase: 04-memory-tool
fixed_at: 2026-07-26T20:07:22Z
review_path: /home/nacs/Documents/git/olla/.planning/phases/04-memory-tool/04-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-07-26T20:07:22Z
**Source review:** `/home/nacs/Documents/git/olla/.planning/phases/04-memory-tool/04-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 7
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: `Observation:` silently truncates a remembered value

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** `0eed98d`
**Applied fix:** Removed `Observation:` from the Ollama stop sequences and added a loop regression proving that a remembered value containing the substring survives a remember/recall round trip.

### CR-02: Legal remember keys cannot be recalled byte-for-byte

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** `ea0aabe`
**Applied fix:** Routed recall through the raw opaque-args path before Markdown-fence stripping and secondary final handling. Added backtick and tag-looking key round-trip coverage.

### CR-03: A literal inner final tag hides a later real final answer

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`
**Commit:** `5543f02`
**Status:** fixed: requires human verification
**Applied fix:** Scanned all final candidates in order, ignored candidates inside the opaque args span, and returned the first outside final. Added an inner-literal-plus-outer-final regression.

### CR-04: A missing `</tool>` discloses the proposed memory value

**Files modified:** `src/olla/parser.py`, `tests/test_parser.py`, `tests/test_loop.py`
**Commit:** `6752700`
**Applied fix:** Terminated unclosed tool-name capture at a following `<args>` opener. Added parser, normal-loop, and dry-run privacy regressions proving the proposed value is absent from terminal output and Observations.

### WR-01: The prompt omits the remembered-value delimiter restriction

**Files modified:** `src/olla/prompts.py`, `tests/test_prompts.py`
**Commit:** `df6c8e1`
**Applied fix:** Extended the literal `</args>` warning to remembered values and updated the prompt contract assertion.

### WR-02: Memory policy is duplicated across a 273-line dispatch function

**Files modified:** `src/olla/loop.py`
**Commit:** `da9c7db`
**Applied fix:** Centralized normalized memory request preparation, shared preview/execution rendering, repetition tracking, and Observation parity while keeping the scratchpad invocation-local and preserving tool confirmation behavior.

### WR-03: `truncate_output()` reports and retains the wrong amount for odd or zero limits

**Files modified:** `src/olla/loop.py`, `tests/test_loop.py`
**Commit:** `80a101b`
**Applied fix:** Allocated odd remainders to the tail, handled a zero-length tail explicitly, rejected negative limits, and added odd, one-character, zero, and negative boundary tests.

## Verification

- Focused per-finding tests passed during each atomic fix.
- `tests/test_loop.py`: 71 passed after the WR-02 refactor.
- Focused truncation checks: 6 passed.
- Full maintained suite: 211 passed (`.venv/bin/pytest -q`).
- Maintained lint: clean (`.venv/bin/ruff check src tests`).
- Repository-wide Ruff also inspected untracked user-owned scratch files and reported pre-existing errors in `final_replace.py` and `read_and_replace.py`; those unrelated files were not modified.
- No fix-owned changes remain staged. Existing user-owned working-tree changes remain unstaged and preserved.

---

_Fixed: 2026-07-26T20:07:22Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
