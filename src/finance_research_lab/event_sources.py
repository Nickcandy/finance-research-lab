from __future__ import annotations

import hashlib
import json
from http.client import HTTPException, IncompleteRead
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import NewsItem

UrlOpen = Callable[[Request, int], Any]

SHANGHAI = ZoneInfo("Asia/Shanghai")
THS_NEWS_URL = "https://news.10jqka.com.cn/tapp/news/push/stock"
DEFAULT_MAX_PAGES = 100
CURSOR_OVERLAP = timedelta(minutes=10)


class EventSource(Protocol):
    name: str

    def fetch(self, since: datetime, until: datetime) -> tuple[NewsItem, ...]: ...


def _default_urlopen(request: Request, timeout: int) -> Any:
    return urlopen(request, timeout=timeout)


class ThsNewsSource:
    name = "ths_global_news"

    def __init__(
        self,
        cache_dir: str | Path = "data/event_cache/ths",
        *,
        urlopen: UrlOpen = _default_urlopen,
        timeout: int = 15,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.cache_dir = Path(cache_dir)
        self.urlopen = urlopen
        self.timeout = timeout
        self.max_pages = max_pages

    def fetch(self, since: datetime, until: datetime) -> tuple[NewsItem, ...]:
        since = _shanghai_time(since)
        until = _shanghai_time(until)
        if since >= until:
            raise ValueError("since must be earlier than until")

        previous_items, cursor = self._read_latest_snapshot()
        fetch_since = since
        if cursor is not None:
            fetch_since = max(since, cursor[0] - CURSOR_OVERLAP)

        records: list[tuple[datetime, NewsItem]] = []
        for page in range(1, self.max_pages + 1):
            rows = self._fetch_page(page)
            if not rows:
                break

            page_times: list[datetime] = []
            for index, row in enumerate(rows):
                try:
                    published_at, item = _parse_item(row)
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError(f"THS page {page} item {index} failed: {exc}") from exc
                page_times.append(published_at)
                if fetch_since <= published_at <= until:
                    records.append((published_at, item))

            if min(page_times) < fetch_since:
                break
        else:
            raise RuntimeError(
                f"THS page {self.max_pages} reached max_pages={self.max_pages} before since"
            )

        for item in previous_items:
            try:
                published_at = datetime.fromisoformat(item.published_at)
            except ValueError:
                continue
            published_at = _shanghai_time(published_at)
            if since <= published_at <= until:
                records.append((published_at, item))
        records.sort(key=lambda record: record[0], reverse=True)
        items = _deduplicate(records)
        self._write_snapshot(since, until, items)
        return items

    def _fetch_page(self, page: int) -> list[dict[str, Any]]:
        query = urlencode({"page": page, "tag": "", "track": "website"})
        request = Request(
            f"{THS_NEWS_URL}?{query}",
            headers={
                "User-Agent": "Mozilla/5.0 finance-research-lab/0.1",
                "Referer": "https://news.10jqka.com.cn/realtimenews.html",
            },
            method="GET",
        )
        for attempt in range(2):
            try:
                with self.urlopen(request, self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                rows = payload["data"]["list"]
                if not isinstance(rows, list):
                    raise ValueError("missing data.list")
                if not all(isinstance(row, dict) for row in rows):
                    raise ValueError("data.list must contain objects")
                return rows
            except (IncompleteRead, HTTPException, KeyError, TypeError, ValueError, OSError) as exc:
                if attempt == 0 and isinstance(exc, (IncompleteRead, HTTPException, OSError)):
                    continue
                message = "missing data.list" if isinstance(exc, KeyError) else str(exc)
                raise RuntimeError(f"THS page {page} failed: {message}") from exc
        raise AssertionError("unreachable")

    def _write_snapshot(
        self,
        since: datetime,
        until: datetime,
        items: tuple[NewsItem, ...],
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{until.date().isoformat()}.json"
        temp_path = path.with_suffix(".json.tmp")
        snapshot = {
            "source": self.name,
            "since": since.isoformat(timespec="seconds"),
            "until": until.isoformat(timespec="seconds"),
            "fetched_at": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
            "item_count": len(items),
            "items": [asdict(item) for item in items],
            "cursor": _cursor_payload(items),
        }
        try:
            temp_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _read_latest_snapshot(
        self,
    ) -> tuple[tuple[NewsItem, ...], tuple[datetime, str] | None]:
        if not self.cache_dir.is_dir():
            return (), None
        for path in sorted(self.cache_dir.glob("????-??-??.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload["items"]
                if not isinstance(rows, list):
                    continue
                items = tuple(NewsItem(**row) for row in rows if isinstance(row, dict))
                cursor_payload = payload.get("cursor")
                if isinstance(cursor_payload, dict):
                    published_at = datetime.fromisoformat(str(cursor_payload["published_at"]))
                    item_id = str(cursor_payload["item_id"])
                elif items:
                    published_at = datetime.fromisoformat(items[0].published_at)
                    item_id = _item_id(items[0])
                else:
                    return items, None
                return items, (_shanghai_time(published_at), item_id)
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                continue
        return (), None


def _shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def _parse_item(row: dict[str, Any]) -> tuple[datetime, NewsItem]:
    headline = str(row.get("title") or "").strip()
    if not headline:
        raise ValueError("missing title")
    try:
        published_at = datetime.fromtimestamp(int(row["rtime"]), SHANGHAI)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid rtime") from exc
    item = NewsItem(
        headline=headline,
        source="同花顺财经直播",
        url=str(row.get("url") or "").strip(),
        published_at=published_at.isoformat(timespec="seconds"),
        body=str(row.get("digest") or "").strip(),
        source_type="news",
    )
    return published_at, item


def _deduplicate(records: list[tuple[datetime, NewsItem]]) -> tuple[NewsItem, ...]:
    seen: set[str] = set()
    items: list[NewsItem] = []
    for _, item in records:
        key = item.url or hashlib.sha256(
            f"{item.headline}\0{item.published_at}\0{item.body}".encode("utf-8")
        ).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return tuple(items)


def _item_id(item: NewsItem) -> str:
    value = item.url or f"{item.headline}\0{item.published_at}\0{item.body}"
    return f"item_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _cursor_payload(items: tuple[NewsItem, ...]) -> dict[str, str] | None:
    if not items:
        return None
    latest = items[0]
    return {"published_at": latest.published_at, "item_id": _item_id(latest)}
