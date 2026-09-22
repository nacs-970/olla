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

## Milestone: v1.1 — Tools Expansion & Interactive REPL

**Shipped:** 2026-09-22
**Phases:** 3 | **Plans:** 7 | **Tasks:** 15

### What Was Built
- Safe read-only inspection tools (`list_dir`, `grep_files`), unprompted dispatch bypassing `safety.check()` entirely (D-09)
- Web search (`search_web`) and page fetch (`fetch_url`) via curl/httpx, DuckDuckGo Lite parsing, shared truncation/untrusted-tagging chokepoints
- Full interactive REPL (`olla` with no task argument): `prompt_toolkit` session, persistent history, multiline editing, slash commands (`/model`/`/exit`/`/quit`/`/clear`), double-Ctrl+C exit
- Cross-turn `SessionState` sharing (Scratchpad, read snapshots, untrusted-observation flag) threaded through `run_loop()` as an optional param, one-shot CLI path unchanged
- `tiktoken`-based rolling context trim with untrusted-tagged LLM-generated digests replacing dropped turns

### What Worked
- Independently re-running the full test suite after every wave (not trusting executor self-reports) caught nothing broken across 7 plans
- `SessionState` as an optional trailing param avoided duplicating `run_loop()`'s step-loop machinery for the REPL path
- Sharing one truncation/untrusted-tagging chokepoint between `fetch_url` and `search_web` avoided two near-duplicate implementations

### What Was Inefficient
- Phase 7 shipped with 2 automated-verification gaps (multiline editing didn't actually enable multiline; a cross-turn stale-snapshot case was untested) that a first `gsd-verifier` pass caught — both closed in a dedicated gap-closure plan (07-04) before the phase was marked passed
- Even after 07-04's gap closure and a clean automated re-verification, live human UAT in a real terminal found 3 further bugs the mocked test suite structurally could not reach: Alt+Enter intercepted by the user's terminal emulator, `patch_stdout()`'s default `raw=False` silently stripping ESC bytes to `?`, and a duplicate final-answer print (raw tags once, parsed text again) that only manifests with a real streaming provider
- Phase 5 (Safe Inspection Tools) was executed and shipped without a formal goal-backward `VERIFICATION.md` ever being produced — only discovered as a gap during this milestone's close readiness check, closed by dispatching `gsd-verifier` retroactively
- A `gsd-tools verification fingerprint` CLI usage error (omitting the required `phaseDir` first argument) was initially misdiagnosed as a CLI bug and reported as such before the root cause was found — cost several redundant digest-recompute cycles

### Patterns Established
- Optional trailing `session=` param on an existing entrypoint function, rather than a parallel REPL-specific execution path, to share state without duplicating loop logic
- Shared chokepoint helpers (`_read_capped`, `_truncate_to_sentence`, `_record_web_observation`) reused across tools with the same truncation/tagging contract
- Live human-terminal UAT as a distinct verification tier after automated tests pass — real TTY/terminal-emulator behavior (key interception, ANSI rendering, streaming print timing) is structurally unreachable by a mocked pytest suite and needs its own pass before a phase involving a REPL/terminal UI is called done

### Key Lessons
1. A phase that touches real terminal I/O (REPL, ANSI styling, key bindings) needs a live-terminal UAT pass in addition to automated tests — this milestone shipped 3 bugs past a "passed" automated verification that only a real terminal surfaced.
2. Don't assume a CLI tool's argument-dropping behavior is a bug before checking its actual signature — verify against a fresh run/help output before filing feedback.
3. Retroactively verify every phase before a milestone close, not just the ones that "feel" unverified — Phase 5 slipped through with zero formal verification for two full phases' worth of time before anyone noticed.

### Cost Observations
- Model mix: Sonnet 5 (main session) + 1 `gsd-verifier` subagent dispatch (Phase 5 retroactive verification)
- Sessions: 1 continuous session spanning phase 7 tail-verification, live-UAT bug fixing, and milestone close
- Notable: live UAT (chat-driven, in the user's own terminal) was the highest-signal-per-token verification step this milestone — 3 real bugs found in a handful of exchanges, none of which the 470+-test automated suite could have caught by construction

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 5 | 19 | Initial release with full safety gate and provider abstraction |
| v1.1 | 3 | 7 | Web tools, read-only inspection tools, interactive REPL; introduced live-terminal UAT as a required verification tier |

### Cumulative Quality

| Milestone | Tests | Verification | Gaps Found / Resolved |
|-----------|-------|--------------|-----------------------|
| v1.0 | 375 | Passed (16/16 reqs) | 3 items resolved before closeout |
| v1.1 | 473 | Passed (10/10 reqs) | 2 automated gaps (phase 7) + 3 live-UAT-only bugs (phase 7) + 1 missing verification (phase 5) — all resolved before closeout |

### Top Lessons (Verified Across Milestones)

1. Small models need deterministic runtime constraints rather than soft prompt instructions.
2. Automated test suites cannot verify real terminal/TTY behavior by construction — REPL/terminal-UI phases need a live-terminal UAT pass before being called done, not just a passing mocked suite.
