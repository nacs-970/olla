# Pitfalls Research

**Domain:** Agentic CLI loop over local Ollama models (small models, 0.6B-7B), shell/file tool execution
**Researched:** 2026-06-10
**Confidence:** MEDIUM-HIGH (core findings verified against official Ollama docs, ollama-python via Context7, and OWASP/security advisories; small-model-specific behavioral claims are MEDIUM/LOW and flagged individually)

## Critical Pitfalls

### Pitfall 1: Sub-7B models are unreliable at structured tool calling — the core premise needs validation, not assumption

**What goes wrong:**
olla's entire value proposition rests on a 0.6B-7B model reliably emitting `<tool>name</tool><args>...</args>` and stopping. Research on small local models running ReAct-style loops found models in the 3B range producing **zero successful tool invocations** across realistic multi-step tasks — they either narrate what they "would" do, emit malformed tags, or never settle into the expected format at all. Separately, a documented case found Qwen2.5-7B passed format checks only ~30% of the time with XML-style tool-call tags (missing closing tags, extra prose, nested tags).

**Why it happens:**
Tool-calling is a learned behavior baked in via fine-tuning on specific formats (often JSON function-calling schemas matching the model's chat template). Generic instruction-tuned small models — especially heavily quantized or "uncensored" community fine-tunes like the ones in olla's target hardware (JOSIEFIED-Qwen3 0.6b/1.7b, gemma uncensored variants) — were not necessarily trained on the exact `<tool>/<args>/<final>` schema olla invents. The smaller the model, the less "spare capacity" it has to follow a novel output contract on top of solving the actual task.

**How to avoid:**
- Treat the `<tool>/<args>/<final>` format as a hypothesis to validate per-model, not a given. Build a tiny "format compliance" smoke test (a handful of fixed prompts run against each target model, checking the parser succeeds) and run it during setup/first-use for a new `--model`.
- Keep the tag vocabulary minimal and the prompt short — every extra instruction competes for the model's limited instruction-following budget.
- Design the parser to be maximally permissive (see Pitfall 2) so partial compliance still works.
- Have a documented "this model doesn't work well with olla" outcome — don't assume universal model-agnosticism is achievable; `--model` flexibility is about *user choice*, not a guarantee of equal quality.
- LOW/MEDIUM confidence note: there is anecdotal evidence (one issue thread) that switching from XML-style tags to plain delimiters like `### TOOL_CALL_START ###` raised compliance from ~30% to ~100% for a 7B model. This directly touches olla's "Key Decision" to use XML-style tags. **Recommend an early validation spike**: test both `<tool>...</tool>` and a plain-marker alternative against the user's actual 0.6B/1.7B/4B models before locking the format. If XML-style tags underperform on the smallest models, a fallback delimiter format should be a documented option, not a full redesign.

**Warning signs:**
- Parser regex/match rate falls below ~80% on a fixed test prompt set for a given model.
- Model frequently produces `<final>` immediately without ever calling a tool, even when a tool is clearly required.
- Increasing `--max-steps` doesn't help — the model is stuck on format, not reasoning.

**Phase to address:**
Loop core (parser design + format validation harness). Flag for deeper research if the validation spike shows XML tags underperform — may need a phase-specific pivot to plain-text markers.

---

### Pitfall 2: Brittle parsing — assuming the model will emit exactly one well-formed tag block per turn

**What goes wrong:**
Small models commonly: add prose before/after the tags ("Sure, I'll check that for you. `<tool>shell</tool>...`"), emit multiple `<tool>` blocks in one response, leave tags unclosed, use inconsistent casing or whitespace, nest tags incorrectly, or mix `<final>` and `<tool>` in the same response (answering AND trying to act). A naive `re.match` or strict XML parser will throw on any of these and either crash the loop or silently do nothing.

**Why it happens:**
Developers test against a handful of "happy path" model outputs during development, then ship. Small models have much higher output variance than large ones — the same prompt can yield compliant output 8/10 times and garbage 2/10 times. The 2/10 case is the one that crashes in production.

**How to avoid:**
- Use lenient, regex-based extraction (find first `<tool>...</tool>` and first matching `<args>...</args>` anywhere in the text) rather than requiring the entire response to be exactly the tag block.
- Strip/ignore leading prose — extract the tag content regardless of what surrounds it.
- If both `<tool>` and `<final>` appear, define a deterministic precedence rule (e.g., `<final>` wins, since the model believes it's done) and document it.
- If no recognizable tag is found at all, don't crash — treat it as a "format violation" turn: feed back a short corrective system message ("Your last response didn't include a valid `<tool>` or `<final>` tag. Respond using only the format: ...") and count it toward `--max-steps`.
- Cap format-violation retries separately (e.g., 2-3 consecutive violations → abort with a clear error) so a model stuck in a bad format doesn't burn the entire step budget on retries.

**Warning signs:**
- Loop exits with an unhandled exception on real model output that worked fine with a different model.
- `--max-steps` gets exhausted purely on "model didn't use a tag" turns with no actual tool execution.

**Phase to address:**
Loop core (parser implementation). This is the single highest-leverage piece of robustness work in v1 — get it lenient and well-tested early, since every other tool depends on it.

---

### Pitfall 3: Model hallucinates the tool's observation instead of waiting for real output

**What goes wrong:**
The model emits `<tool>shell</tool><args>ls -la</args>`, and then — because it's a single forward pass generating tokens — *keeps generating*, producing a fake `<observation>` or "Result: ..." block with invented file listings, then reasons from that fiction and produces a `<final>` answer. The real shell command may never even run, or runs but its output is ignored because the model already "saw" its own hallucinated result.

**Why it happens:**
Autoregressive models don't inherently know "stop, wait for external input" — that's an artifact the harness must enforce. If the prompt format doesn't make the loop's structure explicit, or if the model's response isn't truncated immediately after the closing `</args>` (or `</tool>` for no-arg calls), the model will happily continue the pattern it's seen in training data (which often includes full ReAct transcripts with both action and observation).

**How to avoid:**
- **Buffer the full model response, then truncate at the first complete tool-call tag** before parsing — discard anything the model generated after `</args>`/`</tool>`. Never act on a partial/streamed response as if it were final, and never let model-generated text after the tag close leak into the "observation" the loop appends to history.
- If using Ollama's streaming API, accumulate chunks but stop consuming/cancel the stream as soon as the closing tag is detected (saves tokens/time too — relevant given hardware constraints).
- Use Ollama's `stop` option (a generation parameter supported in `ollama.chat`/`ollama.generate` options) with sequences like `</args>` or `</tool>` if the model's chat template allows it, as a belt-and-suspenders measure — though for small models this is sometimes unreliable, so don't rely on it alone.
- The harness — not the model — appends the real tool output as the "observation" for the next turn. The model never gets to write its own observation; that text, if present, is discarded.

**Warning signs:**
- Tool execution count doesn't match the number of `<tool>` tags the model emitted (model "calls" tools that never actually ran).
- `<final>` answers reference file contents/command output that don't match what the shell/file tool actually returned.

**Phase to address:**
Loop core (response handling — buffer-then-truncate-then-parse, before the parser from Pitfall 2 even runs).

---

### Pitfall 4: The shell blocklist is treated as the safety boundary, when it can't be

**What goes wrong:**
A blocklist of dangerous commands/patterns (`rm -rf /`, `sudo`, `dd`, etc.) is trivially bypassed by:
- **Chaining**: `echo hello; rm -rf ~/important` — the blocked command isn't the first token.
- **Substitution/backticks**: `` echo $(rm -rf ~/important) `` or `` `cat /etc/passwd` ``.
- **Env var expansion / IFS tricks**: building forbidden command names from concatenated variables (`r="rm"; ${r} -rf ...`) or using `${IFS}` to avoid space-based pattern matches.
- **Indirection**: piping to `sh -c`, `bash -c`, `xargs`, `eval`, or invoking via alternate paths (`/usr/bin/rm`, `/proc/self/root/bin/rm`).
- **Whitelisted-command abuse**: a command not on the blocklist (e.g., `find . -delete`, `python3 -c "..."`, `curl | sh`) achieves the same destructive effect.

If `subprocess` is invoked with `shell=True` (likely, since olla needs to run arbitrary shell commands the model writes — pipes, redirects, etc.), the *entire shell feature set* is available to the model's output, and a blocklist is fundamentally a denylist trying to enumerate an infinite attack surface.

**Why it happens:**
Blocklists are easy to write and feel like "doing safety," but pattern-matching against a Turing-complete shell language is provably incomplete. Developers often test the blocklist against a few obvious dangerous strings, see it work, and move on — without considering that the *model itself* (not a malicious user) can produce these patterns either through hallucination, being tricked by content it read (prompt injection via file contents or command output), or simply because the user's natural-language task implies a destructive action the user didn't fully think through.

**How to avoid:**
- **Reframe the blocklist as a fast, cheap speed-bump / UX nicety** ("catch the obvious stuff before bothering the user"), not the safety boundary. The **confirm-before-execute gate is the actual safety boundary** for v1 — every shell command and file write must pass through it (unless `--yes`), and the blocklist's job is just to make *some* dangerous commands fail fast/loudly or get extra warning styling.
- Document this explicitly to users: "the blocklist catches common footguns; it does not make `--yes` safe against an adversarial or badly-prompted model. Use `--yes` only for tasks you trust."
- Show the **fully-resolved command string** (after any quoting/escaping) in the confirm prompt — what will actually run, not what the model "intended."
- Consider blocklisting on the *parsed command structure* where feasible (e.g., refuse if the command contains `;`, `|`, `&&`, `||`, backticks, or `$(...)` AND targets a destructive binary — i.e., combine chaining-detection with destructive-command detection rather than just matching destructive commands at string-start).
- For v1, given "minimal dependencies," a pragmatic middle ground: run via `subprocess.run(cmd, shell=True, ...)` (since shell features like pipes are part of the value prop) but make the confirm prompt *mandatory by default* and prominent — don't let `--yes` be the documented "normal" workflow.

**Warning signs:**
- Blocklist contains only single-word command names (`rm`, `sudo`, `dd`) with no consideration of shell metacharacters.
- Confirm prompt shows the model's *stated intent* rather than the literal command string that will be passed to the shell.
- Internal tests for the blocklist only cover "happy path" dangerous commands, never chained/obfuscated variants.

**Phase to address:**
Safety layer (blocklist + confirm-gate design). This should be designed *together* — the blocklist phase should explicitly document "this is not sufficient alone" and the confirm-gate phase should be scoped as the primary control.

---

### Pitfall 5: File read/write tools bypass shell safety entirely — a separate attack surface

**What goes wrong:**
`write_file(path, content)` and `read_file(path)` are not shell commands, so a shell blocklist does nothing for them. A model can:
- `write_file("~/.bashrc", "<malicious startup command>")` or overwrite `~/.ssh/authorized_keys`, `~/.profile`, crontab files, etc. — persistence/RCE without ever touching the shell tool.
- `read_file("~/.ssh/id_rsa")` or `.env` files, pulling secrets into the conversation history (which then might get echoed back in a `<final>` answer, or logged).
- Path-traverse (`../../etc/passwd`) if paths aren't resolved/validated, or follow symlinks out of an intended working directory.
- Overwrite arbitrary files outside the project directory the user *thinks* they're working in.

**Why it happens:**
File tools feel "safer" than shell because they're narrow and structured, so they often get less scrutiny than the shell tool — but `write_file` to the right path is just as dangerous as many shell commands, and `read_file` is a straightforward secret-exfiltration vector once the content is in context (and potentially in `<final>` output, terminal scrollback, or any logging olla does).

**How to avoid:**
- The confirm-before-execute gate (Pitfall 4) must cover `write_file` (already in v1 scope per PROJECT.md — good) — make sure it shows the **resolved absolute path** and a diff/preview of what will change, not just "write to file".
- For `read_file`, consider whether sensitive paths (dotfiles, `.ssh/`, `.env`, anything matching common secret-file patterns) deserve either a warning, a blocklist of their own, or at minimum aren't silently included if the model is also going to produce a `<final>` summary that gets displayed/logged.
- Resolve and normalize paths (`os.path.realpath`) before acting, and consider whether to constrain file tools to a working directory (cwd or user-specified root) by default — this is a meaningful safety/UX feature even if not strictly "blocking" since the user can always pass `--yes` or confirm anyway. At minimum, *flag* (in the confirm prompt) when a path resolves outside the current working directory.

**Warning signs:**
- `write_file`/`read_file` confirm prompts show the raw path argument from the model rather than the resolved absolute path.
- No test coverage for path traversal (`../`) or home-directory (`~`) expansion in file tool args.

**Phase to address:**
File tools + safety layer (these should ship together — file tools without confirm-gating are not v1-ready per PROJECT.md's own constraints).

---

### Pitfall 6: Context window blown by appending raw tool output, with silent truncation masking the failure

**What goes wrong:**
Every shell stdout/stderr blob and every `read_file` result gets appended verbatim to the conversation history that's re-sent to the model each turn. On small models, the *default* Ollama context window is small (the Modelfile baseline is 2048 tokens; many runtimes default around 4096 unless `num_ctx` is explicitly raised) — and these models also have lower *trained maximum* context than larger models, so even raising `num_ctx` only helps so much. A single `ls -la` in a large directory, a `cat` of a medium-sized file, or a verbose build/test command output can consume the entire remaining budget in one turn. Once the prompt exceeds `num_ctx`, **Ollama silently truncates from the oldest tokens — no error, no warning** — meaning the system prompt (with the tag-format instructions!) can get truncated away first, causing the model to "forget" the output format mid-task. This produces confusing downstream failures (Pitfall 1/2 symptoms) that look like model misbehavior but are actually a context-management bug.

**Why it happens:**
It's the simplest implementation — just keep a list of messages and append. It works fine in development with short test commands and small files, then breaks on real tasks (`pip list`, `git diff`, reading a log file, `find .`) where output can be thousands of tokens.

**How to avoid:**
- **Truncate tool output before appending to history**, not after. For shell stdout/stderr: cap at a fixed character/line budget (e.g., last N lines + first M lines, since errors/summaries are often at the end and command identity is at the start), with a clear `[...output truncated, N lines omitted...]` marker so the model knows data was cut.
- For `read_file`: cap file content length, and/or require the model to specify a line range for large files (or just refuse/warn on files above a size threshold).
- **Explicitly set `num_ctx`** in the `ollama.chat()`/`generate()` `options` dict rather than relying on the runtime default — pick a value appropriate to the target model's trained max and the hardware's available RAM/VRAM (smaller models often support 8k-32k trained context even if the *runtime default* is 2-4k; raising `num_ctx` for agent use is well-documented as the single biggest reliability lever, but it costs memory).
- Track an approximate running token count (rough heuristic: chars/4) and proactively trim/summarize older turns *before* hitting the limit, rather than relying on Ollama's silent truncation as the backstop. Given olla's "minimal dependencies" constraint, a simple sliding-window approach (keep system prompt + last K turns + current task) is more appropriate than a summarization model call.
- Always keep the system prompt (format instructions) pinned/protected from truncation — if anything gets dropped, it should be the oldest tool-output observations, never the system prompt or the original task description.

**Warning signs:**
- Model "forgets" the `<tool>/<args>/<final>` format partway through a long task (after several tool calls with large outputs).
- Tasks that worked with short commands fail/degrade when a command produces lots of output.
- No explicit `num_ctx` is set anywhere in the codebase (relying entirely on Ollama defaults).

**Phase to address:**
Loop core (history management) + shell/file tools (output truncation at the source). This is a cross-cutting concern — flag for phase-specific deeper research on the right truncation heuristics once real usage patterns are known.

---

### Pitfall 7: Confirm-prompt fatigue trains users to blindly approve (or reach for `--yes` permanently)

**What goes wrong:**
If every single tool call — including low-risk ones like `read_file` on an obviously-safe path, or `ls`, `pwd`, `cat README.md` — triggers the same confirm prompt as a destructive `rm` or a `write_file` to a config file, users rapidly habituate to hitting Enter/y without reading. Telemetry from comparable agentic CLIs shows approval rates around 90%+ regardless of risk level once fatigue sets in — meaning the confirm gate stops functioning as a safety control and becomes pure friction. The natural user response is to start every session with `--yes`, which removes the safety layer entirely for the *whole* session, including the one dangerous command buried among twenty safe ones.

**Why it happens:**
Uniform confirmation is the simplest thing to build — one code path, one prompt, applied everywhere. But "everything requires the same scrutiny" is equivalent to "nothing gets real scrutiny." This is a known failure mode (alert fatigue) that transfers directly to agent approval prompts.

**How to avoid:**
- Differentiate prompt **severity/framing** by risk: read-only operations (`read_file`, `shell` commands matching a small "known-safe" allowlist like `ls`, `pwd`, `cat`, `git status`, `git diff`) could be auto-approved or shown with a lighter-touch notice ("running: `ls -la` ...") rather than a blocking y/n, while `write_file` and arbitrary shell commands always require explicit confirmation. (Careful: per Pitfall 4/5, the "low risk" classification must be based on the *resolved* command/path, not surface pattern matching alone.)
- Make the confirm prompt **show the actual content/diff**, not just "Execute shell command? [y/N]" — e.g., show the literal command string, or for `write_file`, show a diff of old vs. new content. A prompt with no information forces a blind trust decision every time, which accelerates fatigue.
- Keep prompts **short and consistent** in format so users can scan them quickly (consistency reduces cognitive load without reducing information).
- `--yes` should be clearly documented as "I trust this entire session, including destructive operations" — not framed as "skip the annoying prompts." Consider whether `--yes` should still show *what* was executed after the fact (a log/summary), so users retain visibility even without per-step gating.
- Don't conflate `--dry-run` and confirm-prompts as redundant — `--dry-run` is for *planning visibility before starting*, confirm-prompts are for *per-step control during execution*. Both have a place but serve different moments.

**Warning signs:**
- Every tool type (read_file, shell, write_file) produces visually identical confirm prompts.
- The confirm prompt doesn't show enough information to make an informed decision without running the command mentally.
- Early user testing shows `--yes` becomes the default invocation pattern within the first few sessions.

**Phase to address:**
Safety layer (confirm-gate design) — should be designed with risk-tiering from the start rather than retrofitted, since retrofitting changes the UX contract users have already learned.

---

### Pitfall 8: `--dry-run` in a multi-step ReAct loop can only meaningfully preview one step

**What goes wrong:**
`--dry-run` is requested as "print planned tool calls without executing." But in a ReAct loop, **step 2 depends on the real observation from step 1** — which doesn't exist in dry-run mode. So either (a) dry-run only shows the *first* tool call the model would make (honest but maybe underwhelming — "is that all dry-run does?"), or (b) the implementation feeds the model a *fake/placeholder* observation to keep the loop going and shows a full multi-step "plan" — which is speculative fiction the model invented based on guessed outputs, and could be wildly wrong/misleading. Users who expect "show me everything that will happen" from option (b) will be misled by a trace that bears no resemblance to the real run.

**Why it happens:**
"Dry run" is a familiar concept from tools like `terraform plan` or `apt --dry-run`, where the *entire plan* can be computed deterministically without side effects. ReAct loops are fundamentally different — they're interactive/adaptive, so there is no deterministic "plan" to compute. Developers borrow the term without confronting that the analogy breaks down after step 1.

**How to avoid:**
- Scope v1 `--dry-run` honestly to **single-step preview**: "Here's the first tool call the model wants to make. Not executing." This is accurate, simple, and still useful (lets users sanity-check the model's interpretation of the task before committing).
- If multi-step preview is desired later, clearly label it as **speculative** ("the model's stated plan, not a guaranteed execution trace — actual steps will depend on real command output") and consider having the model produce a separate "plan" output distinct from the step-by-step tool-call format, rather than simulating the loop with fake observations.
- Document this limitation explicitly so it's not perceived as a bug ("why did dry-run only show one step?").

**Warning signs:**
- Users file issues saying "dry-run showed step 3 would do X, but the real run did Y at step 3" — this is *expected* given the architecture, but will read as a bug if undocumented.
- Implementation feeds synthetic/placeholder tool outputs to the model during dry-run to "keep it going" — this is the trap.

**Phase to address:**
`--dry-run` flag (UX/scoping decision) — should be settled during loop core design, since it constrains how the loop function is structured (does it have a "plan-only" mode vs. "execute" mode, and how do they share code).

---

### Pitfall 9: Repetition/no-progress loops aren't caught by `--max-steps` alone until the budget is fully burned

**What goes wrong:**
A model gets stuck calling the same tool with the same (or trivially varied) arguments repeatedly — e.g., `read_file("config.yaml")` ten times in a row because it "forgot" it already has the content (especially likely if context truncation, Pitfall 6, dropped the earlier observation). `--max-steps 15` *will* eventually stop this, but the user burns all 15 steps (and the wall-clock time of 15 model inferences on a slow local model) before getting any useful signal — and the final output is just "max steps reached," not an explanation of *why*.

**Why it happens:**
`--max-steps` is a global, blunt instrument — it doesn't distinguish "made 15 steps of real progress and ran out" from "called the exact same tool 15 times." Both look identical to a simple counter.

**How to avoid:**
- Track a simple repetition signature: hash of `(tool_name, args)` for the last N steps (e.g., last 3). If the same signature repeats 3x consecutively, **abort early with a specific message** ("olla stopped: the model repeated the same `read_file(\"config.yaml\")` call 3 times — this usually means it lost track of earlier output. Try increasing context or simplifying the task.") rather than burning the full `--max-steps` budget.
- This is cheap to implement (no extra model calls, just comparing recent history) and dramatically improves the debugging experience on slow local hardware where each wasted step costs real wall-clock time.
- Consider distinguishing "max steps reached, task incomplete" from "repetition detected, likely stuck" in the final output — these have different remediation paths for the user (former: increase `--max-steps` or simplify task; latter: investigate context/format issues).

**Warning signs:**
- "Max steps reached" is the most common failure message users see, and inspecting the trace shows the same tool call repeated near-identically.
- No mechanism exists to short-circuit before `--max-steps` other than the model itself emitting `<final>`.

**Phase to address:**
Loop core / `--max-steps` safety feature — small addition to the same step-counting logic, high value for local-model debugging.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Strict XML parsing (`xml.etree`) instead of lenient regex extraction | Faster to write, "correct" parsing | Crashes on the ~20% of small-model outputs that aren't well-formed XML (Pitfall 2) | Never for v1 — lenient parsing is core to the value prop |
| Relying on Ollama's default `num_ctx` | One less config decision | Silent truncation drops system prompt mid-task on long sessions (Pitfall 6) | Never — set `num_ctx` explicitly even if just to a slightly-higher-than-default value |
| Single uniform confirm prompt for all tool types | Simple, one code path | Approval fatigue, `--yes` becomes permanent (Pitfall 7) | Acceptable for a throwaway prototype; not for v1 ship |
| `subprocess.run(cmd, shell=True)` with no output cap | Simple, supports pipes/redirects naturally | Context blowup on verbose commands (Pitfall 6); blocklist bypass surface (Pitfall 4) | Acceptable *if* paired with output truncation + confirm-gate as primary control — don't defer those |
| No repetition detection, rely on `--max-steps` only | Less code | Wastes full step budget + wall-clock time on stuck loops (Pitfall 9) | Acceptable only for the very first prototype iteration; cheap enough to add immediately after |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| `ollama` Python client — model not pulled | Letting `ollama.chat()` raise an unhandled `ResponseError` with a cryptic 404, confusing users about what "pull" means | Catch `ollama.ResponseError`, check `e.status_code == 404`, and either prompt the user to run `ollama pull <model>` (preferred — pulling can be large/slow and shouldn't happen silently inside an agent loop) or offer to `ollama.pull(model)` with a visible progress indicator |
| `ollama` Python client — server not running | Unhandled `ConnectionError` with a raw traceback | Catch `ConnectionError` at startup (before entering the loop) and print a clear "Ollama isn't running — start it with `ollama serve`" message |
| `ollama` Python client — timeouts on first request | Default client timeouts (varies by version/transport) are too short for first-request model loading, which can take well beyond typical defaults on constrained hardware, causing spurious timeout errors that look like olla bugs | Configure the client with a generous timeout for the *first* request of a session (model load + first inference), and consider a shorter timeout for subsequent requests; surface "loading model, this may take a moment" messaging on the first call |
| `ollama` Python client — streaming + tool calls | Assuming `stream=True` interacts cleanly with custom tag-based parsing the same way it does with Ollama's native `tool_calls` field — olla isn't using native function-calling, so streaming is purely a UX/responsiveness concern, not a tool-call mechanism | Either don't stream (simplest, avoids Pitfall 3 entirely — get the full response, then parse) or stream for display purposes only while buffering server-side and only parsing/acting once a complete response (or recognized tag boundary) is received |
| `ollama` Python client — model unloads after idle | Ollama unloads models after ~5 minutes idle by default; a long-running olla session with slow user interaction (e.g., waiting on confirm prompts) could see the *next* model call incur a full reload | Not critical for one-shot mode (no idle gaps), but worth knowing if any future interactive/REPL mode is added — consider `keep_alive` option in chat/generate calls |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded scratchpad growth | `remember(key, value)` calls accumulate across a long task and get re-serialized into every prompt, eating context budget alongside tool outputs | Cap total scratchpad size (e.g., total chars or entry count); consider showing scratchpad contents to the model only as a compact summary, not full verbatim history | Becomes noticeable on tasks with >5-10 `remember` calls or large stored values; compounds with Pitfall 6 |
| Re-sending full conversation history every turn (no caching) | Each step re-tokenizes the entire growing prompt — on CPU-bound local inference, this means per-step latency *increases* as the task progresses | Ollama/llama.cpp have internal prompt-caching for repeated prefixes, but appending new turns at the end should still hit cache for the unchanged prefix — verify this isn't defeated by reformatting the whole history each turn (e.g., re-numbering steps) | Noticeable after ~5-8 steps on slow hardware; could make a 15-step task take minutes longer than necessary |
| Large `read_file` results dumped into context | A single `read_file` on a multi-KB file can consume a large fraction of a 4k-8k context window in one turn | Cap file read size by default (e.g., first N KB or lines), require explicit larger reads only if model asks again with a range | Breaks on any "read this log file" / "read this source file" task larger than a few hundred lines |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Treating the shell blocklist as sufficient safety | Arbitrary command execution via chaining/substitution/indirection bypasses any string-based blocklist (Pitfall 4) | Confirm-gate is the real boundary; blocklist is a speed-bump; document this clearly to users |
| No confirm-gate on `read_file` for sensitive paths | Model reads `~/.ssh/id_rsa`, `.env`, credential files into context, which may then surface in `<final>` output, terminal history, or logs | Either gate `read_file` on sensitive-path patterns, or at minimum ensure conversation history / logs aren't persisted insecurely; warn users that file contents become part of the LLM's context (and potentially the model provider's logs, if ever using a remote model via `--model`) |
| Path traversal / symlink following in file tools | `write_file("../../../etc/something", ...)` or following a symlink writes outside intended scope | Resolve paths with `os.path.realpath`, flag (in confirm prompt) any resolved path outside cwd |
| `--yes` as documented "normal" usage | Removes all per-step safety for an entire session based on initial trust in the *first* command, not the *last* | Document `--yes` as "I've reviewed what this task could do and accept the risk for the whole session" — not as a convenience flag |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Identical confirm prompts for all risk levels | Approval fatigue → blind `y` → `--yes` becomes permanent (Pitfall 7) | Risk-tiered prompts with content shown (literal command / diff) |
| `--dry-run` implies full multi-step plan | Users distrust the tool when reality diverges from the "plan" (Pitfall 8) | Scope dry-run to single-step preview, label anything beyond as speculative |
| "Max steps reached" with no diagnosis | User doesn't know if the task was almost done or hopelessly stuck | Distinguish repetition-detected-abort from genuine step-budget-exhaustion (Pitfall 9), and show the last few steps in the error |
| Silent context truncation manifesting as "model got dumber" | User blames the model/olla for degraded quality mid-task with no visible cause | Explicit `num_ctx` setting + proactive history trimming + visible note when trimming occurs ("[older tool output omitted to fit context]") |
| No indication of what command actually ran vs. what model "said" it ran | User can't tell if Pitfall 3 (hallucinated observation) occurred | Always echo the *actual* executed command and its *actual* output distinctly from the model's reasoning text, even in non-verbose mode |

## "Looks Done But Isn't" Checklist

- [ ] **Tag parser:** Often only tested against clean, hand-written example outputs — verify against real outputs from the *smallest* target model (0.6B), including multi-call, prose-wrapped, and unclosed-tag cases.
- [ ] **Shell blocklist:** Often only tested against single-word dangerous commands at string-start — verify it (or the confirm-gate) handles `;`, `&&`, `|`, backticks, `$()`, and piping to `sh -c`.
- [ ] **`--max-steps`:** Often just a counter — verify it also catches repetition (same tool+args N times) before exhausting the full budget.
- [ ] **Context handling:** Often "works" in dev because test tasks are short — verify behavior on a task that produces a large `shell` output (e.g., `find /` or `pip list`) and confirm the system prompt survives to the final step.
- [ ] **`--dry-run`:** Often implemented as "run the loop but skip `subprocess.run`" — verify it doesn't feed the model fake observations to keep going (Pitfall 8), and that it's clearly single-step or clearly-labeled-speculative.
- [ ] **Error handling for Ollama connection:** Often only tested with Ollama running — verify the error message when Ollama is down or the model isn't pulled is actionable, not a raw traceback.
- [ ] **Confirm-gate scope:** Often covers `shell` but is forgotten for `write_file` — verify both paths (and any future tools) route through the same gate.
- [ ] **Scratchpad bounds:** Often unbounded in v1 — verify there's at least a soft cap so a long task doesn't silently consume the context budget via memory alone.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|-----------------|
| Parser too strict, crashes on real output | LOW | Loosen to regex-based extraction; add a corpus of real failing outputs as regression tests |
| Context truncation drops system prompt | MEDIUM | Set explicit `num_ctx`; add history-trimming that protects system prompt; add a "context budget" debug flag to surface token estimates |
| Blocklist bypass discovered post-ship | MEDIUM | Reframe documentation/UX to emphasize confirm-gate as primary control (no code change required if confirm-gate already covers everything); add the specific bypass pattern to blocklist as defense-in-depth |
| `--yes` caused unwanted destructive action | HIGH (data loss possible) | No code recovery — this is why confirm-gate-by-default matters. Post-incident: add a "last N actions" log file (even in `--yes` mode) so users can at least see what happened and attempt manual recovery |
| Repetition loop wastes user's time | LOW | Add repetition-signature check (Pitfall 9) — small, isolated change to loop core |
| `--dry-run` plan diverged wildly from real run | LOW | Documentation fix + rescope dry-run to single-step; no architectural change needed if loop core already separates "decide next step" from "execute step" |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|---------------|
| 1. Sub-7B tool-calling unreliability | Loop core (format validation spike) | Run fixed test-prompt set against each target model (0.6b, 1.7b, 4b, gemma variants); measure tag-compliance rate before locking format |
| 2. Brittle tag parsing | Loop core (parser) | Unit tests against a corpus of real (not idealized) model outputs including prose-wrapped, multi-call, unclosed-tag cases |
| 3. Hallucinated observations | Loop core (response handling) | Verify tool-execution count == `<tool>` tag count in trace logs; verify no model-generated "observation" text reaches history |
| 4. Blocklist as false safety boundary | Safety layer (blocklist + confirm-gate, designed together) | Test blocklist against chained/obfuscated commands (`;`, `&&`, backticks, `$()`) — confirm they're caught by confirm-gate even if blocklist misses them |
| 5. File tools bypass shell safety | File tools + safety layer | Confirm-gate covers `write_file`/`read_file`; resolved-path shown in prompt; path-traversal test cases |
| 6. Context window blowup / silent truncation | Loop core (history mgmt) + shell/file tools (output capping) | Run a task that produces >2k tokens of tool output; verify system prompt survives and truncation is visible/logged |
| 7. Confirm-prompt fatigue | Safety layer (confirm-gate design) | Risk-tiered prompt design reviewed before implementation; prompts show actual command/diff, not generic text |
| 8. `--dry-run` multi-step fiction | `--dry-run` flag (UX scoping, decided alongside loop core) | Dry-run output reviewed for honesty — single-step preview or clearly-labeled speculative plan |
| 9. Repetition not caught before `--max-steps` | Loop core (`--max-steps` logic) | Construct a deliberately-stuck task (e.g., file that doesn't exist) and verify early abort with diagnosis, not full step-budget burn |

## Sources

- [Why Small LLMs Fail at Tool Calling: The Shocking Discovery from Our Llama 3B Benchmark](https://dev.to/anak_wannaphaschaiyong_11/why-small-llms-fail-at-tool-calling-the-shocking-discovery-from-our-llama-3b-benchmark-5lg) — MEDIUM confidence (single benchmark writeup)
- [What Happens When Local LLMs Fail at Tool Calling — Testing 7 Models with a Rust Coding Agent](https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep) — MEDIUM confidence
- [Feature Request: Avoid xml use in tool call instructions — llama.cpp #12153](https://github.com/ggml-org/llama.cpp/issues/12153) — LOW/MEDIUM confidence (single issue thread, anecdotal 30%→100% claim)
- [Your ReAct Agent Is Wasting 90% of Its Retries](https://towardsdatascience.com/your-react-agent-is-wasting-90-of-its-retries-heres-how-to-stop-it/) — MEDIUM confidence
- [Agent incorrectly invokes hallucinated tool — google/adk-python #4173](https://github.com/google/adk-python/issues/4173) — MEDIUM confidence (real-world issue report)
- [Hermes Agent Security docs](https://hermes-agent.lzw.me/docs/en/user-guide/security) — MEDIUM confidence
- [Sandbox Bypass via Model-Controlled Input — GHSA-m77w-p5jj-xmhg](https://github.com/Gitlawb/openclaude/security/advisories/GHSA-m77w-p5jj-xmhg) — HIGH confidence (security advisory)
- [Prompt injection to RCE in AI agents — Trail of Bits](https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/) — HIGH confidence (reputable security research)
- [AI Agent Security — OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) — HIGH confidence (official OWASP guidance)
- [Python subprocess docs — shell=True warnings](https://docs.python.org/3/library/subprocess.html) — HIGH confidence (official docs)
- [Prevent Command Injection for Python — Semgrep](https://semgrep.dev/docs/cheat-sheets/python-command-injection) — HIGH confidence
- [Context length — Ollama official docs](https://docs.ollama.com/context-length) — HIGH confidence (official docs)
- [Context window size cannot be changed — ollama/ollama #6286](https://github.com/ollama/ollama/issues/6286) — MEDIUM confidence (official repo issue)
- [Fixing Context Limits in OpenCode + Ollama](https://stouf.medium.com/fixing-context-limits-in-opencode-ollama-1d820b332b41) — MEDIUM confidence (corroborates official docs on agent-specific num_ctx recommendations)
- ollama-python README/docs via Context7 (`/ollama/ollama-python`) — HIGH confidence (ResponseError, ConnectionError, streaming patterns)
- [Ollama API Timeout Fix](https://www.aimadetools.com/blog/ollama-api-timeout-fix/) — MEDIUM confidence
- [504 Gateway Timeout — ollama/ollama-python #314](https://github.com/ollama/ollama-python/issues/314) — MEDIUM confidence (official repo issue)
- [Suffering from Agent Permission Fatigue?](https://scalex.dev/blog/ai-agent-permissions/) — MEDIUM confidence (cites ~93% approval-rate telemetry)
- [Approval Fatigue Is Breaking AI Agents — Execution Boundaries Fix It](https://medium.com/@shreya_edulakanti/approval-fatigue-is-breaking-ai-agents-execution-boundaries-fix-it-6c46c6d512dd) — MEDIUM confidence
- [ReAct Pattern: Interleaving Reasoning and Action for LLM Agents](https://mbrenndoerfer.com/writing/react-pattern-llm-reasoning-action-agents) — MEDIUM confidence (stop-sequence/observation-as-ground-truth principle)
- [Agent does not actually invoke tools, only simulates tool usage — crewAI #3154](https://github.com/crewAIInc/crewAI/issues/3154) — MEDIUM confidence (real-world issue corroborating hallucinated-observation pattern)
- [Agent gets stuck in repetitive tool call loops — bytedance/deer-flow #1055](https://github.com/bytedance/deer-flow/issues/1055) — MEDIUM confidence

---
*Pitfalls research for: olla — agentic CLI loop over local Ollama models*
*Researched: 2026-06-10*
