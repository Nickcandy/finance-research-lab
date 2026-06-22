from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import RawNews

UrlOpen = Callable[[Request, int], Any]

MAX_RESPONSE_BYTES = 2_000_000
MAX_BODY_CHARS = 50_000
MIN_BODY_CHARS = 100


def _default_urlopen(request: Request, timeout: int) -> Any:
    return urlopen(request, timeout=timeout)


def fetch_news(
    url: str,
    *,
    urlopen: UrlOpen = _default_urlopen,
    timeout: int = 15,
) -> RawNews:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("News URL must use http or https")

    request = Request(
        url,
        headers={"User-Agent": "finance-research-lab/0.1"},
        method="GET",
    )
    with urlopen(request, timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            raise ValueError(f"News URL did not return HTML: {content_type or 'unknown'}")
        body = response.read(MAX_RESPONSE_BYTES + 1)

    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("News page exceeds the 2 MB response limit")

    parser = _ArticleParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    headline = parser.metadata.get("og:title") or parser.metadata.get("twitter:title")
    headline = _clean_text(headline or parser.title)
    article_body = "\n\n".join(parser.paragraphs).strip()[:MAX_BODY_CHARS]

    if not headline:
        raise ValueError("News page does not contain a title")
    if len(article_body) < MIN_BODY_CHARS:
        raise ValueError("News article body is too short")

    source = _clean_text(parser.metadata.get("og:site_name") or parsed_url.hostname or "")
    published_at = _clean_text(
        parser.metadata.get("article:published_time")
        or parser.metadata.get("datepublished")
        or parser.metadata.get("pubdate")
        or ""
    )
    return RawNews(
        headline=headline,
        source=source,
        url=url,
        published_at=published_at,
        body=article_body,
    )


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.title = ""
        self.paragraphs: list[str] = []
        self._capture_title = False
        self._capture_paragraph = False
        self._ignored_depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            content = _clean_text(attributes.get("content", ""))
            if key and content:
                self.metadata[key] = content
        elif tag == "title":
            self._capture_title = True
            self._buffer = []
        elif tag == "p":
            self._capture_paragraph = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "title" and self._capture_title:
            self.title = _clean_text(" ".join(self._buffer))
            self._capture_title = False
            self._buffer = []
        elif tag == "p" and self._capture_paragraph:
            paragraph = _clean_text(" ".join(self._buffer))
            if paragraph:
                self.paragraphs.append(paragraph)
            self._capture_paragraph = False
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and (self._capture_title or self._capture_paragraph):
            self._buffer.append(data)


def _clean_text(value: str) -> str:
    return " ".join(value.split())
