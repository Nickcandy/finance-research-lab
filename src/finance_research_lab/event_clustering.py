from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from .models import MarketEvent, NewsItem

SHANGHAI = ZoneInfo("Asia/Shanghai")
EXACT_MATCH_WINDOW_SECONDS = 24 * 60 * 60
FUZZY_MATCH_WINDOW_SECONDS = 6 * 60 * 60
FUZZY_TITLE_THRESHOLD = 0.90

_CONTINUOUS_MARKERS = (
    "涨幅",
    "跌幅",
    "涨超",
    "跌超",
    "站上",
    "失守",
    "成交额",
    "净买入",
    "净卖出",
    "融资余额",
    "融券余额",
    "盘初涨",
    "盘初跌",
)
_POSITIVE_MARKERS = ("涨", "增长", "上调", "流入", "买入", "站上", "回升", "高开", "走高", "拉升")
_NEGATIVE_MARKERS = ("跌", "下降", "下调", "流出", "卖出", "失守", "走低", "低开", "亏损", "终止")
_MEASUREMENT_RE = re.compile(
    r"\d+(?:[,.]\d+)*\s*(?:美元/盎司|美元/桶|亿美元|亿港元|个百分点|亿元|万元|港元|美元|%|点|吨|p)",
    re.IGNORECASE,
)
_ORDINAL_RE = re.compile(r"(?:第|[（(])([〇零一二三四五六七八九十百千万\d]+)(?:期|轮|批|次|号)")
_PRODUCT_ID_RE = re.compile(
    r"(?<![a-z0-9])(?:[a-z]+[a-z0-9]*-[a-z0-9]*\d[a-z0-9-]*|[a-z]+\d+[a-z0-9-]*)(?![a-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _PreparedItem:
    item: NewsItem
    normalized_title: str
    normalized_body: str
    metric_signature: str
    timestamp: float | None
    subject: str
    direction: int
    ordinals: frozenset[str]
    product_ids: frozenset[str]
    continuous_update: bool


def cluster_market_events(items: Iterable[NewsItem]) -> tuple[MarketEvent, ...]:
    """Cluster normalized news items into deterministic market events."""

    prepared = _prepare_items(items)
    if not prepared:
        return ()

    parents = list(range(len(prepared)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    for first in range(len(prepared)):
        for second in range(first + 1, len(prepared)):
            if _same_event(prepared[first], prepared[second]):
                union(first, second)

    grouped: dict[int, list[_PreparedItem]] = {}
    for index, item in enumerate(prepared):
        grouped.setdefault(find(index), []).append(item)

    events = []
    for group in grouped.values():
        ordered = sorted(group, key=_prepared_sort_key)
        event_items = tuple(item.item for item in ordered)
        events.append(MarketEvent(title=event_items[0].headline, items=event_items))
    return tuple(sorted(events, key=_event_sort_key))


def rank_hot_events(
    events: Iterable[MarketEvent],
    limit: int = 5,
) -> tuple[MarketEvent, ...]:
    """Rank events by independent source count and freshness."""

    if limit < 1:
        raise ValueError("limit must be positive")

    ranked: list[tuple[tuple[object, ...], MarketEvent]] = []
    for event in events:
        if not event.items:
            raise ValueError("MarketEvent items must not be empty")
        if not event.title.strip():
            raise ValueError("MarketEvent title must not be empty")
        prepared = _prepare_items(event.items)
        source_count = len(
            {
                (item.item.source_type, _normalize_text(item.item.source) or "<unknown>")
                for item in prepared
            }
        )
        latest = max(
            (item.timestamp for item in prepared if item.timestamp is not None),
            default=float("-inf"),
        )
        key = (-source_count, -latest, _normalize_text(event.title), event.title)
        ranked.append((key, event))

    ranked.sort(key=lambda pair: pair[0])
    return tuple(event for _, event in ranked[:limit])


def _prepare_items(items: Iterable[NewsItem]) -> tuple[_PreparedItem, ...]:
    unique_items = tuple(dict.fromkeys(items))
    prepared = tuple(_prepare_item(item) for item in unique_items)
    return tuple(sorted(prepared, key=_prepared_sort_key))


def _prepare_item(item: NewsItem) -> _PreparedItem:
    if not item.headline.strip():
        raise ValueError("NewsItem headline must not be empty")
    normalized_title = _normalize_text(item.headline)
    if not normalized_title:
        raise ValueError("NewsItem headline must contain letters or numbers")
    normalized_source = unicodedata.normalize("NFKC", item.headline).casefold()
    return _PreparedItem(
        item=item,
        normalized_title=normalized_title,
        normalized_body=_normalize_text(item.body),
        metric_signature=_normalize_text(_MEASUREMENT_RE.sub("#", normalized_source)),
        timestamp=_parse_timestamp(item.published_at),
        subject=_subject(item.headline),
        direction=_direction(item.headline),
        ordinals=frozenset(_ORDINAL_RE.findall(normalized_source)),
        product_ids=frozenset(match.casefold() for match in _PRODUCT_ID_RE.findall(normalized_source)),
        continuous_update=any(marker in normalized_source for marker in _CONTINUOUS_MARKERS),
    )


def _parse_timestamp(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid NewsItem published_at: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.timestamp()


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum() or character == "#")


def _subject(headline: str) -> str:
    parts = re.split(r"[:：]", headline, maxsplit=1)
    return _normalize_text(parts[0]) if len(parts) == 2 else ""


def _direction(headline: str) -> int:
    positive = any(marker in headline for marker in _POSITIVE_MARKERS)
    negative = any(marker in headline for marker in _NEGATIVE_MARKERS)
    if positive == negative:
        return 0
    return 1 if positive else -1


def _same_event(first: _PreparedItem, second: _PreparedItem) -> bool:
    if first.item.url and first.item.url == second.item.url:
        return True
    if _conflicts(first, second):
        return False
    if _within_window(first, second, EXACT_MATCH_WINDOW_SECONDS, allow_unknown=True):
        same_title = first.normalized_title == second.normalized_title
        same_body = bool(first.normalized_body) and first.normalized_body == second.normalized_body
        if same_title or same_body:
            return True
    if not _within_window(first, second, FUZZY_MATCH_WINDOW_SECONDS):
        return False
    if (
        first.continuous_update
        and second.continuous_update
        and first.metric_signature == second.metric_signature
    ):
        return True
    return _bigram_dice(first.normalized_title, second.normalized_title) >= FUZZY_TITLE_THRESHOLD


def _conflicts(first: _PreparedItem, second: _PreparedItem) -> bool:
    if first.subject and second.subject and first.subject != second.subject:
        return True
    if first.direction and second.direction and first.direction != second.direction:
        return True
    if first.ordinals and second.ordinals and first.ordinals != second.ordinals:
        return True
    return bool(first.product_ids and second.product_ids and first.product_ids.isdisjoint(second.product_ids))


def _within_window(
    first: _PreparedItem,
    second: _PreparedItem,
    window_seconds: int,
    *,
    allow_unknown: bool = False,
) -> bool:
    if first.timestamp is None or second.timestamp is None:
        return allow_unknown
    return abs(first.timestamp - second.timestamp) <= window_seconds


def _bigram_dice(first: str, second: str) -> float:
    first_bigrams = _bigrams(first)
    second_bigrams = _bigrams(second)
    return 2 * len(first_bigrams & second_bigrams) / (len(first_bigrams) + len(second_bigrams))


def _bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value}
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _prepared_sort_key(item: _PreparedItem) -> tuple[object, ...]:
    timestamp = item.timestamp if item.timestamp is not None else float("-inf")
    return (
        -timestamp,
        item.item.source_type,
        _normalize_text(item.item.source),
        item.item.url,
        item.normalized_title,
        item.normalized_body,
    )


def _event_sort_key(event: MarketEvent) -> tuple[object, ...]:
    prepared = tuple(_prepare_item(item) for item in event.items)
    latest = max(
        (item.timestamp for item in prepared if item.timestamp is not None),
        default=float("-inf"),
    )
    return (-latest, _normalize_text(event.title), event.title)
