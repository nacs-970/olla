# Phase 2: Safety Gate + Loop Control - Research

**Researched:** 2026-06-12
**Domain:** CLI safety gating (blocklist/allowlist + confirm prompts) and ReAct loop control (repetition guard, dry-run) for a single-process Python agent
**Confidence:** HIGH

## Summary

Phase 2 is additive, not architectural: it slots a pure decision function between the existing `parsed["tool"] == "shell"` branch and `run_shell()` in `loop.py`, plus a small counter-based repetition guard inside the existing `for step in range(1, max_steps + 1)` loop. CONTEXT.md's D-01..D-10 already lock the allowlist set, blocklist patterns, repetition threshold (3), and dry-run verdict strings — this research focuses on the implementation shape: a new `src/olla/safety.py` module exporting a pure `check(argv, yes) -> Decision` function (no I/O, no execution), `rich.Confirm.ask` usage and its non-TTY failure mode, a consecutive-counter repetition guard, and pytest patterns for mocking `Confirm.ask`.

The single highest-value finding is that `rich.Confirm.ask` raises `EOFError` (not "return default") when stdin is exhausted/closed — even when a `default=` is passed. This is a real correctness gap for SAFE-04: any non-interactive invocation without `--yes` (piped input, CI, non-TTY) will crash on the first confirm prompt unless the call is wrapped in `try/except EOFError` and treated as a decline. This must be an explicit task, not an afterthought.

**Primary recommendation:** Create `src/olla/safety.py` with a pure `check(argv: list[str], yes: bool) -> Decision` function (Decision = ALLOW | CONFIRM | BLOCK(reason)) that the loop and `--dry-run` both call identically; wrap the actual `rich.Confirm.ask` call in `run_loop` with `try/except EOFError` defaulting to decline; track repetition with a simple `(prev_sig, repeat_count)` pair, not a deque.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Safety gate decision (allow/confirm/block) | CLI process (in-process module `safety.py`) | — | Single-process local CLI; no client/server split. Gate is a pure function called synchronously from the loop before `run_shell()`. |
| Confirm prompt I/O | CLI process (`loop.py`, via `rich.Console`/`Confirm.ask`) | — | Terminal I/O is local; same process reads stdin/writes stdout. |
| Repetition/step-count tracking | CLI process (`loop.py` loop state) | — | In-memory loop-local state, no persistence across runs. |
| Shell execution | CLI process (`tools/shell.py`, unchanged from Phase 1) | — | Already implemented; Phase 2 only gates the call, doesn't change it. |

*(This is a single-process local CLI — one tier. The map exists per template requirements but there is no multi-tier split to misassign.)*

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-04 | Repetition guard aborts the loop with a diagnostic if the same tool+args is called 2-3 times in a row | Counter-based repetition signature pattern (below); placement before execution inside existing `for step in range(1, max_steps+1)` loop; distinct abort message per D-07 |
| SAFE-01 | `--dry-run` flag previews the next planned tool call without executing it or any side effects, then stops | Pure `check()` function reused for dry-run verdict computation (D-09); single real model call + parse only, no `run_shell()` call (Pitfall 8) |
| SAFE-02 | Shell command blocklist as a speed-bump layer, not the primary safety boundary | Pattern-rule table structure for D-03 examples; ordering (blocklist before allowlist, hard-blocks regardless of `--yes` per D-04) |
| SAFE-03 | `--max-steps` cap (default 15) prevents infinite loops | Already implemented in Phase 1 (`for step in range(1, max_steps+1)`, "Reached max steps" message) — Phase 2 adds the repetition guard alongside it, distinct message per D-07 |
| SAFE-04 | Confirm prompt (`rich.Confirm.ask`) before shell/write_file execution, overridable with `--yes` | Verified `Confirm.ask` signature/behavior from installed rich 15.0.0 source; critical EOFError-on-non-TTY finding and required `try/except` wrapper; allowlist (D-01/D-02) determines which commands skip the prompt |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rich` | 15.0.0 (installed, current as of Apr 2026) | `rich.prompt.Confirm.ask` for the confirm gate (SAFE-04) | Already locked in PROJECT.md/CLAUDE.md as the v1 dependency for confirm prompts; `Confirm` class API (`ask(prompt, default=..., console=...)`) verified stable in installed source — same shape documented across rich 13.x-15.x |

**Installation:**
```bash
# rich is already installed in this environment (15.0.0) but NOT yet declared
# in pyproject.toml dependencies — Phase 2 adds it:
```
Add to `pyproject.toml` `[project] dependencies`:
```toml
dependencies = [
    "ollama>=0.6.2",
    "click>=8.1,<9",
    "rich>=13",
]
```

**Version verification:** `pip show rich` confirms version 15.0.0 is installed `[VERIFIED: pip show]`. `Confirm.ask` signature read directly from `/usr/lib/python3.14/site-packages/rich/prompt.py` (installed package source) `[VERIFIED: local package source]`: `ask(prompt="", *, console=None, password=False, choices=None, case_sensitive=True, show_default=True, show_choices=True, default=..., stream=None)`. `Confirm.choices = ["y", "n"]`, `render_default` shows `(y)`/`(n)`.

**Note on version pin:** CLAUDE.md's "Recommended Stack" table specifies `rich>=13,<14` — but the environment has 15.0.0 installed, which `<14` would exclude. The `<14` constraint appears to be stale prior research (it is in the "Recommended Stack" advisory table, not the project's hard "Constraints" section, which only says "minimal deps — ollama, rich, click only"). Recommend `rich>=13` (no upper bound) since `Confirm.ask`'s API is unchanged across 13→15. **Flagged in Open Questions below for explicit confirmation** — this is a one-line `pyproject.toml` decision, not a re-architecture.

### Supporting

No new supporting libraries needed. All Phase 2 logic (blocklist pattern matching, repetition signature, dry-run verdict mapping) uses only stdlib (`re` or `fnmatch` for glob-style patterns, plus tuples/sets — already available, no new imports beyond `rich`).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `rich.prompt.Confirm.ask` | stdlib `input("... [y/N] ")` + manual parsing | Already decided (SAFE-04 names `rich.Confirm.ask` explicitly); `rich` is already in the dependency list per PROJECT.md — no reason to hand-roll |
| `re` for blocklist patterns | `fnmatch.fnmatch` for glob-style path patterns (`/dev/sd*`, `/dev/nvme*`) | `fnmatch` is simpler for the `/dev/sd*|nvme*|hd*` and `/*` style globs in D-03; `re` is more flexible for combined argv+arg matching. Recommend a hybrid: simple substring/prefix checks + `fnmatch` for path globs, avoiding a regex-heavy implementation for ~6-8 rules (see Don't Hand-Roll / Code Examples below) |
| Counter-based repetition signature | `collections.deque(maxlen=3)` of `(tool, argv)` tuples | A deque storing the last 3 calls and checking `all equal` is more general (supports non-consecutive patterns) but D-06/D-08 specify "3 identical in a row" — a `(prev_sig, count)` pair is simpler, O(1) space, and matches the spec exactly. Deque is the right choice only if a future requirement needs windowed (non-strict) repetition detection |

## Package Legitimacy Audit

> slopcheck installation was blocked in this session (sandboxed — installing arbitrary packages outside the research task's declared scope is correctly denied). Per the graceful-degradation protocol, `rich` is tagged `[ASSUMED]` for provenance purposes (discovered via PROJECT.md/CLAUDE.md, not Context7) — **however** the legitimacy evidence is independently overwhelming and does not need a `checkpoint:human-verify` gate:

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `rich` | PyPI | ~6 years (first released 2020) | Tens of millions/month (one of the most-depended-on Python TUI/formatting libs) | github.com/Textualize/rich | not run (blocked) | Approved — already installed (15.0.0), matches PROJECT.md's locked dependency list, official PyPI page confirms Textualize/Will McGugan maintainership `[VERIFIED: pip show + PyPI page]` |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time (installation blocked by sandbox policy as out-of-scope for this research task). `rich` is the only external package this phase touches, it is already installed and running in this exact environment, its PyPI page and GitHub repo are verifiable HIGH-confidence sources independent of slopcheck, and it was already a locked project decision (PROJECT.md/CLAUDE.md) before this research session. The planner does NOT need a `checkpoint:human-verify` task for `rich` itself — only the `pyproject.toml` version-pin question (see Open Questions) needs a one-line confirmation.*

## Architecture Patterns

### System Architecture Diagram

```
                         run_loop() — for step in range(1, max_steps+1)
                                          |
                                          v
                              call_model() -> parse_response()
                                          |
                            +-------------+-------------+
                            |                           |
                      type == "final"            type == "tool" (shell)
                            |                           |
                       print + return          argv = shlex.split(args_raw)
                                                         |
                                          +--------------+---------------+
                                          |  REPETITION GUARD CHECK       |
                                          |  sig = (tool, tuple(argv))    |
                                          |  if sig == prev_sig:          |
                                          |    repeat_count += 1          |
                                          |    if repeat_count >= 3:      |
                                          |      print diagnostic, return |
                                          |  else: repeat_count = 1       |
                                          +--------------+---------------+
                                                         |
                                          +--------------v---------------+
                                          |  SAFETY GATE: safety.check()  |
                                          |  (pure function, no I/O)      |
                                          |  1. blocklist match? -> BLOCK |
                                          |  2. allowlist match? -> ALLOW |
                                          |  3. else            -> CONFIRM|
                                          +--------------+---------------+
                                                         |
                       +---------------------+----------+----------+
                       |                      |                     |
                  Decision==BLOCK      Decision==CONFIRM       Decision==ALLOW
                       |                      |                     |
              observation: "blocked    if --yes: skip prompt   run_shell(argv)
              by safety policy: ..."   else: rich.Confirm.ask        |
              (continue loop,                 |  (wrapped in          |
               no execution)            try/except EOFError           |
                                          -> decline on EOF)           |
                                                |        |             |
                                          decline   confirm            |
                                                |        |             |
                                       observation:  run_shell(argv)   |
                                       "declined by                    |
                                        user" (continue)               |
                                                         |              |
                                                         +------+-------+
                                                                |
                                                        truncate_output()
                                                        -> Observation: ...
                                                        -> messages.append(...)
                                                                |
                                                        loop continues
                                                        (next step)


--dry-run path (separate, runs ONCE):
  call_model() (1 real call) -> parse_response()
    type == "final" -> print "Model would answer directly: <text>", stop
    type == "tool"  -> argv = shlex.split(...)
                       decision = safety.check(argv, yes)  # same pure function
                       verdict_str = map decision -> D-09 strings
                       print "Step 1 would run: <argv> -- <verdict_str>"
                       stop (no run_shell, no second model call)
    type == "none"  -> print "Model produced no valid <tool>/<final> tag: <raw>", stop
```

### Recommended Project Structure
```
src/olla/
├── loop.py          # run_loop: adds repetition-guard counter + gate dispatch
│                     #   + dry-run branch + confirm-prompt wrapper (EOFError-safe)
├── safety.py         # NEW: Decision type, ALLOWLIST set, BLOCKLIST_RULES list,
│                     #   check(argv, yes) -> Decision  (pure, no I/O)
├── cli.py            # --dry-run / --yes: replace inert notices with real
│                     #   enforcement (pass yes/dry_run through to run_loop)
└── tools/
    ├── base.py        # unchanged
    └── shell.py        # unchanged
```

### Pattern 1: Pure Decision Function (Allow/Deny/NeedsConfirm)

**What:** `safety.py` exports a `check(argv: list[str], yes: bool) -> Decision` function that performs ONLY pattern matching against `argv` — no `subprocess`, no `rich.Confirm.ask`, no `print`. It returns one of three outcomes that both `run_loop` and the `--dry-run` path consume identically.

**When to use:** Any time a decision needs to be both *acted upon* (real run) and *previewed* (dry-run) — the only way to guarantee dry-run output matches what would really happen (Pitfall 8) is for both paths to call the exact same function.

**Example:**
```python
# src/olla/safety.py
from dataclasses import dataclass
from typing import Literal

DecisionKind = Literal["ALLOW", "CONFIRM", "BLOCK"]

@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str | None = None  # set when kind == "BLOCK"


ALLOWLIST = {"ls", "pwd", "cat", "echo", "find", "grep", "head", "tail", "wc", "file", "date", "whoami", "env"}


def check(argv: list[str], yes: bool) -> Decision:
    """Pure decision: BLOCK > ALLOW > CONFIRM. No I/O, no execution.

    `yes` does not affect BLOCK (D-04: blocklist hard-blocks regardless of --yes).
    `yes` is accepted here only so callers can map CONFIRM consistently in
    dry-run (verdict text is the same whether --yes is set or not — --yes
    affects whether loop.py *shows* the prompt, not the gate's decision).
    """
    if not argv:
        return Decision("BLOCK", reason="empty command")

    blocked = _blocklist_match(argv)
    if blocked:
        return Decision("BLOCK", reason=blocked)

    if argv[0] in ALLOWLIST:
        return Decision("ALLOW")

    return Decision("CONFIRM")
```

*Source: synthesized from ARCHITECTURE.md's `check(tool_call, tool, flags) -> Allow/Deny/NeedsConfirm` (line 49) and D-01/D-03/D-04 in 02-CONTEXT.md. `[CITED: .planning/research/ARCHITECTURE.md]`*

### Pattern 2: Blocklist as a Small Rule Table, Not One Big Regex

**What:** Each D-03 pattern becomes one entry in a list of `(predicate, reason)` pairs, checked in order. `argv[0]` checks use set membership; argument-pattern checks use `fnmatch.fnmatch` for glob-style paths (`/dev/sd*`, `~`, `$HOME` after expansion) or simple substring/equality for literals (fork-bomb string, `-rf`/`-fr` flag presence).

**When to use:** For ~6-8 rules where each rule is conceptually independent (D-03's bullet list maps 1:1 to table rows) — a single combined regex would be harder to test (can't unit-test "rule 3" in isolation) and harder to extend (adding rule 9 means editing one giant pattern vs. appending one tuple).

**Example:**
```python
import fnmatch

# argv[0] values that are blocked outright — no safe invocation exists
_HARD_BLOCKED_BINARIES = {"sudo", "su", "shutdown", "reboot", "poweroff", "halt"}

# Destructive rm targets (after the user/model writes them — D-03 lists these
# literal forms; matching is on the resolved argv from shlex.split, so shell
# expansion of ~ / $HOME has NOT happened — match the literal tokens)
_RM_DANGEROUS_TARGETS = {"/", "~", "/*", "$HOME", "."}

# dd / mkfs* targeting raw block devices
_DEVICE_GLOB = "/dev/*"
_DEVICE_PREFIXES = ("sd", "nvme", "hd")

FORK_BOMB = ":(){ :|:& };:"


def _blocklist_match(argv: list[str]) -> str | None:
    cmd = argv[0]

    if cmd in _HARD_BLOCKED_BINARIES:
        return f"'{cmd}' is blocked outright (no safe invocation)"

    if cmd == "rm" and any(t in argv[1:] for t in _RM_DANGEROUS_TARGETS):
        return "rm targeting / ~ /* $HOME or . is blocked"

    if cmd in ("dd",) or fnmatch.fnmatch(cmd, "mkfs*"):
        for arg in argv[1:]:
            if fnmatch.fnmatch(arg, _DEVICE_GLOB):
                dev_name = arg.removeprefix("/dev/")
                if any(dev_name.startswith(p) for p in _DEVICE_PREFIXES):
                    return f"{cmd} targeting raw block device {arg} is blocked"

    if " ".join(argv) == FORK_BOMB or argv == [":(){", ":|:&", "};:"]:
        return "fork-bomb pattern is blocked"

    if cmd in ("chmod", "chown") and "-R" in argv and "/" in argv:
        return f"{cmd} -R on / is blocked"

    return None
```

*Source: D-03 examples in 02-CONTEXT.md, translated into a testable rule table `[CITED: .planning/phases/02-safety-gate-loop-control/02-CONTEXT.md]`. Note: SHELL-01 (Phase 1) already locks `shell=False` + `shlex.split` with no pipes/chaining — Pitfall 4's chaining/substitution bypass concerns (`;`, `$()`, backticks) are largely moot here because `shlex.split` treats those characters as literal argv tokens, not shell metacharacters, so a command like `"echo hi; rm -rf /"` becomes `argv = ["echo", "hi;", "rm", "-rf", "/"]` — `argv[0]` is `echo`, which is on the allowlist, but the dangerous tokens are still present as literal strings in `argv[1:]`. This is an edge case worth a code comment but is explicitly out of scope per D-05 ("generic confirm" covers it — `echo` IS on the allowlist though, so this specific example would auto-run harmlessly since `rm` never executes).* `[ASSUMED: this specific allowlist-vs-shlex interaction wasn't explicitly tested against the running code — flag for a quick manual check during planning, see Open Questions]`

### Pattern 3: Repetition Guard — Consecutive Counter, Not a Deque

**What:** Track `prev_sig: tuple | None` and `repeat_count: int`, both initialized before the `for step in range(1, max_steps+1)` loop. After computing `argv` for a shell call, compute `sig = ("shell", tuple(argv))`. If `sig == prev_sig`, increment `repeat_count`; else reset to 1 and set `prev_sig = sig`. If `repeat_count >= 3`, print the D-07 diagnostic and return — **before** calling `run_shell` (the 3rd identical call never executes).

**When to use:** Exactly D-06/D-08's "3 identical (tool, resolved-argv) calls in a row" — a counter is O(1) space/time and requires no imports beyond what's already present.

**Example:**
```python
# inside run_loop, before the for-loop:
prev_sig: tuple | None = None
repeat_count = 0

# inside the for-loop, after computing argv (and after the safety gate,
# so a BLOCKed repeated call doesn't also trigger the repetition abort —
# order doesn't matter much here since both produce a stop, but checking
# the gate first keeps "blocked" vs "stuck" diagnostics distinct):
sig = ("shell", tuple(argv))
if sig == prev_sig:
    repeat_count += 1
else:
    prev_sig = sig
    repeat_count = 1

if repeat_count >= 3:
    print("olla stopped: same shell call repeated 3x -- model likely stuck")
    return
```

*Source: synthesized from D-06/D-07/D-08 (02-CONTEXT.md) and PITFALLS.md Pitfall 9's "hash of (tool_name, args) for the last N steps ... if the same signature repeats 3x consecutively, abort early" `[CITED: .planning/research/PITFALLS.md]`. `tuple(argv)` is required because `list` is unhashable / not `==`-comparable-as-dict-key but IS `==`-comparable directly — actually for this pattern `==` comparison of two lists works fine (`["a","b"] == ["a","b"]` is `True`), so `tuple()` is not strictly required for equality, but using a tuple keeps the signature immutable and consistent if it's ever used as a dict/set key later.*

### Anti-Patterns to Avoid

- **Gate function that prompts or executes internally:** If `check()` calls `Confirm.ask` or `run_shell` itself, `--dry-run` cannot reuse it without side effects, violating Pitfall 8 (D-09/D-10 require the SAME gate logic, zero side effects). Keep `check()` pure; all I/O happens in `loop.py` based on the returned `Decision`.
- **One giant blocklist regex:** Untestable in isolation, hard to extend, hard to produce a specific `reason` string for D-04's "blocked by safety policy: <reason>" observation. Use a rule list (Pattern 2).
- **`Confirm.ask(..., default=False)` as the EOF-safety mechanism:** Verified empirically (this session) — `default=` only applies when the user presses Enter on an empty line at a live TTY; `Confirm.ask` still raises `EOFError` when stdin is exhausted/closed, regardless of `default=`. Must wrap in `try/except EOFError`.
- **Repetition signature including non-deterministic data:** Don't include things like timestamps, PIDs, or output in the signature — only `(tool_name, resolved_argv)` per D-08, exactly as already computed by `shlex.split()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Yes/no confirm prompt with default handling | Custom `input()` + string-comparison loop | `rich.Confirm.ask(prompt, default=...)` | Already locked by SAFE-04; handles `[y/n]` rendering, case-insensitive y/n/yes/no-style input via `process_response`, and re-prompts on invalid input (`InvalidResponse` loop) for free |
| Glob-style path matching (`/dev/sd*`, `/dev/nvme*`) | Hand-rolled string `.startswith`/`.split` logic | stdlib `fnmatch.fnmatch` | One-line glob match, already in stdlib, exactly matches the `*` wildcard shape of D-03's patterns — no new dependency |
| Shell tokenization for the repetition signature | Re-splitting `args_raw` again | Reuse the `argv` already returned by `run_shell`'s internal `shlex.split` (per 02-CONTEXT.md code_context — "reuse this same argv ... rather than re-splitting") | Avoids a second `shlex.split` call and guarantees the repetition signature and the executed command always agree (no drift between "what was checked" and "what ran") |

**Key insight:** Every piece of Phase 2 logic (confirm, blocklist pattern matching, repetition tracking) has either a stdlib primitive or an already-decided library (`rich`) that covers it completely. The only "custom code" is the `safety.py` rule table itself, which is inherently project-specific (the exact D-03 patterns) and can't be a library dependency.

## Common Pitfalls

### Pitfall 1: `rich.Confirm.ask` raises `EOFError` on non-TTY/exhausted stdin, even with `default=` set

**What goes wrong:** In any non-interactive invocation (CI, piped input, `subprocess` calling `olla` with stdin redirected from `/dev/null` or a closed pipe) without `--yes`, the first `CONFIRM`-decision shell call calls `Confirm.ask(...)`, which calls `console.input()` → builtin `input()`. With stdin exhausted, `input()` raises `EOFError: EOF when reading a line`. This propagates as an unhandled exception and crashes `olla` mid-loop — a hard crash, not a safe decline.

**Why it happens:** `rich.prompt.PromptBase.__call__`'s loop only returns `default` when `value == ""` (i.e., the user pressed Enter with no other input) — but `input()` itself raises `EOFError` *before* returning an empty string when stdin has no more data at all. The `default=` parameter never gets a chance to apply.

**How to avoid:** Wrap every `Confirm.ask(...)` call site in `try: ... except EOFError: <decline>`. Treat EOF as the safe-default decline (consistent with "fail safe" — an automated/non-interactive context that hits a CONFIRM-tier command should NOT proceed without explicit `--yes`).
```python
try:
    proceed = Confirm.ask(f"Run {argv}?", default=False)
except EOFError:
    proceed = False
```

**Warning signs:** Tests that invoke `run_loop` with a mocked `ollama.chat` returning a `CONFIRM`-tier shell call, without mocking `Confirm.ask`, will fail with `EOFError` (pytest sets stdin to a null object) — this is actually a GOOD test signal that the wrapper is missing, but only if the test exists. Verified empirically this session: `printf "" | python3 -c "from rich.prompt import Confirm; Confirm.ask('Proceed?', default=False)"` → `EOFError: EOF when reading a line` `[VERIFIED: local execution against installed rich 15.0.0]`.

### Pitfall 2: Two existing CLI tests assert the OLD "not yet enforced" behavior and will FAIL after Phase 2

**What goes wrong:** `tests/test_cli.py::test_dry_run_flag_prints_inert_notice` (lines 54-62) asserts `"--dry-run is not yet enforced"` appears in output, and `test_yes_flag_prints_inert_notice` (lines 65-73) asserts `"--yes is not yet enforced"`. Phase 2's whole point is to REPLACE these notices with real enforcement (`cli.py` lines 30-33). After Phase 2's `cli.py` changes, both these tests will fail (the asserted strings will no longer be printed).

**Why it happens:** These were Phase 1's deliberate placeholders ("Note: ... is not yet enforced (Phase 2)") with tests locking in that placeholder behavior. A phase that *removes* placeholder behavior must also *update* the tests that assert the placeholder exists — this is easy to miss because it looks like "existing tests, not my concern" rather than "tests I must edit."

**How to avoid:** Treat these two tests as REWRITES, not survivors. New expected behavior:
- `test_dry_run_flag_prints_inert_notice` → becomes a test that `--dry-run` triggers the single-step preview path (mock `ollama.chat` to return a `<tool>`/`<final>` response, assert `"Step 1 would run:"` or `"Model would answer directly:"` appears, assert `run_shell` is never called).
- `test_yes_flag_prints_inert_notice` → becomes a test that `--yes` is threaded through to `run_loop` (e.g., `run_loop.assert_called_once_with(..., yes=True, ...)` or equivalent) and that a CONFIRM-tier command does NOT trigger `Confirm.ask` when `yes=True`.

**Warning signs:** Running the full test suite after Phase 2 implementation shows these two tests failing with "assertion not found in output" — this is EXPECTED and means the rewrite was missed, not that the new code is broken.

### Pitfall 3: Blocklist pattern matching against literal (unexpanded) tokens vs. shell-expanded values

**What goes wrong:** D-03 lists `rm -rf` targets including `~` and `$HOME`. Because SHELL-01 uses `shlex.split()` + `shell=False` (no shell interpretation), `~` and `$HOME` arrive as the LITERAL strings `"~"` and `"$HOME"` in `argv` — they are never expanded to `/home/user`. The blocklist must match these literal tokens, not attempt `os.path.expanduser()` or `os.environ["HOME"]` expansion (which would be "smarter" but inconsistent — a model could write `/home/actualuser` directly and bypass a `$HOME`-expansion-based check anyway).

**Why it happens:** Intuition says "the model means the home directory" and reaches for expansion logic, but expansion logic adds a false sense of completeness (you can't enumerate every way to spell `/home/user`) while making the blocklist's behavior less predictable/testable.

**How to avoid:** Match the literal argv tokens exactly as D-03 specifies (`"~"`, `"$HOME"`, `"/"`, `"/*"`, `"."` as literal strings in `argv[1:]` for `rm`). Document this as a known limitation (a model writing the expanded absolute home path bypasses this specific rule) — consistent with Pitfall 4's framing that the blocklist is a speed-bump, not the safety boundary; the confirm-gate (which a non-allowlisted `rm /home/actualuser` would hit) is the real boundary.

**Warning signs:** A test asserting `rm -rf $HOME` is blocked passes, but a test asserting `rm -rf /home/<actual-username>` is also blocked would fail (and SHOULD fail per D-03's literal scope) — don't let scope creep turn this into a path-expansion project.

## Code Examples

### Confirm-gate integration in `run_loop` (combining D-01/D-02/D-04/D-09 with the gate)

```python
# Source: synthesized from rich.prompt.Confirm (verified local install,
# rich 15.0.0) + 02-CONTEXT.md D-01/D-02/D-04
from rich.console import Console
from rich.prompt import Confirm
from olla.safety import check as safety_check

console = Console()

# ... inside the for-loop, after computing argv and the repetition check ...

decision = safety_check(argv, yes=yes)

if decision.kind == "BLOCK":
    preview = f"blocked by safety policy: {decision.reason}"
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})
    continue

if decision.kind == "CONFIRM" and not yes:
    try:
        proceed = Confirm.ask(f"Run {argv}?", console=console, default=False)
    except EOFError:
        proceed = False
    if not proceed:
        preview = "declined by user"
        print(preview)
        messages.append({"role": "user", "content": f"Observation: {preview}"})
        continue

print(f"Step {step}: running {argv}...")
result = run_shell(parsed["args_raw"])
# ... existing result-handling unchanged ...
```

### `--dry-run` single-step preview (D-09/D-10)

```python
# Source: synthesized from D-09/D-10 (02-CONTEXT.md) + Pitfall 8 (PITFALLS.md)
# This is a SEPARATE code path in run_loop (or a separate function), not a
# flag checked inside the normal loop -- it makes exactly ONE model call.

content = call_model(model, messages)
parsed = parse_response(content)

if parsed["type"] == "final":
    print(f"Model would answer directly: {parsed['text']}")
    return

if parsed["type"] == "tool":
    if parsed["tool"] != "shell":
        print(f"Model produced no valid <tool>/<final> tag: {content}")
        return
    try:
        argv = shlex.split(parsed["args_raw"])
    except ValueError as e:
        print(f"Model produced no valid <tool>/<final> tag: {content}")
        return

    decision = safety_check(argv, yes=yes)
    verdict = {
        "ALLOW": "auto-approved (read-only allowlist)",
        "CONFIRM": "would prompt for confirmation",
        "BLOCK": f"BLOCKED: {decision.reason}",
    }[decision.kind]
    print(f"Step 1 would run: {argv} -- {verdict}")
    return

print(f"Model produced no valid <tool>/<final> tag: {content}")
```

### pytest pattern: mocking `Confirm.ask`

```python
# Source: standard unittest.mock / pytest-mock pattern, applied to the
# rich.prompt.Confirm class (verified import path against installed rich)
def test_confirm_tier_runs_on_yes(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["git", "status"], "returncode": 0, "stdout": "clean\n", "stderr": ""}

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", yes=False)

    mock_confirm.assert_called_once()
    mock_run_shell.assert_called_once()


def test_confirm_tier_declines(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mocker.patch("olla.loop.Confirm.ask", return_value=False)
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", yes=False)

    mock_run_shell.assert_not_called()
    captured = capsys.readouterr()
    assert "declined by user" in captured.out


def test_confirm_eof_treated_as_decline(mocker):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mocker.patch("olla.loop.Confirm.ask", side_effect=EOFError)
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", yes=False)

    mock_run_shell.assert_not_called()
```

*Mock target is `olla.loop.Confirm.ask` (the name as imported into `loop.py`'s namespace), not `rich.prompt.Confirm.ask` — standard `unittest.mock` "patch where it's looked up" rule.*

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `cli.py` prints "not yet enforced (Phase 2)" notices for `--dry-run`/`--yes` | `cli.py` threads `dry_run`/`yes` flags into `run_loop`, which enforces them via `safety.check()` + `Confirm.ask` | Phase 2 (this phase) | Two existing `test_cli.py` tests must be rewritten (Pitfall 2) |
| N/A — no prior repetition guard | Counter-based `(prev_sig, repeat_count)` repetition guard inside the existing step loop | Phase 2 (this phase, LOOP-04) | New loop-local state; distinct abort message from max-steps |

**Deprecated/outdated:** Nothing in the rich/Confirm API is deprecated — `Confirm.ask` has been stable across the 13.x-15.x range checked.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `rich>=13` (no upper bound) is the correct `pyproject.toml` constraint, superseding CLAUDE.md's `rich>=13,<14` | Standard Stack | Low — if the planner instead pins `<14`, `pip install` would resolve to a rich 13.x release; `Confirm.ask`'s signature is unchanged there too, so functionality is unaffected either way. Only matters for matching the currently-installed 15.0.0 vs. forcing a downgrade. |
| A2 | The `echo hi; rm -rf /` style argv (literal `;` token from `shlex.split`) is acceptable to leave unhandled because `argv[0]` (`echo`) is allowlisted and the dangerous tokens never reach a shell interpreter | Architecture Patterns / Pattern 2 | Low — SHELL-01 already guarantees `subprocess.run(argv, shell=False)` never interprets `;`/`$()`/backticks as shell syntax; `rm` literally never executes in this scenario. Worth a code comment but not a blocking gap. |
| A3 | `safety.check()` should accept `yes: bool` even though it doesn't affect the BLOCK/ALLOW/CONFIRM decision itself (per D-04, `--yes` only affects whether `loop.py` shows the prompt for a CONFIRM decision) | Architecture Patterns / Pattern 1 | Low — if `check()` is written WITHOUT the `yes` param (simpler signature), `loop.py` still works fine; the param was included for symmetry/dry-run clarity but isn't load-bearing. Planner can drop it from the signature if it adds confusion. |

## Open Questions (RESOLVED)

1. **What happens when the user DECLINES a confirm prompt?**
   - What we know: SC1 says the user "can decline." D-04 establishes the pattern for BLOCK (denial-as-observation, loop continues). D-09/D-10 establish dry-run's stop behavior.
   - What's unclear: CONTEXT.md does not explicitly state whether a CONFIRM-tier decline (a) feeds an "Observation: declined by user" back to the model and continues the loop (consistent with D-04's denial-as-observation pattern for BLOCK), or (b) aborts the whole run immediately.
   - Recommendation: Use the same denial-as-observation pattern as BLOCK (option a) — `messages.append({"role": "user", "content": "Observation: declined by user"})` and `continue`. This is consistent with D-04's stated rationale ("denial reported back so the model can adjust") and lets a single declined step not nuke an otherwise-useful multi-step task. Flag this as the default the planner should encode unless the user specifies otherwise during planning.
   - **RESOLVED:** Adopted in 02-01 Task 2 — the CONFIRM-declined and EOFError-as-decline `<behavior>` bullets both specify the appended observation message content is exactly `"Observation: declined by user"`, and the loop continues to the next step (option a).

2. **`pyproject.toml` rich version constraint: `>=13,<14` (per CLAUDE.md's Recommended Stack) vs. `>=13` (matches installed 15.0.0)?**
   - What we know: `Confirm.ask`'s signature and behavior are verified identical across the installed 15.0.0 and documented for 13.x/14.x — no breaking change affects this phase's usage.
   - What's unclear: Whether `<14` was an intentional pin (e.g., for some other rich feature used elsewhere, or anticipating a future breaking change) or simply the version current at the time CLAUDE.md's stack research was written.
   - Recommendation: Use `rich>=13` (no upper bound) so `pip install -e .` resolves to the already-installed 15.0.0 without forcing a downgrade. One-line `pyproject.toml` decision — surface to the user/planner for a quick confirm, not a blocker.
   - **RESOLVED:** Adopted in 02-01 Task 3 — the action adds `"rich>=13",` (no upper bound) to `pyproject.toml`'s `dependencies` list, per the Package Legitimacy Audit.

3. **Order of repetition-guard check vs. safety-gate check within the loop body.**
   - What we know: Both checks happen "before `run_shell` executes" per CONTEXT.md's Integration Points. D-06/D-08 define the repetition signature as `(tool_name, resolved argv)` — the same value the gate also needs.
   - What's unclear: If a model repeats a BLOCKed command 3 times in a row (e.g., keeps trying `sudo rm -rf /`), should the user see "blocked by safety policy" (BLOCK observation, loop continues) three times and then the repetition-abort on the 3rd, or should the repetition-abort fire first (since the *attempt* itself is the "stuck" signal, regardless of whether it's blocked)?
   - Recommendation: Check repetition guard AFTER the safety gate's BLOCK case is handled as an observation+continue — i.e., compute `argv`, run `safety.check()`, handle BLOCK (observation+continue, do NOT update repetition state for blocked attempts since they never "ran"), THEN for ALLOW/CONFIRM outcomes update the repetition signature. This keeps "model is stuck repeating a blocked command" distinguishable (it'll just keep getting BLOCK observations, which is arguably fine — the model gets feedback each time) from "model is stuck repeating an allowed/confirmed command that produces no useful new info" (the actual LOOP-04 scenario PITFALLS Pitfall 9 describes). Either ordering is defensible; this is a minor sequencing detail for the planner to lock down in the task breakdown.
   - **RESOLVED:** Adopted in 02-02 Task 2 — the "Ordering note" specifies the repetition check sits AFTER the BLOCK/CONFIRM-decline `continue` points (those paths don't reach this code, so they correctly don't affect `prev_sig`/`repeat_count`), but BEFORE the existing "Step N: running..." print and `run_shell` call.

## Environment Availability

> Skip condition met for external services (no databases/Docker/etc.) — but `rich` is a new Python dependency, so a minimal table is included.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `rich` (Python package) | SAFE-04 confirm gate (`Confirm.ask`) | ✓ | 15.0.0 (installed) | — (already locked dependency, no fallback needed) |
| Python | runtime | ✓ | 3.14 (this env; project floor is >=3.10) | — |
| pytest / pytest-mock | test suite | ✓ (per existing `tests/` using `mocker` fixture) | — | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none — `rich` just needs to be added to `pyproject.toml` `dependencies` (it's already installed in the environment).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 with pytest-mock (`mocker` fixture) — already in use, see `tests/test_loop.py`, `tests/test_cli.py` |
| Config file | none found (`pyproject.toml` has no `[tool.pytest.ini_options]` section) — pytest defaults (test discovery via `test_*.py`) are working per existing test files |
| Quick run command | `python3 -m pytest tests/ -x -q` |
| Full suite command | `python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-04 | CONFIRM-tier command prompts via `Confirm.ask`; `--yes` skips prompt; declined command produces observation+continue | unit | `python3 -m pytest tests/test_loop.py -k confirm -x` | ❌ Wave 0 (new tests in `test_loop.py`) |
| SAFE-04 | `Confirm.ask` raising `EOFError` is treated as decline (non-TTY safety) | unit | `python3 -m pytest tests/test_loop.py -k eof -x` | ❌ Wave 0 |
| SAFE-02 | Each D-03 blocklist rule blocks its example command; non-matching commands pass through | unit | `python3 -m pytest tests/test_safety.py -x` | ❌ Wave 0 (new file `test_safety.py`) |
| SAFE-02 | D-04: blocked command produces "blocked by safety policy: <reason>" observation regardless of `--yes` | unit | `python3 -m pytest tests/test_loop.py -k block -x` | ❌ Wave 0 |
| SAFE-01 | `--dry-run` makes exactly one model call, prints `"Step 1 would run: ... -- <verdict>"`, never calls `run_shell` | unit | `python3 -m pytest tests/test_loop.py -k dry_run -x` | ❌ Wave 0 |
| SAFE-01 | `--dry-run` with `<final>` first response prints "Model would answer directly: ..." | unit | `python3 -m pytest tests/test_loop.py -k dry_run_final -x` | ❌ Wave 0 |
| LOOP-04 | 3 identical `(tool, argv)` calls in a row abort with the D-07 diagnostic, distinct from max-steps message | unit | `python3 -m pytest tests/test_loop.py -k repetition -x` | ❌ Wave 0 |
| SAFE-03 | `--max-steps` still works and produces its OWN distinct message (regression — already passes per `test_run_loop_max_steps_no_final`) | unit | `python3 -m pytest tests/test_loop.py -k max_steps -x` | ✅ existing (`tests/test_loop.py::test_run_loop_max_steps_no_final`) |
| D-01/D-02 (allowlist) | `argv[0]` in allowlist → ALLOW decision, no prompt | unit | `python3 -m pytest tests/test_safety.py -k allowlist -x` | ❌ Wave 0 |
| (regression) | `test_dry_run_flag_prints_inert_notice` / `test_yes_flag_prints_inert_notice` rewritten to assert real enforcement | unit | `python3 -m pytest tests/test_cli.py -x` | ⚠️ EXISTS but must be REWRITTEN (Pitfall 2) — not a gap, a required edit |

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/test_safety.py tests/test_loop.py -x -q` (fast subset covering the new module + loop changes)
- **Per wave merge:** `python3 -m pytest tests/ -v` (full suite, including rewritten `test_cli.py`)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_safety.py` — new file, covers SAFE-02 blocklist rule table + D-01/D-02 allowlist + `check()` decision ordering (BLOCK > ALLOW > CONFIRM)
- [ ] `tests/test_loop.py` — additions: confirm-gate (mock `Confirm.ask`), EOFError handling, repetition guard (LOOP-04), `--dry-run` single-step preview (SAFE-01), blocked-command observation (D-04)
- [ ] `tests/test_cli.py` — REWRITE `test_dry_run_flag_prints_inert_notice` and `test_yes_flag_prints_inert_notice` to assert real enforcement instead of the removed placeholder notices (Pitfall 2); also update other tests that call `run_loop` with positional/keyword args if `run_loop`'s signature gains `yes`/`dry_run` parameters (e.g., `test_task_and_model_call_run_loop_with_defaults`, `test_max_steps_option_threaded_through` currently assert exact `run_loop(...)` call signatures — these WILL need updating if new params are added with defaults that don't match current assertions)
- [ ] Framework install: none — pytest/pytest-mock already present and working

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — single-user local CLI, no auth surface |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A — no multi-user/permission model |
| V5 Input Validation | yes | `shlex.split()` (Phase 1, SHELL-01) for command tokenization + `safety.check()` (this phase) for pattern-based validation of `argv` against blocklist before execution |
| V6 Cryptography | no | N/A — no secrets/crypto in this phase |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Destructive shell command execution (`rm -rf /`, `dd` to raw device, fork bomb, `sudo`/privilege-affecting commands) initiated by model hallucination or prompt-injected content | Tampering / Denial of Service | Layered: (1) `shell=False` + `shlex.split` (Phase 1, SHELL-01) eliminates shell-metacharacter injection as an *amplifying* vector; (2) blocklist (SAFE-02, D-03) catches named dangerous patterns as a speed-bump; (3) confirm-gate (SAFE-04) is the REAL boundary — every non-allowlisted command requires explicit user approval before execution (Pitfall 4) |
| Confirm-fatigue leading to blind `y`/`--yes` and bypassing the SAFE-04 boundary entirely | Tampering (user-assisted) | Risk-tiered prompting (D-01/D-02): only a small read-only allowlist auto-runs; everything else — including non-obviously-dangerous commands — shows the resolved argv in the prompt so the user can make an informed per-command decision (Pitfall 7) |
| Non-interactive invocation (CI/piped) hitting a CONFIRM-tier command without `--yes`, causing an unhandled `EOFError` crash that could leave the agent loop in an undefined state | Denial of Service (availability — crash rather than safe denial) | `try/except EOFError` around `Confirm.ask`, treating EOF as decline — fail-safe default for non-interactive contexts (Pitfall 1, this document) |
| Repetition/no-progress loops consuming wall-clock time and (on shared/constrained hardware) resources via repeated `subprocess` calls | Denial of Service (resource exhaustion, local) | LOOP-04 repetition guard aborts after 3 identical `(tool, argv)` calls, independent of `--max-steps` (Pitfall 9) |

## Sources

### Primary (HIGH confidence)
- Installed `rich` 15.0.0 source at `/usr/lib/python3.14/site-packages/rich/prompt.py` — `Confirm`/`PromptBase`/`Confirm.ask` signature, `render_default`, `process_response`, `__call__` loop logic `[VERIFIED: local package source]`
- Installed `rich` 15.0.0 source at `/usr/lib/python3.14/site-packages/rich/console.py` (`Console.input`, lines ~2156-2190) — confirms `input()` is called when no `stream` is provided `[VERIFIED: local package source]`
- Empirical test: `printf "" | python3 -c "from rich.prompt import Confirm; Confirm.ask('Proceed?', default=False)"` → `EOFError: EOF when reading a line` `[VERIFIED: local execution]`
- `pip show rich` → version 15.0.0, Home-page github.com/Textualize/rich `[VERIFIED: pip show]`
- `/home/nacs/Documents/git/olla/.planning/phases/02-safety-gate-loop-control/02-CONTEXT.md` — D-01 through D-10, canonical_refs, code_context, specifics `[CITED]`
- `/home/nacs/Documents/git/olla/.planning/research/PITFALLS.md` — Pitfalls 4, 7, 8, 9 `[CITED]`
- `/home/nacs/Documents/git/olla/.planning/research/ARCHITECTURE.md` — Safety Gate component definition, internal boundaries, Slice 2 build order `[CITED]`
- `/home/nacs/Documents/git/olla/src/olla/loop.py`, `tools/shell.py`, `tools/base.py`, `cli.py`, `tests/test_loop.py`, `tests/test_cli.py`, `tests/test_tools/test_shell.py` — current implementation read directly `[VERIFIED: codebase]`

### Secondary (MEDIUM confidence)
- PyPI rich project page (via WebFetch) — version 15.0.0 released April 12, 2026, maintainer Will McGugan, repo github.com/Textualize/rich `[CITED: pypi.org/project/rich]`

### Tertiary (LOW confidence)
- None — all findings either verified against locally installed source/execution or cited from project research docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `rich` already installed and locked by PROJECT.md; `Confirm.ask` API verified directly from installed source, no new libraries introduced
- Architecture: HIGH — pure decision function pattern directly extends ARCHITECTURE.md's already-specified `safety.py` design; integration points (loop.py dispatch, argv reuse) match existing code structure read directly
- Pitfalls: HIGH — EOFError finding empirically verified in this session against the exact installed rich version; test-breakage finding verified by reading the actual existing test file

**Research date:** 2026-06-12
**Valid until:** 30 days (stable domain — stdlib + one already-installed library, no fast-moving APIs)
