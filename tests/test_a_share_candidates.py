from finance_research_lab.models import RawNews, StockImpact, WatchlistItem
from finance_research_lab.news_trace import build_research_report


def test_build_research_report_can_include_verified_a_share_outside_watchlist() -> None:
    report = build_research_report(
        RawNews(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            url="https://news.example.com/ai-capex",
            body="Microsoft increased AI data center spending and optical module demand.",
        ),
        watchlist=[
            WatchlistItem("601059.SH", "信达证券", "A股", ("券商",)),
        ],
        a_share_universe=[
            _company(
                "300308.SZ",
                "中际旭创",
                themes=("AI", "数据中心", "光模块"),
                business_summary="高速光模块供应商，服务 AI 数据中心供应链",
            )
        ],
    )

    assert [(impact.symbol, impact.name, impact.verification_status) for impact in report.stock_impacts] == [
        ("300308.SZ", "中际旭创", "verified")
    ]
    assert report.stock_impacts[0].watchlist_hit is False
    assert "A 股 universe 主题匹配" in report.stock_impacts[0].evidence[0]


def test_build_research_report_marks_watchlist_hit_without_limiting_candidates() -> None:
    report = build_research_report(
        RawNews(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            body="AI data center capex drives optical module demand.",
        ),
        watchlist=[WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块"))],
        a_share_universe=[
            _company("300308.SZ", "中际旭创", themes=("AI", "数据中心", "光模块")),
            _company("300502.SZ", "新易盛", themes=("AI", "数据中心", "光模块")),
        ],
    )

    impacts = {impact.symbol: impact for impact in report.stock_impacts}

    assert impacts["300308.SZ"].watchlist_hit is True
    assert impacts["300502.SZ"].watchlist_hit is False


def test_build_research_report_separates_unverified_llm_candidates() -> None:
    report = build_research_report(
        RawNews(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            body="AI data center capex drives optical module demand.",
        ),
        watchlist=[],
        a_share_universe=[],
        proposed_impacts=(
            StockImpact(
                "999999.SH",
                "不存在公司",
                "A股",
                "direct",
                "high",
                themes=("AI",),
                reasoning="LLM proposed candidate",
            ),
        ),
    )

    assert report.stock_impacts[0].symbol == "999999.SH"
    assert report.stock_impacts[0].verification_status == "unverified"


def _company(
    symbol: str,
    name: str,
    *,
    themes: tuple[str, ...],
    business_summary: str = "",
):
    from finance_research_lab.models import AShareCompany

    return AShareCompany(
        symbol=symbol,
        name=name,
        market="A股",
        industry="通信设备",
        themes=themes,
        business_summary=business_summary,
        source="test",
    )
