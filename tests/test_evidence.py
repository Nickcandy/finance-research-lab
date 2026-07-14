from finance_research_lab.evidence import (
    build_evidence_plan,
    classify_event,
    fetch_company_announcements,
    fetch_financial_reports,
    fetch_market_snapshot,
    score_value_chain_relevance,
)
from finance_research_lab.models import CompanyAnnouncement, FinancialSnapshot, MarketSnapshot, NewsItem, WatchlistItem


def test_classify_event_detects_capex_and_candidates() -> None:
    classification = classify_event(
        _news(),
        [_watchlist_item(), WatchlistItem("601059.SH", "信达证券", "A股", ("券商",))],
    )

    assert classification.event_type == "资本开支"
    assert classification.candidate_symbols == ("300308.SZ",)
    assert classification.confidence in {"medium", "high"}


def test_build_evidence_plan_selects_company_and_market_tools() -> None:
    plan = build_evidence_plan(
        classify_event(
            _news(),
            [_watchlist_item()],
        )
    )

    assert "company_announcements" in plan.required_tools
    assert "financial_reports" in plan.required_tools
    assert "market_snapshot" in plan.required_tools
    assert plan.candidate_symbols == ("300308.SZ",)


def test_evidence_tools_return_provider_data_without_mock_values() -> None:
    provider = _provider()
    announcements = fetch_company_announcements("300308.SZ", "", "", provider)
    financials = fetch_financial_reports("300308.SZ", ("latest",), provider)
    market = fetch_market_snapshot("300308.SZ", 5, provider)

    assert announcements[0].symbol == "300308.SZ"
    assert announcements[0].url == "https://www.cninfo.com.cn/a"
    assert financials[0].report_period == "2026-03-31"
    assert market.symbol == "300308.SZ"
    assert market.period_return_pct == 4.0
    assert market.provider == "akshare/eastmoney"


def test_score_value_chain_relevance_uses_zero_to_three_scale() -> None:
    score = score_value_chain_relevance(_news(), _watchlist_item())

    assert score.upstream_relevance_score == 3
    assert score.downstream_relevance_score == 3
    assert score.revenue_elasticity_score == 3


def _news() -> NewsItem:
    return NewsItem(
        headline="AI data center capex increases optical module demand",
        source="Example News",
        url="https://news.example.com/ai-capex",
        published_at="2026-06-22T10:00:00Z",
        body="Microsoft increased AI data center spending and optical module demand.",
    )


def _watchlist_item() -> WatchlistItem:
    return WatchlistItem(
        "300308.SZ",
        "中际旭创",
        "A股",
        ("AI", "数据中心", "光模块"),
        "AI 光模块供应链",
        "估值拥挤",
        "通信设备",
    )


class _Provider:
    def announcements(self, symbol: str, start_date: str, end_date: str):
        return (
            CompanyAnnouncement(
                symbol=symbol,
                title="真实公告标题",
                announcement_type="日常经营",
                published_at="2026-06-01",
                url="https://www.cninfo.com.cn/a",
                provider="akshare/cninfo",
            ),
        )

    def financials(self, symbol: str):
        return (
            FinancialSnapshot(
                symbol=symbol,
                report_period="2026-03-31",
                revenue=120.0,
                revenue_yoy=10.0,
                net_profit=20.0,
                net_profit_yoy=8.0,
                gross_margin=30.0,
                provider="akshare/eastmoney",
            ),
        )

    def market(self, symbol: str, lookback_days: int):
        return MarketSnapshot(
            symbol=symbol,
            trade_date="2026-06-10",
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            pct_chg=2.0,
            volume=200.0,
            amount=1000.0,
            lookback_days=lookback_days,
            period_return_pct=4.0,
            volume_ratio=2.0,
            provider="akshare/eastmoney",
        )


def _provider() -> _Provider:
    return _Provider()
