---
status: diagnosed
trigger: "Phase 03 UAT gap G-03-4: file edit wrote unrelated model-generated content before reading the target; diagnose model-capacity limitations versus application contract gaps without fixing."
created: 2026-07-28T14:16:15+07:00
updated: 2026-07-28T14:27:21+07:00
---

## Current Focus

bug_class: bohrbug (the unsafe transition is deterministic for a given model-emitted write_file call; model selection of that call is stochastic, but runtime acceptance is not).
hypothesis: CONFIRMED — a small-model semantic failure produced the bad call, and the application independently permitted it because write confirmation authenticates only the target path and no runtime contract requires a prior read of that target or validates edit provenance/content.
test: Completed isolated mocked first-turn write_file probe, static prompt/runtime/test inspection, and relevant automated test run.
expecting: Confirmed result was read_calls=0, write_calls=1, exact unrelated payload dispatched, and a path-only confirm prompt.
next_action: Return diagnosis only; do not implement the suggested guardrails.
candidate_causes:
  - code: run_loop treats every syntactically valid write_file payload as executable after a path-only confirmation, without read-before-write state or content/provenance validation.
  - config/environment: qwen3.5:2b-256k model capacity/instruction adherence can increase malformed semantic plans, but no model setting can create a missing deterministic guard.
  - data: an existing target makes full-content write_file destructive when generated content is not derived from its current contents.
and_gate: yes — the observed wrong overwrite needs both a bad model-selected payload and an application path that accepts that payload; either a correct model sequence or a deterministic edit guard would prevent this incident.

## Symptoms

expected: After confirmation, the requested edit is applied to the existing file without replacing it with unrelated model-generated content.
actual: With qwen3.5:2b-256k, the agent called write_file before read_file, wrote 148 unrelated bytes to trash.md after confirmation, then called recall for a key never remembered and reported it could not edit the file. Separate read-only attempts sometimes used remember/recall, hallucinated contents, or performed an unnecessary write. Current trash.md content is unrelated prose.
errors: No Python exception; semantic/tool-selection failure and wrong overwrite.
reproduction: Test 4 in .planning/phases/03-file-tools/03-UAT.md, discovered during UAT. Do not rerun against trash.md or call the live model.
started: Discovered during Phase 03 UAT; evidence does not establish whether earlier versions behaved differently.

## Eliminated

- hypothesis: The parser or file tool transformed correct edit content into unrelated prose.
  evidence: parse_response preserves write_file payloads verbatim and write_file passes that exact string to Path.write_text; the isolated probe delivered `unrelated payload\n` unchanged to write_file.
  timestamp: 2026-07-28T14:27:21+07:00

- hypothesis: Scratchpad state corruption caused the overwrite.
  evidence: The overwrite dispatch completes before the later recall. Recall of an absent key correctly returns `memory not found`; it explains the model's failed recovery, not the preceding destructive write.
  timestamp: 2026-07-28T14:27:21+07:00

- hypothesis: Model size alone is the complete root cause and the application contract is adequate.
  evidence: With no live model involved, a deterministic mocked first-turn write for an existing-file edit task is accepted after path-only confirmation with zero reads. The project explicitly targets 2-4B models, so relying on perfect semantic planning from that class contradicts the product's stated operating envelope.
  timestamp: 2026-07-28T14:27:21+07:00

## Evidence

- timestamp: 2026-07-28T14:17:12+07:00
  checked: Phase 03 UAT and gap-closure plan.
  found: UAT records write_file before read_file, 148 unrelated bytes written after approval, then recall of a never-remembered key; Plan 03-04 addresses shell-vs-file tool priority but contains no read-before-write/edit-preservation contract.
  implication: The behavior crosses tool-selection and destructive-write safety boundaries; the earlier prompt closure did not cover semantic edit ordering.

- timestamp: 2026-07-28T14:17:12+07:00
  checked: src/olla/loop.py write_file dispatch.
  found: The loop splits path/content, refuses only a missing content line, asks `Write to <resolved path>?`, and immediately calls write_file on approval. It records no successful reads and performs no same-target, version, or provenance check.
  implication: Once the model emits a syntactically valid write_file payload, approval authorizes a blind full overwrite regardless of whether the target was read.

- timestamp: 2026-07-28T14:17:12+07:00
  checked: src/olla/tools/files.py and src/olla/parser.py.
  found: write_file uses Path.write_text, which replaces the complete file; the parser intentionally preserves model-supplied write content verbatim. Neither layer knows that the user requested an edit rather than arbitrary file creation/replacement.
  implication: The unrelated bytes were not invented by the file layer, but the application executes them as a whole-file replacement with no edit-specific precondition.

- timestamp: 2026-07-28T14:17:12+07:00
  checked: SYSTEM_PROMPT and prompt contract tests.
  found: The prompt documents five tool syntaxes and forbids shell for file I/O, but does not say that edits to existing files must read the same path first, must preserve all unrequested content, or must not use scratchpad memory as a substitute for file contents. Tests assert syntax/examples only.
  implication: Small models receive no explicit semantic workflow rule for safe edits, and the runtime does not compensate for that omission.

- timestamp: 2026-07-28T14:17:12+07:00
  checked: tests/test_loop.py file-tool coverage.
  found: The only read-then-write end-to-end test scripts a compliant model that reads /tmp/in.txt and writes /tmp/out.txt; write tests assert confirmation/dispatch, not that an existing write target was read first or that output preserves the read content.
  implication: Existing automated coverage proves tool wiring and path confirmation, not the UAT truth for editing an existing file.

- timestamp: 2026-07-28T14:17:12+07:00
  checked: Debug knowledge base and SBFL eligibility.
  found: No knowledge-base file exists. There is no failing automated regression test for G-03-4 and therefore no failing/passing per-test coverage spectrum suitable for SBFL.
  implication: Proceed with a focused deterministic probe rather than spectrum ranking.

- timestamp: 2026-07-28T14:27:21+07:00
  checked: Isolated run_loop probe with call_model, read_file, write_file, and Confirm.ask mocked; task was `read existing.md and replace hello with goodbye` and first response was a write_file payload containing unrelated text.
  found: The loop reported read_calls=0 and write_calls=1, dispatched write_file('existing.md', 'unrelated payload\n'), and prompted only `Write to <resolved existing.md>?`.
  implication: This directly confirms the runtime will authorize and execute the UAT's unsafe write-before-read sequence independently of model brand or size.

- timestamp: 2026-07-28T14:27:21+07:00
  checked: Relevant automated tests using the project virtual environment.
  found: 36 selected loop, prompt, parser, and file-tool tests passed, including direct write approval and scripted read-then-write. No test required that the write target equal a previously read target or that proposed content derive from the read observation.
  implication: The existing suite is green while the safety invariant is absent; G-03-4 is a contract/coverage gap rather than a Python execution failure.

- timestamp: 2026-07-28T14:27:21+07:00
  checked: Project requirements and Phase 03 threat model.
  found: Requirements deliberately choose full-file write_file over model-generated patches, and T-03-06 explicitly accepted overwrite-without-notice because the confirm prompt shows only the resolved path. The project simultaneously defines 2-4B models as its core target.
  implication: The incident realizes a known accepted design risk that becomes unacceptable under the new UAT truth; upgrading the model may reduce frequency but cannot close the application safety gap.

- timestamp: 2026-07-28T14:27:21+07:00
  checked: Current prompt examples after the 03-04 shell-priority changes.
  found: The write example is a standalone direct overwrite of notes.txt followed by `I updated...`; it is not a single read-observe-write transcript. Memory is also presented without a boundary saying it is not a source for file contents.
  implication: The prompt improvement redirects file I/O away from shell but still teaches/permits the exact premature write pattern and leaves file-vs-scratchpad roles ambiguous for weak models.

## Resolution

root_cause: "AND-gated failure: (1) qwen3.5:2b-256k produced a semantically invalid plan — premature write_file with hallucinated content and later misuse of recall — consistent with weak small-model instruction/tool adherence; and (2) the application treats model output as authoritative: SYSTEM_PROMPT lacks an explicit existing-file edit protocol and demonstrates standalone writing, while run_loop executes any syntactically valid full-file payload after confirming only the path, with no prior same-target read, snapshot/version, content preview, or provenance guard. Model size is an incident trigger/amplifier; the actionable data-loss root cause is the missing prompt/runtime edit contract."
fix: "Not applied. Suggested direction: teach one compact same-file read -> Observation -> write edit transcript; state that scratchpad is never a substitute for file contents; deterministically require a successful read of an existing resolved target before overwrite and reject stale snapshots; show create-vs-overwrite plus a locally computed diff/content preview at confirmation. For simple substitutions, consider a guarded exact-replace tool (old text must match) so correctness does not depend on a small model reproducing the entire file. Add model-independent regressions for premature same-target writes, stale reads, and exact preservation of unrequested content."
verification: "Diagnosis verified without Ollama or filesystem mutation: isolated mocked probe reproduced unsafe dispatch (0 reads, 1 write, path-only confirmation); 36 relevant existing tests passed, demonstrating the missing invariant is not currently covered. No fix was applied."
files_changed:
  - .planning/debug/file-edit-wrong-content.md
