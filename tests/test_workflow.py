from finance_research_lab.models import RawNews
from finance_research_lab.workflow import run_news_trace_workflow


def test_run_news_trace_workflow_records_agent_steps(
    tmp_path,
    monkeypatch,
) -> None:
    def missing_agent_config(*args, **kwargs):
        raise ValueError("LLM_API_KEY is not set")

    monkeypatch.setattr(
        "finance_research_lab.tools.analyze_research_report_with_agent",
        missing_agent_config,
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: _successful_fetch(url),
    )
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,估值和拥挤交易\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.md"

    run = run_news_trace_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=watchlist,
        output_path=output,
    )

    assert run.run_name == "news_trace"
    assert [step.step_name for step in run.steps] == [
        "fetch_news",
        "read_watchlist",
        "trace_news",
        "render_report",
        "write_report",
    ]
    assert all(step.status == "success" for step in run.steps)
    assert "agent fallback" in run.steps[2].summary
    assert output.exists()
    markdown = output.read_text(encoding="utf-8")
    assert "## 2. 事件理解" in markdown
    assert "中际旭创" in markdown


def test_run_news_trace_workflow_stops_on_missing_watchlist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: _successful_fetch(url),
    )
    output = tmp_path / "report.md"

    run = run_news_trace_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=tmp_path / "missing.csv",
        output_path=output,
    )

    assert [step.step_name for step in run.steps] == ["fetch_news", "read_watchlist"]
    assert run.steps[1].status == "error"
    assert not output.exists()


def _successful_fetch(url: str):
    from finance_research_lab.agent_models import ToolResult

    return ToolResult(
        "fetch_news",
        "success",
        RawNews(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            url=url,
            published_at="2026-06-22T10:00:00Z",
            body="Microsoft increased AI data center spending and optical module demand.",
        ),
    )
