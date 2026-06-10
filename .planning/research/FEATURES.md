# Feature Research

**Domain:** Lightweight local-LLM agentic CLI ("minimal ReAct loop" category — gptme, Open Interpreter, shell-gpt/sgpt, simonw's `llm`, aider, zerostack, local-cli)
**Researched:** 2026-06-10
**Confidence:** MEDIUM (convergent across multiple comparable tools; some specifics LOW where only one source covers them, flagged inline)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or unsafe.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Shell command execution tool | The defining capability of this category — every comparable tool (gptme, Open Interpreter, shell-gpt, local-cli, zerostack) leads with "run shell commands" | LOW | Already in olla's v1 scope. |
| File read/write tools | Second universal primitive across all surveyed tools | LOW | Already in olla's v1 scope. |
| Confirm-before-execute (with override flag) | Universal across the category: Open Interpreter confirms unless `--auto-run`/`-y`; shell-gpt prompts execute/describe/abort; gptme has `-y/--no-confirm`; local-cli has `--yes` for risky commands | LOW | Already in olla's v1 scope (`--yes` override). Naming convention `--yes`/`-y` is the de-facto standard — keep it. |
| Dangerous-command blocking (blocklist) | Every tool that executes shell commands on local model output has *some* deny-list — local-cli explicitly blocks `rm -rf /`, fork bombs, device writes; Open Interpreter relies on alignment + optional safe mode | LOW | Already in olla's v1 scope. Note: this is a "best effort" layer in every tool, never presented as a real sandbox — set user expectations accordingly (see PITFALLS). |
| Loop/iteration cap (max-steps) | Universal guardrail against runaway loops — generic agent frameworks default to 10-100 iterations; without it a small model can loop indefinitely and burn the user's machine/time | LOW | Already in olla's v1 scope (`--max-steps`, default 15). Reasonable default for small models — keep low since each step costs real wall-clock time on constrained hardware. |
| Model selection flag, no hardcoded default | Tools targeting "any local model" (simonw's `llm`, local-cli, zerostack) all expose explicit model selection; users in this niche routinely swap models per-task | LOW | Already in olla's v1 scope (`--model`). |
| One-shot / non-interactive mode | gptme has `-n/--non-interactive` (implies `--no-confirm`); shell-gpt is fundamentally one-shot; this is the simplest possible UX and the natural v1 entry point | LOW | Already in olla's v1 scope (`olla "task"`). |
| **Visible step-by-step progress output** (reasoning / tool call / observation shown as it happens) | Users need to see *what the agent is doing* to trust it and to know when to Ctrl-C — a silent agent running shell commands feels broken or scary. This is **distinct** from "rich colored output" (which is about formatting/polish, not whether progress is shown at all) | LOW | **NOT in olla's current explicit scope — should be added.** Plain-text "Step 3: running `ls -la`..." style output is sufficient; defer color/formatting to v2 per existing scope decision. Missing this entirely would make olla feel broken on first run. |
| Pip-installable, single console-script entry point | Standard for Python CLI tools in this space (shell-gpt, gptme, simonw's `llm` all ship this way) | LOW | Already in olla's v1 scope. |
| **Explicit Ollama context window sizing (`num_ctx`)** | Ollama defaults to a **2048-token context window and silently truncates/discards anything beyond it** — no error, no warning. For a ReAct loop that accumulates system prompt + tool definitions + multi-turn history + scratchpad notes, this is a silent correctness bug waiting to happen: the model loses early context and starts hallucinating or repeating itself, which looks like "the model is bad" but is actually "the harness mis-configured the context window." aider explicitly documents setting `num_ctx` large enough for (request + 8k reply) for exactly this reason. | LOW-MEDIUM | **Not currently in olla's PROJECT.md — flag as a near-mandatory v1 item.** This sits at the intersection of "feature" and "correctness," but it directly defends olla's core value prop (accuracy on small models without context drift). Pass `num_ctx` explicitly via the Ollama API options on every request, sized to (estimated prompt tokens + headroom for response). HIGH confidence (primary source: aider docs). |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required for v1, but valuable and align with olla's "lightweight + small-model-friendly" positioning.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Tag-based (`<tool>`/`<args>`/`<final>`) output format instead of JSON function-calling | Small instruction-tuned models (0.6B-4B) are measurably worse at well-formed JSON tool calls than at simple tags. The dev.to "7 models" benchmark found that even within the same model family, tool-call format compliance varies wildly, and "format confusion" (model dumps JSON-looking text in a markdown block instead of calling the actual API) was a top failure mode. A simpler, more constrained tag grammar is easier for a 0.6B model to produce *and* easier for a regex-based parser to tolerantly extract even when slightly malformed. | LOW (already chosen) | This is genuinely olla's strongest differentiator vs. frameworks built around OpenAI-style JSON tool schemas (LangChain, most "function calling" wrappers). Already a Key Decision in PROJECT.md — validate it's documented as *the* headline differentiator, not just an implementation detail. |
| Scratchpad / `remember(key, value)` memory tool | Persistent memory across turns is present in more mature/larger tools (zerostack's MEMORY.md, agentmemory, gptme's "save"/"lessons" tools) but is **not standard at v1** for minimal tools — it's the kind of thing that gets added once a project graduates from "loop that completes a task" to "agent that runs across sessions." | MEDIUM | Defensible for olla's v1 *if and only if* it's framed as a **context-compaction mechanism**: instead of keeping a verbose tool observation (e.g., full `ls -la` output) in the rolling context, the model writes a short `remember()` note and the harness can drop/summarize the original observation. Used this way it *reduces* token overhead, which directly serves the core value. If it's just "another tool the model can call" with no context-management payoff, it adds prompt surface (one more tool definition, more tokens per turn) without buying back anything — which cuts against "minimal per-turn token overhead." **Recommendation: keep it, but explicitly wire it into context management, not just as a free-floating tool.** |
| `--dry-run` (print planned tool calls without executing) | Differentiator for a tool whose target users are cautious about letting small/unreliable models run shell commands — lets a user preview what the agent *would* do before trusting `--yes`. None of gptme, Open Interpreter, shell-gpt, or local-cli expose this as a named flag (they rely on per-step confirm prompts instead), so it's not a category norm — it's an extra. | MEDIUM | **Semantics need to be defined explicitly before implementation** — in an iterative ReAct loop, the model decides its next action *based on the previous action's observation*. A true "full plan preview" isn't possible without actually running the loop (you'd need to fake observations). Realistic options: (a) run the full loop but intercept execution — print "would run: `<command>`" at each step and substitute a placeholder/empty observation, or (b) only preview the *first* proposed action and exit. Recommend (a): it still exercises the reasoning loop turn-by-turn (useful for seeing how the model *would* react) while guaranteeing zero side effects. Document this clearly so users don't expect a complete static plan. |
| Per-tool allowlist/restriction flag (e.g., gptme's `-t/--tools`, "none" to disable all) | Lets advanced users restrict a session to read-only tools (no shell, no write) for safety or for purely informational tasks | LOW-MEDIUM | Not in olla's v1 scope and reasonable to defer — confirm-gating + blocklist already cover the safety case. Good v1.x candidate once core loop is validated. |
| Repetition / doom-loop guard (deny or warn on identical tool call repeated N times) | The single most-cited small-model failure mode across sources: a model that gets an error retries the *exact same* failing call repeatedly, burning the step budget. zerostack implements this explicitly (warn/deny at 3+ identical repeats). The dev.to benchmark found this exact pattern wasted ~30K tokens in one run before a prompt-level fix cut it to ~9K. | LOW | **Strong candidate to pull into v1** (see "Specifically for olla's tool set" section below) — cheap to implement (string-compare last N tool calls), addresses the #1 documented failure mode, and is more targeted than `max-steps` alone. |
| Token/context usage indicator (e.g., "~1.2k/4k tokens used this turn") | Directly visible feedback on the thing olla is optimizing for (context bloat) — no comparable tool surfaces this prominently, but it's cheap (Ollama API returns token counts) and reinforces the "stay lean" pitch | LOW | Good v1.x/v2 differentiator — low cost, high narrative alignment with core value. Not essential for v1 functional completeness. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a tool targeting small local models on constrained hardware.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| JSON/OpenAI-style function-calling schema | "Standard" tool-calling format, used by most frameworks (LangChain, OpenAI SDK, simonw's `llm` tool plugins) | Small models (sub-4B) are unreliable at producing valid JSON with correct escaping/nesting — the dev.to benchmark shows even capable small models drift into "JSON-as-prose" failure modes. Adopting this format would directly undermine olla's core value (reliability on small models) | Tag-based `<tool>/<args>/<final>` format (already chosen) — simpler grammar, more tolerant parsing, lower token overhead for schema definitions in the system prompt |
| Diff/patch-based file editing (aider's edit format, gptme's "patch" tool with conflict-marker-style hunks) | Mature tools use it because full-file rewrites are token-expensive on large files | Structured patch/diff formats are *exactly* the kind of multi-field structured output that small models fail at — aider's own docs note less capable models "have difficulty properly returning code edits." Adding this to olla would reintroduce the structured-output reliability problem the tag-based format was chosen to avoid | `write_file(path, content)` (full rewrite) — already olla's v1 choice. Token cost on large files is a real tradeoff but is the right one for reliability; document the tradeoff so it's understood as deliberate, not an oversight |
| Sandboxed/containerized execution (Docker, bubblewrap, VM isolation) | "Real" safety for arbitrary shell execution — zerostack offers bubblewrap sandboxing as an option | Heavyweight dependency, setup friction, and platform-specific (doesn't work cleanly cross-platform without extra installs) — directly conflicts with "pip install, minimal deps, runs anywhere Ollama runs" | Blocklist + confirm-gating + max-steps + dry-run, clearly documented as "best effort, not a security boundary" — matches what every comparable tool actually ships (Open Interpreter explicitly disclaims "no guarantees of safety") |
| Persistent autonomous/background operation (agent runs continuously across sessions, "wakes up" on triggers) | gptme explicitly markets this as a capability for advanced users; appealing as a "set and forget" pitch | Directly conflicts with confirm-gating and max-steps as safety models — an unattended agent with shell access on a personal laptop is a different risk profile entirely, and zerostack explicitly lists this as something it avoids | One-shot mode (current v1 design) — user invokes, agent runs to completion or step cap, user reviews. Session-to-session memory (if added later) should be opt-in and bounded, not "always running" |
| Web browsing / browser automation tool (Playwright-driven, as in gptme) | Seems like a natural extension of "agent with tools" | Heavy dependency (Playwright + browser binaries), large token cost per page (HTML/text dumps), and explicitly already deferred (web search) per PROJECT.md Out of Scope | SearXNG-style web search tool deferred to v2 as already decided — browser automation is an even heavier version of the same deferred capability, keep deferred |
| Rich interactive REPL with slash commands (`/model`, `/checkpoint`, `/rollback`) | gptme, local-cli, ollama-agent (arrase) all offer this; feels like "what a real CLI agent should have" | Significant UI/state-management complexity (session state, command parsing, history management) for a tool whose v1 goal is validating the core ReAct loop — already correctly deferred per PROJECT.md | One-shot mode now; REPL in v2 once the loop and tool set are validated (already the plan) |
| Config file (`~/.olla/config.toml`) for per-project tool toggles, defaults, etc. | Every "grown up" CLI eventually gets one (gptme, aider, simonw's `llm` all have config files) | Premature for v1 — adds a config-loading/merging layer and a new place for things to silently misbehave before the core loop is even validated | CLI flags for now (already the plan); config file in v2 once flag set stabilizes and patterns of repeated flag usage emerge |

## Feature Dependencies

```
Confirm-before-execute (shell/write_file)
    └──requires──> Visible step-by-step output
                       (user must SEE the proposed action to confirm/reject it meaningfully)

Blocklist
    └──enhances──> Confirm-before-execute
                       (blocklist catches the worst cases even if user reflexively says "yes")

Scratchpad/remember tool
    └──requires (to be a net token win)──> Context-compaction logic
                       (dropping/summarizing verbose observations once noted)

Dry-run
    └──overlaps with──> Confirm-before-execute
                       (both answer "what would happen?" — dry-run is confirm-everything
                        with auto-reject; define dry-run's exact semantics to avoid
                        building two redundant code paths)

Repetition/doom-loop guard
    └──enhances──> Max-steps cap
                       (catches the most common failure mode FAST, before burning
                        the whole step budget)

num_ctx sizing
    └──is a precondition for──> ReAct loop correctness at all
                       (without it, multi-turn context silently truncates regardless
                        of how good the loop/tool design is)

Tag-based <tool>/<args>/<final> format
    └──requires──> Tolerant parser (handle markdown-wrapped tags, minor malformations)
                       (small models will not produce perfectly well-formed tags 100% of the time)
```

### Dependency Notes

- **Confirm-before-execute requires visible output:** A confirm prompt that says "Run this command? [y/N]" without first showing *what* the model reasoned and *why* it chose this command leaves the user confirming blind. The step-by-step progress display and the confirm prompt are really one feature with two parts — implement together.
- **Blocklist enhances confirm-before-execute:** Confirm prompts suffer from "confirmation fatigue" — after the 5th `[y/N]` prompt, users start reflex-pressing `y`. The blocklist is the backstop for exactly that moment. Keep both even though they overlap in intent.
- **Scratchpad requires context-compaction to be a net win:** If `remember()` is implemented as "yet another tool definition + yet another turn," it adds tokens without removing any. To honor olla's core value (minimal per-turn overhead), the harness should use a `remember()` call as a trigger to trim/summarize the corresponding tool observation from the rolling context. This is a design dependency, not just a sequencing one — flag for the architecture/roadmap phase.
- **Dry-run overlaps with confirm-before-execute:** Both features answer "what is the agent about to do?" Recommend defining dry-run as "run the loop with all tool calls intercepted (printed, not executed, with empty/placeholder observations fed back)" so it reuses the same step-display code path as normal execution+confirm, rather than building a separate static-plan renderer.
- **Repetition guard enhances max-steps:** max-steps is a blunt 15-step ceiling that only fires after the budget is exhausted. A repetition guard (e.g., "last 2-3 tool calls were identical → stop and surface to user, or inject a corrective message") catches the most common documented failure mode (identical-call retry loops) in 2-3 steps instead of 15, saving both time and tokens — directly serving the "fast on constrained hardware" value prop.
- **num_ctx sizing is a precondition for everything else:** If Ollama silently truncates context, every other feature (scratchpad memory, multi-step reasoning, tool-call history) degrades unpredictably and looks like "the model is dumb" when it's actually "the harness fed the model a window it can't see." This must be correct before evaluating whether any other feature "works."
- **Tag format requires tolerant parsing:** PROJECT.md already commits to tag-based output specifically *because* small models handle it better than JSON — but "better" is not "perfect." The parser must tolerate: tags wrapped in markdown code fences, extra whitespace/newlines inside tags, minor case variations, and trailing prose after a `<final>` tag. A parser that hard-fails on the first deviation reintroduces the exact fragility the tag format was chosen to avoid.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the ReAct loop concept on small local models.

- [ ] ReAct loop core with tag-based parsing (tolerant of minor malformation/markdown-wrapping) — the central bet of the project
- [ ] Shell tool, file read/write tools — minimum useful action surface
- [ ] Confirm-before-execute + visible step-by-step output (one combined UX feature) — non-negotiable for trust on a tool that runs shell commands
- [ ] Blocklist + max-steps — baseline safety backstops, already planned
- [ ] **Repetition/doom-loop guard** (NEW recommendation) — cheapest, highest-leverage addition; directly targets the #1 documented small-model failure mode
- [ ] **Explicit `num_ctx` sizing on Ollama requests** (NEW recommendation) — without this, the rest of the loop's correctness is undermined silently
- [ ] `--model` flag, one-shot mode, pip install — already planned, low complexity, table stakes for distribution

### Add After Validation (v1.x)

Features to add once the core loop proves it works reliably on 0.6B-4B models.

- [ ] Scratchpad/`remember` tool — add once context-compaction strategy is designed (don't ship as a "free" extra tool with no token-management payoff)
- [ ] `--dry-run` — add once its exact semantics (full-loop preview with intercepted execution vs. first-action-only) are decided; low risk to defer since confirm-gating already covers the immediate safety need
- [ ] Per-tool allowlist (`--tools`/`-t` style) — natural follow-up once users start asking "can I run this in read-only mode"
- [ ] Token/context usage indicator — cheap, reinforces core value narrative, good "v1.1" polish item

### Future Consideration (v2+)

Features to defer until the core loop and tool set are validated (already aligned with PROJECT.md's Out of Scope).

- [ ] Interactive/REPL mode — adds session-state complexity; defer until one-shot loop is solid
- [ ] Config file — defer until flag usage patterns stabilize and there's real demand for persisted defaults
- [ ] Web search / browser tools — heaviest deferred items, large token cost, large dependency footprint
- [ ] Rich colored output — pure polish, zero functional risk in deferring
- [ ] Diff/patch-based file editing — only revisit if full-file rewrites prove too token-expensive in practice AND a small-model-friendly patch format can be found (unlikely soon — see Anti-Features)
- [ ] Persistent cross-session memory / "always-on" agent mode — conflicts with the one-shot + confirm-gated safety model; would need a fundamentally different safety design

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| ReAct loop + tag parsing (tolerant) | HIGH | MEDIUM | P1 |
| Shell + file tools | HIGH | LOW | P1 |
| Confirm-before-execute + visible output | HIGH | LOW | P1 |
| Blocklist | HIGH | LOW | P1 |
| Max-steps cap | MEDIUM | LOW | P1 |
| Repetition/doom-loop guard | HIGH | LOW | P1 |
| `num_ctx` explicit sizing | HIGH | LOW | P1 |
| `--model` flag, one-shot mode, pip install | HIGH | LOW | P1 |
| Scratchpad/`remember` (with compaction) | MEDIUM | MEDIUM | P2 |
| `--dry-run` (semantics defined) | MEDIUM | MEDIUM | P2 |
| Per-tool allowlist | LOW-MEDIUM | LOW-MEDIUM | P2 |
| Token/context usage indicator | LOW-MEDIUM | LOW | P2 |
| REPL mode | MEDIUM | HIGH | P3 |
| Config file | LOW | MEDIUM | P3 |
| Web search / browser tools | LOW (for this niche) | HIGH | P3 |
| Diff/patch editing | LOW (actively risky) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | gptme | Open Interpreter | shell-gpt / local-cli / zerostack | olla's Approach |
|---------|-------|-------------------|-------------------------------------|------------------|
| Tool-call format | Configurable: markdown, XML, or "tool" (native) format | Native function-calling (model-dependent) | local-cli: native tool calls; shell-gpt: single-shot command generation, no loop | Tag-based `<tool>/<args>/<final>` always — chosen specifically for small-model reliability, not configurable in v1 |
| Confirmation | `-y/--no-confirm`, `-n/--non-interactive` | Confirm by default, `--auto-run`/`-y` to skip | local-cli: `--yes` for risky ops; shell-gpt: per-command execute/describe/abort prompt | `--yes` flag overrides per-step confirm — matches convention |
| Safety/blocklist | Relies on confirm + tool allowlist (`-t none` to disable all tools) | "Safe mode" (experimental code scanning) + model alignment + confirm | local-cli: explicit dangerous-pattern blocklist (`rm -rf /`, fork bombs) + env sanitization | Blocklist (planned) — closest to local-cli's approach, appropriately scoped for v1 |
| Iteration limits | Not prominently documented | Loop continues until model signals completion (no hard documented cap) | zerostack: doom-loop detection (3+ identical calls) | `--max-steps` (default 15) + **recommend adding** repetition guard, which none of these competitors combine explicitly — would be a novel safety differentiator |
| Memory/scratchpad | "save"/"lessons"/"todo" tools, MCP-based persistence | None built-in | zerostack: MEMORY.md + scratchpad/daily logs (markdown files) | `remember(key, value)` in-session tool — simpler than zerostack's file-based approach; recommend tying to context compaction |
| Context window handling | Provider-dependent (often cloud models with large windows) | Provider-dependent | aider (adjacent tool): explicitly sets Ollama `num_ctx` to avoid silent truncation | **Recommend adopting aider's explicit `num_ctx` pattern** — none of the "minimal loop" competitors surveyed handle this proactively, representing both a risk (if missed) and an opportunity (if done well and documented) |
| Dry-run | Not present | Not present | Not present in any surveyed tool | Planned for olla — genuinely differentiating if semantics are well-defined; needs careful scoping (see Differentiators) |
| Distribution | PyPI (`pip install gptme`) | PyPI (`pip install open-interpreter`) | shell-gpt: PyPI; local-cli: stdlib-only, zero deps | PyPI via `pyproject.toml`, minimal deps (`ollama`, `rich`, `click`) — aligned with category norms |

## Sources

- [gptme GitHub](https://github.com/gptme/gptme) — tool list, autonomous agent framing
- [gptme CLI Reference](https://gptme.org/docs/cli.html) — `-y/--no-confirm`, `-n/--non-interactive`, `-t/--tools`, `--tool-format` flags
- [aider + Ollama docs](https://aider.chat/docs/llms/ollama.html) — `num_ctx` / silent context truncation issue (HIGH confidence, primary source)
- [Open Interpreter Safety docs / SAFE_MODE.md](https://github.com/OpenInterpreter/open-interpreter/blob/main/docs/SAFE_MODE.md) — confirm-by-default, `--auto-run`/`-y`, safe mode disclaimers
- [Open Interpreter Settings](https://docs.openinterpreter.com/settings/all-settings) — `auto_run`, `safe_mode`, `offline` config
- [shell-gpt / TheR1D/shell_gpt GitHub](https://github.com/TheR1D/shell_gpt) — execute/describe/abort confirmation pattern
- [simonw/llm GitHub](https://github.com/simonw/llm) and [LLM 0.26 tools announcement](https://simonwillison.net/2025/May/27/llm-tools/) — tool plugin system, provider-agnostic design
- [zerostack GitHub](https://github.com/gi-dellav/zerostack) — five-tier permission system, doom-loop detection (3+ identical calls), explicit anti-features (no persistent autonomy, minimal LoC philosophy)
- [lutelute/local-cli GitHub](https://github.com/lutelute/local-cli) — stdlib-only zero-dependency design, dangerous-command blocklist, small-model curation (`qwen3:0.6b`)
- ["What Happens When Local LLMs Fail at Tool Calling — Testing 7 Models with a Rust Coding Agent" (dev.to)](https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep) — failure mode taxonomy (refusal-to-act, format confusion, retry loops), prompt-level fixes, token waste data (30K→9K)
- `.planning/PROJECT.md` — olla's existing v1 scope, constraints, and Out of Scope decisions

---
*Feature research for: lightweight local-LLM agentic CLI*
*Researched: 2026-06-10*
