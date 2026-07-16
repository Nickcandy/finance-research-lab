from __future__ import annotations

from itertools import permutations

import pytest

from finance_research_lab.event_clustering import cluster_market_events, rank_hot_events
from finance_research_lab.models import MarketEvent, NewsItem


def _news(
    headline: str,
    published_at: str,
    *,
    source: str = "同花顺财经直播",
    url: str = "",
    body: str = "",
    source_type: str = "news",
) -> NewsItem:
    return NewsItem(
        headline=headline,
        source=source,
        url=url,
        published_at=published_at,
        body=body,
        source_type=source_type,
    )


def test_cluster_merges_exact_headline_and_body_matches_and_preserves_sources() -> None:
    items = (
        _news(
            "AI 算力中心正式投产",
            "2026-07-16T10:00:00+08:00",
            url="https://example.com/ths",
            body="算力中心今天正式投产",
        ),
        _news(
            "AI算力中心正式投产",
            "2026-07-16T10:05:00+08:00",
            source="巨潮资讯",
            url="https://example.com/cninfo",
            body="另一段正文",
            source_type="announcement",
        ),
        _news(
            "算力项目投入运行",
            "2026-07-16T10:10:00+08:00",
            source="官方媒体",
            url="https://example.com/official",
            body="算力中心今天正式投产",
        ),
    )

    events = cluster_market_events(items)

    assert len(events) == 1
    assert events[0].title == "算力项目投入运行"
    assert events[0].summary == ""
    assert events[0].themes == ()
    assert events[0].source_urls == (
        "https://example.com/official",
        "https://example.com/cninfo",
        "https://example.com/ths",
    )


def test_cluster_merges_continuous_market_updates() -> None:
    items = tuple(
        _news(f"韩国综指跌幅扩大至{percent}%", published_at)
        for percent, published_at in (
            (5, "2026-07-16T08:17:00+08:00"),
            (6, "2026-07-16T08:40:00+08:00"),
            (7, "2026-07-16T09:14:00+08:00"),
        )
    )

    events = cluster_market_events(items)

    assert len(events) == 1
    assert events[0].title == "韩国综指跌幅扩大至7%"
    assert tuple(item.headline for item in events[0].items) == (
        "韩国综指跌幅扩大至7%",
        "韩国综指跌幅扩大至6%",
        "韩国综指跌幅扩大至5%",
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("韩国综指跌幅扩大至7%", "韩国综指涨幅扩大至8%"),
        ("现货黄金站上4080美元/盎司", "现货黄金失守4050美元/盎司"),
        (
            "朗特智能：预计2026年上半年净利润同比下降87.48%-91.65%",
            "硕贝德：预计2026年上半年净利润同比下降19.48%-28.42%",
        ),
        ("恒瑞医药：HRS-8829获批临床试验", "恒瑞医药：HRS-8797获批临床试验"),
        (
            "财政部、中国人民银行进行中央国库现金管理商业银行定期存款（十一期）招投标",
            "财政部、中国人民银行进行中央国库现金管理商业银行定期存款（十二期）招投标",
        ),
    ],
)
def test_cluster_does_not_merge_conflicting_or_template_similar_events(
    first: str,
    second: str,
) -> None:
    items = (
        _news(first, "2026-07-16T10:00:00+08:00"),
        _news(second, "2026-07-16T10:05:00+08:00"),
    )

    assert len(cluster_market_events(items)) == 2


def test_cluster_requires_fuzzy_matches_to_be_within_six_hours() -> None:
    items = (
        _news("现货黄金失守4030美元/盎司", "2026-07-16T01:00:00+08:00"),
        _news("现货黄金失守4040美元/盎司", "2026-07-16T08:00:01+08:00"),
    )

    assert len(cluster_market_events(items)) == 2


def test_cluster_is_order_independent_and_keeps_empty_url_items() -> None:
    items = (
        _news(
            "APEC数字周将在成都拉开帷幕，外交部介绍有关情况",
            "2026-07-16T10:00:00Z",
            url="https://example.com/first",
        ),
        _news(
            "APEC数字周将在成都拉开帷幕 外交部介绍有关情况",
            "2026-07-16T18:05:00+08:00",
            source="官方媒体",
        ),
    )

    expected = cluster_market_events(items)

    for ordered_items in permutations(items):
        assert cluster_market_events(ordered_items) == expected
    assert len(expected) == 1
    assert expected[0].source_urls == ("https://example.com/first",)


def test_cluster_removes_only_identical_news_items() -> None:
    item = _news("事件 A", "", body="正文")
    same_headline_other_source = _news("事件 A", "", source="官方媒体", body="正文")

    events = cluster_market_events((item, item, same_headline_other_source))

    assert len(events) == 1
    assert events[0].items == (item, same_headline_other_source)


def test_rank_prefers_independent_sources_then_recency_without_same_source_boost() -> None:
    corroborated = MarketEvent(
        "多来源事件",
        (
            _news("多来源事件", "2026-07-16T08:00:00+08:00"),
            _news(
                "多来源事件公告",
                "2026-07-16T08:05:00+08:00",
                source="巨潮资讯",
                source_type="announcement",
            ),
        ),
    )
    fresh = MarketEvent("最新事件", (_news("最新事件", "2026-07-16T11:00:00+08:00"),))
    repeated = MarketEvent(
        "连续播报事件",
        tuple(
            _news(f"连续播报事件 {index}", f"2026-07-16T10:0{index}:00+08:00")
            for index in range(3)
        ),
    )

    ranked = rank_hot_events((repeated, fresh, corroborated))

    assert tuple(event.title for event in ranked) == ("多来源事件", "最新事件", "连续播报事件")
    assert rank_hot_events((repeated, fresh, corroborated), limit=2) == ranked[:2]


def test_rank_is_order_independent_and_treats_missing_time_as_oldest() -> None:
    missing_time = MarketEvent("无时间事件", (_news("无时间事件", ""),))
    alpha = MarketEvent("A 事件", (_news("A 事件", "2026-07-16T10:00:00Z"),))
    beta = MarketEvent("B 事件", (_news("B 事件", "2026-07-16T18:00:00+08:00"),))
    events = (missing_time, beta, alpha)

    expected = rank_hot_events(events)

    for ordered_events in permutations(events):
        assert rank_hot_events(ordered_events) == expected
    assert tuple(event.title for event in expected) == ("A 事件", "B 事件", "无时间事件")


def test_empty_inputs_return_empty_tuples() -> None:
    assert cluster_market_events(()) == ()
    assert rank_hot_events(()) == ()


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ((_news(" ", "2026-07-16T10:00:00+08:00"),), "headline"),
        ((_news("事件", "not-a-time"),), "published_at"),
    ],
)
def test_cluster_rejects_invalid_news_items(items: tuple[NewsItem, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        cluster_market_events(items)


def test_rank_rejects_invalid_events_and_limit() -> None:
    with pytest.raises(ValueError, match="items"):
        rank_hot_events((MarketEvent("空事件", ()),))
    with pytest.raises(ValueError, match="published_at"):
        rank_hot_events((MarketEvent("坏时间", (_news("坏时间", "bad"),)),))
    with pytest.raises(ValueError, match="limit"):
        rank_hot_events((), limit=0)
