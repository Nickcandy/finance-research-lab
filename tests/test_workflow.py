from finance_research_lab.models import RawNews
from finance_research_lab.workflow import run_news_trace_workflow, run_research_agent_workflow


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
        "read_a_share_universe",
        "trace_news",
        "render_report",
        "write_report",
    ]
    assert all(step.status == "success" for step in run.steps)
    assert "agent fallback" in run.steps[3].summary
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


def test_run_news_trace_workflow_stops_on_missing_a_share_universe(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: _successful_fetch(url),
    )
    output = tmp_path / "report.md"

    run = run_news_trace_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=_watchlist_csv(tmp_path),
        a_share_universe_path=tmp_path / "missing-universe.csv",
        output_path=output,
    )

    assert [step.step_name for step in run.steps] == [
        "fetch_news",
        "read_watchlist",
        "read_a_share_universe",
    ]
    assert run.steps[2].status == "error"
    assert not output.exists()


def test_run_research_agent_workflow_writes_tasks_evidence_and_report(tmp_path, monkeypatch) -> None:
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
    watchlist = _watchlist_csv(tmp_path)
    output = tmp_path / "agent-report.md"

    run = run_research_agent_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=watchlist,
        output_path=output,
    )

    assert run.run_name == "research_agent"
    assert [step.step_name for step in run.steps] == [
        "fetch_news",
        "read_watchlist",
        "read_a_share_universe",
        "plan_research_tasks",
        "trace_news",
        "collect_evidence",
        "render_agent_report",
        "write_report",
    ]
    assert all(step.status == "success" for step in run.steps)
    markdown = output.read_text(encoding="utf-8")
    assert "## Agent 执行摘要" in markdown
    assert "## 研究任务" in markdown
    assert "## 证据列表" in markdown
    assert "https://news.example.com/ai-capex" in markdown
    assert "中际旭创" in markdown
    assert "股票池主题" in markdown


def test_run_research_agent_workflow_stops_when_fetch_fails(tmp_path, monkeypatch) -> None:
    from finance_research_lab.agent_models import ToolResult

    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: ToolResult("fetch_news", "error", None, "network timeout"),
    )
    output = tmp_path / "agent-report.md"

    run = run_research_agent_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=_watchlist_csv(tmp_path),
        output_path=output,
    )

    assert [step.step_name for step in run.steps] == ["fetch_news"]
    assert run.steps[0].status == "error"
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


def _watchlist_csv(tmp_path):
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,估值和拥挤交易\n",
        encoding="utf-8",
    )
    return watchlist
