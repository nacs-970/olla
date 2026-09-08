# Phase 6: Lightweight Web Search & Fetch - Research

**Researched:** 2026-09-09
**Domain:** Zero-dependency HTML scraping (DuckDuckGo Lite search + arbitrary webpage fetch) via stdlib `html.parser` and the existing `httpx` dependency, integrated into olla's unconfirmed-dispatch ReAct tool loop.
**Confidence:** HIGH — the two riskiest technical unknowns (DDG Lite's real HTML shape and its bot-detection behavior) were verified this session with live `curl`/Python probes against the real service, not assumed from training data or secondhand research.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (Confirmation dispatch):** `search_web`/`fetch_url` bypass `safety.check()` entirely and dispatch unconfirmed, same tier as `list_dir`/`grep_files` — `run_loop()` routes straight to their tool adapters. No new tool-name branch added to `src/olla/safety.py`. — **Reversibility:** costly — if a future requirement needs central ALLOW/CONFIRM/BLOCK policy over web tools, this needs `safety.check()` to grow a tool-name-aware signature and every call site revisited (same shape as Phase 5's D-09).
- **D-02 (URL safety):** `fetch_url` applies no host or scheme restrictions — no SSRF guardrails (no blocking of localhost, private IP ranges, or the cloud metadata endpoint `169.254.169.254`), no scheme allowlist. Same trust posture as other unconfirmed tools. — **Reversibility:** reversible — a validation layer can be added later without breaking the tool's public contract. — **User confirmed deliberately** after the SSRF exposure was explicitly flagged (unconfirmed dispatch + arbitrary model-chosen URL could reach internal/metadata endpoints).
- **D-03 (extraction scope):** Boilerplate-aware extraction using stdlib `html.parser` (`HTMLParser` subclass) — always drop `script`, `style`, `nav`, `header`, `footer` tags before extracting text. No aggressive stripping of `aside`/`form`/`iframe`/`svg`/`noscript`.
- **D-04 (truncation):** Truncation at WEB-03's 3,000-char cap trims back to the last sentence boundary (`.`, `!`, `?`) at or under the limit, not a hard mid-word/mid-sentence slice. Append a truncation note when cut (matches Phase 5 D-11's cap-note convention).
- **D-05 (search parsing approach):** DuckDuckGo Lite results parsed via stdlib `html.parser`, not regex — consistent parsing approach with `fetch_url`'s extraction (D-03), more robust to markup than targeted regex.
- **D-06 (search card format):** Snippet cards shown to the model as a numbered list, 3 lines each: `N. <title>` / `   <url>` / `   <summary>` — matches `list_dir`/`grep_files`' plain-text convention, easy for small models to reference by number.

### Claude's Discretion

- Exact wording of the truncation note for `fetch_url` (analogous to Phase 5's `(+N more, not shown)`).
- `httpx.Client` timeout value and retry/backoff policy for both tools (follow `src/olla/providers/openai_compat.py`'s existing `httpx.Client(timeout=...)` pattern; no user preference expressed).
- Internal helper structure for the `HTMLParser` subclass(es) — shared base between `search_web` and `fetch_url` parsing vs. separate implementations.
- Exact tag name for untrusted wrapping of web observations (e.g. `<untrusted_web_content>`), following the `<untrusted_file_content>`/`<untrusted_shell_output>`/`<untrusted_memory_content>` naming precedent in `src/olla/loop.py`.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. SSRF guardrails were considered and explicitly declined (see D-02), not deferred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEB-01 | `search_web(query)` queries DuckDuckGo Lite via curl/httpx, returning top 3-5 snippet cards with titles and links, no extra pip deps | Verified live HTML shape of `lite.duckduckgo.com/lite/` (see "DuckDuckGo Lite HTML Contract" below); verified `httpx` is already a direct dependency (`pyproject.toml:16`) so "no extra pip deps" is satisfied by using `httpx` instead of shelling to `curl`; verified the exact User-Agent requirement to get real results instead of a bot-challenge page |
| WEB-02 | `fetch_url(url)` fetches a webpage via curl/httpx, extracts readable text, strips HTML markup | `HTMLParser` subclass pattern verified against Python 3.14.7 stdlib (depth-counter for dropped tags, CDATA raw-text handling for `script`/`style`, `&nbsp;`→`\xa0` entity decoding) with a runnable probe pasted below |
| WEB-03 | Hard output truncation ≤3,000 chars for web tool observations before appending to conversation | `truncate_output()` (`loop.py:452-462`) is a *different* algorithm (head+tail at 2000 chars) than D-04's sentence-boundary trim at 3000 — Pitfall 1 below documents why these must not be composed |
| WEB-04 | Web tool observations tag state untrusted, revoking `--yes` auto-bypass on subsequent destructive actions | `_record_file_observation`/`_record_shell_observation`/`_record_memory_observation` (`loop.py:404-449`) and the `untrusted_observation_seen` flag threading (`loop.py:973`, `1027-1076`) are the exact precedent to extend with a new `_record_web_observation` |
</phase_requirements>

## Summary

This phase adds two read-only, unconfirmed-dispatch tools — `search_web(query)` and `fetch_url(url)` — that both talk HTTP via the already-declared `httpx` dependency (`pyproject.toml:16`, `httpx>=0.27.0`) and parse HTML via the stdlib `html.parser.HTMLParser`, with zero new pip dependencies. No package legitimacy audit action is needed since nothing new is installed.

The two hardest technical questions in this phase were **not** answerable from training data alone and were verified live this session: (1) what DuckDuckGo Lite's actual result HTML looks like, and (2) whether it can be queried without a browser-grade `User-Agent`. Both were tested directly: a plain `curl` with no `User-Agent` (and, separately, a default `httpx`-style UA string) returns an anti-bot "select all squares containing a duck" CAPTCHA challenge page instead of results; a `curl` with a standard browser UA string (`Mozilla/5.0 ...`) returns real results via a simple GET to `https://lite.duckduckgo.com/lite/?q=<query>`. This is the single most important, easy-to-miss implementation detail in this phase — a naive `httpx.get(url, params={"q": query})` with no header override will silently return a CAPTCHA page that a "boilerplate-aware" extractor happily renders as if it were search results, with no exception raised.

The second-hardest detail is that DDG Lite's organic result links are **not** direct URLs — the anchor's `href` is a DuckDuckGo redirect (`//duckduckgo.com/l/?uddg=<url-encoded-target>&rut=<hash>`), and the real destination must be extracted from the `uddg` query parameter and URL-decoded. This was verified by writing and running a real `HTMLParser` subclass against a saved copy of the live page (output pasted below) — it also confirms `HTMLParser` decodes `&amp;` → `&` in attribute values *before* your `handle_starttag` sees them, so `urllib.parse.parse_qs` works correctly on the raw `href` attribute without any pre-processing.

The third detail, distinct from D-02's already-declined SSRF posture, is a **resource-safety** concern specific to this project's documented hardware constraint (`STATE.md:102` records a 7.2GB model OOM-killed on this host's 7.1GB RAM): `fetch_url` targets an arbitrary model-chosen URL with no size limit, and `httpx` will buffer the entire response body into memory before your code sees any of it unless you explicitly stream and cap it. This is not SSRF (D-02 is about *destination*, this is about *response size*) and is not covered by any CONTEXT.md decision — flagged as an Open Question for the planner below.

**Primary recommendation:** Add `src/olla/tools/web.py` with `search_web(query)` and `fetch_url(url)`, both built on a short-lived `httpx.Client(timeout=..., follow_redirects=True)` with an explicit browser-style `User-Agent` header, parsed via two `HTMLParser` subclasses (one for DDG Lite result triples, one for boilerplate-stripped plain text), truncated by a *new* sentence-boundary helper (not `truncate_output()`), and wired into `loop.py` following the exact `list_dir`/`grep_files` unconfirmed-dispatch shape plus a new `_record_web_observation` for WEB-04.

## Architectural Responsibility Map

> olla is a single-process CLI, not a multi-tier web app — the generic Browser/SSR/API/CDN/DB tiers from the template don't apply literally. Mapped instead to olla's own layered architecture (`.planning/codebase/ARCHITECTURE.md`), which is what the planner and plan-checker actually need for tier-correctness sanity-checking in this codebase.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP fetch (DDG Lite query, arbitrary URL fetch) | Tool Adapter (`src/olla/tools/web.py`, new) | — | Matches `src/olla/tools/files.py`/`shell.py`/`inspect.py`: adapters own external I/O and catch expected exceptions, returning `ToolResult`-shaped dicts rather than raising |
| HTML parsing / boilerplate stripping / DDG result extraction | Tool Adapter (`src/olla/tools/web.py`, new) | — | Pure parsing logic stays with the I/O it parses, same as `grep_files`' regex living in `tools/inspect.py` rather than `loop.py` |
| Truncation to ≤3,000 chars, sentence-boundary trim (D-04) | Tool Adapter (`src/olla/tools/web.py`, new) | — | Must happen *before* `loop.py` sees the string, because `loop.py`'s only truncation helper (`truncate_output()`) implements a different, incompatible algorithm (see Pitfall 1) |
| Unconfirmed dispatch, repetition guard, message-history append | Orchestration (`src/olla/loop.py`) | — | Owns all dispatch/confirmation/observation-formatting per `ARCHITECTURE.md:350-362` ("Bypassing the Policy Boundary" — the same separation applies here, just without a `safety.check()` call per D-01) |
| Untrusted-state tagging (WEB-04) | Orchestration (`src/olla/loop.py`) | — | `untrusted_observation_seen` is loop-scoped state (`loop.py:973`); a new `_record_web_observation` extends the existing `<untrusted_X_content>` wrapping precedent (`loop.py:404-449`) |
| Tool-call contract documentation | Prompt (`src/olla/prompts.py`) | — | `SYSTEM_PROMPT` is the only place the model learns the `<tool>search_web</tool>`/`<tool>fetch_url</tool>` argument shapes; must also update the `"7 tools available"` roster line (see Pitfall 2) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | >=0.27.0 (already a direct dependency) `[VERIFIED: pyproject.toml:16]` | Issue the DDG Lite GET/POST and the arbitrary `fetch_url` GET | Already used elsewhere in the codebase (`src/olla/providers/openai_compat.py:89`, `156`) with the exact `httpx.Client(timeout=...)` context-manager pattern this phase should reuse. Satisfies WEB-01's "without extra pip dependencies" by not shelling out to `curl` and not adding `requests`. |
| `html.parser.HTMLParser` (stdlib) | Python >=3.10 floor (`pyproject.toml:8`) | Subclass to (a) extract DDG Lite result triples, (b) strip boilerplate tags and collect visible text | `[VERIFIED]` — ran a real `HTMLParser` subclass against the live-fetched DDG Lite page this session (script + output below); confirmed nested-tag depth-counter behavior, `CDATA_CONTENT_ELEMENTS = ('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes')` (`[VERIFIED]` via `python3 -c "from html.parser import HTMLParser; print(HTMLParser.CDATA_CONTENT_ELEMENTS)"`, Python 3.14.7), and `&nbsp;`→`\xa0` decoding, all directly relevant to D-03/D-05. |
| `urllib.parse` (stdlib) | bundled | Extract and decode the real target URL from DDG Lite's `//duckduckgo.com/l/?uddg=...` redirect wrapper | `[VERIFIED]` — `parse_qs(urlsplit(href).query)["uddg"][0]` correctly recovered the real URL from every result row of the live-fetched page (see pasted script output below). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (stdlib) `re` | bundled | Optional post-parse whitespace normalization (`\s{2,}` → single space, `\n{3,}` → `\n\n`) after `HTMLParser` collection | Only for whitespace collapsing after extraction — D-05 already locks `html.parser` (not regex) for the *structural* parsing itself; regex here is text cleanup, not markup parsing, so it does not conflict with D-05. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx.Client` | Shelling out to `curl` via `subprocess` (as WEB-01/WEB-02's literal wording suggests) | Already-declared `httpx` dependency is simpler, has no `PATH`-dependent external binary requirement, and matches the existing HTTP call pattern in `providers/openai_compat.py`. `curl` subprocess would also need `shlex`/argv-safety review for the URL argument. Not recommended. |
| stdlib `html.parser` | `BeautifulSoup`/`lxml` | Explicitly out of scope — WEB-01 requires "without extra pip dependencies" and CLAUDE.md's Stack doc lists these as things NOT to add. D-03/D-05 already lock `html.parser`. |

**Installation:** None — no new dependencies. `httpx>=0.27.0` is already declared (`pyproject.toml:16`); `html.parser`/`urllib.parse`/`re` are stdlib.

## Package Legitimacy Audit

No external packages are installed in this phase. `httpx>=0.27.0` (`[VERIFIED: pyproject.toml:16]`) is an existing, already-audited direct dependency; `html.parser` and `urllib.parse` are Python stdlib. The Package Legitimacy Gate protocol does not apply — no `npm view`/`pip index versions`/registry check is needed because nothing new reaches the registry.

**Packages removed due to [SLOP] verdict:** none (n/a — no packages installed)
**Packages flagged as suspicious [SUS]:** none (n/a — no packages installed)

## Architecture Patterns

### System Architecture Diagram

```
Model turn (XML tags)
   |
   v
_prepare_action()  --parses <tool>search_web</tool> or <tool>fetch_url</tool>--> _Action(kind="search_web"/"fetch_url", ...)
   |
   v
run_loop() dispatch  (NEW: elif action.kind == "search_web": ... / elif action.kind == "fetch_url": ...)
   |                          (no safety.check() call -- D-01, same as list_dir/grep_files)
   v
_execute_search_web() / _execute_fetch_url()   [loop.py, new]
   |
   v
tools/web.py: search_web(query) / fetch_url(url)      [new module]
   |
   +--> httpx.Client(timeout=..., follow_redirects=True)
   |         headers={"User-Agent": "<browser-like UA>"}   <-- REQUIRED for DDG Lite (verified)
   |         .get("https://lite.duckduckgo.com/lite/", params={"q": query})   [search_web]
   |         .get(url)                                                        [fetch_url]
   |
   +--> HTML response body
   |         |
   |         v
   |   HTMLParser subclass
   |     search_web: skip <tr class="result-sponsored">, extract a.result-link (href+text)
   |                 + td.result-snippet text; decode uddg= from href via urllib.parse
   |     fetch_url:  drop script/style/nav/header/footer subtrees (depth counter),
   |                 collect visible text from everything else
   |         |
   |         v
   |   sentence-boundary truncate to <=3000 chars (D-04)  [NEW helper, NOT loop.truncate_output()]
   |
   v
ToolResult {"content": <formatted text>} or {"error": ...}
   |
   v
_execute_search_web()/_execute_fetch_url() in loop.py
   |
   v
_record_web_observation(messages, content)   [NEW, wraps in <untrusted_web_content>...</untrusted_web_content>]
   |
   v
untrusted_observation_seen = True   --> forces re-confirmation on next CONFIRM-tier shell/write_file
   |                                     action even under --yes (WEB-04, same mechanism as
   |                                     _record_file_observation/_record_shell_observation)
   v
messages.append({"role": "tool", "content": "Observation: <untrusted_web_content>...\n"})
   |
   v
Next model turn sees the Observation and continues the ReAct loop
```

### Recommended Project Structure
```
src/olla/
├── tools/
│   ├── web.py          # NEW: search_web(query), fetch_url(url), HTMLParser subclasses, truncation helper
│   ├── inspect.py       # existing precedent (list_dir/grep_files) for adapter shape
│   ├── base.py          # ToolResult contract -- reuse directly
│   └── ...
├── loop.py              # add _Action fields, _prepare_action branches, _preview_action branches,
│                        # _execute_search_web/_execute_fetch_url, _record_web_observation,
│                        # run_loop() dispatch branches
└── prompts.py           # document search_web/fetch_url contract; update "N tools available" roster line

tests/
└── test_tools/
    └── test_web.py      # NEW: unit tests for search_web/fetch_url, HTMLParser subclasses, truncation
                          # (mirrors tests/test_tools/test_inspect.py's structure)
```

### Pattern 1: Short-lived `httpx.Client` per call, matching the existing provider pattern
**What:** Open a `with httpx.Client(...) as client:` block for the single request, not a module-level persistent client.
**When to use:** Both `search_web` and `fetch_url` — each is a one-shot synchronous call inside a single tool invocation, exactly like `OpenAICompatProvider.get_context_length()`.
**Example:**
```python
# Source: existing project pattern, src/olla/providers/openai_compat.py:88-104 (read this session)
try:
    with httpx.Client(timeout=5.0) as client:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = client.get(f"{self.base_url}/models", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            ...
except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
    ...
```

### Pattern 2: DuckDuckGo Lite query — verified request shape
**What:** A GET to `https://lite.duckduckgo.com/lite/?q=<query>` with a browser-style `User-Agent` header returns real results. No UA, or an `httpx`-default-style UA, returns an anti-bot CAPTCHA page instead — silently, with HTTP 200, no exception.
**Verified this session:**
```
$ curl -s -A "Mozilla/5.0" "https://lite.duckduckgo.com/lite/?q=python+html.parser" -o ddg.html
$ grep -o "result-link" ddg.html | head -1
result-link          # <- real results

$ curl -s "https://lite.duckduckgo.com/lite/?q=python+html.parser" -o ddg-noua.html   # no UA
$ grep -o "anomaly" ddg-noua.html
anomaly              # <- "Unfortunately, bots use DuckDuckGo too" CAPTCHA page

$ curl -s -A "python-httpx/0.27.2" "https://lite.duckduckgo.com/lite/?q=test+query" -o ddg-httpxua.html
$ grep -o "anomaly" ddg-httpxua.html
anomaly              # <- default httpx-style UA is ALSO challenged
```
**Recommended tool code:**
```python
# src/olla/tools/web.py (new)
import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

def search_web(query: str) -> ToolResult:
    try:
        with httpx.Client(timeout=..., follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get("https://lite.duckduckgo.com/lite/", params={"q": query})
    except (httpx.TimeoutException, httpx.TransportError) as error:
        return {"error": f"search_web request failed: {error}"}
    ...
```
**Confidence:** HIGH — `[VERIFIED]` via three live `curl` probes this session (with browser UA, no UA, default-httpx-style UA), reproduced above.

### Pattern 3: Extracting the real URL from DDG Lite's redirect wrapper
**What:** Organic result anchors point at `//duckduckgo.com/l/?uddg=<url-encoded-target>&rut=<hash>`, not the real URL directly. `HTMLParser` decodes the `&amp;` in the attribute value to `&` before your code sees it, so a plain `urllib.parse` call recovers the real URL with no extra un-escaping step.
**Verified this session** (ran against the live-fetched `lite.duckduckgo.com/lite/?q=python+html.parser` page):
```python
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs

class DDGParse(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.sponsored_depth = 0
        self.cur_href = None
        self.cur_title = []
        self.in_title_anchor = False
        self.in_snippet = False
        self.snippet_buf = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "tr" and "result-sponsored" in attrs_d.get("class", ""):
            self.sponsored_depth += 1
        if tag == "a" and attrs_d.get("class") == "result-link" and self.sponsored_depth == 0:
            self.in_title_anchor = True
            self.cur_href = attrs_d.get("href")
            self.cur_title = []
        if tag == "td" and attrs_d.get("class") == "result-snippet" and self.sponsored_depth == 0:
            self.in_snippet = True
            self.snippet_buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self.in_title_anchor:
            self.in_title_anchor = False
            self.results.append({"title": "".join(self.cur_title).strip(), "href": self.cur_href, "snippet": None})
        if tag == "td" and self.in_snippet:
            self.in_snippet = False
            if self.results:
                self.results[-1]["snippet"] = "".join(self.snippet_buf).strip()
        if tag == "tr" and self.sponsored_depth > 0:
            self.sponsored_depth -= 1

    def handle_data(self, data):
        if self.in_title_anchor:
            self.cur_title.append(data)
        if self.in_snippet:
            self.snippet_buf.append(data)

p = DDGParse()
p.feed(open("ddg.html", encoding="utf-8").read())
for r in p.results[:5]:
    real_url = parse_qs(urlsplit(r["href"]).query)["uddg"][0]
    print(r["title"], "->", real_url)
```
**Actual output produced this session (from the real live page):**
```
html.parser — Simple HTML and XHTML parser — Python 3.14.7 documentation -> https://docs.python.org/3/library/html.parser.html
How to parse HTML in Python: A step-by-step guide for beginners -> https://www.scrapingbee.com/blog/python-html-parsers/
html.parser — Simple HTML and XHTML parser in Python -> https://www.tutorialspoint.com/article/html-parser-simple-html-and-xhtml-parser-in-python
html — HyperText Markup Language support — Python 3.14.7 documentation -> https://docs.python.org/3/library/html.html
Parsing HTML using Python - Stack Overflow -> https://stackoverflow.com/questions/11709079/parsing-html-using-python
```
Note the two sponsored results (positions 1-2 in the raw HTML, "Python Online Courses..." and "100 Projects In 100 Days...", both inside `<tr class="result-sponsored">`) were correctly excluded — the discriminator is the `class="result-sponsored"` on the `<tr>`, **not** the anchor's `class='result-link'`, which is present on both sponsored and organic anchors. Filtering on the anchor class alone would ship ads to the model.
**Defensive note:** if `uddg` is ever absent from a result's `href` (markup change, edge case), fall back to the raw `href` rather than dropping the result — don't let a missing query param silently discard a result.
**Confidence:** HIGH — `[VERIFIED]`, ran against real, live-fetched HTML this session, output pasted above.

### Pattern 4: Nested-tag-safe boilerplate stripping for `fetch_url` (D-03)
**What:** A depth counter per dropped-tag-name (not a boolean flag) so `<nav><nav>...</nav>outer</nav>`-style nesting doesn't prematurely re-enable text collection on the inner `</nav>`.
**Verified this session:**
```python
from html.parser import HTMLParser

class P(HTMLParser):
    def handle_starttag(self, tag, attrs): print("START", tag)
    def handle_endtag(self, tag): print("END", tag)
    def handle_data(self, data): print("DATA", repr(data))

html = ('<div><script>var x = "</scr" + "ipt>";</script>'
        '<nav><nav>inner</nav>outer</nav><p>Hello&nbsp;World</p></div>')
P().feed(html)
```
**Actual output:**
```
START div
START script
DATA 'var x = "</scr" + "ipt>";'
END script
START nav
START nav
DATA 'inner'
END nav
DATA 'outer'
END nav
START p
DATA 'Hello\xa0World'
END p
END div
```
This confirms three things that matter for the implementation:
1. `script` content (even containing a string that looks like `</script>`) is delivered as one raw `handle_data` call with no spurious nested tag events — `html.parser` treats `script`/`style` as CDATA raw-text elements (`HTMLParser.CDATA_CONTENT_ELEMENTS`, `[VERIFIED]` via `python3 -c "from html.parser import HTMLParser; print(HTMLParser.CDATA_CONTENT_ELEMENTS)"` → `('script', 'style', 'xmp', 'iframe', 'noembed', 'noframes')`).
2. `<nav><nav>...` genuinely emits two `START nav`/`END nav` pairs — a boolean `in_nav` flag would flip back to `False` after the *inner* `</nav>`, leaking `outer` into the extracted text. A depth counter, incremented on start and decremented (clamped at 0) on end, is required.
3. `&nbsp;` decodes to `\xa0` (non-breaking space), not ASCII space — normalize this before whitespace-collapsing or double-spacing artifacts will appear in extracted text.
**Recommended implementation shape:**
```python
_DROP_TAGS = frozenset({"script", "style", "nav", "header", "footer"})

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._drop_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_TAGS:
            self._drop_depth += 1

    def handle_endtag(self, tag):
        if tag in _DROP_TAGS and self._drop_depth > 0:
            self._drop_depth -= 1

    def handle_data(self, data):
        if self._drop_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks).replace("\xa0", " ")
        return re.sub(r"[ \t]+", " ", raw).strip()
```
**Confidence:** HIGH — `[VERIFIED]`, both probes ran this session against real Python 3.14.7 stdlib (project floor is 3.10; `HTMLParser`'s CDATA/nesting/entity behavior used here has been stable since Python 3.5 per `[CITED: docs.python.org/3/library/html.parser.html]` deprecation of `convert_charrefs=False` and `HTMLParseError` removal — not independently re-verified on 3.10 specifically this session, low risk since this is long-stable stdlib behavior).

### Anti-Patterns to Avoid
- **Filtering DDG Lite results by anchor `class="result-link"` alone:** ships sponsored/ad results to the model — filter by the parent `<tr class="result-sponsored">` instead (Pattern 3).
- **Regex-parsing DDG Lite or arbitrary HTML:** explicitly locked against by D-05/D-03; also empirically fragile here — the live page uses single-quoted attributes (`class='result-snippet'`) inconsistently mixed with double-quoted ones, which `HTMLParser` normalizes transparently but a regex would have to special-case.
- **Reusing `loop.truncate_output()` for web tool output:** implements a different algorithm (head+tail at 2000 chars) than D-04's sentence-boundary trim at 3000 chars — see Pitfall 1.
- **Trusting `httpx`'s default `follow_redirects`:** `[VERIFIED]` via `inspect.signature(httpx.Client.__init__)` on the installed `httpx==0.28.1` (satisfies the declared `>=0.27.0` floor) that `follow_redirects` defaults to `False`. `fetch_url` needs `follow_redirects=True` explicitly or most real-world URLs (which redirect to `https://`, `www.`, or canonical paths) will return an unhelpful 301/302 body instead of the target page.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML tokenizing/parsing | A regex-based tag stripper | stdlib `HTMLParser` subclass (D-03/D-05 already lock this) | Regex-based HTML stripping breaks on nested tags, CDATA content (`script`/`style`), and attribute-quote-style inconsistency, all three of which are demonstrably present in the live DDG Lite page this session. |
| URL redirect-wrapper decoding | Manual string-splitting on `uddg=` | `urllib.parse.urlsplit()` + `parse_qs()` | Handles percent-decoding, multiple query params, and the protocol-relative `//` URL form correctly without edge-case string surgery. |
| HTTP retries/timeouts | Custom retry loop | `httpx.Client(timeout=httpx.Timeout(...))`, at most 0-1 manual retries | The existing `providers/openai_compat.py` already has a proven backoff pattern (`[1.0, 2.0, 4.0]` delays) for a *streaming* long-lived call; a single-shot `search_web`/`fetch_url` call should stay simpler — 0-1 retries is enough per this session's httpx-conventions research, since a CLI tool call should fail fast rather than hang the user's terminal. |

**Key insight:** Every "don't hand-roll" here is already decided by D-03/D-05 (stdlib parser, not regex) or already precedented in the codebase (`httpx.Client` pattern in `providers/openai_compat.py`) — this phase's actual risk is not "which library" but "get the DDG Lite request headers and result-row discrimination exactly right," which is why this research prioritized live verification over library selection.

## Common Pitfalls

### Pitfall 1: Composing `truncate_output()` with web-tool output silently defeats both WEB-03 and D-04
**What goes wrong:** If `_execute_search_web`/`_execute_fetch_url` in `loop.py` copies the exact shape of `_execute_list_dir` (`loop.py:839-859`) — `_record_file_observation(messages, truncate_output(raw_content))` — the tool's own sentence-boundary-trimmed, ≤3000-char output gets *re*-truncated by `truncate_output()`'s head+tail algorithm at its 2000-char default (`MAX_OBSERVATION_CHARS = 2000`, `loop.py:36`), producing a head+`[...truncated N chars...]`+tail shape with the trailing portion of the intended output ripped out of the middle.
**Why it happens:** `_execute_list_dir`/`_execute_grep_files`/`_execute_read_file` all call `truncate_output(raw_content)` before recording — copying that call site by pattern-matching without checking that `truncate_output`'s algorithm (head+tail at 2000) is incompatible with D-04's algorithm (sentence-boundary at 3000) is the most likely execution-time mistake.
**How to avoid:** Do the sentence-boundary trim to ≤3000 chars *inside* `tools/web.py`, and record the result directly via a new `_record_web_observation(messages, preview)` **without** wrapping it in `truncate_output()` first. State this explicitly as a plan constraint: "web tool observation recording does not call `truncate_output()`."
**Warning signs:** A test asserting `len(observation) <= 3000` passes, but a test asserting the *last sentence is complete* (D-04's actual requirement) fails, or the observation contains `[...truncated`.

### Pitfall 2: The system prompt's tool-count roster is a literal string asserted by an exact-match test
**What goes wrong:** `src/olla/prompts.py:5` says `"You have 7 tools available: \`read_file\`, \`write_file\`, \`shell\`, \`remember\`, \`recall\`, \`list_dir\`, \`grep_files\`."` — adding `search_web`/`fetch_url` without updating both the count and the backtick-quoted name set breaks `tests/test_prompts.py::test_system_prompt_advertises_tool_roster`.
**Why it happens:** The assertion is narrow and easy to overlook because it's phrased as a "contract test," not obviously tied to the new tools.
**How to avoid:** Update `SYSTEM_PROMPT`'s roster line to `"9 tools available"` and add `` `search_web` ``/`` `fetch_url` `` to the backtick set, and update the test in the same plan wave.
**Warning signs:** `[VERIFIED: tests/test_prompts.py:1-22]` — read this session, quoted verbatim:
```python
def test_system_prompt_advertises_tool_roster():
    tool_line = next(
        line for line in SYSTEM_PROMPT.splitlines() if "tools available" in line
    )

    assert "7 tools available" in tool_line
    assert set(re.findall(r"`([^`]+)`", tool_line)) == {
        "shell",
        "read_file",
        "write_file",
        "remember",
        "recall",
        "list_dir",
        "grep_files",
    }
```

### Pitfall 3: `_prepare_action`/`_preview_action` both need new branches, not just `run_loop()` dispatch
**What goes wrong:** CONTEXT.md's Integration Points section names `run_loop()` dispatch and `prompts.py` as the touch points, but `run_loop()` asserts `action.signature is not None` (`loop.py:1016`) right after `_prepare_action()` returns — so `_prepare_action` (`loop.py:218-349`) must gain `search_web`/`fetch_url` branches producing a well-formed `_Action` with a repetition-tracking `signature`, exactly like the existing `list_dir`/`grep_files` branches (`loop.py:292-332`). Separately, `_preview_action` (`loop.py:534-608`) is the `--dry-run` code path; missing a branch there means `--dry-run` prints `"Model would call unknown tool 'search_web'"` instead of a useful preview, even though the live-execution path works correctly.
**Why it happens:** CONTEXT.md's Integration Points list was written before this level of `loop.py` structural detail was traced; it names the two most visible touch points but not the two internal ones the codebase actually requires.
**How to avoid:** Plan tasks must explicitly cover: (1) new `_Action` fields if needed (likely just reusing `path`/`args_raw` shape for `fetch_url`'s single-arg case and a `query` conceptually-`args_raw`-shaped string for `search_web`), (2) `_prepare_action` branches, (3) `_preview_action` branches, (4) `run_loop()` dispatch branches, (5) new `_execute_search_web`/`_execute_fetch_url` functions, (6) new `_record_web_observation`.
**Warning signs:** `--dry-run` on a `search_web`/`fetch_url` call falls through to the `else: _display(f"Model would call unknown tool '{action.tool}'")` branch (`loop.py:607-608`).

### Pitfall 4: `httpx`'s default `follow_redirects=False` silently breaks `fetch_url` on most real URLs
**What goes wrong:** Many real-world URLs 301/302-redirect (bare domain → `www.`, `http://` → `https://`, trailing-slash canonicalization). Without `follow_redirects=True`, `fetch_url` returns the redirect response's (often near-empty) body instead of the target page's content, with no error — it looks like a successful fetch of useless content.
**Why it happens:** `requests` (the more commonly-known Python HTTP library) follows redirects by default; `httpx` deliberately does not, and this project's only existing `httpx` usage (`providers/openai_compat.py`) doesn't need redirects (it calls a fixed, non-redirecting API endpoint), so there's no in-repo precedent to copy correctly from.
**How to avoid:** Pass `follow_redirects=True` explicitly when constructing the `httpx.Client` for `fetch_url` (and `search_web`, for consistency/safety).
**Warning signs:** `[VERIFIED]` this session — `python3 -c "import httpx, inspect; print(inspect.signature(httpx.Client.__init__).parameters['follow_redirects'])"` on installed `httpx==0.28.1` (satisfies pyproject's `>=0.27.0`) prints `follow_redirects: 'bool' = False`.

### Pitfall 5: Unbounded response body buffering on a RAM-constrained host
**What goes wrong:** `fetch_url` targets an arbitrary, model-chosen URL with no size limit (D-02 declined *destination* restrictions, but response *size* was not discussed). A non-streaming `client.get(url)` call buffers the entire response body in memory before your code ever sees it, and there's no cap on how large that could be (a multi-hundred-MB file, an infinite stream, etc.).
**Why it happens:** This is a resource-safety gap, not a security-policy gap — it's outside D-02's scope (D-02 is about *where* the request goes; this is about *how much* comes back) and wasn't raised during discuss-phase.
**How to avoid:** Stream the response (`with client.stream("GET", url) as response:`) and cap total bytes read via `response.iter_bytes()`, aborting once a ceiling (e.g. a few MB) is reached, before ever decoding to text or feeding the `HTMLParser`. `[VERIFIED]` `httpx.Response.iter_bytes(chunk_size=None)` exists on installed `httpx==0.28.1` and is the mechanism for this.
**Warning signs:** Not directly testable without a live oversized endpoint; flagged here as a recommendation, not a locked decision — see Open Questions below. Motivated by `STATE.md`'s own recorded blocker: `[VERIFIED: .planning/STATE.md:102]` "`gemma4:e2b` (7.2GB) does not fit in this host's 7.1GB RAM (OOM-killed)" — the project's stated hardware ceiling is already this tight.

## Code Examples

### Recording a web observation as untrusted (WEB-04), following the exact existing precedent
```python
# Source: src/olla/loop.py:436-449 (read this session) -- _record_shell_observation,
# the direct precedent to copy for a new _record_web_observation:
def _record_shell_observation(messages: list[dict], preview: str) -> None:
    """Record command output as explicitly untrusted tool data."""
    debug_log("Shell observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_shell_output>\n"
                f"{preview}\n"
                "</untrusted_shell_output>"
            ),
        }
    )

# NEW, following the same shape (tag name is Claude's discretion per CONTEXT.md):
def _record_web_observation(messages: list[dict], preview: str) -> None:
    """Record web tool output as explicitly untrusted network data."""
    debug_log("Web observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_web_content>\n"
                f"{preview}\n"
                "</untrusted_web_content>"
            ),
        }
    )
```

### Gate-consequence test pattern to reuse for WEB-04 (verified precedent for Phase 5's equivalent)
```python
# Source: tests/test_loop.py:1560-1602 (read this session) --
# test_untrusted_file_instruction_cannot_use_yes_for_shell_or_write.
# The equivalent WEB-04 test should follow this exact shape: mock a search_web/fetch_url
# call returning attacker-controlled text, then assert a subsequent shell/write_file call
# still prompts for confirmation even with yes=True, and that Confirm.ask is called.
def test_untrusted_file_instruction_cannot_use_yes_for_shell_or_write(tmp_path, mocker):
    ...
    mocker.patch("olla.loop.check", return_value={"kind": "CONFIRM"})
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", side_effect=[False, False])
    ...
    run_loop("summarize the file", "model", 4, "sys", yes=True)
    ...
    assert mock_confirm.call_count == 2  # both actions after untrusted content required confirmation
```

### Recommended `httpx.Timeout` configuration (Claude's Discretion per CONTEXT.md)
```python
# [VERIFIED] via python3 -c "import httpx, inspect; print(inspect.signature(httpx.Timeout.__init__))"
# on installed httpx==0.28.1 (satisfies pyproject.toml's declared >=0.27.0):
import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
# Recommended over the single-float shorthand used in providers/openai_compat.py:89
# (httpx.Client(timeout=5.0)) because search_web/fetch_url hit unpredictable third-party
# hosts (vs. openai_compat.py's fixed, known-fast API endpoint) -- a slightly higher read
# timeout than connect timeout tolerates slow-to-respond arbitrary webpages without
# hanging indefinitely. Recommended retry policy: 0 retries (fail fast, return an error
# ToolResult) -- this is a synchronous CLI tool call, not a background job; a hung retry
# loop blocks the user's terminal. [ASSUMED: this specific retry-count recommendation is
# a synthesis of general httpx/CLI-UX practice, not sourced from an authoritative httpx
# doc read this session -- flagged in Assumptions Log.]
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `fetch_url` should also send the same browser-style `User-Agent` header as `search_web`, for general compatibility with arbitrary sites that block default HTTP-client UAs | Pattern 2 / Standard Stack | Low — this is a defensive recommendation, not a locked behavior; if wrong, `fetch_url` simply returns fewer usable results for UA-gated sites, no safety impact given D-02 already accepts a permissive trust posture |
| A2 | 0-1 retries with no backoff is the right retry policy for `search_web`/`fetch_url` (vs. `providers/openai_compat.py`'s 3-retry/exponential-backoff pattern for the model-call path) | Code Examples ("Recommended `httpx.Timeout` configuration") | Low-medium — if a flaky network warrants more retries, user experience degrades (a `search_web` call that could have succeeded on retry #2 instead returns an error), but nothing breaks; easy to change post-hoc since it's Claude's Discretion per CONTEXT.md, not a locked decision |
| A3 | A response-size cap (e.g. streaming with a byte ceiling) is needed for `fetch_url` given the project's documented RAM constraint | Pitfall 5 | Medium — if omitted, `fetch_url` on a very large or infinite response could exhaust memory on a host already documented to OOM-kill a 7.2GB model under 7.1GB RAM; not covered by any CONTEXT.md decision, so the planner should either adopt this recommendation or explicitly accept the risk (see Open Questions) |
| A4 | DuckDuckGo's Terms of Service / Acceptable Use Policy prohibit automated querying of `lite.duckduckgo.com` | (not stated as fact anywhere in this document — deliberately) | N/A — this claim was investigated and **not included** as a finding. A `WebFetch` of `duckduckgo.com/aup` returned no usable policy text (likely JS-rendered), so per the absent-evidence rule this is "no observation," not a verified or even assumed fact. Only the `robots.txt` finding below is stated, and stated precisely (see Open Questions). |

**Robots.txt finding (verified, not an assumption):** `duckduckgo.com/robots.txt` contains `Disallow: /lite` and `Disallow: /html` `[VERIFIED via curl this session]` — but this phase's requests target `lite.duckduckgo.com/lite/` (a *different host*), whose own `robots.txt` returns `Allow: /` `[VERIFIED via curl this session: "User-agent: *\nAllow: /\nSitemap: https://lite.duckduckgo.com/sitemap.xml"]`. Per RFC 9309, a robots.txt file governs only its own host — `duckduckgo.com`'s disallow rules for the path `/lite` do not apply to the separate `lite.duckduckgo.com` origin this phase actually queries. This is stated narrowly: robots.txt does not disallow crawling `lite.duckduckgo.com`; robots.txt says nothing about ToS/AUP terms, which govern conduct independently of robots.txt and were not independently verifiable this session (see A4).

**If this table were empty:** it is not — see A1-A3 above; A4 is documented as an explicit non-finding per the absent-evidence provenance rule, not a risk to act on.

## Open Questions (RESOLVED)

1. **Should `fetch_url` cap response size before decoding, given the project's documented RAM constraint?** (RESOLVED)
   - What we know: `httpx.Client.get()` buffers the full response body before returning; `httpx.Response.iter_bytes()` exists and can be used to stream with a byte ceiling instead (`[VERIFIED]` this session). `STATE.md:102` documents this host OOM-killing a 7.2GB model under 7.1GB RAM.
   - What's unclear: CONTEXT.md's discuss-phase covered SSRF (destination) but not response-size (volume); no user decision exists either way.
   - Recommendation: Planner should add a byte-ceiling stream-read (e.g., cap at a few MB, matching the spirit of WEB-03's "keep it small" intent) as a new task, or explicitly note it as an accepted risk in the plan if descoped — either way, this should be a conscious plan decision, not silently absent.
   - **Resolution:** Adopted the recommendation as a locked implementation constraint. `06-01-PLAN.md` Task 1 implements a shared `_read_capped(client, method, url, **kwargs)` helper in `src/olla/tools/web.py` — streams via `client.stream(...)` + `response.iter_bytes()`, stops accumulating once `_MAX_RESPONSE_BYTES` (5,000,000) is crossed, and is reused by both `fetch_url` (06-01 Task 1) and `search_web` (06-02 Task 1) so neither tool performs a plain buffering `client.get()`. Covered by `T-06-04` in both plans' `<threat_model>` and by `06-01-PLAN.md` Task 2's byte-cap streaming test.

2. **Does `search_web` need a fallback query strategy if DuckDuckGo Lite's anti-bot challenge triggers despite a correct User-Agent (e.g. due to IP-based rate limiting on repeated calls in a session)?** (RESOLVED)
   - What we know: A single request with a browser-style UA succeeded reliably in this session's testing (multiple separate queries all returned real results). DDG is known to rate-limit/CAPTCHA-challenge based on request volume and IP reputation in addition to UA, per this session's research digest (not independently verified — CAPTCHA-triggering by volume was not reproduced live, since only a handful of requests were made).
   - What's unclear: Whether a CAPTCHA-challenge response should surface to the model as a clear "search unavailable" error (recommended) vs. being silently mis-parsed as zero results.
   - Recommendation: `search_web`'s `HTMLParser` subclass should detect the absence of expected result markup (e.g., zero `result-link` anchors AND presence of `anomaly-modal` class) and return `{"error": "search_web: DuckDuckGo Lite returned a bot-challenge page instead of results"}` rather than a silently empty result list — this makes the failure mode legible to both the model and a human debugging it.
   - **Resolution:** Adopted the recommendation as-is. `06-02-PLAN.md` Task 1 implements the bot-challenge detector in `_DDGResultParser`/`search_web` (zero `result-link` anchors plus an anomaly-page markup check returns the exact error string quoted above; zero anchors with no anomaly markup returns a distinct "no results found" content instead). Covered by `T-06-05` in `06-02-PLAN.md`'s `<threat_model>` and by dedicated bot-challenge / genuine-zero-results tests in Task 1.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Network access to `lite.duckduckgo.com` | WEB-01 (`search_web`) | Yes `[VERIFIED: this session's dev sandbox]` | — | None — if network is unavailable at runtime, `search_web` should return a `ToolResult` error dict (`httpx.TransportError`/`httpx.TimeoutException` caught), same pattern as `run_shell`'s `FileNotFoundError` handling |
| Network access to arbitrary hosts | WEB-02 (`fetch_url`) | Cannot be verified in general (target is model-chosen and unbounded) | — | Same error-dict pattern as above |
| `httpx>=0.27.0` | Both tools | Yes `[VERIFIED: pyproject.toml:16, installed version 0.28.1]` | 0.28.1 in this dev sandbox | None needed — already a project dependency |
| stdlib `html.parser`, `urllib.parse` | Both tools | Yes (stdlib, any Python >=3.10) | bundled with Python 3.14.7 in this dev sandbox; project floor 3.10 | None needed |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — both tools already have a defined error-return path for network failure, matching the existing `run_shell`/`read_file` conventions.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8 `[VERIFIED: pyproject.toml:25]`, pytest-mock >=3.14 `[VERIFIED: pyproject.toml:26]` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `[VERIFIED: pyproject.toml:33-34]`: `testpaths = ["tests"]` (correcting `.planning/codebase/TESTING.md`'s 2026-07-25 claim of "no `[tool.pytest.ini_options]` section" — that section now exists in the current `pyproject.toml`, read this session) |
| Quick run command | `python -m pytest tests/test_tools/test_web.py` (new file) |
| Full suite command | `python -m pytest tests` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WEB-01 | `search_web` parses DDG Lite HTML into 3-5 title/url/snippet cards, skips sponsored rows, decodes `uddg` redirect URLs | unit | `pytest tests/test_tools/test_web.py -k search_web` | ❌ Wave 0 |
| WEB-01 | `search_web` sends the required browser-style `User-Agent` header | unit (mock `httpx.Client`, assert header on request) | `pytest tests/test_tools/test_web.py -k user_agent` | ❌ Wave 0 |
| WEB-02 | `fetch_url` strips `script`/`style`/`nav`/`header`/`footer`, keeps `aside`/`form`/`iframe`/`svg`/`noscript` content | unit | `pytest tests/test_tools/test_web.py -k fetch_url_extraction` | ❌ Wave 0 |
| WEB-03 | Both tools' output is ≤3,000 chars | unit | `pytest tests/test_tools/test_web.py -k truncat` | ❌ Wave 0 |
| WEB-03/D-04 | Truncated output ends at a sentence boundary, not mid-sentence | unit | `pytest tests/test_tools/test_web.py -k sentence_boundary` | ❌ Wave 0 |
| WEB-04 | `search_web`/`fetch_url` output is wrapped in an untrusted-content tag and sets `untrusted_observation_seen` | integration (`run_loop`, mocked `httpx`) | `pytest tests/test_loop.py -k untrusted_web` | ❌ Wave 0 |
| WEB-04 | Untrusted web observation revokes `--yes` for a subsequent shell/write_file call | integration (`run_loop`, follows `tests/test_loop.py:1560-1602` shape) | `pytest tests/test_loop.py -k web_cannot_use_yes` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_tools/test_web.py tests/test_loop.py -k web`
- **Per wave merge:** `python -m pytest tests`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tools/test_web.py` — new file, covers WEB-01/WEB-02/WEB-03. Per `.planning/codebase/TESTING.md`'s established "inline test data" convention (no `tests/fixtures/` directory exists), inline a trimmed 2-3-result DDG Lite HTML sample as a string constant in the test file rather than reading from a saved scratch file — this session's `ddg.html` was written to a temp scratchpad and will not persist for the executor.
- [ ] `tests/test_loop.py` — add `search_web`/`fetch_url` cases to the existing untrusted-observation test suite (`test_untrusted_file_instruction_cannot_use_yes_for_shell_or_write` at `tests/test_loop.py:1560` is the direct template).
- [ ] No new test framework/fixture/conftest needed — `mocker.patch("olla.loop.httpx.Client", ...)` or patching `olla.tools.web.httpx.Client` directly follows the existing `mocker.patch("olla.loop.run_shell")`/`mocker.patch("olla.loop.read_file")` pattern (`[VERIFIED: .planning/codebase/TESTING.md:105-122]` and cross-checked against `loop.py`'s actual import style this session).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | Model-supplied `query`/`url` strings are passed to `httpx` as-is; `urllib.parse` handles URL structure safely (no manual string concatenation into request URLs) |
| V12 (OWASP-adjacent) Server-Side Request Forgery | Yes — explicitly assessed and explicitly declined by the user | See row below |
| V6 Cryptography | No | No credentials, secrets, or cryptographic operations in this phase (DDG Lite/`fetch_url` are unauthenticated GETs) |
| V2 Authentication / V3 Session Management | No | No authentication involved in either tool |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation | Disposition this phase |
|---------|--------|---------------------|------------------------|
| SSRF via `fetch_url` reaching internal services / cloud metadata endpoint (`169.254.169.254`) | Information Disclosure / Spoofing | Host/scheme allowlist blocking localhost, private IP ranges (RFC 1918/link-local), and the metadata endpoint | **Explicitly declined per D-02** — user was shown this exact threat during discuss-phase (`06-DISCUSSION-LOG.md`: "Claude flagged the SSRF exposure explicitly... asked for confirmation with a narrower 'block metadata + localhost only' alternative. User reconfirmed 'No restrictions, as chosen'"). Recorded here for traceability, not re-litigated. |
| Redirect-following extends SSRF exposure to redirect targets | Information Disclosure | Validate the *final* redirect target, not just the initial URL | Not separately re-decided — `follow_redirects=True` is needed for `fetch_url` to be useful (Pitfall 4), and it extends the already-accepted D-02 exposure to wherever an initial URL redirects. Stated as a fact, not re-argued, since D-02 already accepts arbitrary-destination fetches. |
| Prompt injection via untrusted web content (search snippets or fetched page text instructing the model to take unintended actions) | Tampering / Elevation of Privilege | Explicit untrusted-content tagging + confirmation-gate revocation on subsequent destructive actions | **Directly addressed by WEB-04** — the exact mechanism proven for file/shell/memory content (`loop.py:404-449`, `973`) is being extended to web content in this phase. |
| Unbounded response size / resource exhaustion | Denial of Service (against the local host) | Streamed read with byte ceiling | **Not covered by a CONTEXT.md decision** — flagged as Pitfall 5 / Open Question 1 above, recommendation given, left to planner |

## Sources

### Primary (HIGH confidence — verified this session via direct tool execution)
- `curl` against `https://lite.duckduckgo.com/lite/?q=...` with three different User-Agent configurations (browser UA, no UA, `httpx`-default-style UA) — confirmed the exact request shape needed and the anti-bot challenge behavior when it's wrong.
- `curl` against `https://duckduckgo.com/robots.txt`, `https://lite.duckduckgo.com/robots.txt`, `https://html.duckduckgo.com/robots.txt` — confirmed per-host robots.txt scope.
- A real `HTMLParser` subclass run against the live-fetched DDG Lite page — confirmed `uddg` redirect-URL extraction, sponsored-row discrimination, and entity-decoding-before-parse behavior.
- A second `HTMLParser` probe against synthetic HTML containing nested `<nav>` and a `script` tag with a fake-closing-tag string — confirmed depth-counter necessity and CDATA raw-text handling.
- `python3 -c "from html.parser import HTMLParser; print(HTMLParser.CDATA_CONTENT_ELEMENTS)"` — confirmed the exact tag list.
- `python3 -c "import httpx, inspect; ..."` against installed `httpx==0.28.1` — confirmed `follow_redirects` default and `httpx.Timeout`/`httpx.Response.iter_bytes` signatures.
- `Read` of `src/olla/loop.py` (full file), `src/olla/tools/inspect.py`, `src/olla/tools/base.py`, `src/olla/providers/openai_compat.py`, `src/olla/safety.py`, `src/olla/prompts.py`, `src/olla/parser.py`, `pyproject.toml`, `tests/test_prompts.py:1-30`, `.planning/codebase/ARCHITECTURE.md:345-364`, `.planning/codebase/CONVENTIONS.md` (full) — all claims about existing code structure, naming, and test contracts in this document are sourced from these direct reads, not grep-only inspection.

### Secondary (MEDIUM confidence)
- `antigravity:delegate` (Gemini/agy) research digest on `html.parser` API details, DDG Lite bot-detection reputation, and `httpx` timeout conventions — cross-checked against this session's own live probes where the two overlapped (they agreed); the digest's `robots.txt`/ToS claim was independently re-verified and **corrected** (see Assumptions Log) rather than taken at face value.
- `[CITED: docs.python.org/3/library/html.parser.html]` — `convert_charrefs` default, `HTMLParseError` removal history (not independently re-run against every claimed Python version this session, but consistent with the live Python 3.14.7 behavior observed).

### Tertiary (LOW confidence)
- Agy's claim that DuckDuckGo's ToS/AUP explicitly prohibit automated querying — **not included as a finding** in this document; the underlying `WebFetch` of the AUP page returned no usable text this session, so this is treated as no observation, not a verified or assumed fact (see Assumptions Log A4).
- Agy's claim about rate-limiting behavior scaling with request volume/IP reputation beyond the UA effect — plausible and consistent with general anti-bot practice, but not independently reproduced (only a handful of requests were made this session); reflected as Open Question 2, not a locked finding.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, `httpx` version and API surface directly inspected against the installed package this session.
- Architecture: HIGH — every integration point (`_prepare_action`, `_preview_action`, `run_loop` dispatch, `_record_*_observation`, `untrrusted_observation_seen`) verified by reading `loop.py` in full, not summarized from memory.
- Pitfalls: HIGH for Pitfalls 1-4 (each verified via direct code read or live probe this session); MEDIUM for Pitfall 5 (recommendation, not a locked decision — flagged as Open Question).

**Research date:** 2026-09-09
**Valid until:** ~14 days for the DuckDuckGo Lite HTML shape/anti-bot behavior specifically (third-party services can change markup or bot-detection thresholds without notice — this is the fastest-moving part of this research); ~90 days for the stdlib `html.parser`/`httpx` API findings (stable, slow-moving).
