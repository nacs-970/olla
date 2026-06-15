# Roadmap: olla

## Overview

olla ships as a vertical-slice build that de-risks the core bet first and layers additive capability on a proven base. Phase 1 stands up the ReAct loop, the tolerant tag parser, stop-sequence wiring, explicit context sizing, the shell tool, and the CLI/distribution shell — then validates empirically that small local models actually emit usable `<tool>`/`<args>`/`<final>` tags. Phase 2 slots a safety gate into the proven parse-to-dispatch boundary (blocklist, confirm-prompt, dry-run, max-steps, repetition guard). Phase 3 adds file read/write tools through that gate, and Phase 4 adds the scratchpad memory tool. Three independent research angles converge on this exact ordering and risk profile.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Core Loop + Shell Tool + CLI** - Working ReAct loop that parses model tags, runs shell commands, and installs as `olla`; format compliance validated against target models (completed 2026-06-11)
- [x] **Phase 2: Safety Gate + Loop Control** - Blocklist, confirm-before-execute, dry-run, step cap, and repetition guard gate every dangerous action (gap closure round 3 in progress — 02-06 pending) (completed 2026-06-13)
- [ ] **Phase 3: File Tools** - Model can read and write files through the safety gate
- [ ] **Phase 4: Memory Tool** - Model can store and recall cross-turn scratchpad notes

## Phase Details

### Phase 1: Core Loop + Shell Tool + CLI

**Goal**: A user can run `olla "task"` against any local Ollama model and watch a reason-act-observe loop drive a shell command to completion, with the tag-format bet validated against the actual target models.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: LOOP-01, LOOP-02, LOOP-03, LOOP-05, SHELL-01, CLI-01, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):

  1. User runs `olla "task description" --model <name>` and the loop drives a shell command to a `<final>` answer without a hardcoded default model
  2. The parser extracts `<tool>`/`<args>`/`<final>` from real model output even when wrapped in markdown fences, surrounding prose, or unclosed tags
  3. The model stops generating at the tool-call boundary (stop-sequence) instead of hallucinating its own observation, and a large tool output is truncated before it can silently push the system prompt out of the context window
  4. Each step prints visible progress ("Step N: running `<cmd>`...") as the loop executes
  5. `pip install` exposes the `olla` console-script on PATH
  6. A format-validation smoke test reports tag-compliance rates for each target model (JOSIEFIED-Qwen3 0.6b/1.7b/4b, gemma4:e2b, gemma4-uncensored-aggressive), confirming the XML-tag bet or surfacing the need for a fallback format

**Plans:** 2/2 plans complete

**Wave 1**

- [x] 01-01-PLAN.md — Walking Skeleton: CLI -> ReAct loop -> ollama.chat -> tag parser -> shell tool -> printed final answer (success criteria 1-5)

**Wave 2** *(ready — Wave 1 complete)*

- [x] 01-02-PLAN.md — `olla --smoke-test` tag-compliance table across target models (success criterion 6, D-07/D-08)

**Research flag**: NEEDS RESEARCH-PHASE. The XML-tag-compliance assumption (PITFALLS Pitfall 1) must be validated empirically via the smoke test against the listed target models before Phase 1 is "done." If compliance is <80% on the smallest models, a plain-delimiter fallback format should be validated in parallel and documented as an option.

### Phase 2: Safety Gate + Loop Control

**Goal**: A user can trust olla with shell execution because every dangerous action is gated by a confirm prompt, blocklisted patterns are caught, and the loop cannot run away or thrash on a repeated call.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04
**Success Criteria** (what must be TRUE):

  1. Before any shell execution, the user sees the fully-resolved command string in a confirm prompt and can decline, with `--yes` skipping confirmation
  2. A blocklisted command (`rm -rf /`, `sudo`, `dd`, etc.) is caught as a speed-bump before the confirm prompt
  3. `--dry-run` shows the next planned tool call and stops without executing it or causing any side effect
  4. The loop aborts with a diagnostic when it hits `--max-steps` (default 15) or when the same tool+args is called 2-3 times in a row

**Plans:** 8/8 plans complete

**Wave 1**

- [x] 02-01-PLAN.md — Confirm-gate end-to-end: safety.py decision module (ALLOWLIST + blocklist rule table + check()), BLOCK/CONFIRM/ALLOW dispatch wired into run_loop with EOFError-safe confirm, --yes threaded through cli.py, rich added as dependency (success criteria 1-2, SAFE-02, SAFE-04)

**Wave 2** *(depends on Wave 1 — Decision contract from safety.py)*

- [x] 02-02-PLAN.md — Dry-run preview + repetition guard: --dry-run single-call preview reusing safety.check() for an honest verdict, 3x-repeat repetition guard with diagnostic distinct from max-steps message, SAFE-03 regression test (success criteria 3-4, SAFE-01, LOOP-04, SAFE-03)

**Gap Closure**

- [x] 02-03-PLAN.md — Gap closure round 1: env/find ALLOWLIST bypass (CR-01), repetition-guard ordering (WR-01), fork-bomb unspaced-variant detection (WR-02) (SAFE-02, SAFE-04, LOOP-04)
- [x] 02-04-PLAN.md — Gap closure round 2: narrower env/find unwrap gaps under `--yes` (CR-01 re-opened), fork-bomb data-argument false positive (WR-02 regression), chmod/chown -Rf bypass (WR-03), run_shell double-parse cleanup (IN-01) (SAFE-02, SAFE-04)
- [x] 02-05-PLAN.md — Gap closure round 3a: bash/sh/zsh -c wrap-and-recurse (CR-01 re-opened), chmod/chown -R on doubled-slash `/` (CR-02), dd/mkfs doubled-slash device path (CR-03) (SAFE-02, SAFE-04)
- [x] 02-06-PLAN.md — Gap closure round 3b: equivalent-form bypasses found post-02-05 — combined short-flag `bash -lc`/`sh -ic`/`zsh -xc` (CR-01 round 3), `chmod/chown -R //` doubled-slash target on rule 7 (CR-02 round 3), `dd`/`mkfs of=//dev/sda` doubled-slash device path (CR-03 round 3) (SAFE-02, SAFE-04)
- [x] 02-07-PLAN.md — Gap closure round 4: dot-segment equivalent-form root-target bypass on rule 7 (`chmod/chown -R /.`, `//.`, `/./`) (CR-02 round 4) (SAFE-02, SAFE-04)
- [x] 02-08-PLAN.md — Gap closure round 5: Python 3.10 import compatibility — drop `typing.NotRequired` (PEP 655, 3.11+) from `safety.py`'s `Decision` TypedDict, restoring `import olla.safety` on the declared >=3.10 floor (CR-01) (LOOP-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04)

### Phase 3: File Tools

**Goal**: As a user running an agentic task with olla, I want the model to read existing files and write modified files through the confirm-gate, so that it can inspect and update my project's files to complete the task.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: FILE-01, FILE-02
**Success Criteria** (what must be TRUE):

  1. The model calls `read_file(path)` and receives the file's contents, truncated if oversized so it cannot blow the context window
  2. The model calls `write_file(path, content)` and the file is written only after the user confirms, with the resolved path shown in the prompt
  3. A task that requires inspecting a file and then writing a modified version completes end-to-end

**Plans:** 1/2 plans executed

**Wave 1**

- [x] 03-01-PLAN.md — `read_file` end-to-end: tools/files.py::read_file, ToolResult.content, run_loop dispatch restructure (read_file ALLOW-tier, dry-run preview, repetition guard generalization), SYSTEM_PROMPT update (success criterion 1, FILE-01)

**Wave 2** *(depends on Wave 1 — write_file shares loop.py's dispatch shape with read_file)*

- [ ] 03-02-PLAN.md — `write_file` end-to-end: parser Pitfall-1 fix (preserve fences/trailing newline in write_file content), tools/files.py::write_file, run_loop CONFIRM-gate dispatch (resolved-path prompt, --yes, dry-run preview, repetition guard), SYSTEM_PROMPT write_file doc + `</args>` caveat, SC3 read-then-write integration test (success criteria 2-3, FILE-02)

### Phase 4: Memory Tool

**Goal**: The model can persist and recall short notes across turns within a single run so it can carry intermediate facts forward without re-deriving them.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: MEM-01
**Success Criteria** (what must be TRUE):

  1. The model calls `remember(key, value)` and a later turn can retrieve that value
  2. A multi-step task that depends on a fact stored early completes correctly using the recalled note

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Loop + Shell Tool + CLI | 2/2 | Complete   | 2026-06-11 |
| 2. Safety Gate + Loop Control | 8/8 | Complete   | 2026-06-14 |
| 3. File Tools | 1/2 | In Progress|  |
| 4. Memory Tool | 0/TBD | Not started | - |
</content>
