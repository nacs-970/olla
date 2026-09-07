# Phase 5: Safe Inspection Tools - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-08
**Phase:** 5-Safe Inspection Tools
**Areas discussed:** list_dir output format, grep_files matching semantics, Safety dispatch mechanism, Truncation & cap behavior

---

## list_dir output format

| Option | Description | Selected |
|--------|-------------|----------|
| Single level (recommended) | Matches `ls` semantics, cheapest to cap at 50 entries, model calls again on a subdirectory to go deeper | ✓ |
| Recursive with depth limit | Walks subdirectories up to a fixed depth; richer per call but harder to cap | |

**User's choice:** Single level per call; model recurses by calling `list_dir` again on a subdirectory.

| Option | Description | Selected |
|--------|-------------|----------|
| Human-readable (1.2K, 3.4M) | Matches `ls -lh`, shorter tokens for large files | ✓ |
| Raw bytes | Exact but verbose | |

**User's choice:** Human-readable sizes.

| Option | Description | Selected |
|--------|-------------|----------|
| Alphabetical, dirs first (recommended) | Matches common `ls` grouping, deterministic | ✓ |
| Alphabetical, mixed | Single sort key, no grouping | |

**User's choice:** Alphabetical, dirs first.

| Option | Description | Selected |
|--------|-------------|----------|
| Show as own type, don't follow (recommended) | Lists as `[l] name -> target`, avoids symlink loops | ✓ |
| Resolve and show as target type | Follows link to classify type/size; risks loops | |

**User's choice:** Show symlinks as own type, don't follow.

**Notes:** User later clarified (during the Truncation area) that hidden dotfiles should be shown by default (`ls -a` behavior), not hidden like plain `ls` — captured as D-05 in CONTEXT.md.

---

## grep_files matching semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Recursive by default (recommended) | Matches typical "search my codebase" intent | |
| Single directory only | Bounded per-call cost, more calls needed | ✓ |

**User's choice:** Single directory by default ("single unless use flag").

**Follow-up:** User's phrasing implied an optional recursive flag not present in the original 2-arg signature. Asked a clarifying question on how to expose it.

| Option | Description | Selected |
|--------|-------------|----------|
| Add `recursive: bool = False` param | `grep_files(pattern, path, recursive=False)`, model passes `recursive=true` to go deeper | ✓ |
| Path convention (trailing `/**`) | No new param, adds path-parsing convention | |
| Drop recursive entirely | Single-directory only, same pattern as `list_dir` | |

**User's choice:** Add `recursive: bool = False` parameter.

| Option | Description | Selected |
|--------|-------------|----------|
| Case-sensitive (recommended) | Matches Python `re` and grep default | ✓ |
| Case-insensitive | Friendlier but diverges from literal regex | |

**User's choice:** Case-sensitive.

| Option | Description | Selected |
|--------|-------------|----------|
| Null-byte sniff (recommended) | Read first ~8KB, skip if NUL byte found — same heuristic grep/git use | ✓ |
| Extension allowlist | Simpler but needs maintenance, misses formats | |

**User's choice:** Null-byte sniff.

---

## Safety dispatch mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Bypass safety.check() entirely (recommended) | loop.py dispatches straight to tool adapters, same as read_file today | ✓ |
| Extend check() to accept tool name | Centralizes ALLOW/CONFIRM/BLOCK but adds shell-shaped argv handling to a non-shell call site | |

**User's choice:** Bypass `safety.check()` entirely.

| Option | Description | Selected |
|--------|-------------|----------|
| Let OS error surface as ToolResult error (recommended) | Matches read_file()/write_file() convention | ✓ |
| Explicit pre-check before running | More code, marginally clearer error text | |

**User's choice:** Let OS error surface as ToolResult error.

---

## Truncation & cap behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Append '(+N more)' note (recommended) | Model knows results were cut and can narrow its query | ✓ |
| Silently truncate | Simpler but model may assume it saw everything | |

**User's choice:** Append `(+N more)` note.

**Follow-up:** User's phrasing ("unless like ls -a") raised a new question about hidden-file visibility, not originally scoped as a separate area.

| Option | Description | Selected |
|--------|-------------|----------|
| Hide dotfiles by default (plain `ls`) | Excludes dotfiles from listings/counts | |
| Show dotfiles (like `ls -a`) | All entries including dotfiles listed and counted | ✓ |

**User's choice:** Show dotfiles by default (`ls -a` behavior) — folded into `list_dir output format` as D-05.

| Option | Description | Selected |
|--------|-------------|----------|
| First N in scan order (recommended) | Natural os.scandir/os.walk order, no extra ranking | ✓ |
| First N alphabetically across whole result set | Requires full sort before capping | |

**User's choice:** First N in scan order.

---

## Claude's Discretion

- Exact wording of the `(+N more)` truncation note.
- Internal helper structure for the null-byte binary sniff and `.git` exclusion.

## Deferred Ideas

None — discussion stayed within phase scope.
