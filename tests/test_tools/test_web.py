"""Tests for the fetch_url web tool."""

from olla.tools.web import _HEADERS, _TextExtractor, _truncate_to_sentence, fetch_url

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
