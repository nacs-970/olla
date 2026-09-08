"""Lightweight webpage fetch/extract tool (boilerplate stripping, byte-capped read)."""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import httpx

from olla.tools.base import ToolResult

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_MAX_RESPONSE_BYTES = 5_000_000
_DROP_TAGS = frozenset({"script", "style", "nav", "header", "footer"})
_NO_TEXT_PLACEHOLDER = "(no readable text extracted)"
_TRUNCATION_NOTE = "\n[...truncated, content continues beyond this point...]"

_DDG_URL = "https://lite.duckduckgo.com/lite/"
_DDG_BOT_CHALLENGE_MARKER = "anomaly-modal"
_DDG_NO_RESULTS_CONTENT = "no results found"
_DDG_BOT_CHALLENGE_ERROR = (
    "search_web: DuckDuckGo Lite returned a bot-challenge page instead of results"
)
_DDG_MAX_RESULTS = 5

_WHITESPACE_RE = re.compile(r"[ \t]+")


class _TextExtractor(HTMLParser):
    """Collect visible text while dropping script/style/nav/header/footer subtrees."""

    def __init__(self) -> None:
        super().__init__()
        self._drop_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_TAGS:
            self._drop_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS and self._drop_depth > 0:
            self._drop_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        joined = "".join(self._chunks).replace("\xa0", " ")
        return _WHITESPACE_RE.sub(" ", joined).strip()


def _truncate_to_sentence(text: str, limit: int = 3000) -> str:
    """Return `text` unchanged at/under `limit` chars; otherwise trim to a sentence."""
    if len(text) <= limit:
        return text

    window = text[:limit]
    cut = -1
    for punctuation in (".", "!", "?"):
        cut = max(cut, window.rfind(punctuation))
    if cut == -1:
        return window + _TRUNCATION_NOTE
    return window[: cut + 1] + _TRUNCATION_NOTE


class _DDGResultParser(HTMLParser):
    """Collect DuckDuckGo Lite organic result triples, skipping sponsored rows."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str | None]] = []
        self._sponsored_depth = 0
        self._in_title_anchor = False
        self._cur_href: str | None = None
        self._cur_title: list[str] = []
        self._in_snippet = False
        self._snippet_buf: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attrs_d = dict(attrs)
        css_class = attrs_d.get("class") or ""
        if tag == "tr" and "result-sponsored" in css_class:
            self._sponsored_depth += 1
            return
        if self._sponsored_depth > 0:
            return
        if tag == "a" and css_class == "result-link":
            self._in_title_anchor = True
            self._cur_href = attrs_d.get("href")
            self._cur_title = []
        elif tag == "td" and css_class == "result-snippet":
            self._in_snippet = True
            self._snippet_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title_anchor:
            self._in_title_anchor = False
            self.results.append(
                {
                    "title": "".join(self._cur_title).strip(),
                    "href": self._cur_href,
                    "snippet": None,
                }
            )
        elif tag == "td" and self._in_snippet:
            self._in_snippet = False
            if self.results:
                self.results[-1]["snippet"] = "".join(self._snippet_buf).strip()
        elif tag == "tr" and self._sponsored_depth > 0:
            self._sponsored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title_anchor:
            self._cur_title.append(data)
        if self._in_snippet:
            self._snippet_buf.append(data)


def _decode_ddg_href(href: str) -> str:
    """Recover the real target URL from a DuckDuckGo Lite `uddg=` redirect."""
    return parse_qs(urlsplit(href).query).get("uddg", [href])[0]


def _format_ddg_cards(results: list[dict[str, str | None]]) -> str:
    """Render up to `_DDG_MAX_RESULTS` results as numbered 3-line cards."""
    cards = []
    for index, result in enumerate(results[:_DDG_MAX_RESULTS], start=1):
        href = result.get("href") or ""
        real_url = _decode_ddg_href(href)
        title = result.get("title") or ""
        snippet = result.get("snippet") or ""
        cards.append(f"{index}. {title}\n   {real_url}\n   {snippet}")
    return "\n\n".join(cards)


def _read_capped(client: httpx.Client, method: str, url: str, **kwargs: object) -> bytes:
    """Stream a response, stopping once accumulated bytes exceed the cap."""
    accumulated = bytearray()
    with client.stream(method, url, **kwargs) as response:
        for chunk in response.iter_bytes():
            accumulated.extend(chunk)
            if len(accumulated) > _MAX_RESPONSE_BYTES:
                break
    return bytes(accumulated)


def search_web(query: str) -> ToolResult:
    """Query DuckDuckGo Lite and return up to 5 sponsored-free snippet cards."""
    if query.strip() == "":
        return {"error": "search_web: no query provided"}

    try:
        with httpx.Client(
            timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
        ) as client:
            raw_bytes = _read_capped(
                client, "GET", _DDG_URL, params={"q": query}
            )
    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as error:
        return {"error": f"search_web request failed: {error}"}

    decoded = raw_bytes.decode("utf-8", errors="replace")
    parser = _DDGResultParser()
    parser.feed(decoded)

    if not parser.results:
        if _DDG_BOT_CHALLENGE_MARKER in decoded:
            return {"error": _DDG_BOT_CHALLENGE_ERROR}
        return {"content": _DDG_NO_RESULTS_CONTENT}

    formatted = _format_ddg_cards(parser.results)
    return {"content": _truncate_to_sentence(formatted, 3000)}


def fetch_url(url: str) -> ToolResult:
    """Fetch `url` and return boilerplate-stripped, truncated readable text."""
    if url.strip() == "":
        return {"error": "fetch_url: no url provided"}

    try:
        with httpx.Client(
            timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
        ) as client:
            raw_bytes = _read_capped(client, "GET", url)
    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as error:
        return {"error": f"fetch_url request failed: {error}"}

    decoded = raw_bytes.decode("utf-8", errors="replace")
    extractor = _TextExtractor()
    extractor.feed(decoded)
    extracted_text = extractor.text()

    if extracted_text == "":
        return {"content": _NO_TEXT_PLACEHOLDER}

    return {"content": _truncate_to_sentence(extracted_text, 3000)}
