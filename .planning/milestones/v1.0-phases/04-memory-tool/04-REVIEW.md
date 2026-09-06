---
phase: 04-memory-tool
reviewed: 2026-07-30T16:39:18Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/olla/loop.py
  - src/olla/parser.py
  - src/olla/prompts.py
  - src/olla/tools/memory.py
  - tests/test_loop.py
  - tests/test_parser.py
  - tests/test_prompts.py
  - tests/test_tools/test_memory.py
findings:
  critical: 1
  warning: 2
  info: 0
  total: 3
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-30T16:39:18Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The post-fix review found one security blocker and two correctness/robustness warnings. The five prior findings are repaired on their originally tested paths, and all 187 scoped tests plus all 313 maintained tests pass. However, deterministic probes reproduced an incomplete cross-tool trust-state fix: recalled notes are now correctly represented as untrusted tool-role messages, but the execution gate does not mark that observation as untrusted, allowing `--yes` to skip a following write or CONFIRM-tier shell prompt. The parser's outer-fence repair also handles only equal-length fences, and the public memory boundary still admits multi-line and arbitrarily large keys that violate the protocol/resource assumptions.

## Narrative Findings (AI reviewer)

The findings below come from direct adversarial review and read-only execution probes against the current working tree. No structural/fallow findings were supplied.

## Critical Issues

### CR-01: Recall's tool-role trust label is not propagated to the confirmation gate

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:709-726`

**Affected paths:** `/home/nacs/Documents/git/olla/src/olla/loop.py:505-507`, `/home/nacs/Documents/git/olla/src/olla/loop.py:632-648`, `/home/nacs/Documents/git/olla/src/olla/loop.py:808-814`

**Issue:** `_execute_memory()` correctly records every recall through `_record_memory_observation()` as an explicitly untrusted `role: "tool"` message, and the system prompt likewise declares recalled notes untrusted. Unlike successful file and shell observations, however, the memory branch never updates `untrusted_observation_seen`. Consequently, with `yes=True`, the next CONFIRM-tier shell call or `write_file` call bypasses `Confirm.ask` even though it immediately follows an observation the application itself labels untrusted. A deterministic `remember -> recall -> write_file` probe produced `confirm_calls == 0` and `write_calls == 1`. This leaves the previous CR-01 fix inconsistent with the confirmation hardening and allows instructions or hallucinated actions resurfacing through recall to reach host-side effects without the independent confirmation promised after untrusted tool output.

**Fix:** Make `_execute_memory()` return whether it emitted an untrusted recall observation and merge that result into the same sticky trust state used by file and shell observations. Add `yes=True` regressions for recall followed by both `write_file` and a CONFIRM-tier shell call.

```python
def _execute_memory(...) -> bool:
    ...
    if action.memory_request.tool == "recall":
        _record_memory_observation(messages, preview)
        return True
    _record_observation(messages, preview)
    return False

# In run_loop:
untrusted_observation_seen = (
    _execute_memory(...)
    or untrusted_observation_seen
)
```

## Warnings

### WR-01: Valid longer closing Markdown fences leak into unclosed tool arguments

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:14-26`

**Issue:** `_unwrap_outer_markdown_fence()` requires the closing delimiter to be exactly the same length as the opening delimiter. Markdown closing fences may use the same character with at least the opening length. When a small model emits an otherwise valid longer closer while also omitting `</args>`, the outer wrapper is not removed and becomes part of the semantic payload. Deterministic probes returned `"key\nvalue\n````"` for a triple-backtick-wrapped `remember`, `"key \n~~~~"` for `recall`, and a five-backtick suffix in `write_file` content. This is the same data-corruption class the outer-fence fix was intended to close.

**Fix:** Match a closing run of the same fence character whose length is greater than or equal to the opening run, while still requiring only whitespace after it and end-of-input. Add longer-closer tests for `remember`, `recall`, `write_file`, and one ordinary tool; retain a negative test proving a shorter closer is not unwrapped.

```python
fence_char = re.escape(delimiter[0])
minimum = len(delimiter)
closing = re.search(
    rf"\r?\n[ \t]*{fence_char}{{{minimum},}}[ \t]*(?:\r?\n)?\Z",
    content,
)
```

### WR-02: Memory-key validation still permits unreachable and context-bloating keys

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/tools/memory.py:20-49`

**Affected paths:** `/home/nacs/Documents/git/olla/src/olla/tools/memory.py:58-97`, `/home/nacs/Documents/git/olla/src/olla/loop.py:289-317`, `/home/nacs/Documents/git/olla/src/olla/loop.py:709-726`

**Issue:** The repaired public boundary trims and rejects empty keys, but it does not enforce the protocol's one-line key shape or any key-size bound. `Scratchpad.remember(RememberCall("first\nsecond", "secret"))` succeeds and can be recalled directly, even though `parse_remember_args("first\nsecond\nsecret")` necessarily creates key `first` and value `second\nsecret`; the public adapter can therefore hold states the model-facing remember protocol cannot create. Separately, a 5,000-character missing recall key produces a 5,018-character model Observation and an equally large progress line because keys are neither bounded nor passed through `truncate_output`, exceeding `MAX_OBSERVATION_CHARS` and undermining the phase's bounded-scratchpad/context contract.

**Fix:** Define and enforce a one-line maximum key length in both argument parsers and the public `Scratchpad` methods, returning actionable non-raising errors before mutation. Defensively bound memory error/acknowledgment Observations as well. Add direct-boundary tests for embedded line delimiters and boundary/over-bound key lengths, plus a loop test asserting oversized key text cannot exceed the configured Observation budget.

## Validation

- Scoped suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_loop.py tests/test_parser.py tests/test_prompts.py tests/test_tools/test_memory.py` — 187 passed.
- Full maintained suite: `.venv/bin/python -B -m pytest -p no:cacheprovider -q` — 313 passed.
- Scoped Ruff with `--no-cache` — passed.
- Scoped `git diff --check` — passed.
- Deterministic probes reproduced CR-01, WR-01, and both WR-02 boundary failures.
- No source files were modified.

---

_Reviewed: 2026-07-30T16:39:18Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
