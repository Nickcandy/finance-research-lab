from finance_research_lab.models import MarketEvent, NewsItem, Theme


def test_news_item_supports_event_source_types() -> None:
    items = (
        NewsItem("AI 服务器订单增长", "同花顺", source_type="news"),
        NewsItem("关于重大合同的公告", "巨潮资讯", source_type="announcement"),
        NewsItem("成交量显著放大", "新浪行情", source_type="market_anomaly"),
        NewsItem("产业政策发布", "工信部", source_type="policy"),
    )

    assert tuple(item.source_type for item in items) == (
        "news",
        "announcement",
        "market_anomaly",
        "policy",
    )


def test_market_event_preserves_unique_source_urls() -> None:
    event = MarketEvent(
        title="算力产业链资本开支增加",
        items=(
            NewsItem("云厂商提高资本开支", "同花顺", "https://example.com/news/1"),
            NewsItem("光模块公司获得订单", "巨潮资讯", "https://example.com/news/2"),
            NewsItem("重复来源", "交叉确认", "https://example.com/news/1"),
            NewsItem("行情异动", "新浪行情", source_type="market_anomaly"),
        ),
    )

    assert event.source_urls == (
        "https://example.com/news/1",
        "https://example.com/news/2",
    )


def test_theme_groups_related_market_events() -> None:
    event = MarketEvent(
        title="算力产业链资本开支增加",
        items=(NewsItem("云厂商提高资本开支", "同花顺"),),
    )

    theme = Theme(name="AI 算力", events=(event,))

    assert theme.events == (event,)
