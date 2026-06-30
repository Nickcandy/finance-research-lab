from datetime import date

from finance_research_lab.models import (
    EventAnalysis,
    NewsTrace,
    RawNews,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
)
from finance_research_lab.report import render_news_trace, render_research_report


def test_render_news_trace_contains_core_sections() -> None:
    trace = NewsTrace(
        headline="稳定币监管框架推进",
        source="manual",
        news_type="政策 / 监管",
        payer="支付公司",
        receiver="稳定币发行方",
        value_chain=["监管", "发行", "支付"],
        direct_beneficiaries=[],
        indirect_beneficiaries=[],
        sentiment_mappings=[],
        stage="待判断",
        action_state="等验证",
        verification_points=["查官方文件"],
    )
    md = render_news_trace(trace, date(2026, 6, 16))
    assert "# 热点追源：稳定币监管框架推进" in md
    assert "## 3. 市场映射" in md
    assert "- [ ] 查官方文件" in md


def test_render_research_report_contains_agent_ready_sections() -> None:
    report = ResearchReport(
        raw_news=RawNews(headline="AI capex increases", source="manual"),
        event=EventAnalysis(
            event_type="资本开支 / 产能扩张",
            themes=("AI", "数据中心"),
            involved_entities=(),
            key_facts=("标题命中主题：AI、数据中心",),
            source_quality="待复核",
            confidence="low",
            reasoning="基于标题关键词的规则 fallback",
        ),
        value_chain=ValueChainTrace(
            payer="云厂商",
            receiver="光模块供应链",
            chain_steps=("AI CapEx", "数据中心", "光模块"),
            impact_direction="positive",
            reasoning="资本开支增加可能带来供应链需求",
        ),
        stock_impacts=(
            StockImpact(
                symbol="300308.SZ",
                name="中际旭创",
                market="A股",
                impact_type="direct",
                impact_strength="high",
                themes=("AI", "光模块"),
                reasoning="主题重合度较高",
                evidence=("股票池主题：AI / 光模块",),
                risks=("估值拥挤",),
                verification_status="verified",
                verification_source="test",
                watchlist_hit=True,
            ),
        ),
        validation_tasks=(ValidationTask("查官方文件", "官方公告或可靠媒体原文"),),
        stage="待判断",
        action_state="等验证",
    )

    md = render_research_report(report, date(2026, 6, 22))

    assert "# 研究报告：AI capex increases" in md
    assert "## 2. 事件理解" in md
    assert "资本开支 / 产能扩张" in md
    assert "AI CapEx -> 数据中心 -> 光模块" in md
    assert "## 4. 已校验 A 股候选" in md
    assert "## 5. 待确认候选" in md
    assert "## 7. Watchlist 命中" in md
    assert "中际旭创（300308.SZ，A股）" in md
    assert "direct / high" in md
    assert "校验：已校验（test）" in md
    assert "Watchlist：命中" in md
    assert "- [ ] 查官方文件（需要：官方公告或可靠媒体原文）" in md
