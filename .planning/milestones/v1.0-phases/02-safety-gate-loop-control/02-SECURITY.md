---
phase: 02
slug: safety-gate-loop-control
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-14
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Model output `<args>` → `shlex.split()` → `safety.check(argv, yes)` | Untrusted model-generated argv crosses into the safety classifier; classifier output (ALLOW/CONFIRM/BLOCK) gates whether `run_shell` ever executes it. | argv (list[str]) |
| `safety.check()` decision → `loop.py` dispatch → `subprocess.run` | BLOCK/CONFIRM/ALLOW decision must be enforced correctly — BLOCK never reaches `run_shell`; CONFIRM+`--yes=True` skips human prompt only, never BLOCK. `subprocess.run(argv, shell=False, ...)` — no shell interpretation. | Decision dict, argv |
| stdin → `Confirm.ask()` | Confirm prompt reads stdin; non-interactive contexts (CI, piped, `&`-backgrounded) raise `EOFError` — must fail-closed (decline), not crash/hang. | user y/n |
| `--yes` flag → CONFIRM bypass | User-controlled override must bypass CONFIRM only, never BLOCK or change `check()`'s `kind`. | bool flag |
| model loop → repetition counter | `(tool, tuple(argv))` signature tracked across iterations; 3rd identical signature aborts before 3rd execution — distinct message from max-steps abort. | (tool, argv) signature |
| `bash/sh/zsh -c <string>` → `shlex.split(c_string)` → recursive `_blocklist_match` | The `-c` argument is itself untrusted model output, tokenized and recursively re-classified against the full blocklist (same pattern as `env`/`find -exec` unwrap). Guarded by `len(argv) > c_index + 1` to prevent IndexError on truncated `-c`. | c_string → argv |
| `olla` CLI startup → `import olla.cli` → `olla.loop` → `olla.safety` | Module import chain must succeed on declared minimum Python >=3.10. A 3.11-only typing symbol here is a total DoS independent of user input. | n/a (import-time) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Tampering / DoS | `safety._blocklist_match` + `loop.py` shell branch | mitigate | Pattern table covers destructive cmds (rm-on-root, dd/mkfs raw devices, fork-bomb, chmod/chown -R /, sudo/su/shutdown/reboot/poweroff/halt); `check()` called before any `run_shell`, BLOCK short-circuits via `continue`. Verified: `run_shell.call_count == 0` on BLOCK. | closed |
| T-02-02 | Tampering (confirm-fatigue) | `safety.ALLOWLIST` + `loop.py` CONFIRM branch | mitigate | ALLOWLIST limited to 13 read-only binaries, matched on `argv[0]` only — destructive subcommands always fall through to CONFIRM with `Confirm.ask` showing resolved argv. | closed |
| T-02-03 | DoS (non-interactive crash) | `loop.py` Confirm.ask wrapper | mitigate | `try/except EOFError` treats EOF as decline (fail-closed), appends "declined by user" observation, loop continues. Verified by dedicated EOFError test. | closed |
| T-02-04 | Spoofing (fabricated success) | `loop.py` CONFIRM-declined / BLOCK paths | mitigate | Both BLOCK and declined-CONFIRM append a truthful `Observation:` message so the model's next turn sees the real outcome, never fabricated success. | closed |
| T-02-SC | Tampering (dependency) | `pyproject.toml` `rich>=13` | accept | Legitimacy verified in 02-RESEARCH.md (official Textualize package, installed 15.0.0, no [ASSUMED]/[SUS] flags); version-constraint edit only, not a new install. | closed |
| T-02-05 | Information Disclosure | `loop.py` dry-run branch | accept | `--dry-run` reveals BLOCK/CONFIRM/ALLOW classification for the model's own next action — intended UX for a local single-user CLI, not a disclosure boundary. | closed |
| T-02-06 | Tampering (dry-run executes) | `loop.py` dry-run branch | mitigate | Dry-run branch structurally separate, `return`s before `run_shell`/`Confirm.ask` on every dispatch path. Verified: `run_shell.call_count == 0` and `Confirm.ask.call_count == 0` across all 6 dry-run scenarios. | closed |
| T-02-07 | DoS (runaway repeated calls) | `loop.py` repetition counter | mitigate | `(tool, tuple(argv))` signature tracked; 3rd consecutive identical signature aborts before 3rd `run_shell`. Verified: `run_shell.call_count == 2` on 3x-repeat test. | closed |
| T-02-08 | Repudiation (abort path ambiguity) | `loop.py` repetition vs max-steps messages | mitigate | Disjoint wording for the two abort messages; regression test asserts max-steps message fires for varied calls AND repetition message absent. | closed |
| T-02-03-01 | Elevation of Privilege | `safety.py` ALLOWLIST (`env`/`find` argv[0]-only) | mitigate | Removed `env`/`find` from ALLOWLIST; added `_unwrap_env`/`_unwrap_find_exec` + recursive `_blocklist_match` so `env sudo ...`, `env rm -rf /`, `find ... -exec sudo ...` → BLOCK. (CR-01) | closed |
| T-02-03-02 | Tampering | `safety.py` `_FORK_BOMB_TOKENS` | mitigate | Replaced exact-list equality with `_FORK_BOMB_RE` regex search over joined argv — catches spaced and unspaced fork-bomb spellings. (WR-02) | closed |
| T-02-03-03 | DoS (resource exhaustion) | `loop.py` repetition guard ordering | mitigate | `sig`/`repeat_count` computed and checked `>= 3` immediately after argv parse, before BLOCK/CONFIRM branches — model stuck on a BLOCKed/declined command aborts at 3x, not at max_steps. (WR-01) | closed |
| T-02-03-04 | Tampering (residual) | `_unwrap_env`/`_unwrap_find_exec` nesting | accept | Recursive `_blocklist_match` naturally handles nesting (e.g. `env env env rm -rf /`); pathological 10+ level nesting is theoretical recursion-depth DoS, not realistic for shlex-tokenized LLM output. | closed |
| T-02-03-SC | Tampering (dependency) | none | n/a | No pip installs in this plan; package legitimacy gate not applicable. | closed |
| T-02-04-01 | Elevation of Privilege | `safety._unwrap_env` | mitigate | `_ENV_FLAGS_WITH_ARG`-aware index walk: `env -u FOO sudo rm -rf /` → unwraps to `["sudo","rm","-rf","/"]` → hard-blocked-binary rule → BLOCK. | closed |
| T-02-04-02 | Elevation of Privilege | `safety._unwrap_find_exec` | mitigate | Multi-clause unwrap inspects every `-exec`/`-execdir`/`-ok`/`-okdir` clause, not just the first; outer `find` invocation still gated by rule (3) regardless of clause count. | closed |
| T-02-04-03 | DoS (usability, self-inflicted) | `safety._blocklist_match` rule (6), fork-bomb regex | mitigate | Anchored `_FORK_BOMB_RE.match()` (position 0 only) + explicit `bash/sh/zsh -c <arg>` check — fork-bomb pattern as a *data argument* to an allowlisted command no longer false-positives; direct/`-c`-wrapped invocations still BLOCK. | closed |
| T-02-04-04 | Tampering | `safety._blocklist_match` rule (7), chmod/chown | mitigate | Combined short-flag match (`-Rf`/`-fR`/etc.) closes bypass that let those resolve to CONFIRM instead of BLOCK for `chmod -Rf 777 /`. | closed |
| T-02-04-05 | Repudiation / Info Disclosure | `tools.shell.run_shell` argv signature | accept | Pure refactor (`args_raw: str` → `argv: list[str]`); `run_loop` already computed argv via `shlex.split` for the safety check before this change — no new trust boundary or parsing surface. | closed |
| T-02-04-06 | Elevation of Privilege (collision) | `safety._unwrap_env` flag-arg consumption | accept | Verified: `env -u sudo rm -rf /` — `-u` consumes `"sudo"` as its argument (discarded, not substituted); remaining wrapped argv `["rm","-rf","/"]` still independently hits rule (4) → BLOCK. | closed |
| T-02-04-SC | Tampering (dependency) | none | accept | Pure refactor of existing `safety.py`/`shell.py`/`loop.py` and tests; no new dependencies. | closed |
| T-02-05-01 | Elevation of Privilege | `safety._blocklist_match` rule (6b), `bash/sh/zsh -c` | mitigate | `shlex.split()` the `-c` argument and recursively `_blocklist_match` the result, inside a `len(argv) > c_index + 1` guard. `bash -c "sudo rm -rf /"` → BLOCK. (CR-01 round-2) | closed |
| T-02-05-02 | Tampering | `safety._blocklist_match` rule (6b), `shlex.split` failure | accept | `ValueError` on unbalanced quotes in `-c` string → `wrapped = []`, recursion skipped, falls through to existing CONFIRM/ALLOW for outer argv — same as pre-existing malformed-argv handling elsewhere; no crash, no new bypass. | closed |
| T-02-05-03 | Tampering | `safety._blocklist_match` rule (7), chmod/chown `--recursive` | mitigate | Added `a == "--recursive"` to rule (7)'s match set — `chmod --recursive 777 /` → BLOCK, matching `-R`/`-Rf` coverage. (CR-02) | closed |
| T-02-05-04 | Tampering | `safety._blocklist_match` rule (4), `rm -rf //`/`///` | mitigate | `_normalize_rm_target()` collapses `^/{2,}$` to `/` before the dangerous-targets membership check. (CR-03) | closed |
| T-02-05-05 | Elevation of Privilege (residual) | `safety._blocklist_match` rule (6b), shell-chained `-c` strings | accept | `bash -c "true; sudo rm -rf /"` → `shlex.split` yields `["true;", "sudo", ...]`; recursion checks `argv[0]="true;"` only, not `;`-delimited sub-commands → remains CONFIRM. Same bypass class as `env -S`. Flagged as known limitation. Superseded by **T-02-08-05** (final disposition). | closed |
| T-02-05-06 | DoS (crash) | `safety._blocklist_match` rule (6b), `argv[c_index+1]` indexing | mitigate | Restructured rule (6b) into a single outer `len(argv) > c_index + 1` guard wrapping both fork-bomb and shlex-recurse checks — `["bash","-c"]` (no command) now falls through to CONFIRM instead of raising `IndexError`. 2 new regression tests. | closed |
| T-02-05-SC | Tampering (dependency) | none | accept | `shlex` is stdlib, already used elsewhere; package legitimacy gate not applicable. | closed |
| T-02-06-01 | Tampering | `_blocklist_match` rule (6b), combined short-flags `bash -lc`/`sh -ic`/`zsh -xc` | mitigate | Replaced exact `"-c" in argv` membership with scan for any token starting with `-`, not `--`, containing `c`; recurses via existing shlex-split-and-blocklist path. (CR-01 round-3) | closed |
| T-02-06-02 | Tampering | `_blocklist_match` rule (7), `chmod -R 777 //` doubled-slash | mitigate | Applied `_normalize_slash_target` (renamed from `_normalize_rm_target`) to rule (7)'s `/` target check. (CR-02 round-3) | closed |
| T-02-06-03 | Tampering | `_is_dangerous_device_arg`, `dd of=//dev/sda` doubled-slash | mitigate | Leading-run-only slash collapse `re.sub(r"^/{2,}", "/", path)` before `/dev/*` fnmatch check. (CR-03 round-3) | closed |
| T-02-06-04 | Elevation of Privilege | `loop.py` dispatch under `--yes` for the above 3 vectors | mitigate | Once T-02-06-01/02/03 classify correctly as BLOCK, existing unchanged BLOCK-dispatch closes `--yes`-exploitable path. Verified end-to-end via `test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks`. No `loop.py` changes required. | closed |
| T-02-06-05 | Tampering (residual) | shell-chained `-c` strings | accept | Pre-existing residual from T-02-05-05, explicitly unchanged in round 3. Superseded by **T-02-08-05** (final disposition). | closed |
| T-02-06-06 | Tampering (residual) | `env -S "<cmd>"` single-string wrap | accept | `_unwrap_env` treats `-S`/`--split-string` as flag-with-argument rather than unwrapping its string value. Pre-existing residual, out of scope for round 3. Superseded by **T-02-08-05** (final disposition). | closed |
| T-02-06-SC | Tampering (dependency) | none | accept | stdlib `re`/`fnmatch`/`shlex` only; package legitimacy gate not applicable. | closed |
| T-02-07-01 | Tampering | `_blocklist_match` rule (7), `chmod -R /.`/`//.`/`/./` dot-segment forms | mitigate | Widened root-target check to `_normalize_slash_target(a) == "/" OR os.path.normpath(a).rstrip("/") == ""`. (round-4) | closed |
| T-02-07-02 | Elevation of Privilege | `loop.py` dispatch under `--yes` for `chmod/chown -R /.`-family | mitigate | Once T-02-07-01 classifies correctly, existing unchanged BLOCK-dispatch closes the `--yes`-exploitable path; no `loop.py` change needed per VERIFICATION.md. | closed |
| T-02-07-03 | Tampering (residual) | `rm -rf /.` (rule 4, `_normalize_slash_target`) | accept | Out of scope per VERIFICATION.md round-4 — `rm` has `--preserve-root` default in most distros (lower severity than chmod/chown, which have none). Rule (4) byte-for-byte unchanged; remains CONFIRM. Superseded by **T-02-08-04** (final disposition). | closed |
| T-02-07-04 | Tampering (residual) | shell-chained `-c` strings | accept | Pre-existing residual from round-3 (T-02-06-05), unchanged. Superseded by **T-02-08-05** (final disposition). | closed |
| T-02-07-05 | Tampering (residual) | `env -S "<cmd>"` single-string wrap | accept | Pre-existing residual from round-3 (T-02-06-06), unchanged. Superseded by **T-02-08-05** (final disposition). | closed |
| T-02-07-SC | Tampering (dependency) | none | accept | stdlib `os`/`re`/`fnmatch`/`shlex` only; package legitimacy gate not applicable. | closed |
| T-02-08-01 | DoS (import-time) | `safety.py` line 7 — `NotRequired` (PEP 655, Py>=3.11 only) | mitigate | Dropped `NotRequired`; `class Decision(TypedDict, total=False)` — available since Py3.8, no runtime behavior change. Restores `safety→loop→cli` import chain on declared >=3.10 floor. (CR-01 round-5) | closed |
| T-02-08-02 | Tampering (regression) | future reintroduction of 3.11+-only typing symbols | mitigate | New static-source regression test greps `safety.py` for `NotRequired`/`Required[` and fails on any Python version. Manual-verification note for `python3.10 -c "import olla.safety"` documented for CI/another dev machine. | closed |
| T-02-08-03 | Information Disclosure / Repudiation | `Decision(TypedDict, total=False)` vs `NotRequired` | accept | Project ships no type checker (pytest/pytest-mock/ruff only). `check()`'s 4 return paths all set `kind` unconditionally (verified by reading source) — weakening has zero practical effect. Re-tightening needs `typing_extensions`, violates minimal-dependency constraint. | closed |
| T-02-08-04 | Tampering (residual, final) | `rm -rf /.` vs `chmod/chown -R /.` asymmetry (WR-01) | accept | **Final disposition** of T-02-07-03 lineage. `chmod/chown -R /.`-family correctly BLOCK (T-02-07-01); `rm -rf /.` remains CONFIRM due to `rm`'s `--preserve-root` default. Documented asymmetry, unchanged across rounds 4-5. | closed |
| T-02-08-05 | Tampering (residual, final) | `env -S "<cmd>"` + shell-chained `-c` strings | accept | **Final disposition** of T-02-06-06/T-02-07-05 (`env -S`) and T-02-05-05/T-02-06-05/T-02-07-04 (chained `-c`) lineages. Both remain CONFIRM, not BLOCK. Documented known limitations, unchanged across rounds 3-5. | closed |
| T-02-08-SC | Tampering (dependency) | none | accept | stdlib `typing`/`inspect` only, both already available; `pyproject.toml` untouched. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party) · n/a (not applicable)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-02-SC | `rich>=13` package legitimacy independently verified (official Textualize, no [SUS]/[ASSUMED] flags) | gsd-secure-phase | 2026-06-14 |
| AR-02 | T-02-05 | `--dry-run` revealing own-action classification is intended UX for a local single-user CLI, not a disclosure boundary | gsd-secure-phase | 2026-06-14 |
| AR-03 | T-02-03-04 | Recursive `env`/`find` unwrap naturally handles nesting; 10+ level pathological nesting is theoretical, unrealistic for shlex-tokenized LLM output | gsd-secure-phase | 2026-06-14 |
| AR-04 | T-02-03-SC | No package installs in plan 02-03 | gsd-secure-phase | 2026-06-14 |
| AR-05 | T-02-04-05 | `run_shell` argv-signature refactor introduces no new trust boundary — argv already derived via `shlex.split` pre-change | gsd-secure-phase | 2026-06-14 |
| AR-06 | T-02-04-06 | `env -u sudo rm -rf /` flag-arg collision verified safe — absorbed token discarded, remaining argv classified independently | gsd-secure-phase | 2026-06-14 |
| AR-07 | T-02-04-SC | No new dependencies — pure refactor of existing modules/tests | gsd-secure-phase | 2026-06-14 |
| AR-08 | T-02-05-02 | `shlex.split` failure on malformed `-c` string falls through to existing CONFIRM/ALLOW path, no crash/no new bypass | gsd-secure-phase | 2026-06-14 |
| AR-09 | T-02-05-SC | `shlex` is stdlib, already in use | gsd-secure-phase | 2026-06-14 |
| AR-10 | T-02-06-SC | No new dependencies — stdlib `re`/`fnmatch`/`shlex` only | gsd-secure-phase | 2026-06-14 |
| AR-11 | T-02-07-SC | No new dependencies — stdlib `os`/`re`/`fnmatch`/`shlex` only | gsd-secure-phase | 2026-06-14 |
| AR-12 | T-02-08-03 | `TypedDict(total=False)` vs `NotRequired` is a type-checker-only distinction; project has no type checker and `check()` always sets `kind` | gsd-secure-phase | 2026-06-14 |
| AR-13 | T-02-08-04 | **Known limitation (final):** `rm -rf /.` classifies CONFIRM not BLOCK — `rm`'s `--preserve-root` default mitigates real-world impact; `chmod/chown -R /.` (no such default) correctly BLOCK | gsd-secure-phase | 2026-06-14 |
| AR-14 | T-02-08-05 | **Known limitation (final):** `env -S "<cmd>"` and shell-chained `-c` strings (e.g. `bash -c "true; sudo rm -rf /"`) classify CONFIRM not BLOCK — recursion checks only the first shlex token of the wrapped/`-c` string, not `;`/`&&`/`|`-delimited sub-commands. Residual across rounds 3-5, explicitly out of scope. | gsd-secure-phase | 2026-06-14 |
| AR-15 | T-02-08-SC | No new dependencies — stdlib `typing`/`inspect` only | gsd-secure-phase | 2026-06-14 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-14 | 47 | 47 | 0 | gsd-secure-phase (plan-time register; all 8 plans authored `<threat_model>` blocks — short-circuit per workflow Step 3) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-14
