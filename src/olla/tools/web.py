"""Lightweight webpage fetch/extract tool (boilerplate stripping, byte-capped read)."""

import re
from html.parser import HTMLParser

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


def _read_capped(client: httpx.Client, method: str, url: str, **kwargs: object) -> bytes:
    """Stream a response, stopping once accumulated bytes exceed the cap."""
    accumulated = bytearray()
    with client.stream(method, url, **kwargs) as response:
        for chunk in response.iter_bytes():
            accumulated.extend(chunk)
            if len(accumulated) > _MAX_RESPONSE_BYTES:
                break
    return bytes(accumulated)


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
