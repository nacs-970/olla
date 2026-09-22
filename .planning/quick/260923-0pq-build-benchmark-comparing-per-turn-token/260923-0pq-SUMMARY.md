---
phase: quick-260923-0pq
plan: quick-260923-0pq
subsystem: testing
tags: [ollama, benchmark, tokens, xml-tags, tool-calling, click]

requires: []
provides:
  - "scripts/benchmark_tool_overhead.py: standalone three-arm token-overhead benchmark (xml_full/xml_trimmed/native), not yet run against a real model"
affects: [next-milestone-planning, tools-expansion]

actuals:
  tokens: 4388
  tasks: 1
  commits: 1
plan_head_before: c1dde72c60aafc55555176f104fdba725f069622

tech-stack:
  added: []
  patterns:
    - "Direct ollama.chat() calls for token-count measurement, bypassing call_model()/Provider wrappers that discard prompt_eval_count/eval_count"
    - "Arm-order rotation per task to avoid systematic prompt-cache bias toward any one arm"

key-files:
  created: [scripts/benchmark_tool_overhead.py]
  modified: []

key-decisions:
  - "Cache-prefix check uses an arm-independent (system, task) pair (CACHE_CHECK_SYSTEM/CACHE_CHECK_TASK) rather than reusing a real arm+task pair — reusing xml_full+shell_task (the first measured call in the loop) would have pre-warmed that specific arm's cache, deflating its measured prompt_eval_count relative to the other two arms and biasing the result toward olla's existing 'cuts per-turn overhead' claim, which the plan explicitly forbids"
  - "scripts/ chosen over tests/ per plan: pyproject.toml's testpaths=['tests'] would make pytest collect and execute this against a live network on every test run, and scripts/ is excluded from the wheel build (packages=['src/olla'])"

requirements-completed: []

coverage:
  - id: D1
    description: "scripts/benchmark_tool_overhead.py exists, imports SYSTEM_PROMPT unmodified, defines xml_trimmed/native arms with fairness properties, and --print-prompts runs to completion with no network call"
    requirement: "BENCH-01"
    verification:
      - kind: other
        ref: ".venv/bin/python scripts/benchmark_tool_overhead.py --model dry-check --print-prompts (exit 0, 12 lines of per-(arm,task) output, no ollama.chat() invoked)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real benchmark run against a local Ollama model producing measured per-task/aggregate token counts and both signed % differences, documented in SUMMARY.md"
    requirement: "BENCH-01"
    verification: []
    human_judgment: true
    rationale: "Cannot be attempted — Task 2's precondition (a reachable local Ollama server) is unmet on this machine. No automated or manual verification of this deliverable exists yet."

duration: 12min
completed: 2026-09-22
status: incomplete
---

# Quick Task 260923-0pq: Three-Arm Tool-Overhead Benchmark Summary

**Benchmark script built and verified structurally (Task 1 complete); the real measurement run against a local Ollama model (Tasks 2-3) is blocked because Ollama itself is not installed on this machine.**

## Performance

- **Duration:** ~12 min (Task 1 only)
- **Started:** 2026-09-22T19:20:00Z
- **Completed:** 2026-09-22T19:32:00Z
- **Tasks:** 1 of 3 completed (Task 1 done; Task 2 blocked on human action; Task 3 not started)
- **Files modified:** 1

## Accomplishments

- Built `scripts/benchmark_tool_overhead.py`, a standalone, reusable benchmark comparing three tool-calling arms against a real local Ollama model:
  - `xml_full` — olla's real, unmodified `SYSTEM_PROMPT` imported via `from olla.prompts import SYSTEM_PROMPT` (9 tools, exactly as shipped to production)
  - `xml_trimmed` — a hand-written 3-tool XML variant (shell/read_file/write_file + final), explicitly commented as NOT used in production, existing only to give a fair 3-vs-3 comparison against `native`
  - `native` — a minimal system prompt plus Ollama's `tools=` function-schema parameter for the same 3 tools
- All three arms call `ollama.chat()` directly with an identical `options={"stop": ["</args>"], "num_ctx": 8192, "temperature": 0}` dict, reading `prompt_eval_count`/`eval_count` as top-level response keys (never `run_loop()`/`call_model()`/`Provider`, which discard those fields)
- `--print-prompts` gives a no-network, no-Ollama-required dry-check mode — verified to run to completion (exit 0) and print a one-line summary per (arm, task) pair for all 4 tasks × 3 arms (12 lines), with zero `ollama.chat()` calls
- A cache-prefix check (`CACHE CHECK:` line) runs before the real measurement loop, using a system+task pair (`CACHE_CHECK_SYSTEM`/`CACHE_CHECK_TASK`) deliberately disjoint from every real arm's prefix, so the check itself cannot pre-warm the cache for the measurement loop that follows
- The real measurement loop rotates arm order per task (`arm_order_for_task()`) rather than grouping all calls of one arm together, to avoid a systematic prompt-cache advantage for whichever arm would otherwise always run first
- `--output <path>` writes full raw per-call results (model, options, per-(task,arm) counts, per-arm aggregate totals) as JSON
- `--model` has no hardcoded default (per the project's no-default-model constraint); the CLI uses Click, matching the project's existing dependency

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the three-arm benchmark script** - `86b8d00` (feat)

Task 2 (checkpoint:human-action) and Task 3 (auto, depends on Task 2's precondition) were not executed — see "Issues Encountered" below.

**Plan metadata:** Not yet committed — the orchestrator handles the docs commit for this quick task separately, per the constraints given to this executor.

## Files Created/Modified

- `scripts/benchmark_tool_overhead.py` - Standalone 3-arm (xml_full/xml_trimmed/native) token-overhead benchmark against `ollama.chat()`, with `--print-prompts` (no-network dry check), `--output` (raw JSON), and `--model` (required, no default) CLI flags

## Decisions Made

- **Cache-check pair chosen to be arm-independent.** The plan's action text described "run one fixed (arm, task) pair's `ollama.chat()` call twice" without specifying which pair. Reusing an actual arm (e.g. `xml_full` + the first task, which is also the first pair the real measurement loop calls) would have warmed that specific arm's prompt-prefix cache before the real loop measured it — deflating `xml_full`'s first measured `prompt_eval_count` relative to the other two arms, which would start cold. That specific bias runs toward confirming olla's existing "cuts per-turn overhead" claim, which the plan explicitly says must never be engineered toward (Rule 1 auto-fix: this is a bug in measurement fairness, not a deviation from the plan's letter — the plan's fairness intent required an arm-independent check even though the literal text didn't specify one). Fixed by introducing `CACHE_CHECK_SYSTEM`/`CACHE_CHECK_TASK`, a system+task pair used only by the cache check and never by any real arm.
- **`scripts/` over `tests/` for the new file**, per the plan's explicit rationale (pytest `testpaths` collection and wheel-build exclusion) — no deviation, this was already specified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Cache-check pair changed from a real arm+task pair to a dedicated, arm-independent pair**
- **Found during:** Task 1 (writing the cache-check function)
- **Issue:** Reusing `ARM_NAMES[0]` + `TASKS[0][1]` (i.e., `xml_full` + `shell_task`) for the pre-loop cache check would pre-warm exactly the prefix the real measurement loop reads first (task_index=0, rotation 0 puts `xml_full` first), deflating `xml_full`'s first measured `prompt_eval_count` relative to `xml_trimmed`/`native`, which would start cold. This biases the aggregate `xml_full vs native` percentage toward the direction of olla's existing public claim — something the plan's action text explicitly forbids doing via arm/task/option manipulation.
- **Fix:** Introduced `CACHE_CHECK_SYSTEM = "You are a helpful assistant."` and `CACHE_CHECK_TASK = "Reply with the single word: ok."`, a prefix disjoint from all three real arms, used only inside `run_cache_check()`.
- **Files modified:** `scripts/benchmark_tool_overhead.py`
- **Verification:** Re-ran `--print-prompts` after the change (exit 0, unchanged 12-line output — the dry-check path doesn't exercise `run_cache_check()`, but confirms nothing else broke); read through `run_cache_check()`/`call_arm()`/`arm_order_for_task()` to confirm no real arm shares `CACHE_CHECK_SYSTEM`/`CACHE_CHECK_TASK`.
- **Committed in:** `86b8d00` (Task 1 commit, since the file had not yet been committed when this was found)

---

**Total deviations:** 1 auto-fixed (1 bug — measurement-fairness bias in the cache check)
**Impact on plan:** Necessary for the benchmark's core correctness requirement (the plan itself mandates the result must be measured, never engineered toward the existing claim). No scope creep — same file, same task, no new files or arms added.

## Issues Encountered

**Task 2 is a blocking human-action checkpoint that cannot be resolved by this executor. Diagnostics gathered this session (by the orchestrator, confirmed unresolved):**

- `/usr/local/bin/ollama` does not exist — the Ollama binary is missing.
- `systemctl status ollama` shows the unit crash-looping: `activating (auto-restart)`, `code=exited, status=203/EXEC` (exec failure, consistent with the missing binary).
- `curl` itself is not installed on this machine, so even `curl http://localhost:11434/api/tags` cannot be used to test connectivity.

Per this executor's explicit constraints: **did not** attempt to install/repair Ollama, **did not** skip ahead to Task 3, and **did not** substitute a remote/cloud provider (which the plan itself forbids in Task 1's action text — a different tokenizer/chat template would invalidate the whole local-model comparison).

**Task 2 status: blocked, not started in the sense of being resolved.** The user needs to:
1. Reinstall/repair the Ollama binary (likely needs root — official install script or package manager, matching `/etc/systemd/system/ollama.service`'s original install method).
2. Start the service (`systemctl start ollama` or equivalent) and confirm it stays up (`systemctl status ollama` shows `active (running)`, not restarting).
3. Confirm at least one small local model (0.6B-7B range) is pulled and available (`ollama list`).
4. Install `curl` (or otherwise verify) so `curl -s http://localhost:11434/api/tags` can return a 200/JSON body, and name the installed model to pass as `--model` in Task 3.

**Task 3 status: not started.** Its `<precondition>` ("Task 2's checkpoint confirmed a reachable local Ollama server and named an installed model") is unmet — per this executor's protocol, an unmet precondition halts the task and is never auto-approved, even in auto mode. The plan's Task 3 automated verify (`grep -c "%"` against this SUMMARY) will fail against this document, since it contains prose about percentages in the deviation/decision sections but no measured `xml_full vs native`/`xml_trimmed vs native` numbers from a real run — that is the expected, correct state for a plan blocked before its measurement task, not a fabricated result.

## User Setup Required

**Ollama must be installed and running before this plan can complete.** See "Issues Encountered" above for the exact diagnostic state and the four steps needed. Once resolved, re-run `/gsd-quick` (or the equivalent continuation) for `260923-0pq` to execute Task 2's confirmation and Task 3's real benchmark run — `scripts/benchmark_tool_overhead.py` from Task 1 requires no changes to proceed.

## Next Phase Readiness

- `scripts/benchmark_tool_overhead.py` is complete, lint-clean (`ruff check` passes), and structurally verified — it needs no further code changes to run for real once Ollama is repaired.
- Blocked: cannot proceed to Task 2/3 until the user repairs the local Ollama installation (binary missing, systemd unit crash-looping, `curl` absent for connectivity testing).
- This plan's overall `must_haves.artifacts` entry for the SUMMARY.md ("Measured % difference... from a real run against an installed local Ollama model") is NOT yet satisfied — that artifact only exists once Task 3 runs. This SUMMARY documents the blocked state, not the measured result.

---
*Phase: quick-260923-0pq*
*Completed: 2026-09-22 (Task 1 only; plan incomplete)*

## Self-Check: PASSED

- FOUND: `scripts/benchmark_tool_overhead.py`
- FOUND: commit `86b8d00`
- FOUND: `.planning/quick/260923-0pq-build-benchmark-comparing-per-turn-token/260923-0pq-SUMMARY.md`
