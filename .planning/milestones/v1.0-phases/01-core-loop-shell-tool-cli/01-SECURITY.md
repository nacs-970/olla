---
phase: 01
slug: core-loop-shell-tool-cli
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-11
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Model output -> parser | Local Ollama model's text response is untrusted-ish: may contain malformed tags or adversarial-looking strings | Free-text model output |
| Parser -> shell tool | `parsed["args_raw"]` (model-chosen string) flows into `run_shell()` and becomes argv via `shlex.split()` | Shell command string |
| Shell tool -> OS process | `subprocess.run(argv, ...)` executes a real process with the user's privileges | argv list |
| pip install -> developer machine | `pyproject.toml` declares 5 third-party packages installed via `pip install -e ".[dev]"` | Package artifacts |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Tampering / Elevation of Privilege | `src/olla/tools/shell.py:run_shell` | mitigate | `shlex.split(args_raw)` (line 16) + `subprocess.run(argv, shell=False, ...)` (line 22) — shell metacharacters become literal argv tokens, no shell interpretation | closed |
| T-01-02 | Denial of Service | `src/olla/tools/shell.py:run_shell` | mitigate | `subprocess.run(..., timeout=30)` (line 22) caught via `subprocess.TimeoutExpired` (line 31-32), returns structured error instead of hanging | closed |
| T-01-03 | Denial of Service | `src/olla/loop.py:run_loop` | mitigate | `--max-steps` (default 15) hard-caps loop iterations (line 35); prints `"Reached max steps (N) without a <final> answer."` (line 73) on exhaustion | closed |
| T-01-04 | Information Disclosure | `src/olla/loop.py` message history | accept | Untruncated model response + shell output visible only to user's own terminal — single-user local tooling, no remote/multi-tenant exposure in Phase 1 | closed |
| T-01-SC | Tampering (Supply Chain) | `pyproject.toml` dependencies | mitigate | `checkpoint:human-verify` (Task 2, gate="blocking-human") — developer spot-checked `ollama`, `click`, `pytest`, `pytest-mock`, `ruff` on PyPI (no typosquats), approved before `pip install -e ".[dev]"`. Declared deps in `pyproject.toml` match the approved set exactly | closed |
| T-01-05 | Tampering / Elevation of Privilege | model-chosen shell commands (no allowlist/blocklist/confirm) | accept (scheduled) | Phase 1 shell tool intentionally has only shlex+`shell=False`+timeout+max-steps. Blocklist (SAFE-02), confirm-before-execute (SAFE-01), `--dry-run` enforcement (SAFE-04) deferred to Phase 2 per ROADMAP. `--dry-run`/`--yes` exist as no-op CLI stubs only | closed |
| T-01-06 | Tampering / Elevation of Privilege / DoS | `src/olla/smoke.py:run_smoke_test` -> `call_model` -> `ollama.chat` | mitigate | Inherits T-01-01/02/03 — verified `smoke.py` performs no `subprocess`/`run_shell`/`shlex` calls; sends only static `FIXED_PROMPTS` through the existing mitigated path, no new attack surface | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-04 | T-01-04 | Single-user local CLI; full message history (incl. shell output) visible only in the user's own terminal — no remote/multi-tenant exposure at this phase | Plan 01-01 threat model | 2026-06-11 |
| AR-01-05 | T-01-05 | No command allowlist/blocklist/confirm-gate yet (intentional walking-skeleton scope); SAFE-01/02/04 scheduled for Phase 2 (next phase), not deferred indefinitely | Plan 01-01 threat model | 2026-06-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-11 | 7 | 7 | 0 | gsd-secure-phase (short-circuit: register_authored_at_plan_time, threats_open=0, no auditor spawn needed) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-11
