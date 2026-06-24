from __future__ import annotations

from datetime import date

from finance_research_lab.agent_models import ToolResult
from finance_research_lab.models import (
    EventAnalysis,
    RawNews,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
)
from finance_research_lab.radar_report import render_opportunity_radar
from finance_research_lab.workflow import run_radar_workflow


def test_run_radar_workflow_multiple_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: ToolResult("fetch_news", "success", RawNews(_headline_for_url(url), "Example", url)),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist: ToolResult("trace_news", "success", _report(news)),
    )
    watchlist = _watchlist_csv(tmp_path)
    output = tmp_path / "radar.md"

    run = run_radar_workflow(
        urls=["https://news.example.com/one", "https://news.example.com/two"],
        watchlist_path=watchlist,
        output_path=output,
    )

    assert run.run_name == "radar"
    assert run.steps[-1].step_name == "write_report"
    assert all(step.status == "success" for step in run.steps)
    markdown = output.read_text(encoding="utf-8")
    assert "AI capex expands" in markdown
    assert "Stablecoin policy advances" in markdown


def test_run_radar_workflow_one_url_fails(tmp_path, monkeypatch) -> None:
    def fetch(url: str) -> ToolResult:
        if url.endswith("/bad"):
            return ToolResult("fetch_news", "error", None, "network timeout")
        return ToolResult("fetch_news", "success", RawNews("AI capex expands", "Example", url))

    monkeypatch.setattr("finance_research_lab.workflow.fetch_news_tool", fetch)
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist: ToolResult("trace_news", "success", _report(news)),
    )
    output = tmp_path / "radar.md"

    run = run_radar_workflow(
        urls=["https://news.example.com/bad", "https://news.example.com/good"],
        watchlist_path=_watchlist_csv(tmp_path),
        output_path=output,
    )

    assert any(step.status == "error" for step in run.steps)
    assert run.steps[-1].step_name == "write_report"
    assert output.exists()
    assert "AI capex expands" in output.read_text(encoding="utf-8")


def test_run_radar_workflow_all_fail(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: ToolResult("fetch_news", "error", None, "network timeout"),
    )
    output = tmp_path / "radar.md"

    run = run_radar_workflow(
        urls=["https://news.example.com/one", "https://news.example.com/two"],
        watchlist_path=_watchlist_csv(tmp_path),
        output_path=output,
    )

    assert run.run_name == "radar"
    assert run.steps[-1].status == "error"
    assert not output.exists()


def test_radar_report_sections() -> None:
    long_term = _report(
        RawNews("AI capex expands", "Example", "https://news.example.com/ai"),
        stage="待判断",
        action_state="放观察池",
        impact=StockImpact(
            "300308.SZ",
            "中际旭创",
            "A股",
            "direct",
            "high",
            reasoning="直接受益于光模块需求",
        ),
    )
    short_term = _report(
        RawNews("Compute order lands", "Example", "https://news.example.com/order"),
        stage="启动",
        action_state="可小仓试",
        impact=StockImpact(
            "000063.SZ",
            "中兴通讯",
            "A股",
            "indirect",
            "medium",
            reasoning="订单验证产业趋势",
        ),
    )
    risk = _report(
        RawNews("Theme overheats", "Example", "https://news.example.com/hot"),
        stage="高潮",
        action_state="高潮勿追",
        impact=StockImpact(
            "601059.SH",
            "信达证券",
            "A股",
            "sentiment",
            "low",
            reasoning="低强度情绪映射",
        ),
    )

    markdown = render_opportunity_radar([long_term, short_term, risk], date(2026, 6, 24))

    assert "# 今日投资机会雷达 2026-06-24" in markdown
    assert "## 3. 中长线观察\n- 中际旭创（300308.SZ，A股）" in markdown
    assert "## 4. 短期交易机会\n- 中兴通讯（000063.SZ，A股）" in markdown
    assert "## 5. 高位不追 / 风险排除\n- 信达证券（601059.SH，A股）" in markdown
    assert markdown.count("找到最早官方来源或可靠媒体原文") == 1

    empty = render_opportunity_radar([], date(2026, 6, 24))
    assert "## 3. 中长线观察\n暂无" in empty
    assert "## 4. 短期交易机会\n暂无" in empty
    assert "## 5. 高位不追 / 风险排除\n暂无" in empty


def _watchlist_csv(tmp_path):
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,估值和拥挤交易\n",
        encoding="utf-8",
    )
    return watchlist


def _headline_for_url(url: str) -> str:
    if url.endswith("/two"):
        return "Stablecoin policy advances"
    return "AI capex expands"


def _report(
    news: RawNews,
    *,
    stage: str = "待判断",
    action_state: str = "放观察池",
    impact: StockImpact | None = None,
) -> ResearchReport:
    return ResearchReport(
        raw_news=news,
        event=EventAnalysis(
            event_type="资本开支 / 产能扩张",
            themes=("AI", "数据中心"),
            key_facts=("AI 资本开支继续增长",),
            source_quality="待复核",
            confidence="low",
            reasoning="测试报告",
        ),
        value_chain=ValueChainTrace(
            payer="云厂商",
            receiver="光模块供应链",
            chain_steps=("AI CapEx", "数据中心", "光模块"),
            impact_direction="positive",
            reasoning="测试链路",
        ),
        stock_impacts=(
            impact
            or StockImpact(
                "300308.SZ",
                "中际旭创",
                "A股",
                "direct",
                "high",
                reasoning="主题重合度较高",
            ),
        ),
        validation_tasks=(
            ValidationTask("找到最早官方来源或可靠媒体原文", "官方公告、监管文件或可靠媒体原文"),
            ValidationTask("找到最早官方来源或可靠媒体原文", "重复问题应去重"),
        ),
        stage=stage,
        action_state=action_state,
    )
