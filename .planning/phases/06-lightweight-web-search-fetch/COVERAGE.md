# API Coverage — DuckDuckGo Lite / arbitrary webpage fetch

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

**No external API/SDK integration this phase.** The detector's textual match (`SCOPE` contains
"integrate"/"connect"-shaped verbs paired with "API"-shaped nouns, e.g. httpx being wired into
tool adapters) is a false positive against olla's own prior "API Connect with olla" phase-name
text and this phase's own use of the word "integrated" to describe `httpx` reuse — there is no
formal API/SDK with an enumerable capability surface being onboarded here:

- `search_web(query)` consumes `lite.duckduckgo.com/lite/` as an unauthenticated HTML web page
  (scraped via `httpx.Client.get()` + stdlib `HTMLParser`), not a documented/versioned API with
  a capability list (no API key, no SDK, no OpenAPI/GraphQL/gRPC contract, no webhook, no OAuth).
- `fetch_url(url)` targets an arbitrary, model-chosen URL — by definition there is no fixed
  "service" whose capability surface could be enumerated; it is a generic HTTP GET + text
  extraction, the same shape as the existing `read_file` tool but over HTTP instead of the
  filesystem.
- `httpx` itself is not new this phase (already a direct dependency, already used in
  `src/olla/providers/openai_compat.py`) — this phase reuses the existing HTTP client library,
  it does not integrate a new external service SDK.

No coverage matrix is produced because there is no enumerable capability list to opt in/out of —
"search" and "fetch" are the entirety of what an unauthenticated HTML scrape can offer, and both
are fully in scope (WEB-01, WEB-02).
