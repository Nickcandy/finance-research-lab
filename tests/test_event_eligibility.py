from finance_research_lab.event_eligibility import (
    PURE_STOCK_PRICE_UPDATE,
    market_event_exclusion_reason,
    news_item_exclusion_reason,
)
from finance_research_lab.models import MarketEvent, NewsItem


def test_pure_stock_price_updates_are_not_research_events() -> None:
    items = (
        NewsItem("兆易创新触及跌停", "同花顺", body="兆易创新触及跌停，成交额269.8亿元，封单1320手。"),
        NewsItem("中际旭创盘中涨超10%", "同花顺", body="中际旭创盘中涨超10%，现报168.5元。"),
        NewsItem("美光科技股价下跌8.59%", "同花顺", body="美光科技股价下跌8.59%，总市值1.01万亿美元。"),
    )

    assert [news_item_exclusion_reason(item) for item in items] == [
        PURE_STOCK_PRICE_UPDATE,
        PURE_STOCK_PRICE_UPDATE,
        PURE_STOCK_PRICE_UPDATE,
    ]


def test_price_move_with_causal_fact_remains_researchable() -> None:
    item = NewsItem(
        "港股澜起科技直线跳水跌超20%",
        "同花顺",
        body="消息面上，韩国检方调查公司涉嫌半导体零部件价格操纵一事。",
    )

    assert news_item_exclusion_reason(item) == ""


def test_sector_index_and_commodity_moves_are_not_filtered_in_this_task() -> None:
    headlines = (
        "证券板块走低，华安证券跌停",
        "科创50指数跌幅扩大至4%",
        "欧洲主要股指开盘多数下跌",
        "沪指跌幅扩大至2%",
        "韩国综指跌幅扩大至7%",
        "港股汽车股持续走高，小鹏集团-W涨超7%",
        "现货白银跌超1%",
        "6月PPI意外下跌后，美国国债价格小幅走高",
    )

    assert [
        news_item_exclusion_reason(NewsItem(value, "同花顺"))
        for value in headlines
    ] == [""] * len(headlines)


def test_event_is_researchable_when_any_member_contains_a_cause() -> None:
    pure = NewsItem("澜起科技盘中跌超15%", "同花顺", body="澜起科技盘中跌超15%。")
    causal = NewsItem(
        "澜起科技跳水",
        "公司回应",
        body="公司公告称正在配合韩国检方调查。",
    )

    assert market_event_exclusion_reason(MarketEvent(pure.headline, (pure,))) == PURE_STOCK_PRICE_UPDATE
    assert market_event_exclusion_reason(MarketEvent(pure.headline, (pure, causal))) == ""
