# Phase 2: Safety Gate + Loop Control - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

A safety gate sits between the parsed tool call and shell execution in `run_loop`. Every shell call is checked against a blocklist (hard backstop), then either auto-runs (small read-only allowlist) or goes through a confirm prompt (`--yes` skips this, blocklist still applies). `--dry-run` previews step 1 — the resolved command plus what the gate would have decided — without executing. The loop also gains a repetition guard: 3 identical `(tool, argv)` calls in a row aborts with a diagnostic distinct from the "max steps reached" message.

</domain>

<decisions>
## Implementation Decisions

### Confirm-Prompt Scope (SAFE-04)
- **D-01:** Risk-tiered confirm. A small whole-binary read-only allowlist (`ls`, `pwd`, `cat`, `echo`, `find`, `grep`, `head`, `tail`, `wc`, `file`, `date`, `whoami`, `env`) auto-runs without prompting. Every other shell command goes through `rich.Confirm.ask` (mechanism already locked by SAFE-04) showing the resolved argv, before execution — overridable with `--yes`.
- **D-02:** Allowlist matches `argv[0]` only (whole-binary), never binary+subcommand pairs. Tools with destructive subcommands (`git`, `docker`, etc.) are NOT on the allowlist — they always confirm. Avoids subcommand-parsing edge cases (aliases, `-C`, etc.).

### Blocklist + `--yes` Interaction (SAFE-02)
- **D-03:** Blocklist is pattern-based — `argv[0]` + dangerous-arg combination, not blanket command-name:
  - `rm`/`rm -rf`/`rm -fr` targeting `/`, `~`, `/*`, `$HOME`, or `.`
  - `dd` / `mkfs*` targeting `/dev/sd*|nvme*|hd*`
  - fork-bomb pattern `:(){ :|:& };:`
  - `chmod`/`chown -R` on `/`
  - `sudo`, `su`, `shutdown`, `reboot`, `poweroff`, `halt` — blocked outright as `argv[0]` (no safe invocation exists)
- **D-04:** Blocklist hard-blocks regardless of `--yes` — two independent safety knobs. `--yes` only skips the confirm prompt for non-blocklisted commands. A blocklisted command returns a "blocked by safety policy: <reason>" observation to the model (denial reported back so the model can adjust, per ARCHITECTURE's gate pattern), never silently dropped.
- **D-05:** No Arch-specific additions (`pacman -R*`, `systemctl poweroff/reboot`). Generic OS-destruction set (D-03) is sufficient — those paths already require `sudo` (covered) or fall under generic confirm.

### Repetition Guard (LOOP-04)
- **D-06:** Threshold = **3** identical `(tool, resolved-argv)` calls in a row → abort. (LOOP-04 said "2-3"; matches PITFALLS Pitfall 9's explicit "3x consecutively" example.)
- **D-07:** Hard-abort immediately on the 3rd repeat — no corrective-nudge step first. Diagnostic message must be visibly distinct from "max steps reached" (e.g. `"olla stopped: same shell call repeated 3x — model likely stuck"`) so the user knows which remediation path applies (PITFALLS Pitfall 9).
- **D-08:** Repetition signature = `(tool_name, resolved argv list)` — the same `argv` already computed by `shlex.split()` for step display (Phase 1 D-05), not the raw `<args>` string. Whitespace/quoting variants that resolve to the same argv count as repeats.

### Dry-Run Preview (SAFE-01)
- **D-09:** `--dry-run` runs exactly ONE real model call, parses the response, and prints `"Step 1 would run: <argv> — <verdict>"` where `<verdict>` is one of: `"auto-approved (read-only allowlist)"`, `"would prompt for confirmation"`, or `"BLOCKED: <reason>"`. The verdict is computed by running the gate-check logic (D-01/D-03) without executing — argv + full gate verdict, not argv alone.
- **D-10:** If the first response is `<final>` (no tool call), print `"Model would answer directly: <text>"` and stop. If unparseable, print `"Model produced no valid <tool>/<final> tag: <raw output>"` and stop. Either way, show the actual output of the one real model call — never a fake/placeholder observation (Pitfall 8).

### Claude's Discretion
- Exact blocklist regex/pattern implementation beyond the named examples in D-03 — D-03 gives the shape and concrete examples; planner/research finalizes the pattern syntax.
- Whether the safety gate is a new `safety.py` module (per ARCHITECTURE's recommended structure) or inlined in `loop.py` — planner's call based on resulting code size for a ~280-line codebase.
- Exact confirm-prompt wording and how it visually integrates with the existing "Step N: running <argv>..." display (Phase 1 D-05/D-06).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Safety constraints (blocklist/confirm/dry-run non-negotiable from v1), dependency list including `rich`
- `.planning/REQUIREMENTS.md` — SAFE-01, SAFE-02, SAFE-03, SAFE-04, LOOP-04 definitions for Phase 2
- `.planning/ROADMAP.md` §Phase 2 — goal and success criteria 1-4 (confirm gate, blocklist speed-bump, dry-run single-step, max-steps/repetition abort)

### Research (load-bearing for Phase 2)
- `.planning/research/PITFALLS.md` — Pitfall 4 (blocklist is a speed-bump, confirm-gate is the real boundary — informs D-04), Pitfall 7 (confirm-fatigue → risk-tiered prompts — informs D-01/D-02), Pitfall 8 (dry-run single-step honesty, no fake observations — informs D-09/D-10), Pitfall 9 (repetition-guard design, distinct diagnostic message — informs D-06/D-07/D-08)
- `.planning/research/ARCHITECTURE.md` — Safety Gate component definition (~lines 24-50, 271: Allow/Deny/NeedsConfirm decision model, denial-as-observation pattern), Slice 2 build order (~lines 357-365)
- `.planning/research/FEATURES.md` — Confirm/blocklist/dry-run/repetition P1 prioritization and rationale (~lines 56-95)
- `.planning/research/SUMMARY.md` — Phase 2 section (~lines 108-125)

### Prior Phase Context
- `.planning/phases/01-core-loop-shell-tool-cli/01-CONTEXT.md` — D-05/D-06 step-display pattern ("Step N: running <argv>..." + truncated output) that confirm/dry-run output (D-09) reuses; SHELL-01 lock (`shell=False` + `shlex.split()`, no pipes/chaining) means blocklist chaining-bypass (Pitfall 4's main concern) is largely moot — simplifies D-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/olla/loop.py` `run_loop` — the `parsed["tool"] == "shell"` branch (~lines 45-69) is the dispatch point where the safety gate inserts, before `run_shell()` is called
- `src/olla/tools/shell.py` `run_shell(args_raw)` — already computes `argv = shlex.split(args_raw)` internally and returns it in `ToolResult["argv"]`; reuse this same argv for allowlist/blocklist matching (D-01/D-03) and repetition signature (D-08) rather than re-splitting
- `src/olla/cli.py` — `--dry-run` and `--yes` flags already exist (currently print "not yet enforced (Phase 2)" notices, lines 30-33); Phase 2 replaces these notices with real enforcement
- `src/olla/loop.py` `truncate_output` / `MAX_OBSERVATION_CHARS` — existing pattern for formatting observation text; "blocked by safety policy" observations (D-04) follow the same `Observation: <text>` shape

### Established Patterns
- Step display: `"Step N: running <resolved argv>..."` (Phase 1 D-05) then a truncated output preview (D-06) — confirm prompt and dry-run verdict (D-09) should slot into this same per-step display, reusing the resolved argv already printed
- `ToolResult` TypedDict (`tools/base.py`, `total=False`) — error-only results via an `"error"` key; a blocked/denied result can follow the same shape (e.g. `{"argv": [...], "error": "blocked by safety policy: ..."}`)

### Integration Points
- `loop.py`'s `for step in range(1, max_steps + 1)` loop — repetition-signature tracking (last 3 `(tool, argv)` pairs, D-06/D-08) and the safety-gate check (D-01/D-03/D-04) both live inside this loop, before `run_shell` executes
- `pyproject.toml` `dependencies` — currently `["ollama>=0.6.2", "click>=8.1,<9"]`; Phase 2 adds `rich>=13` (reserved for this phase per `01-RESEARCH.md`, not yet a dependency)

</code_context>

<specifics>
## Specific Ideas

- Allowlist starter set (D-01): `ls`, `pwd`, `cat`, `echo`, `find`, `grep`, `head`, `tail`, `wc`, `file`, `date`, `whoami`, `env`
- Blocklist pattern examples (D-03): `rm -rf {/, ~, /*, $HOME, .}`; `dd`/`mkfs*` → `/dev/sd*|nvme*|hd*`; fork-bomb `:(){ :|:& };:`; `chmod`/`chown -R /`; `sudo`/`su`/`shutdown`/`reboot`/`poweroff`/`halt` blocked outright
- Dry-run verdict strings (D-09): `"auto-approved (read-only allowlist)"` / `"would prompt for confirmation"` / `"BLOCKED: <reason>"`
- Repetition diagnostic example (D-07): `"olla stopped: same shell call repeated 3x — model likely stuck"`

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 2 scope.

</deferred>

---

*Phase: 2-Safety Gate + Loop Control*
*Context gathered: 2026-06-12*
