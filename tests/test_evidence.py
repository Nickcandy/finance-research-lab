from finance_research_lab.evidence import (
    build_evidence_plan,
    classify_event,
    fetch_company_announcements,
    fetch_financial_reports,
    fetch_market_snapshot,
    score_value_chain_relevance,
)
from finance_research_lab.models import RawNews, WatchlistItem


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


def test_mock_company_and_market_tools_return_structured_data() -> None:
    announcements = fetch_company_announcements("300308.SZ", "", "")
    financials = fetch_financial_reports("300308.SZ", ("latest",))
    market = fetch_market_snapshot("300308.SZ", 5)

    assert announcements[0].symbol == "300308.SZ"
    assert financials[0].report_period == "latest"
    assert market.symbol == "300308.SZ"
    assert market.close > 0
    assert market.volume > 0
    assert market.amount > 0


def test_score_value_chain_relevance_uses_zero_to_three_scale() -> None:
    score = score_value_chain_relevance(_news(), _watchlist_item())

    assert score.upstream_relevance_score == 3
    assert score.downstream_relevance_score == 3
    assert score.revenue_elasticity_score == 3


def _news() -> RawNews:
    return RawNews(
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
