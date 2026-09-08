"""Tests for the fetch_url web tool."""

import httpx

from olla.tools.web import (
    _HEADERS,
    _MAX_RESPONSE_BYTES,
    _TextExtractor,
    _truncate_to_sentence,
    fetch_url,
)

_SAMPLE_HTML = """
<html>
<head>
<script>alert('script-marker-text')</script>
<style>.x{color:red} /* style-marker-text */</style>
</head>
<body>
<nav><nav>nested-nav-marker</nav>outer-nav-marker</nav>
<header>partner-nav-marker</header>
<main>
<p>Hello&nbsp;World, this is kept text.</p>
<aside>aside-keep-marker</aside>
</main>
<footer>site-footer-marker</footer>
</body>
</html>
"""


def test_text_extractor_drops_script_style_nav_header_footer():
    extractor = _TextExtractor()
    extractor.feed(_SAMPLE_HTML)
    text = extractor.text()

    assert "script-marker-text" not in text
    assert "style-marker-text" not in text
    assert "nested-nav-marker" not in text
    assert "outer-nav-marker" not in text
    assert "partner-nav-marker" not in text
    assert "site-footer-marker" not in text


def test_text_extractor_keeps_paragraph_text_and_normalizes_nbsp():
    extractor = _TextExtractor()
    extractor.feed(_SAMPLE_HTML)
    text = extractor.text()

    assert "Hello World, this is kept text." in text


def test_text_extractor_keeps_aside_content():
    extractor = _TextExtractor()
    extractor.feed(_SAMPLE_HTML)
    text = extractor.text()

    assert "aside-keep-marker" in text


def test_truncate_to_sentence_noop_under_limit():
    text = "A short sentence that is well under the limit."
    assert _truncate_to_sentence(text, limit=3000) == text


def test_truncate_to_sentence_noop_at_exact_limit():
    text = "a" * 3000
    assert _truncate_to_sentence(text, limit=3000) == text


def test_fetch_url_empty_returns_error_without_http_call(mocker):
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")

    result = fetch_url("")

    assert "error" in result
    mock_client_cls.assert_not_called()


def test_fetch_url_whitespace_only_returns_error_without_http_call(mocker):
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")

    result = fetch_url("   ")

    assert "error" in result
    mock_client_cls.assert_not_called()


def test_fetch_url_all_boilerplate_returns_placeholder(mocker):
    html = (
        b"<html><head><script>var x = 1;</script>"
        b"<style>.a{color:red}</style></head>"
        b"<body><nav>menu</nav><footer>footer text</footer></body></html>"
    )
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
    client_instance = mock_client_cls.return_value.__enter__.return_value
    stream_cm = client_instance.stream.return_value
    stream_cm.__enter__.return_value.iter_bytes.return_value = [html]

    result = fetch_url("https://example.com/empty")

    assert result == {"content": "(no readable text extracted)"}


def test_fetch_url_small_page_returns_cleaned_content(mocker):
    html = b"<html><body><p>Hello&nbsp;world</p></body></html>"
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
    client_instance = mock_client_cls.return_value.__enter__.return_value
    stream_cm = client_instance.stream.return_value
    stream_cm.__enter__.return_value.iter_bytes.return_value = [html]

    result = fetch_url("https://example.com")

    assert result == {"content": "Hello world"}
    _, kwargs = mock_client_cls.call_args
    assert kwargs["follow_redirects"] is True
    assert kwargs["headers"] == _HEADERS


def test_truncate_to_sentence_hard_cuts_at_limit_when_no_punctuation():
    text = "a" * 4000
    result = _truncate_to_sentence(text, limit=3000)

    body, _, note = result.partition("\n")
    assert len(body) == 3000
    assert note != ""
    assert len(result) > 3000


def test_truncate_to_sentence_counts_code_points_not_utf8_bytes():
    # Each "🎉" is one Python character but 4 UTF-8 bytes; a byte-based
    # implementation would cut around 750 characters instead of 3000.
    text = "🎉" * 4000
    result = _truncate_to_sentence(text, limit=3000)

    body, _, note = result.partition("\n")
    assert len(body) == 3000
    assert note != ""


def test_fetch_url_stops_reading_once_byte_cap_exceeded(mocker):
    chunk = b"x" * 1_000_000
    total_chunks = (_MAX_RESPONSE_BYTES // len(chunk)) + 20
    drained_count = 0

    def chunk_generator():
        nonlocal drained_count
        for _ in range(total_chunks):
            drained_count += 1
            yield chunk

    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
    client_instance = mock_client_cls.return_value.__enter__.return_value
    stream_cm = client_instance.stream.return_value
    stream_cm.__enter__.return_value.iter_bytes.return_value = chunk_generator()

    result = fetch_url("https://example.com/big")

    assert "content" in result
    assert drained_count < total_chunks


def test_fetch_url_timeout_returns_error(mocker):
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
    mock_client_cls.side_effect = httpx.TimeoutException("timed out")

    result = fetch_url("https://example.com/slow")

    assert "error" in result


def test_fetch_url_transport_error_returns_error(mocker):
    mock_client_cls = mocker.patch("olla.tools.web.httpx.Client")
    mock_client_cls.side_effect = httpx.TransportError("connection refused")

    result = fetch_url("https://example.com/down")

    assert "error" in result
