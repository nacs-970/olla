# Phase 6: Lightweight Web Search & Fetch - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-09
**Phase:** 6-Lightweight Web Search & Fetch
**Areas discussed:** Confirmation tier for web tools, URL safety guardrails (fetch_url), fetch_url content extraction & truncation, search_web output format

---

## Confirmation tier for web tools

| Option | Description | Selected |
|--------|-------------|----------|
| Unconfirmed (recommended) | Dispatch straight to adapter like list_dir/grep_files — read-only, no local mutation risk. Matches INSPECT-03 precedent. | ✓ |
| Confirm-gated | Route through safety.check() first — user approves every web call. Safer, but adds a prompt per search/fetch. | |
| Confirm-gated only for fetch_url | search_web unconfirmed (fixed endpoint), fetch_url confirm-gated (arbitrary URL). | |

**User's choice:** Unconfirmed (recommended)
**Notes:** Locked as D-01. Same tier as list_dir/grep_files.

---

## URL safety guardrails (fetch_url)

| Option | Description | Selected |
|--------|-------------|----------|
| Block private/internal + non-http(s) (recommended) | Reject localhost, private IP ranges, metadata endpoint, non-http(s) schemes. | |
| Restrict to http(s) scheme only | Block file://, ftp://, etc. but allow any host including localhost/internal. | |
| No restrictions | Trust the model's URL as-is, same posture as other unconfirmed read-only tools. | ✓ |

**User's choice:** No restrictions
**Notes:** Claude flagged the SSRF exposure explicitly (cloud metadata endpoint `169.254.169.254`, localhost/internal services reachable via unconfirmed `fetch_url`) and asked for confirmation with a narrower "block metadata + localhost only" alternative. User reconfirmed "No restrictions, as chosen" — deliberate, not overlooked. Locked as D-02.

---

## fetch_url content extraction & truncation

| Option | Description | Selected |
|--------|-------------|----------|
| Plain tag-strip (recommended) | Strip all tags, collapse whitespace. Simple, stdlib html.parser, zero new deps. | |
| Boilerplate-aware extraction | Heuristic main-content detection, drop nav/header/footer/script/style. | ✓ |

**User's choice:** Boilerplate-aware extraction

Follow-up — strip scope:

| Option | Description | Selected |
|--------|-------------|----------|
| script/style/nav/header/footer only (recommended) | Drop non-content structural tags and executable code only. | ✓ |
| Aggressive: also drop aside/form/iframe/svg/noscript | Wider net, more content-loss risk. | |

**User's choice:** script/style/nav/header/footer only

Follow-up — truncation cutoff:

| Option | Description | Selected |
|--------|-------------|----------|
| Hard cutoff at 3000 (recommended) | Simple slice [:3000] + truncation note, matches Phase 5 D-11/D-12 precedent. | |
| Trim to last sentence boundary | Slice at <=3000 chars but back off to last '.'/'!'/'?' before the cutoff. | ✓ |

**User's choice:** Trim to last sentence boundary
**Notes:** Locked as D-03 (extraction scope) and D-04 (truncation).

---

## search_web output format

| Option | Description | Selected |
|--------|-------------|----------|
| stdlib html.parser (recommended) | Subclass HTMLParser, more robust to HTML quirks, shared approach with fetch_url. | ✓ |
| Targeted regex | Regex over DDG Lite's specific table/row structure — lighter but brittle. | |

**User's choice:** stdlib html.parser

Follow-up — card format:

| Option | Description | Selected |
|--------|-------------|----------|
| Numbered list, 3 lines each (recommended) | "N. title / url / summary" per result — easy for small models to scan. | ✓ |
| Single-line per result | More compact, harder to scan, summary gets squeezed. | |

**User's choice:** Numbered list, 3 lines each
**Notes:** Locked as D-05 (parsing approach) and D-06 (card format).

---

## Claude's Discretion

- Exact wording of the `fetch_url` truncation note.
- `httpx.Client` timeout value and retry/backoff policy for both tools.
- Internal helper structure for the `HTMLParser` subclass(es) — shared vs. separate between `search_web` and `fetch_url`.
- Exact tag name for untrusted wrapping of web observations (e.g. `<untrusted_web_content>`).

## Deferred Ideas

None — discussion stayed within phase scope. SSRF guardrails were considered and explicitly declined (see D-02), not deferred.
