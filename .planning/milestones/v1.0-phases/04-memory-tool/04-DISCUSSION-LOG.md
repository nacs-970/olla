# Phase 4: Memory Tool - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-25
**Phase:** 4-Memory Tool
**Areas discussed:** Store and recall contract, Key and update rules, Scratchpad limits, User-visible behavior, Explicitly empty recall, Prompt teaching footprint, Error diagnostics

---

## Store and Recall Contract

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Retrieval mechanism | Separate `recall(key)` tool | Overload `remember`; inject all notes every turn |
| `remember` argument format | Key on first line, value on remaining lines | `key=value`; fixed delimiter |
| Whitespace handling | Trim key, preserve value exactly | Trim both; preserve both exactly |
| Success observations | `remembered: <key>`; recall returns value verbatim | Label both responses; echo key and value after write |

**User's choice:** Selected the recommended explicit two-tool, line-oriented contract throughout.
**Notes:** The format honors the project-wide non-JSON micro-format decision.

---

## Key and Update Rules

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Case matching | Case-sensitive after trimming | Case-insensitive; agent discretion |
| Existing key | Overwrite atomically | Reject; append |
| Missing lookup | `memory not found: <key>` | Empty value; generic missing message |
| Empty/malformed write | Reject empty key or missing value line; allow explicit empty value | Reject all empty values; treat key-only as empty |

**User's choice:** Selected predictable dictionary semantics with explicit missing/malformed outcomes.
**Notes:** A missing value line is distinct from a present zero-character value.

---

## Scratchpad Limits

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Limit dimensions | Per-value, key-count, and total-character limits | Per-value only; no explicit bounds |
| Per-value limit | 2,000 characters | 1,000; 4,000; user briefly proposed 2,500 then revised to 2,000 |
| Overall limits | 32 keys and 16,000 value characters | 16/16,000; 64/64,000 |
| Overflow behavior | Reject atomically, preserve scratchpad | Evict oldest; truncate new value |

**User's choice:** Selected all three hard bounds and non-destructive rejection.
**Notes:** The final 2,000-character choice matches the existing observation limit.

---

## User-Visible Behavior

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Progress line | `Step N: remembering/recalling <key>...` | Generic running line; no progress |
| Observation visibility | Print acknowledgments, values, and errors | Hide recalled values; model-only observations |
| Confirmation | Never prompt | Confirm writes only; confirm both |
| Dry-run | Validate; show key and value length, never value | Show full value; show tool name only |

**User's choice:** Selected consistency with existing visible tool steps without echoing a value during storage.
**Notes:** Memory remains confirmation-free because it has no host side effects.

---

## Explicitly Empty Recall

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Empty recall | `memory is empty: <key>` | `(empty memory)`; `(no output)` |
| Empty write acknowledgment | `remembered empty: <key>` | Normal acknowledgment; `(0 chars)` suffix |
| Limit accounting | One key, zero value characters | Synthetic character; count against neither |
| Whitespace-only values | Preserve and treat as non-empty | Normalize to empty; reject |

**User's choice:** Selected explicit empty-state messages and exact whitespace preservation.
**Notes:** This prevents the loop's generic `(no output)` fallback from hiding a valid empty memory.

---

## Prompt Teaching Footprint

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Teaching method | Short rules plus one compact round-trip example | Rules only; separate example per tool |
| Example behavior | Store a concrete fact, recall later, use in `<final>` | Immediate recall; placeholders only |
| Observations in example | Show both exact memory observations | Tool calls only; recall observation only |
| Existing prompt content | Preserve all shell/file teaching | Consolidate all examples; remove existing examples |

**User's choice:** Selected a single concrete memory transcript added alongside the existing validated prompt.
**Notes:** When all three mutually exclusive teaching options were entered initially, the user clarified option 1.

---

## Error Diagnostics

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Malformed writes | Distinct actionable messages | Generic invalid arguments; full usage on every error |
| Empty recall key | `invalid recall: key must not be empty` | Missing-memory response; generic invalid arguments |
| Oversized value | Report actual size and 2,000 limit | Limit only; generic memory-limit error |
| Whole-scratchpad overflow | Distinguish key and total capacity failures | One generic message; always report all metrics |

**User's choice:** Selected concise errors containing exactly the information needed for the model to correct its next call.
**Notes:** Total-capacity errors report the attempted total size; key-limit errors report the 32-key maximum.

---

## the agent's Discretion

- Exact internal data types and helper/function names.
- Whether memory results add dedicated `ToolResult` fields or reuse an existing field.
- Test decomposition and any focused dispatch refactor needed to avoid branch duplication.

## Deferred Ideas

- MEM-02 context compaction remains a v2 requirement and was not added to Phase 4.
