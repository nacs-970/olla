# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-09-07  
**Phases:** 5 | **Plans:** 19 | **Tasks:** 36

### What Was Built
- ReAct agentic execution loop driving shell, file read/write, and scratchpad memory
- XML-style tolerant parser (`<tool>`, `<args>`, `<final>`) with streaming tag leak suppression
- Defense-in-depth safety gate: command blocklist, recursive unwrapping, confirm prompt, `--yes` override
- POSIX atomic writes, mandatory read-derived overwrite checks, bounded unified diff previews
- Pluggable provider architecture supporting local Ollama and remote OpenAI-compatible endpoints

### What Worked
- Fast test suite: 375 tests executing in ~7 seconds without flaky external dependencies
- Defense-in-depth safety layering prevented both command-line injection and indirect prompt injection attacks
- Strict read-derived overwrite requirement completely eliminated destructive file replacement by small models

### What Was Inefficient
- Small models (0.6B-2B) struggle with implicit multi-step tool dependencies, requiring explicit prompt-level instruction and runtime prerequisite enforcement
- Initial blocklist required multiple refinement passes to close subtle bypasses (`normpath`, flags, recursive wrappers)

### Patterns Established
- Pre-parsed argv threading from safety checks directly to execution
- Read-derived overwrite protocol: read, snapshot, diff preview, recheck freshness, atomic write
- Invocation-scoped bounded scratchpad memory

### Key Lessons
1. Never trust small models to preserve file context across overwrites without deterministic runtime guards.
2. Recursive shell parsing (`sh -c`, `find -exec`, `env`) must precede blocklist filtering.

### Cost Observations
- Notable: 100% automated test coverage of safety gates before live model execution.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 5 | 19 | Initial release with full safety gate and provider abstraction |

### Cumulative Quality

| Milestone | Tests | Verification | Gaps Found / Resolved |
|-----------|-------|--------------|-----------------------|
| v1.0 | 375 | Passed (16/16 reqs) | 3 items resolved before closeout |

### Top Lessons (Verified Across Milestones)

1. Small models need deterministic runtime constraints rather than soft prompt instructions.
