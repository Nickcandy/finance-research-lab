from finance_research_lab.workflow import run_news_trace_workflow


def test_run_news_trace_workflow_records_agent_steps(tmp_path) -> None:
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,估值和拥挤交易\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.md"

    run = run_news_trace_workflow(
        headline="AI data center capex increases optical module demand",
        source="example",
        watchlist_path=watchlist,
        output_path=output,
    )

    assert run.run_name == "news_trace"
    assert [step.step_name for step in run.steps] == [
        "read_watchlist",
        "trace_news",
        "render_report",
        "write_report",
    ]
    assert all(step.status == "success" for step in run.steps)
    assert output.exists()
    assert "中际旭创" in output.read_text(encoding="utf-8")


def test_run_news_trace_workflow_stops_on_missing_watchlist(tmp_path) -> None:
    output = tmp_path / "report.md"

    run = run_news_trace_workflow(
        headline="稳定币监管框架推进",
        source="manual",
        watchlist_path=tmp_path / "missing.csv",
        output_path=output,
    )

    assert [step.step_name for step in run.steps] == ["read_watchlist"]
    assert run.steps[0].status == "error"
    assert not output.exists()
