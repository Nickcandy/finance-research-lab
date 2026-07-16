from dataclasses import replace

import pytest

from finance_research_lab.models import (
    AShareCompany,
    FinancialSnapshot,
    MarketSnapshot,
    NewsItem,
    StockImpact,
)
from finance_research_lab.news_trace import build_research_report
from finance_research_lab.workflow import (
    _apply_tool_verification,
    _complete_candidate_evidence,
    _evidence_outputs,
    _research_tool_registry,
    run_news_trace_workflow,
    run_research_agent_workflow,
)


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
    assert run.steps[-1].status == "success"
    assert any("fallback" in step.summary for step in run.steps)
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
    monkeypatch.setattr("finance_research_lab.workflow.AkShareEvidenceProvider", _Provider)
    monkeypatch.setattr("finance_research_lab.workflow.BaoStockMarketProvider", _BaoStockProvider)
    watchlist = _watchlist_csv(tmp_path)
    output = tmp_path / "agent-report.md"

    run = run_research_agent_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=watchlist,
        output_path=output,
    )

    assert run.run_name == "research_agent"
    assert [step.step_name for step in run.steps][:7] == [
        "fetch_news",
        "read_watchlist",
        "read_a_share_universe",
        "classify_event",
        "plan_research_tasks",
        "trace_news",
        "build_evidence_plan",
    ]
    assert any(step.step_name.startswith("fetch_company_announcements:") for step in run.steps)
    assert any(step.step_name.startswith("fetch_financial_reports:") for step in run.steps)
    assert any(step.step_name.startswith("fetch_market_snapshot:") for step in run.steps)
    assert run.steps[-1].status == "success"
    assert any("fallback" in step.summary for step in run.steps)
    markdown = output.read_text(encoding="utf-8")
    assert "## Agent 执行摘要" in markdown
    assert "## 研究任务" in markdown
    assert "## Evidence-first 研究计划" in markdown
    assert "### 事件类型" in markdown
    assert "### 证据计划" in markdown
    assert "### 上下游 scale" in markdown
    assert "### 市场反应" in markdown
    assert "### 待补充" in markdown
    assert "## 证据列表" in markdown
    assert "https://news.example.com/ai-capex" in markdown
    assert "中际旭创" in markdown
    assert "股票池主题" in markdown
    assert "300308.SZ 2026-03-31" in markdown
    assert "来源：baostock" in markdown
    assert "unexpected keyword argument 'periods'" not in markdown


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


def test_research_agent_keeps_report_when_market_evidence_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finance_research_lab.tools.analyze_research_report_with_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("LLM_API_KEY is not set")),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.fetch_news_tool",
        lambda url: _successful_fetch(url),
    )
    monkeypatch.setattr("finance_research_lab.workflow.AkShareEvidenceProvider", _FailingMarketProvider)
    monkeypatch.setattr(
        "finance_research_lab.workflow.BaoStockMarketProvider", _FailingBaoStockProvider
    )
    output = tmp_path / "agent-report.md"

    run = run_research_agent_workflow(
        url="https://news.example.com/ai-capex",
        watchlist_path=_watchlist_csv(tmp_path),
        output_path=output,
    )

    assert output.exists()
    assert any(step.step_name.startswith("fetch_market_snapshot:") and step.status == "error" for step in run.steps)
    markdown = output.read_text(encoding="utf-8")
    assert "baostock:" in markdown
    assert "akshare: provider timeout" in markdown


def test_tool_verification_requires_relevance_company_and_market_evidence() -> None:
    report = _candidate_report()
    market = MarketSnapshot("300308.SZ", "2026-07-10", 100, 101, 99, 100, 0, 100, 1000, 5)

    market_only = _apply_tool_verification(report, (), (), (market,))
    complete = _apply_tool_verification(
        report,
        (),
        (FinancialSnapshot("300308.SZ", "2026-03-31", revenue=100),),
        (market,),
    )

    assert market_only.stock_impacts[0].verification_status == "unverified"
    assert complete.stock_impacts[0].verification_status == "verified"
    assert complete.stock_impacts[0].verification_source == "AkShare company and market evidence"


def test_tool_verification_reports_fallback_market_source() -> None:
    report = _candidate_report()
    financial = FinancialSnapshot("300308.SZ", "2026-03-31", revenue=100)
    market = MarketSnapshot(
        "300308.SZ", "2026-07-10", 100, 101, 99, 100, 0, 100, 1000, 5, provider="akshare"
    )

    verified = _apply_tool_verification(report, (), (financial,), (market,))

    assert verified.stock_impacts[0].verification_source == "AkShare company and akshare market evidence"


def test_tool_verification_preserves_excluded_candidates() -> None:
    report = _candidate_report(verification_status="excluded")

    verified = _apply_tool_verification(report, (), (), ())

    assert verified.stock_impacts[0].verification_status == "excluded"


@pytest.mark.parametrize(
    ("impact_type", "impact_strength", "expected"),
    [
        ("direct", "medium", "verified"),
        ("negative", "high", "verified"),
        ("indirect", "low", "unverified"),
        ("sentiment", "high", "unverified"),
        ("direct", "unknown", "unverified"),
        ("false_positive", "low", "excluded"),
    ],
)
def test_tool_verification_applies_event_relevance_gate(
    impact_type,
    impact_strength,
    expected,
) -> None:
    report = _candidate_report(impact_type=impact_type, impact_strength=impact_strength)
    financial = FinancialSnapshot("300308.SZ", "2026-03-31", revenue=100)
    market = MarketSnapshot("300308.SZ", "2026-07-10", 100, 101, 99, 100, 0, 100, 1000, 5)

    verified = _apply_tool_verification(report, (), (financial,), (market,))

    assert verified.stock_impacts[0].verification_status == expected


def test_missing_model_calls_are_completed_with_company_and_market_evidence() -> None:
    steps = []

    results, warnings = _complete_candidate_evidence(
        _research_tool_registry(_Provider()),
        ("300308.SZ",),
        (),
        {},
        steps,
    )
    announcements, financials, markets = _evidence_outputs(results)

    assert announcements == ()
    assert financials[0].symbol == "300308.SZ"
    assert markets[0].symbol == "300308.SZ"
    assert warnings == []
    assert [step.step_name for step in steps] == [
        "fetch_financial_reports:300308.SZ",
        "fetch_market_snapshot:300308.SZ",
    ]


def test_completed_candidate_evidence_is_reused_within_a_run() -> None:
    steps = []
    attempted = {}

    first, first_warnings = _complete_candidate_evidence(
        _research_tool_registry(_Provider()),
        ("300308.SZ",),
        (),
        attempted,
        steps,
    )
    second, second_warnings = _complete_candidate_evidence(
        _research_tool_registry(_Provider()),
        ("300308.SZ",),
        first,
        attempted,
        steps,
    )

    assert second == first
    assert first_warnings == second_warnings == []
    assert [step.step_name for step in steps] == [
        "fetch_financial_reports:300308.SZ",
        "fetch_market_snapshot:300308.SZ",
    ]


def test_empty_company_evidence_remains_missing_and_visible() -> None:
    steps = []

    results, warnings = _complete_candidate_evidence(
        _research_tool_registry(_EmptyCompanyProvider()),
        ("300308.SZ",),
        (),
        {},
        steps,
    )
    announcements, financials, markets = _evidence_outputs(results)

    assert announcements == ()
    assert financials == ()
    assert markets[0].symbol == "300308.SZ"
    assert warnings == ["300308.SZ 缺少非空公司公告或财报证据。"]


def _successful_fetch(url: str):
    from finance_research_lab.agent_models import ToolResult

    return ToolResult(
        "fetch_news",
        "success",
        NewsItem(
            headline="AI data center capex increases optical module demand",
            source="Example News",
            url=url,
            published_at="2026-06-22T10:00:00Z",
            body="Microsoft increased AI data center spending and optical module demand.",
        ),
    )


def _candidate_report(
    verification_status="verified",
    impact_type="direct",
    impact_strength="medium",
):
    news = NewsItem("AI capex", "test", body="AI optical module demand")
    report = build_research_report(
        news,
        [],
        [AShareCompany("300308.SZ", "中际旭创", "A股", themes=("AI", "光模块"))],
        proposed_impacts=(
            StockImpact(
                "300308.SZ",
                "中际旭创",
                "A股",
                impact_type,
                impact_strength,
                verification_status=verification_status,
            ),
        ),
    )
    impact = replace(
        report.stock_impacts[0],
        impact_type=impact_type,
        impact_strength=impact_strength,
        verification_status=verification_status,
    )
    return replace(report, stock_impacts=(impact,))


def _watchlist_csv(tmp_path):
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,估值和拥挤交易\n",
        encoding="utf-8",
    )
    return watchlist


class _Provider:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def announcements(self, symbol, start_date="", end_date=""):
        from finance_research_lab.models import CompanyAnnouncement

        return (
            CompanyAnnouncement(symbol, "真实公告", "日常经营", "2026-06-01", "https://cninfo.example/a"),
        )

    def financials(self, symbol):
        from finance_research_lab.models import FinancialSnapshot

        return (FinancialSnapshot(symbol, "2026-03-31", revenue=100.0, net_profit=10.0),)

    def market(self, symbol, lookback_days):
        from finance_research_lab.models import MarketSnapshot

        return MarketSnapshot(
            symbol, "2026-06-10", 100.0, 105.0, 99.0, 104.0, 2.0, 200.0, 1000.0, lookback_days
        )


class _FailingMarketProvider(_Provider):
    def market(self, symbol, lookback_days):
        raise RuntimeError("provider timeout")


class _BaoStockProvider(_Provider):
    def market(self, symbol, lookback_days):
        return replace(super().market(symbol, lookback_days), provider="baostock")


class _FailingBaoStockProvider(_Provider):
    def market(self, symbol, lookback_days):
        raise RuntimeError("baostock timeout")


class _EmptyCompanyProvider(_Provider):
    def announcements(self, symbol, start_date="", end_date=""):
        return ()

    def financials(self, symbol):
        return ()
