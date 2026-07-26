---
phase: 04-memory-tool
reviewed: 2026-07-26T18:43:00Z
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
  warning: 2
  info: 0
  total: 6
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-26T18:43:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The scoped suite passes (`107 passed`) and Ruff reports no violations, but fresh adversarial probes reproduced four correctness/privacy blockers. Legitimate memory text can be silently truncated, some accepted keys cannot be recalled, final precedence fails when a payload contains a literal final tag before a real final answer, and a malformed tool tag can print the private value. The bounded `Scratchpad` replacement logic is atomic at the specified value, key, and total-capacity boundaries. Normal memory results preserve Observation parity on the covered cases, the third normalized repeated memory call is stopped before adapter execution, dry-run does not call the adapter, and separate `run_loop` invocations receive separate stores.

## Narrative Findings (AI reviewer)

The following findings come from direct review and read-only execution probes against the submitted files.

## Critical Issues

### CR-01: `Observation:` in a note silently truncates the stored value

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:33`

**Issue:** `call_model()` configures `"Observation:"` as a generation stop sequence. That string is ordinary, legal note content under the raw remember contract. If the model generates `<args>key\nbefore Observation: after</args>`, Ollama stops before `Observation:`. Because `ARGS_RE` accepts an unclosed args block through end-of-input, the parser accepts the returned prefix and `Scratchpad.remember()` stores it with a normal success acknowledgment. The loss is therefore silent. `tests/test_loop.py:36` currently asserts the unsafe stop list rather than testing this collision.

**Fix:** Remove `"Observation:"` from the model stop list and add a regression proving that a remember value containing that exact substring reaches `parse_remember_args()` intact.

```python
response = ollama.chat(
    model=model,
    messages=messages,
    options={"stop": ["</args>"], "num_ctx": 8192},
    think=think,
)
```

### CR-02: Accepted remember keys do not round-trip through `recall`

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:32-56`

**Issue:** `remember` uses the raw opaque-argument path, so keys such as `a```b` and `<final>name</final>` are accepted and stored after trimming. `recall` instead goes through global code-fence stripping and a second final-tag search. A reproduced end-to-end run stored `a```b`, then recalled key `a` and returned `memory not found: a`; recalling `<final>name</final>` is parsed as a final answer and terminates the loop. This violates the contract that keys are normalized only by trimming and remain case-sensitive.

**Fix:** Preserve raw arguments for `recall` too, then let `parse_recall_args()` perform the only key normalization. Add end-to-end regressions for keys containing backticks and tag-looking text.

```python
OPAQUE_ARG_TOOLS = {"write_file", "remember", "recall"}

if raw_tool_match and raw_args_match:
    tool = raw_tool_match.group(1).strip()
    if tool in OPAQUE_ARG_TOOLS:
        return {"type": "tool", "tool": tool, "args_raw": raw_args_match.group(1)}
```

### CR-03: An inner literal final tag hides a later real final answer

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:19-30`

**Issue:** Final precedence examines only `FINAL_RE.search(content)`, the first final match. For `<tool>remember</tool><args>key\nliteral <final>data</final></args><final>done</final>`, the first match is correctly identified as payload data, but the parser never searches for the later outside match and returns the remember call instead of `done`. This contradicts the locked decision that literal finals inside opaque args remain data while a final outside args wins.

**Fix:** Examine every final opener/match and return the first one whose start is outside the opaque argument span. Add a regression containing both an inner literal final and a later outer final.

```python
args_start, args_end = raw_args_match.span(1) if raw_args_match else (-1, -1)
for opener in re.finditer(r"<final>", content, re.IGNORECASE):
    if not (args_start <= opener.start() < args_end):
        final_match = FINAL_RE.match(content, opener.start())
        if final_match:
            return {"type": "final", "text": final_match.group(1).strip()}
```

### CR-04: A missing `</tool>` discloses the remember value

**Classification:** BLOCKER

**File:** `/home/nacs/Documents/git/olla/src/olla/parser.py:6`

**Affected output paths:** `/home/nacs/Documents/git/olla/src/olla/loop.py:103-105`, `/home/nacs/Documents/git/olla/src/olla/loop.py:296-299`

**Issue:** `TOOL_RE` tolerates an unclosed tool tag by capturing through end-of-input. For `<tool>remember<args>key\nTOP_SECRET</args>`, the parsed tool name becomes `remember<args>key\nTOP_SECRET</args>`. Both dry-run and normal unknown-tool branches interpolate that entire string into terminal output; normal mode also sends it back as an Observation. The fresh dry-run probe printed `Model would call unknown tool 'remember<args>key\nTOP_SECRET</args>'`, violating the explicit no-disclosure contract.

**Fix:** Stop an unclosed tool-name capture at a following `<args>` opener (or reject it without echoing raw text), and never interpolate an unvalidated multiline tool identifier into user-visible output. Add normal and dry-run malformed-tag privacy regressions.

```python
TOOL_RE = re.compile(
    r"<tool>(.*?)(?:</tool>|(?=<args>)|$)",
    re.DOTALL | re.IGNORECASE,
)
```

## Warnings

### WR-01: The prompt omits the remember payload's delimiter restriction

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/prompts.py:19-32`

**Issue:** The prompt warns that literal `</args>` truncates file content, but gives no equivalent warning for remembered values even though they use the same delimiter and model stop sequence. A model asked to remember that literal text will store only the prefix without being told that the format cannot represent the input.

**Fix:** Extend the warning and its contract test to cover remembered values. If literal delimiter fidelity is required, define an escaping rule instead of silently accepting a prefix.

```text
Never include a literal </args> sequence inside file content or a remembered value — it will cut off your output early.
```

### WR-02: Memory dispatch extends a 273-line duplicated control-flow path

**Classification:** WARNING

**File:** `/home/nacs/Documents/git/olla/src/olla/loop.py:37-309`

**Issue:** `run_loop()` contains separate dry-run and normal dispatch trees plus repeated signature counting, third-repeat checks, result selection, printing, and Observation appending for each tool. This is a concrete robustness problem rather than a formatting preference: malformed memory output can fall into generic branches that do not share the memory privacy policy, as CR-04 demonstrates, while each new tool must independently preserve exact output/Observation parity.

**Fix:** Extract shared helpers for repetition accounting and Observation rendering, and route parsed memory calls through one handler used by both execution modes. Keep `Scratchpad` construction invocation-local and pass an execution/preview flag into the handler rather than duplicating policy.

---

_Reviewed: 2026-07-26T18:43:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
