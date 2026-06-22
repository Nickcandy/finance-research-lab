from __future__ import annotations

from finance_research_lab.news_fetcher import fetch_news


class FakeHTMLResponse:
    def __init__(self, html: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.body = html.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "FakeHTMLResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body[:size] if size >= 0 else self.body


def test_fetch_news_extracts_static_article() -> None:
    html = """
    <html><head>
      <title>Fallback title</title>
      <meta property="og:title" content="AI investment expands">
      <meta property="og:site_name" content="Example News">
      <meta property="article:published_time" content="2026-06-22T10:00:00Z">
    </head><body><article>
      <p>Microsoft increased its planned investment in AI data centers this year.</p>
      <p>The company said the spending will support servers, networking and power equipment.</p>
    </article></body></html>
    """

    news = fetch_news(
        "https://news.example.com/articles/ai-capex",
        urlopen=lambda request, timeout: FakeHTMLResponse(html),
    )

    assert news.headline == "AI investment expands"
    assert news.source == "Example News"
    assert news.url == "https://news.example.com/articles/ai-capex"
    assert news.published_at == "2026-06-22T10:00:00Z"
    assert "servers, networking and power equipment" in news.body


def test_fetch_news_rejects_unsupported_url_scheme() -> None:
    try:
        fetch_news("file:///tmp/news.html")
    except ValueError as exc:
        assert "http or https" in str(exc)
    else:
        raise AssertionError("expected invalid URL to fail")


def test_fetch_news_rejects_incomplete_article() -> None:
    html = "<html><head><title>Short</title></head><body><p>Too short.</p></body></html>"

    try:
        fetch_news(
            "https://news.example.com/short",
            urlopen=lambda request, timeout: FakeHTMLResponse(html),
        )
    except ValueError as exc:
        assert "body is too short" in str(exc)
    else:
        raise AssertionError("expected incomplete article to fail")
