# Phase 2: Safety Gate + Loop Control - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 2-Safety Gate + Loop Control
**Areas discussed:** Confirm-prompt scope, Blocklist content + --yes interaction, Repetition-guard threshold, Dry-run preview detail

---

## Confirm-prompt scope

| Option | Description | Selected |
|--------|-------------|----------|
| Uniform — every call | Simple, one code path. Risk: confirm-fatigue on trivial commands (Pitfall 7). | |
| Risk-tiered | Small read-only allowlist auto-runs; everything else confirms. | ✓ |

**User's choice:** Risk-tiered (Recommended)
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Whole-binary only | Match argv[0] against fixed list of always-read-only binaries (ls, pwd, cat, etc). Excludes git/docker entirely. | ✓ |
| Binary+subcommand pairs | e.g. git status/diff allowed, git push confirms. More coverage, more edge cases. | |

**User's choice:** Whole-binary only (Recommended)
**Notes:** —

---

## Blocklist content + --yes interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Blocklist hard-blocks | Blocklisted command always refused, even with --yes. Two independent knobs. | ✓ |
| --yes bypasses everything | Single safety knob — --yes means run anything. | |

**User's choice:** Blocklist hard-blocks (Recommended)
**Notes:** PITFALLS flags "--yes caused unwanted destructive action" as the HIGH-severity risk this avoids.

| Option | Description | Selected |
|--------|-------------|----------|
| Pattern-based | Match argv[0] + dangerous-arg combo (rm -rf /, dd→/dev/sd*, etc). Plain `rm file.txt` unaffected. | ✓ |
| Blanket command-name | argv[0] in {rm, dd, mkfs, sudo, ...} — ANY use blocked outright. | |

**User's choice:** Pattern-based (Recommended)
**Notes:** Matches REQUIREMENTS.md's own wording ("rm -rf /" not bare "rm").

| Option | Description | Selected |
|--------|-------------|----------|
| Generic set is enough | Covers OS-level destruction; pacman/systemctl already gated by sudo or confirm. | ✓ |
| Add Arch-specific patterns | Extra entries for pacman -R*, systemctl poweroff/reboot. | |

**User's choice:** Generic set is enough (Recommended)
**Notes:** —

---

## Repetition-guard threshold

| Option | Description | Selected |
|--------|-------------|----------|
| 3 in a row | Matches Pitfall 9's explicit "3x consecutively" example and LOOP-04's "2-3" upper bound. | ✓ |
| 2 in a row | Fail faster, more false-positive risk. | |

**User's choice:** 3 in a row (Recommended)
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Hard-abort | 3rd identical call → stop immediately with diagnostic. No extra model call/tokens. | ✓ |
| Nudge then abort | 2nd identical → corrective observation; 3rd → abort. One extra model call if it doesn't help. | |

**User's choice:** Hard-abort (Recommended)
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Resolved argv | Compare (tool_name, argv-list) — already computed for step display. | ✓ |
| Raw args_raw string | Compare exact `<args>` string — whitespace/quoting variants treated as different. | |

**User's choice:** Resolved argv (Recommended)
**Notes:** —

---

## Dry-run preview detail

| Option | Description | Selected |
|--------|-------------|----------|
| Argv + verdict | Show resolved argv plus gate verdict (auto-approved / would-confirm / BLOCKED). | ✓ |
| Argv only | Minimal — matches D-05's existing display with no new annotation. | |

**User's choice:** Argv + verdict (Recommended)
**Notes:** One model call already paid for; gate-check (no execution) is free and maximizes the "sanity-check before --yes" use-case (FEATURES.md).

| Option | Description | Selected |
|--------|-------------|----------|
| Show what model produced | <final> → print the final text; unparseable → print raw output. Either way, honest report of the one real call. | ✓ |
| Generic "nothing to preview" | Simpler message, discards the model's actual first-step output. | |

**User's choice:** Show what model produced (Recommended)
**Notes:** Avoids Pitfall 8 (no fake/placeholder observations).

---

## Claude's Discretion

- Exact blocklist regex/pattern implementation beyond the named examples
- Whether the safety gate is a new `safety.py` module or inlined in `loop.py`
- Exact confirm-prompt wording and visual integration with existing step display

## Deferred Ideas

None — discussion stayed within Phase 2 scope.
