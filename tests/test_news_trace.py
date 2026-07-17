from finance_research_lab.news_trace import (
    build_research_report,
    build_trace,
    infer_themes,
    verify_research_report_candidates,
)
from finance_research_lab.models import AShareCompany, NewsItem, StockImpact, WatchlistItem


def test_infer_themes_for_ai_capex() -> None:
    themes = infer_themes("Microsoft raises AI data center capex guidance")
    assert "AI" in themes
    assert "数据中心" in themes


def test_build_trace_maps_watchlist_items() -> None:
    watchlist = [
        WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块")),
        WatchlistItem("601059.SH", "信达证券", "A股", ("券商",)),
    ]
    trace = build_trace("AI data center capex increases optical module demand", "example", watchlist)
    assert trace.news_type == "资本开支 / 产能扩张"
    assert [item.name for item in trace.direct_beneficiaries] == ["中际旭创"]


def test_build_research_report_maps_event_chain_and_stock_impacts() -> None:
    watchlist = [
        WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块")),
        WatchlistItem("601059.SH", "信达证券", "A股", ("券商",)),
    ]

    report = build_research_report(
        NewsItem(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            url="https://news.example.com/ai-capex",
            body="Microsoft increased AI data center spending and optical module demand.",
        ),
        watchlist,
    )

    assert report.raw_news.headline == "AI data center capex increases optical module demand"
    assert report.event.event_type == "资本开支 / 产能扩张"
    assert "AI" in report.event.themes
    assert "数据中心" in report.event.themes
    assert "AI CapEx" in report.value_chain.chain_steps
    assert [(impact.name, impact.impact_type) for impact in report.stock_impacts] == [
        ("中际旭创", "direct")
    ]
    assert report.validation_tasks[0].status == "pending"


def test_candidate_identity_is_corrected_by_unique_company_name() -> None:
    news = NewsItem("德明利连续第三日跌停", "同花顺")
    proposed = StockImpact(
        "300391.SZ",
        "德明利",
        "A股",
        "direct",
        "high",
        verification_status="unverified",
    )
    report = build_research_report(news, [], proposed_impacts=(proposed,))

    verified = verify_research_report_candidates(
        report,
        [],
        [AShareCompany("001309.SZ", "德明利", "A股", source="akshare")],
    )

    assert len(verified.stock_impacts) == 1
    impact = verified.stock_impacts[0]
    assert (impact.symbol, impact.name) == ("001309.SZ", "德明利")
    assert impact.verification_status == "verified"
    assert impact.impact_direction == "negative"
    assert impact.confidence == "low"
    assert "300391.SZ -> 001309.SZ" in impact.evidence[-1]


def test_unresolved_candidate_stays_unverified() -> None:
    news = NewsItem("未知公司异动", "同花顺")
    proposed = StockImpact(
        "300391.SZ",
        "不存在的公司",
        "A股",
        "direct",
        "high",
        verification_status="unverified",
    )
    report = build_research_report(news, [], proposed_impacts=(proposed,))

    verified = verify_research_report_candidates(
        report,
        [],
        [AShareCompany("300391.SZ", "长药退", "A股", source="akshare")],
    )

    assert verified.stock_impacts[0].verification_status == "unverified"
    assert verified.stock_impacts[0].name == "不存在的公司"
