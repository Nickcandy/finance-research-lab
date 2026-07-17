from __future__ import annotations

from finance_research_lab.impact_scoring import (
    infer_news_impact_direction,
    stock_impact_score,
    summarize_event_impact,
)
from finance_research_lab.models import (
    EventAnalysis,
    NewsItem,
    ResearchReport,
    StockImpact,
    ValueChainTrace,
)


def test_news_direction_classifier_is_conservative() -> None:
    assert infer_news_impact_direction("公司中标大额订单") == "positive"
    assert infer_news_impact_direction("公司被立案并大幅下跌") == "negative"
    assert infer_news_impact_direction("需求增长但毛利率不及预期") == "mixed"
    assert infer_news_impact_direction("公司举行年度股东大会") == "unknown"


def test_stock_impact_score_separates_direction_from_relation_strength() -> None:
    positive = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "high",
        impact_direction="positive",
        confidence="high",
    )
    negative = StockImpact(
        "688048.SH",
        "长光华芯",
        "A股",
        "indirect",
        "medium",
        impact_direction="negative",
        confidence="medium",
    )

    assert stock_impact_score(positive) == 80
    assert stock_impact_score(negative) == -45
    assert stock_impact_score(
        StockImpact("000001.SZ", "平安银行", "A股", "direct", "high")
    ) is None


def test_event_summary_keeps_conflicting_company_directions_mixed() -> None:
    news = NewsItem("产业链影响分化", "测试来源")
    report = ResearchReport(
        raw_news=news,
        event=EventAnalysis("供需变化", confidence="medium"),
        value_chain=ValueChainTrace("上游", "下游", impact_direction="mixed"),
        stock_impacts=(
            StockImpact(
                "300308.SZ",
                "中际旭创",
                "A股",
                "direct",
                "high",
                impact_direction="positive",
                confidence="high",
            ),
            StockImpact(
                "688048.SH",
                "长光华芯",
                "A股",
                "indirect",
                "medium",
                impact_direction="negative",
                confidence="medium",
            ),
        ),
        validation_tasks=(),
        stage="待判断",
        action_state="等验证",
    )

    summary = summarize_event_impact(report)

    assert summary.direction == "mixed"
    assert summary.score == 18
    assert summary.confidence == "medium"
