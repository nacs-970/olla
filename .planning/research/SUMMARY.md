# Project Research Summary

**Project:** olla (lightweight ReAct agent CLI for local Ollama models)  
**Domain:** Agentic CLI, small-model LLM, local inference  
**Researched:** 2026-06-10  
**Confidence:** MEDIUM

## Executive Summary

Olla is a minimal ReAct loop CLI targeting small local models (0.6B-7B) on constrained hardware, explicitly trading away framework abstractions and per-turn token overhead for responsiveness and reliability on inference-limited hardware. The core bet — that small models handle simple `<tool>/<args>/<final>` tags better than JSON function-calling — is sound in principle (supported by failing benchmarks of competitive tools), but hinges entirely on empirical validation against the user's specific target models (0.6B Qwen, 1.7B Qwen, 4B Qwen, Gemma variants). This single validation sprint in Phase 1 is the highest-priority risk mitigation.

The research across Stack, Features, Architecture, and Pitfalls shows strong convergence on a four-phase vertical-slice build order: (1) loop core + parser + stop-sequence + shell tool (highest risk, lowest certainty), (2) safety gate + blocklist + confirm, (3) file tools, (4) memory/scratchpad. Three independent sources (ARCHITECTURE's "Build Order," FEATURES' P1 prioritization, PITFALLS' "Pitfall-to-Phase Mapping") arrive at this same structure, which is rare and valuable signal. However, research also surfaced a critical conflict: STACK recommends `shell=False + shlex.split()` for safety, while ARCHITECTURE and PITFALLS assume `shell=True` with pipes/redirects as a core feature — these cannot both be true. Resolving this trade-off (confirm-gate-as-boundary vs. shell-agnostic token-filtering) is the second-highest-priority design decision for Phase 2 (safety).

The roadmap should also incorporate three P1 features not currently in PROJECT.md but strongly recommended by multiple research sources: explicit `num_ctx` sizing (FEATURES + PITFALLS, silent truncation is a critical failure mode), a repetition/doom-loop guard (FEATURES + PITFALLS Pitfall 9, cheap and high-leverage on small-model debugging), and a format-validation smoke-test harness for Pitfall 1 (per-model format compliance checking at setup time).

## Key Findings

### Recommended Stack

Python 3.10+ with core dependencies: `ollama>=0.6.2` (official Python client, thin wrapper), `click>=8.1,<9` (CLI arg parsing and confirm prompts), and `rich>=13,<14` for streaming output (scoped to streaming + confirm prompts only — defer colored panels/tables/polish to v2 per PROJECT.md). Testing with `pytest>=8` and `pytest-mock>=3.14`.

**Core technologies:**
- **Python 3.10+**: Matches `click` 8.4's minimum and enables modern syntax (`match` statements, type unions). Arch Linux ships 3.12+ by default, no compatibility tax.
- **ollama>=0.6.2**: Official Ollama Python client, actively maintained (Apr 2026). Use sync `chat()` (ReAct loop is inherently sequential) with `stream=False` for v1 (simpler parsing, full response needed before tag extraction).
- **click>=8.1,<9**: Industry-standard Python CLI (38%+ adoption). Provides built-in `confirm()` and `prompt()` helpers that map directly to safety-gate UX (required per PROJECT.md).
- **rich>=13,<14** (optional but recommended): Use only for streaming token output + confirm prompts (LOW token/latency overhead); defer all decorative output (panels, progress bars, syntax highlighting) to v2.
- **pytest>=8 + pytest-mock>=3.14**: Unit test framework. Tag parser and loop logic are deterministic and heavily testable; mock `ollama.chat` calls to validate logic independently.

**Important clarification:** `ollama>=0.6.2` transitively pulls `pydantic>=2.9` and `httpx>=0.27` — accepted cost of using the official client. Do not add Pydantic directly to olla's own code (use dicts/dataclasses instead), but accept the transitive dependency.

### Expected Features

**Must-have (table stakes) for v1:**
- ReAct loop with tag-based parsing (`<tool>`, `<args>`, `<final>`) — the core value prop, reliability on small models
- Shell command execution tool (defining capability of the category)
- File read/write tools (second universal primitive)
- Confirm-before-execute with `--yes` override — table stake for trust on shell execution
- Blocklist for dangerous commands — table stake for basic safety (note: not a true boundary, see Pitfalls)
- Loop iteration cap (`--max-steps`, default 15) — universal guardrail against runaway loops
- Model selection flag (`--model`), no hardcoded default — user targets different 0.6B-7B models per-task
- One-shot mode (`olla "task"`) — simplest and natural v1 entry point
- Pip-installable, single console-script entry point

**Must-add per research (not in current PROJECT.md scope):**
- **Explicit `num_ctx` sizing on every Ollama request:** Ollama defaults to 2048-token context, silently truncates beyond that. FEATURES and PITFALLS both flag this as near-mandatory; aider's documentation confirms.
- **Visible step-by-step progress output:** "Step 3: running `ls -la`..." — FEATURES flags this as missing from explicit v1 scope; Table Stakes list includes it.
- **Repetition/doom-loop guard:** Detect if the model calls the same tool with the same args 2-3 times in a row; abort early. FEATURES lists as P1 recommendation; PITFALLS Pitfall 9 details it. Cheap and high-leverage.
- **Stop-sequences in Ollama requests:** Pass `options={"stop": ["</args>"]}` to halt generation at the action boundary, preventing hallucinated observations (ARCHITECTURE Pattern 3 = PITFALLS Pitfall 3).

**Should-have (competitive differentiators) for v1.x:**
- Scratchpad/`remember` tool with context-compaction strategy
- `--dry-run` flag (scoped to single-step preview, not speculative multi-step plan)
- Per-tool allowlist (`--tools` style, read-only mode)
- Token/context usage indicator

**Defer to v2+ (explicitly listed in PROJECT.md as out of scope):**
- Interactive/REPL mode
- Config file (`~/.olla/config.toml`)
- Web search / browser automation
- Diff/patch-based file editing
- Rich colored output (pure polish)

### Architecture Approach

Stateless-backend (Ollama), stateful-client (messages list) iterative loop with tolerant regex-based tag parsing and an explicit safety gate between parse and dispatch. The loop appends raw model output verbatim, parses, then checks safety constraints before execution — never letting the model's raw text become the "observation" fed back. The parser is maximally permissive (prose before/after tags, missing closing tags, multiple tool blocks) because small-model output variance is high.

**Major components:**
1. **AgentLoop (`loop.py`)** — owns `messages: list[dict]`, drives think→act→observe, enforces `--max-steps`, terminates on `<final>` or step cap
2. **Parser (`parser.py`)** — pure function, regex-based extraction of `<final>`, `<tool>`, `<args>` from raw model text; returns `Final | ToolCall | None`
3. **Safety Gate (`safety.py`)** — sits between parse and dispatch; applies blocklist, confirm prompts, and `--dry-run` short-circuiting
4. **Tool Registry (`tools/`)** — protocol-driven; shell, read_file, write_file, remember/recall (memory tool)
5. **Prompt/System Prompt (`prompts.py`)** — renders instructions with tool descriptions; the contract between prompt and parser

**Build order (vertical slices):** Slice 1 = core loop + parser + stop-sequence + shell tool (highest risk); Slice 2 = safety gate + blocklist + confirm + dry-run; Slice 3 = file tools; Slice 4 = memory tool. Three independent sources in the research converge on this ordering.

### Critical Pitfalls

1. **Format compliance assumption (Pitfall 1):** Sub-7B models are unreliable at producing well-formed `<tool>/<args>/<final>` tags. Research found 3B models with zero successful tool invocations, and 7B models achieving ~30% format compliance. *Mitigation:* Build a smoke-test harness that runs a fixed prompt set against each target model (0.6b, 1.7b, 4b, Gemma variants) during Phase 1 setup to measure tag-compliance rate. Have a documented "this model doesn't work with olla" outcome.

2. **Brittle parsing (Pitfall 2):** Small models add prose before/after tags, emit multiple tool blocks, leave tags unclosed. Naive regex fails, loop crashes. *Mitigation:* Lenient regex-based extraction; if no tag found, feed a corrective `user` message and count toward step budget rather than crashing. Cap format-violation retries (2-3 consecutive → abort).

3. **Hallucinated observations (Pitfall 3):** Model emits tool call then keeps generating, fabricating its own fake `Observation: ...` and reasoning from that fiction. *Mitigation:* Buffer the full response, truncate at the first closing tag boundary before parsing; pass `options={"stop": ["</args>"]}` to Ollama; the harness—not the model—appends real tool output.

4. **Blocklist as false safety boundary (Pitfall 4):** Command chaining, substitution, env vars, piping to `sh -c` all bypass simple string-match blocklists. *Mitigation:* Reframe blocklist as a "fast speed-bump," not the boundary. **Confirm-gate is the actual safety boundary.** Show the fully-resolved command string in the confirm prompt.

5. **Context window silent truncation (Pitfall 6):** Ollama defaults to 2048-token context, silently truncates oldest tokens first (dropping system prompt). Single `ls -la` on a large directory blows the budget, system prompt disappears, model "forgets" format mid-task. *Mitigation:* **Explicitly set `num_ctx` in every `ollama.chat()` call**; truncate tool output at source before appending; track approximate context usage; keep system prompt pinned from truncation.

## Implications for Roadmap

Research strongly converges on a four-phase build order, with explicit vertical-slice rationale and risk prioritization.

### Phase 1: Core Loop + Parser + First Tool (Highest Risk)

**Rationale:** This phase is where the core bet (XML-tag reliability on 0.6B-4B models) surfaces and must be validated or rejected. It's the riskiest because small-model quirks will actually appear here. Everything else is built on top of a working loop + parser.

**Delivers:**
- Iterative ReAct loop with full message-list state management
- Lenient, regex-based tag parser handling prose/unclosed/multi-call edge cases
- Stop-sequence wiring (`options={"stop": ["</args>"]}`) to prevent hallucinated observations
- First tool: shell command execution
- **Explicit `num_ctx` sizing** on every Ollama request
- **Format-validation smoke-test harness** (does XML work for target models?)
- **Visible step-by-step progress output** ("Step N: running `command`...")
- `--model` flag, one-shot mode, pip-installable entry point

**Research flag:** NEEDS RESEARCH-PHASE. The tag-format assumption hinges on empirical validation. The smoke test must run against the user's actual target models (0.6B, 1.7B, 4B Qwen variants + Gemma) before Slice 1 is considered "done." If XML-tag compliance is <80% on the smallest models, a contingency format (plain delimiters) should be validated in parallel and be a documented fallback option.

### Phase 2: Safety Gate + Blocklist + Confirm-Prompting

**Rationale:** Safety machinery is explicitly called "non-negotiable from v1" in PROJECT.md, but it's architecturally additive to a working loop — it slots into the existing parse→dispatch boundary without changing loop logic or parser. This comes after Phase 1 because Phase 1 must work first.

**Delivers:**
- `SafetyGate` component with blocklist, confirm-prompting, `--dry-run` short-circuiting
- Risk-tiered confirm prompts (read-only ops lighter-touch; write/shell destructive ops require explicit confirmation)
- Confirm prompts that show actual command string / resolved path / diff, not generic text
- `--yes` flag with clear documentation
- `--dry-run` flag scoped to single-step preview
- `--max-steps` enforcement + **repetition/doom-loop guard** (abort on 2-3 consecutive identical tool+args pairs)

**Design decisions to lock down:**
- **Shell execution model (CRITICAL, unresolved gap):** STACK recommends `shell=False + shlex.split()` for safety; ARCHITECTURE/PITFALLS assume `shell=True` with pipes/redirects as a feature. Phase 2 planning must choose: does olla support pipes/redirects (`shell=True` + confirm-as-boundary), or is safety stricter (`shell=False` + no shell syntax available)?
- **Blocklist pattern matching:** Move beyond simple command-name matching to structure-aware matching (detect `;`, `&&`, `||`, backticks, `$()` in arguments).
- **`--dry-run` semantics:** Lock down as single-step preview.

**Research flag:** MEDIUM. Confirm-gate design benefits from seeing Phase 1 patterns, but the broad architecture is standard across agent systems.

### Phase 3: File Tools (Read/Write)

**Rationale:** File tools are natural additions once the core loop + safety gate are validated. They flow through the existing gate with no new logic.

**Delivers:**
- `read_file(path)` tool with output truncation (cap at N KB or lines for large files)
- `write_file(path, content)` tool flagged `requires_confirm=True`
- Path resolution/normalization, path-traversal defense
- Confirm prompts showing resolved absolute path + diff/preview for writes

**Research flag:** LOW. File tools are well-established patterns; no research-phase needed.

### Phase 4: Memory/Scratchpad Tool

**Rationale:** Lowest risk, additive only, no new gate logic needed. Comes last because memory is a nice-to-have (P2 per FEATURES).

**Delivers:**
- `remember(key, value)` and `recall(key)` tools
- In-memory dict scoped to single run
- Optional: cap total scratchpad size to prevent unbounded context blowup

**Research flag:** LOW. Simple in-memory dict + per-turn token management. No research-phase needed.

### Phase Ordering Rationale

1. **Loop + Parser first (Phase 1)** because everything depends on it working, and small-model quirks are most likely to surface here. Format validation smoke-test determines whether the core bet is viable.
2. **Safety second (Phase 2)** because it's additive (sits at an existing boundary) and benefits from seeing Phase 1 patterns.
3. **File tools third (Phase 3)** because they're straightforward registry additions with no new gate logic.
4. **Memory last (Phase 4)** because it's purely additive (lowest risk, lowest priority per FEATURES).

### Convergence Signal

ARCHITECTURE's "Build Order," FEATURES' P1 prioritization, and PITFALLS' "Pitfall-to-Phase Mapping" all independently converge on this four-phase vertical-slice structure. When three independent research sources arrive at the same conclusion, that's high-confidence signal for the roadmapper.

### Research Flags

**Phase 1 needs research-phase:**
- **XML-tag format compliance validation** against target models (0.6B, 1.7B, 4B Qwen, Gemma variants). If compliance is <80%, plain-delimiter alternative should be validated in parallel.

**Phase 2 needs lighter research:**
- **Confirm-gate UX patterns** — review prior work (gptme, Open Interpreter, aider) on how to tier prompts.
- **Shell execution model trade-off** (shell=True vs. shell=False) — unresolved in research (STACK vs. ARCHITECTURE/PITFALLS disagree). Must be an explicit decision.

**Phases 3-4 skip research-phase:**
- File tools and memory tools are standard patterns with well-established practices.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core technologies and versions verified via official sources. One unresolved tension: STACK recommends `shell=False`, but ARCHITECTURE/PITFALLS assume `shell=True`. |
| Features | MEDIUM | P1 features align with table-stakes category norms. Three features strongly recommended by multiple research sources but not in PROJECT.md: `num_ctx` sizing (FEATURES + PITFALLS both flag), repetition guard (FEATURES + PITFALLS + competitor analysis), visible step-by-step output (FEATURES table-stakes). |
| Architecture | MEDIUM-HIGH | Component boundaries and vertical-slice build order converge across three sources. One uncertainty: exact tag-parsing regex is synthesized from best practices rather than a single canonical reference — needs validation against real model output in Phase 1. |
| Pitfalls | MEDIUM-HIGH | Critical pitfalls are sourced from developer blogs, GitHub issues, and official Ollama docs. One LOW-confidence claim: plain delimiters outperform XML (30%→100%) comes from a single GitHub issue thread — needs empirical validation in Phase 1 smoke-test. |
| **Overall** | **MEDIUM** | Three core bets are HIGH-confidence (architecture patterns, safety model, build order). One core bet is MEDIUM confidence (XML-tag format reliability) and is the single highest-priority validation spike for Phase 1. |

## Gaps to Address

1. **XML-tag format compliance (Pitfall 1 validation):** Research is mixed on whether sub-4B models reliably emit well-formed `<tool>/<args>/<final>` tags. Anecdotal evidence suggests plain delimiters may outperform XML on some 7B models. *Action:* Phase 1 planning must include a smoke-test harness (run fixed prompt set against each target model, measure tag-compliance rate). If <80% compliance on any target model, a fallback plain-delimiter format should be validated in parallel and documented as an option.

2. **Shell execution model (STACK vs. ARCHITECTURE/PITFALLS conflict):** STACK recommends `subprocess.run(shell=False, ...)` with `shlex.split()` for safety. ARCHITECTURE and PITFALLS assume `shell=True` with pipes/redirects as a feature. These are fundamentally incompatible. *Action:* Phase 2 planning must explicitly choose: (a) support full shell syntax (shell=True) with confirm-gate as the primary control, or (b) safer but limited shell (shell=False). Document the choice and its tradeoffs explicitly.

3. **Rich dependency scoping (STACK "Conflict to Resolve"):** PROJECT.md lists `rich` as a dependency but defers "colored output" to v2. STACK recommends keeping `rich` but scoping usage to streaming output + confirm prompts only (functional, not decorative). *Action:* Confirm with the user whether v1 includes this minimal `rich` usage (streaming + confirm) or switches to plain `print()`/`input()` entirely.

4. **`--dry-run` exact semantics (Pitfall 8):** Research recommends single-step preview scoping, but needs explicit UX decision. *Action:* Phase 2 planning should finalize: does `--dry-run` show only the first tool call (honest but brief), or does it simulate the full loop with placeholder observations (speculative but more informative)? Recommend option 1 (single-step, honest), but this is a UX call.

5. **Per-model tool-call format fallback:** If the smoke-test in Phase 1 reveals that XML tags underperform on small models, a contingency plan is needed. *Action:* If Pitfall 1 validation shows <80% compliance on target models, Phase 1 should include a parallel validation of an alternative format (plain markers or delimiters).

## Sources

### Primary (Official/HIGH confidence)

- **Ollama official docs**: Context length documentation — silent truncation behavior, `num_ctx` parameter
- **Ollama Python client (official)**: GitHub — API signatures, version 0.6.2 (Apr 2026), streaming and stop-sequence support
- **PyPI official package index**: `click` 8.4.1, `ollama` 0.6.2, `pytest` >=8 requirements
- **Python subprocess docs**: Official stdlib docs — `shell=True` security warnings, best practices
- **OWASP AI Agent Security Cheat Sheet**: Official guidance — blocklist limitations, confirm-gate as boundary

### Secondary (Research/MEDIUM confidence)

- **ARCHITECTURE.md research** (this project): Component boundaries, build order, stop-sequence pattern, tag-parsing strategy
- **FEATURES.md research** (this project): Feature prioritization across category competitors, P1 recommendations including `num_ctx` and repetition guard
- **PITFALLS.md research** (this project): Hazard taxonomy, mitigation strategies, cross-mapping to phases
- **Dev.to: "What Happens When Local LLMs Fail at Tool Calling"**: 7-model benchmark showing format failure modes, token waste
- **Trail of Bits: "Prompt Injection to RCE in AI Agents"**: Command injection patterns, blocklist bypass surface
- **Aider documentation**: `num_ctx` parameter importance for local Ollama
- **Semgrep Python command-injection cheat sheet**: Subprocess safety patterns

### Tertiary (GitHub issues/MEDIUM-LOW confidence, needs validation)

- **GitHub issue (llama.cpp #12153)**: Anecdotal claim that plain delimiters outperform XML-style tags (30%→100% on one 7B model). *Needs empirical validation in Phase 1 smoke-test.*
- **Ollama issue tracker**: Qwen3 tool-calling reliability issues — corroborates PROJECT.md's decision to avoid native tool-calling
- **GitHub issue (crewAI #3154)**: Agent hallucinating tool usage — confirms Pitfall 3 pattern
- **GitHub issue (ollama/ollama #6286)**: Context window sizing cannot be changed at runtime

---

*Research completed: 2026-06-10*  
*Synthesized by: Claude Code Synthesis Agent*  
*Ready for roadmap creation: yes (with Phase 1 format-validation spike as contingency plan)*
