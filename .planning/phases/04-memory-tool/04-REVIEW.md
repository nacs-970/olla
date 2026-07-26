---
phase: 04-memory-tool
reviewed: 2026-07-26T18:59:04Z
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
  critical: 4
  warning: 3
  info: 0
  total: 7
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-26T18:59:04Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The scoped suite passes (`107 passed`), the full maintained suite passes (`200 passed`), and Ruff reports no violations. Those checks do not exercise several adversarial protocol cases: direct probes reproduced four correctness/privacy blockers involving stop-sequence data loss, non-round-trippable keys, incorrect final precedence, and disclosure through a malformed tool tag. The bounded `Scratchpad` replacement logic is atomic at the specified value, key-count, and total-value boundaries, but the model-facing parser and loop do not safely preserve all accepted memory calls. Three additional warnings cover the undocumented memory delimiter restriction, duplicated dispatch policy, and incorrect truncation behavior for supported custom limits.

## Narrative Findings (AI reviewer)

The following findings come from direct review and read-only execution probes against the submitted files.

## Critical Issues

### CR-01: `Observation:` silently truncates a remembered value

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:33`

**Issue:** `call_model()` configures `"Observation:"` as a generation stop sequence, although that text is valid note content under the contract that every value character is preserved. Ollama can therefore return only `<tool>remember</tool><args>key\nbefore ` for a proposed value such as `before Observation: after`. Because `ARGS_RE` deliberately accepts an unclosed args block through end-of-input, `parse_response()` and `parse_remember_args()` accept that prefix as a valid `RememberCall`; the loop then reports a normal success while silently losing the suffix. The existing `test_call_model` asserts the unsafe option instead of covering the collision.

**Fix:** Remove `"Observation:"` from the stop list and add an integration regression proving that this substring survives inside a remembered value.

```python
response = ollama.chat(
    model=model,
    messages=messages,
    options={"stop": ["</args>"], "num_ctx": 8192},
    think=think,
)
```

### CR-02: Legal remember keys cannot be recalled byte-for-byte

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:32-56`

**Issue:** `remember` uses the raw opaque-args branch, so non-empty keys such as `a```b` and `<final>name</final>` are accepted and stored after trimming. `recall` instead passes through global Markdown-fence removal and a second final-tag search. A direct probe parsed recall of `a```b` as key `a`, while recall of `<final>name</final>` became a final answer and would terminate the loop. This violates the case-sensitive key contract, under which trimming is the only key normalization, and makes accepted notes unreachable or able to alter loop control.

**Fix:** Handle `recall` before code-fence stripping and secondary final detection, preserve its raw payload, and apply only `.strip()`/`parse_recall_args()` normalization. Add remember/recall round-trip tests for backticks and tag-looking keys.

```python
if raw_tool_match and raw_args_match:
    tool = raw_tool_match.group(1).strip()
    if tool in {"write_file", "remember"}:
        return {"type": "tool", "tool": tool, "args_raw": raw_args_match.group(1)}
    if tool == "recall":
        return {
            "type": "tool",
            "tool": tool,
            "args_raw": raw_args_match.group(1).strip(),
        }
```

### CR-03: A literal inner final tag hides a later real final answer

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:19-30`

**Issue:** Final precedence inspects only the first `FINAL_RE.search()` match. For `<tool>remember</tool><args>key\nliteral <final>data</final></args><final>done</final>`, the first final is correctly recognized as payload data, but the parser never looks for the later outside final. It returns the remember call instead of the real `done` answer. This contradicts the intended rule that tag-looking text inside an opaque value remains data while an outside final wins.

**Fix:** Examine all final candidates and return the first one outside the matched opaque args span. Add a regression containing both an inner literal final and a later outer final.

```python
args_span = raw_args_match.span(1) if raw_args_match else None
for final_match in FINAL_RE.finditer(content):
    if args_span is None or not (args_span[0] <= final_match.start() < args_span[1]):
        return {"type": "final", "text": final_match.group(1).strip()}
```

### CR-04: A missing `</tool>` discloses the proposed memory value

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:6`

**Affected output paths:** `/home/nacs/Documents/git/olla/src/olla/loop.py:103-105`, `/home/nacs/Documents/git/olla/src/olla/loop.py:296-299`

**Issue:** `TOOL_RE` tolerates an unclosed tool tag by capturing through end-of-input. For `<tool>remember<args>key\nTOP_SECRET</args>`, the parsed tool identifier becomes the multiline string `remember<args>key\nTOP_SECRET</args>`. Both normal and dry-run unknown-tool branches interpolate that unvalidated identifier into terminal output; normal mode also returns it to the model as an Observation. A direct dry-run probe printed the sentinel value, bypassing the memory write-preview redaction policy.

**Fix:** Terminate an unclosed tool-name capture at a following `<args>` opener or reject malformed identifiers without echoing their raw contents. Add normal and dry-run privacy regressions.

```python
TOOL_RE = re.compile(
    r"<tool>(.*?)(?:</tool>|(?=<args>)|$)",
    re.DOTALL | re.IGNORECASE,
)
```

## Warnings

### WR-01: The prompt omits the remembered-value delimiter restriction

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/prompts.py:31`

**Issue:** The prompt warns that literal `</args>` truncates file content, but gives no equivalent warning for remembered values even though both use the same delimiter and model stop sequence. A model asked to remember that literal text will submit only the prefix, which the tolerant parser accepts as a complete value. The user receives a success acknowledgment for incomplete memory.

**Fix:** Extend the warning and prompt contract test to cover remembered values. If the literal delimiter must be representable, define an escaping/encoding rule instead of accepting a truncated prefix.

```text
Never include a literal </args> sequence inside file content or a remembered value — it will cut off your output early.
```

### WR-02: Memory policy is duplicated across a 273-line dispatch function

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:37-309`

**Issue:** `run_loop()` has separate dry-run and normal dispatch trees, and each tool branch repeats signature accounting, the third-repeat check, result selection, printing, and Observation creation. This is a concrete robustness risk: malformed memory output reaches generic branches that do not enforce memory redaction, as CR-04 demonstrates, and every new tool must independently preserve output/Observation parity and confirmation rules.

**Fix:** Extract shared repetition and Observation helpers, then route memory parsing/rendering through one handler with explicit preview/execution behavior. Keep the `Scratchpad` instance local to `run_loop()` and preserve the existing per-tool confirmation semantics.

### WR-03: `truncate_output()` reports and retains the wrong amount for odd or zero limits

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:22-28`

**Issue:** Both head and tail use `limit // 2`. For an odd limit such as `5`, only four payload characters are retained while the marker claims `len(text) - 5` were removed; for `limit` 0 or 1, `text[-0:]` returns the entire string, so the helper does not truncate at all. The default limit happens to be even, but the public `limit` parameter advertises behavior that is incorrect at valid boundary values.

**Fix:** Allocate the remainder to the tail, handle a zero-length tail explicitly, and reject negative limits. Add tests for odd, one-character, zero, and negative limits.

```python
if limit < 0:
    raise ValueError("limit must be non-negative")
head_len = limit // 2
tail_len = limit - head_len
head = text[:head_len]
tail = text[-tail_len:] if tail_len else ""
```

---

_Reviewed: 2026-07-26T18:59:04Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
