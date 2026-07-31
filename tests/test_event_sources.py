from __future__ import annotations

import json
from http.client import IncompleteRead
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from finance_research_lab.event_sources import ThsNewsSource

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeJSONResponse:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeJSONResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=SHANGHAI).timestamp())


def _item(
    title: str,
    published_at: str,
    url: str = "",
    digest: str = "正文",
) -> dict[str, object]:
    return {
        "title": title,
        "digest": digest,
        "rtime": _timestamp(published_at),
        "url": url,
    }


def _urlopen_for_pages(pages: dict[int, list[dict[str, object]]], calls: list[int]):
    def urlopen(request, timeout):
        assert timeout == 15
        page = int(parse_qs(urlparse(request.full_url).query)["page"][0])
        calls.append(page)
        return FakeJSONResponse({"data": {"list": pages.get(page, [])}})

    return urlopen


def test_ths_source_fetches_window_dedupes_and_writes_snapshot(tmp_path) -> None:
    calls: list[int] = []
    pages = {
        1: [
            _item("未来记录", "2026-07-14T12:30:00", "https://example.com/future"),
            _item("事件 A", "2026-07-14T11:00:00", "https://example.com/a"),
            _item("事件 A 重复", "2026-07-14T10:59:00", "https://example.com/a"),
        ],
        2: [
            _item("事件 B", "2026-07-13T13:00:00", digest="相同内容"),
            _item("事件 B", "2026-07-13T13:00:00", digest="相同内容"),
            _item("过期记录", "2026-07-13T11:59:59", "https://example.com/old"),
        ],
    }
    source = ThsNewsSource(
        tmp_path,
        urlopen=_urlopen_for_pages(pages, calls),
    )

    items = source.fetch(
        datetime(2026, 7, 13, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 14, 12, tzinfo=SHANGHAI),
    )

    assert calls == [1, 2]
    assert [item.headline for item in items] == ["事件 A", "事件 B"]
    assert items[0].published_at == "2026-07-14T11:00:00+08:00"
    assert all(item.source == "同花顺财经直播" for item in items)
    assert all(item.source_type == "news" for item in items)

    snapshot = json.loads((tmp_path / "2026-07-14.json").read_text(encoding="utf-8"))
    assert snapshot["source"] == "ths_global_news"
    assert snapshot["item_count"] == 2
    assert [item["headline"] for item in snapshot["items"]] == ["事件 A", "事件 B"]


def test_ths_source_treats_naive_times_as_shanghai_and_overwrites_snapshot(tmp_path) -> None:
    path = tmp_path / "2026-07-14.json"
    path.write_text("old snapshot", encoding="utf-8")
    source = ThsNewsSource(tmp_path, urlopen=_urlopen_for_pages({}, []))

    assert source.fetch(datetime(2026, 7, 13, 12), datetime(2026, 7, 14, 12)) == ()

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert snapshot["since"] == "2026-07-13T12:00:00+08:00"
    assert snapshot["until"] == "2026-07-14T12:00:00+08:00"
    assert snapshot["items"] == []


def test_ths_source_rejects_invalid_window_without_writing(tmp_path) -> None:
    source = ThsNewsSource(tmp_path, urlopen=_urlopen_for_pages({}, []))

    with pytest.raises(ValueError, match="since must be earlier than until"):
        source.fetch(datetime(2026, 7, 14, 12), datetime(2026, 7, 14, 12))

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"unexpected": {}}, "missing data.list"),
        ({"data": {"list": [_item("", "2026-07-14T11:00:00")]}}, "missing title"),
        ({"data": {"list": [{"title": "事件", "rtime": "bad"}]}}, "invalid rtime"),
    ],
)
def test_ths_source_reports_page_for_invalid_payload(tmp_path, payload, message) -> None:
    source = ThsNewsSource(tmp_path, urlopen=lambda request, timeout: FakeJSONResponse(payload))

    with pytest.raises(RuntimeError, match=rf"page 1.*{message}"):
        source.fetch(datetime(2026, 7, 13), datetime(2026, 7, 14))

    assert list(tmp_path.iterdir()) == []


def test_ths_source_reports_invalid_json_and_preserves_snapshot(tmp_path) -> None:
    path = tmp_path / "2026-07-14.json"
    path.write_text("old snapshot", encoding="utf-8")
    response = FakeJSONResponse({})
    response.body = b"not-json"
    source = ThsNewsSource(tmp_path, urlopen=lambda request, timeout: response)

    with pytest.raises(RuntimeError, match="page 1"):
        source.fetch(datetime(2026, 7, 13), datetime(2026, 7, 14))

    assert path.read_text(encoding="utf-8") == "old snapshot"


def test_ths_source_reports_http_failure_with_page(tmp_path) -> None:
    def fail(request, timeout):
        raise OSError("network down")

    source = ThsNewsSource(tmp_path, urlopen=fail)

    with pytest.raises(RuntimeError, match="page 1.*network down"):
        source.fetch(datetime(2026, 7, 13), datetime(2026, 7, 14))


def test_ths_source_retries_incomplete_read_once(tmp_path) -> None:
    calls = 0

    def flaky(request, timeout):
        nonlocal calls
        del request, timeout
        calls += 1
        if calls == 1:
            raise IncompleteRead(b"{}")
        return FakeJSONResponse({"data": {"list": []}})

    source = ThsNewsSource(tmp_path, urlopen=flaky)

    assert source.fetch(datetime(2026, 7, 13), datetime(2026, 7, 14)) == ()
    assert calls == 2


def test_ths_source_merges_incremental_news_and_advances_cursor(tmp_path) -> None:
    first_pages = {
        1: [
            _item("已有新闻", "2026-07-14T11:00:00", "https://example.com/old"),
            _item("窗口边界", "2026-07-13T11:59:00", "https://example.com/boundary"),
        ]
    }
    ThsNewsSource(
        tmp_path,
        urlopen=_urlopen_for_pages(first_pages, []),
    ).fetch(
        datetime(2026, 7, 13, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 14, 12, tzinfo=SHANGHAI),
    )
    second_pages = {
        1: [
            _item("新增新闻", "2026-07-14T11:05:00", "https://example.com/new"),
            _item("已有新闻", "2026-07-14T11:00:00", "https://example.com/old"),
            _item("重叠记录", "2026-07-14T10:49:00", "https://example.com/overlap"),
        ]
    }

    items = ThsNewsSource(
        tmp_path,
        urlopen=_urlopen_for_pages(second_pages, []),
    ).fetch(
        datetime(2026, 7, 13, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 14, 12, 10, tzinfo=SHANGHAI),
    )

    assert [item.headline for item in items] == ["新增新闻", "已有新闻"]
    snapshot = json.loads((tmp_path / "2026-07-14.json").read_text(encoding="utf-8"))
    assert snapshot["cursor"]["published_at"] == "2026-07-14T11:05:00+08:00"
    assert snapshot["cursor"]["item_id"].startswith("item_")


def test_ths_source_fails_at_page_limit_without_overwriting_snapshot(tmp_path) -> None:
    path = tmp_path / "2026-07-14.json"
    path.write_text("old snapshot", encoding="utf-8")
    calls: list[int] = []
    pages = {1: [_item("窗口内记录", "2026-07-14T11:00:00")]}
    source = ThsNewsSource(
        tmp_path,
        max_pages=1,
        urlopen=_urlopen_for_pages(pages, calls),
    )

    with pytest.raises(RuntimeError, match="page 1.*max_pages=1"):
        source.fetch(datetime(2026, 7, 13), datetime(2026, 7, 14, 12))

    assert calls == [1]
    assert path.read_text(encoding="utf-8") == "old snapshot"
