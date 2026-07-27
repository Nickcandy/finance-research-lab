from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from finance_research_lab.agent_models import ToolResult
from finance_research_lab.claim_pipeline import (
    ClaimBatchResult,
    ClaimPipelineResult,
    stable_news_item_id,
)
from finance_research_lab.claims import Claim
from finance_research_lab.daily_radar_report import render_daily_event_radar
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.llm.chat_completions_client import ChatCompletionsClient
from finance_research_lab.llm.usage import LLMUsageSession
from finance_research_lab.models import (
    EventAnalysis,
    FinancialSnapshot,
    MarketEvent,
    MarketSnapshot,
    NewsItem,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
)
from finance_research_lab.workflow import run_daily_radar_workflow

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_daily_radar_shares_usage_session_and_scopes_event_calls(
    tmp_path,
    monkeypatch,
) -> None:
    captured = {}

    def trace(news, watchlist, universe, **kwargs):
        del watchlist, universe
        captured.update(kwargs)
        return ToolResult("trace_news", "success", _report(news))

    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    _force_pro_claims(monkeypatch)
    monkeypatch.setattr("finance_research_lab.workflow.trace_news_tool", trace)
    watchlist, universe = _research_inputs(tmp_path)
    usage = LLMUsageSession(
        "daily_radar",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
    )
    usage.record_success(
        operation="research_report",
        model="deepseek-v4-flash",
        input_tokens=100,
        output_tokens=20,
    )
    client = ChatCompletionsClient(usage_session=usage)
    output = tmp_path / "daily-radar.md"

    run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        llm_client=client,
    )

    assert captured["client"] is client
    assert captured["scope_id"].startswith("evt_")
    assert "## LLM 使用与费用" in output.read_text(encoding="utf-8")


def test_render_daily_event_radar_has_stable_sections_and_all_sources() -> None:
    events = (
        MarketEvent(
            "AI 算力中心投产",
            (
                _news(
                    "AI 算力中心投产",
                    "2026-07-16T11:00:00+08:00",
                    source="官方媒体",
                    url="https://example.com/official",
                ),
                _news(
                    "算力中心正式运行",
                    "2026-07-16T10:00:00+08:00",
                    source="同花顺财经直播",
                    url="https://example.com/ths",
                ),
                _news(
                    "重复来源确认",
                    "2026-07-16T09:00:00+08:00",
                    source="同花顺财经直播",
                    url="https://example.com/ths",
                ),
            ),
        ),
        MarketEvent("无链接事件", (_news("无链接事件", "", source="同花顺财经直播"),)),
    )

    markdown = render_daily_event_radar(
        events,
        datetime(2026, 7, 15, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 16, 12, tzinfo=SHANGHAI),
    )

    assert "# 今日 A股投资研究雷达 2026-07-16" in markdown
    assert "2026-07-15T12:00:00+08:00 至 2026-07-16T12:00:00+08:00" in markdown
    assert "> 热点事件数：2" in markdown
    assert "> 用途：研究辅助，不构成投资建议。" in markdown
    assert "### 1.1 AI 算力中心投产" in markdown
    assert "- 最新时间：2026-07-16T11:00:00+08:00" in markdown
    assert "- 报道数量：3" in markdown
    assert "- 独立来源：2（官方媒体 / 同花顺财经直播）" in markdown
    assert markdown.count("https://example.com/ths") == 1
    assert "https://example.com/official" in markdown
    assert "### 1.2 无链接事件" in markdown
    assert "  - 暂无可用 URL" in markdown
    for section in (
        "## 2. 已校验 A股候选",
        "## 3. 待确认候选",
        "## 4. 风险排除 / 伪相关",
        "## 5. Watchlist 命中",
        "## 6. 明日验证任务",
        "## 7. 待复盘记录",
    ):
        assert section in markdown
    assert markdown.count("暂无（Task 5/6 尚未接入）") == 6


def test_render_daily_event_radar_rejects_empty_or_invalid_input() -> None:
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    with pytest.raises(ValueError, match="events"):
        render_daily_event_radar((), start, end)
    with pytest.raises(ValueError, match="window"):
        render_daily_event_radar((_event("事件", end),), end, start)
    with pytest.raises(ValueError, match="items"):
        render_daily_event_radar((MarketEvent("空事件", ()),), start, end)


def test_render_daily_event_radar_fills_research_sections() -> None:
    news = _news(
        "AI 算力中心投产",
        "2026-07-16T11:00:00+08:00",
        url="https://example.com/event",
    )
    event = MarketEvent(news.headline, (news,))
    verified = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "high",
        reasoning="光模块需求可能受益",
        evidence=("公司财报与行情证据齐全",),
        risks=("需求不及预期",),
        verification_source="AkShare company and baostock market evidence",
        watchlist_hit=True,
    )
    report = _report(news, (verified,))

    markdown = render_daily_event_radar(
        (event,),
        datetime(2026, 7, 15, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 16, 12, tzinfo=SHANGHAI),
        (report,),
    )

    assert "- 事件类型：资本开支 / 产能扩张" in markdown
    assert "- 主题：AI / 数据中心" in markdown
    assert "- 产业链：AI CapEx -> 数据中心 -> 光模块" in markdown
    assert "## 2. 已校验 A股候选\n\n- 中际旭创（300308.SZ，A股）" in markdown
    assert "校验：AkShare company and baostock market evidence" in markdown
    assert "证据：公司财报与行情证据齐全" in markdown
    assert "风险：需求不及预期" in markdown
    assert "## 5. Watchlist 命中\n\n- 中际旭创（300308.SZ，A股）" in markdown
    assert "- [ ] 找到公司公告" in markdown
    assert "Task 5/6 尚未接入" not in markdown


def test_render_daily_event_radar_keeps_false_positives_out_of_a_share_candidates() -> None:
    news = _news("海外监管事件", "2026-07-16T11:00:00+08:00")
    event = MarketEvent(news.headline, (news,))
    false_positive = StockImpact(
        "603259.SH",
        "药明康德",
        "A股",
        "false_positive",
        "low",
        reasoning="与事件无关",
        verification_status="unverified",
        watchlist_hit=True,
    )
    overseas = StockImpact(
        "COIN",
        "Coinbase",
        "美股",
        "indirect",
        "low",
        verification_status="unverified",
        watchlist_hit=True,
    )

    markdown = render_daily_event_radar(
        (event,),
        datetime(2026, 7, 15, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 16, 12, tzinfo=SHANGHAI),
        (_report(news, (false_positive, overseas)),),
    )

    assert "## 3. 待确认候选\n\n暂无" in markdown
    assert "## 4. 风险排除 / 伪相关\n\n- 药明康德（603259.SH，A股）" in markdown
    assert "## 5. Watchlist 命中\n\n- 药明康德（603259.SH，A股）" in markdown
    assert "Coinbase" not in markdown


@pytest.mark.parametrize(
    ("as_of", "expected_until"),
    [
        (datetime(2026, 7, 16, 12), datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)),
        (
            datetime(2026, 7, 16, 4, tzinfo=timezone.utc),
            datetime(2026, 7, 16, 12, tzinfo=SHANGHAI),
        ),
    ],
)
def test_daily_radar_workflow_scores_all_events_without_forcing_pro(
    tmp_path,
    monkeypatch,
    as_of: datetime,
    expected_until: datetime,
) -> None:
    captured: dict[str, object] = {}

    class Source:
        name = "ths_global_news"

        def __init__(self, cache_dir) -> None:
            captured["cache_dir"] = cache_dir

        def fetch(self, since, until):
            captured["since"] = since
            captured["until"] = until
            return tuple(
                _news(
                    f"事件 {index}",
                    f"2026-07-16T{index + 5:02d}:00:00+08:00",
                    url=f"https://example.com/{index}",
                )
                for index in range(6)
            )

    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", Source)
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult("trace_news", "success", _report(news)),
    )
    output = tmp_path / "daily-radar.md"
    cache = tmp_path / "cache"
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        output,
        cache,
        as_of,
        watchlist_path=watchlist,
        a_share_universe_path=universe,
    )

    assert run.run_name == "daily_radar"
    assert [step.step_name for step in run.steps[:5]] == [
        "fetch_event_source",
        "cluster_market_events",
        "rank_hot_events",
        "read_watchlist",
        "read_a_share_universe",
    ]
    assert sum(step.step_name.startswith("route_event:") for step in run.steps) == 6
    assert sum(step.step_name.startswith("analyze_event:") for step in run.steps) == 0
    assert [step.step_name for step in run.steps[-2:]] == ["render_daily_radar", "write_report"]
    assert all(step.status == "success" for step in run.steps)
    assert [step.summary for step in run.steps[:3]] == ["6 item(s)", "6 item(s)", "6 item(s)"]
    assert captured == {
        "cache_dir": cache,
        "since": expected_until.replace(day=15),
        "until": expected_until,
    }
    markdown = output.read_text(encoding="utf-8")
    assert "事件 5" in markdown
    assert "事件 1" in markdown
    assert "事件 0" in markdown


def test_daily_radar_workflow_verifies_candidates_with_company_and_market_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    _force_pro_claims(monkeypatch)
    impact = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "high",
        reasoning="AI 光模块供应链",
        watchlist_hit=True,
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult(
            "trace_news", "success", _report(news, (impact,))
        ),
    )

    class CompanyProvider:
        def __init__(self, cache, refresh=False) -> None:
            pass

        def financials(self, symbol):
            return (FinancialSnapshot(symbol, "2026-03-31", revenue=100),)

        def announcements(self, symbol, start_date="", end_date=""):
            return ()

        def market(self, symbol, lookback_days):
            raise AssertionError("fallback should not run")

    class MarketProvider:
        def __init__(self, cache, refresh=False) -> None:
            pass

        def market(self, symbol, lookback_days):
            return MarketSnapshot(
                symbol,
                "2026-07-16",
                100,
                102,
                99,
                101,
                1,
                1000,
                10000,
                lookback_days,
                provider="baostock",
            )

    monkeypatch.setattr("finance_research_lab.workflow.AkShareEvidenceProvider", CompanyProvider)
    monkeypatch.setattr("finance_research_lab.workflow.BaoStockMarketProvider", MarketProvider)
    watchlist, universe = _research_inputs(tmp_path)
    output = tmp_path / "daily-radar.md"

    run = run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        evidence_cache_path=tmp_path / "evidence",
        market_cache_path=tmp_path / "market",
    )

    assert run.steps[-1].status == "success"
    assert any(step.step_name == "fetch_financial_reports:300308.SZ" for step in run.steps)
    assert any(step.step_name == "fetch_market_snapshot:300308.SZ" for step in run.steps)
    markdown = output.read_text(encoding="utf-8")
    assert "## 2. 已校验 A股候选\n\n- 中际旭创（300308.SZ，A股）" in markdown
    assert "AkShare company and baostock market evidence" in markdown
    assert "## 8. 重大事件榜" in markdown
    assert "## 9. 重点股票榜" in markdown
    assert "## 10. 高影响待核验" in markdown
    assert "## 11. Watchlist 风险预警" in markdown
    assert "影响分表示研究优先级，不是收益预测" in markdown


def test_daily_radar_snapshot_keeps_and_routes_all_researchable_events(
    tmp_path,
    monkeypatch,
) -> None:
    class Source:
        def __init__(self, cache_dir) -> None:
            pass

        def fetch(self, since, until):
            return tuple(
                _news(f"事件 {index}", f"2026-07-16T{index + 5:02d}:00:00+08:00")
                for index in range(6)
            )

    analyzed: list[str] = []

    def trace(news, watchlist, universe):
        analyzed.append(news.headline)
        return ToolResult("trace_news", "success", _report(news))

    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", Source)
    monkeypatch.setattr("finance_research_lab.workflow.trace_news_tool", trace)
    watchlist, universe = _research_inputs(tmp_path)
    snapshot_path = tmp_path / "daily-radar.json"

    run_daily_radar_workflow(
        tmp_path / "daily-radar.md",
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        json_output_path=snapshot_path,
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert len(payload["all_events"]) == 6
    assert len(payload["events"]) == 6
    assert payload["summary"]["total_event_count"] == 6
    assert payload["summary"]["core_event_count"] == 6
    assert len(analyzed) == 0
    catalog = json.loads(
        (tmp_path / "event-catalogs" / f"{payload['run']['id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(catalog["events"]) == 6


def test_daily_radar_keeps_pure_price_event_but_skips_its_analysis(
    tmp_path,
    monkeypatch,
) -> None:
    pure_price = NewsItem(
        "中际旭创盘中涨超10%",
        "同花顺",
        published_at="2026-07-16T11:59:00+08:00",
        body="股价盘中涨超10%，成交额超50亿元。",
    )

    class Source:
        def __init__(self, cache_dir) -> None:
            pass

        def fetch(self, since, until):
            causal = tuple(
                _news(
                    f"公司 {index} 公告获得订单",
                    f"2026-07-16T{index + 5:02d}:00:00+08:00",
                )
                for index in range(6)
            )
            return (pure_price, *causal)

    analyzed: list[str] = []

    def trace(news, watchlist, universe):
        analyzed.append(news.headline)
        return ToolResult("trace_news", "success", _report(news))

    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", Source)
    monkeypatch.setattr("finance_research_lab.workflow.trace_news_tool", trace)
    watchlist, universe = _research_inputs(tmp_path)
    snapshot_path = tmp_path / "daily-radar.json"

    run_daily_radar_workflow(
        tmp_path / "daily-radar.md",
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        json_output_path=snapshot_path,
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    pure_summary = next(
        event for event in payload["all_events"] if event["title"] == pure_price.headline
    )
    assert pure_summary["analysis_status"] == "not_applicable"
    assert pure_summary["exclusion_reason"] == "pure_stock_price_update"
    assert pure_price.headline not in analyzed
    assert pure_price.headline not in {event["title"] for event in payload["events"]}
    assert len(analyzed) == 0


def test_daily_radar_does_not_fetch_evidence_for_unresolved_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    unresolved = StockImpact(
        "300391.SZ",
        "德明利",
        "A股",
        "direct",
        "high",
        verification_status="unverified",
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult(
            "trace_news", "success", _report(news, (unresolved,))
        ),
    )

    class Provider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def financials(self, symbol):
            raise AssertionError(f"unexpected evidence request for {symbol}")

        announcements = financials
        market = financials

    monkeypatch.setattr("finance_research_lab.workflow.AkShareEvidenceProvider", Provider)
    monkeypatch.setattr("finance_research_lab.workflow.BaoStockMarketProvider", Provider)
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        tmp_path / "daily-radar.md",
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
    )

    assert run.steps[-1].status == "success"


def test_daily_radar_workflow_writes_optional_frontend_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    _force_pro_claims(monkeypatch)
    impact = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "low",
        reasoning="AI 光模块供应链",
        verification_status="unverified",
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult(
            "trace_news", "success", _report(news, (impact,))
        ),
    )
    watchlist, universe = _research_inputs(tmp_path)
    output = tmp_path / "daily-radar.md"
    snapshot_path = tmp_path / "daily-radar.json"

    run = run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        json_output_path=snapshot_path,
    )

    assert run.steps[-1].step_name == "write_snapshot"
    assert run.steps[-1].status == "success"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2.2"
    assert payload["events"][0]["analysis_tier"] == "pro"
    assert payload["events"][0]["event_importance"] >= 0
    assert payload["summary"]["scoring_version"] == "1.1"
    assert payload["events"][0]["title"] == "事件"
    assert payload["all_events"][0]["title"] == "事件"
    assert (tmp_path / "event-catalogs" / f"{payload['run']['id']}.json").is_file()
    assert (
        tmp_path
        / "point-in-time"
        / payload["run"]["id"]
        / "scoring-1.1.json"
    ).is_file()
    pit_payload = json.loads(
        (
            tmp_path
            / "point-in-time"
            / payload["run"]["id"]
            / "scoring-1.1.json"
        ).read_text(encoding="utf-8")
    )
    assert pit_payload["snapshot"]["run"]["id"] == payload["run"]["id"]
    assert pit_payload["event_catalog_path"] == (
        f"event-catalogs/{payload['run']['id']}.json"
    )
    event_id = payload["events"][0]["id"]
    assert (tmp_path / "event-analyses" / payload["run"]["id"] / f"{event_id}.json").is_file()
    assert payload["candidate_groups"]["unverified"][0]["symbol"] == "300308.SZ"
    assert payload["run"]["steps"][-1]["step_name"] == "write_report"


def test_daily_radar_snapshot_failure_preserves_previous_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult("trace_news", "success", _report(news)),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.write_daily_radar_snapshot",
        lambda payload, path: (_ for _ in ()).throw(OSError("snapshot disk full")),
    )
    watchlist, universe = _research_inputs(tmp_path)
    output = tmp_path / "daily-radar.md"
    snapshot_path = tmp_path / "daily-radar.json"
    snapshot_path.write_text("old snapshot", encoding="utf-8")

    run = run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        json_output_path=snapshot_path,
    )

    assert output.exists()
    assert run.steps[-1].step_name == "write_snapshot"
    assert run.steps[-1].status == "error"
    assert "snapshot disk full" in run.steps[-1].summary
    assert snapshot_path.read_text(encoding="utf-8") == "old snapshot"


def test_daily_radar_workflow_reports_source_failure_without_overwriting(tmp_path, monkeypatch) -> None:
    class Source:
        name = "ths_global_news"

        def __init__(self, cache_dir) -> None:
            pass

        def fetch(self, since, until):
            raise RuntimeError("network down")

    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", Source)
    output = tmp_path / "daily-radar.md"
    output.write_text("old report", encoding="utf-8")

    run = run_daily_radar_workflow(output, as_of=datetime(2026, 7, 16, 12))

    assert [step.step_name for step in run.steps] == ["fetch_event_source"]
    assert run.steps[0].status == "error"
    assert "network down" in run.steps[0].summary
    assert output.read_text(encoding="utf-8") == "old report"


def test_daily_radar_workflow_empty_source_stops_at_rank_without_overwriting(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _empty_source)
    output = tmp_path / "daily-radar.md"
    output.write_text("old report", encoding="utf-8")

    run = run_daily_radar_workflow(output, as_of=datetime(2026, 7, 16, 12))

    assert [step.step_name for step in run.steps] == [
        "fetch_event_source",
        "cluster_market_events",
        "rank_hot_events",
    ]
    assert [step.status for step in run.steps] == ["success", "success", "error"]
    assert run.steps[-1].summary == "no market events found"
    assert output.read_text(encoding="utf-8") == "old report"


@pytest.mark.parametrize(
    ("target", "failure", "expected_steps"),
    [
        (
            "cluster_market_events",
            "cluster failed",
            ("fetch_event_source", "cluster_market_events"),
        ),
        (
            "render_daily_event_radar",
            "render failed",
                (
                    "fetch_event_source",
                    "cluster_market_events",
                    "rank_hot_events",
                    "read_watchlist",
                    "read_a_share_universe",
                    "score_all_market_events",
                    "route_event:1",
                    "render_daily_radar",
                ),
        ),
    ],
)
def test_daily_radar_workflow_stops_on_processing_failure(
    tmp_path,
    monkeypatch,
    target: str,
    failure: str,
    expected_steps: tuple[str, ...],
) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult("trace_news", "success", _report(news)),
    )
    monkeypatch.setattr(
        f"finance_research_lab.workflow.{target}",
        lambda *args: (_ for _ in ()).throw(RuntimeError(failure)),
    )
    output = tmp_path / "daily-radar.md"
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
    )

    assert tuple(step.step_name for step in run.steps) == expected_steps
    assert run.steps[-1].status == "error"
    assert failure in run.steps[-1].summary
    assert not output.exists()


def test_daily_radar_workflow_records_write_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("finance_research_lab.workflow.ThsNewsSource", _one_item_source)
    monkeypatch.setattr(
        "finance_research_lab.workflow.trace_news_tool",
        lambda news, watchlist, universe: ToolResult("trace_news", "success", _report(news)),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.write_report_tool",
        lambda markdown, output: ToolResult("write_report", "error", str(output), "disk full"),
    )
    output = tmp_path / "daily-radar.md"
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        output,
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
    )

    assert len(run.steps) == 9
    assert run.steps[-1].step_name == "write_report"
    assert run.steps[-1].status == "error"
    assert run.steps[-1].summary == "disk full"
    assert not output.exists()


def test_daily_radar_pro_events_isolate_scope_and_reuse_company_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    items = (
        _news("事件 A", "2026-07-16T11:00:00+08:00", url="https://example.com/a"),
        _news("事件 B", "2026-07-16T10:00:00+08:00", url="https://example.com/b"),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.ThsNewsSource",
        lambda cache_dir: type(
            "Source",
            (),
            {"fetch": lambda self, since, until: items},
        )(),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.cluster_market_events",
        lambda news_items: tuple(MarketEvent(item.headline, (item,)) for item in news_items),
    )
    _force_pro_claims(monkeypatch)
    scopes = []
    impact = StockImpact("300308.SZ", "中际旭创", "A股", "direct", "high")

    def trace(news, watchlist, universe, **kwargs):
        del watchlist, universe
        scopes.append(kwargs["scope_id"])
        return ToolResult("trace_news", "success", _report(news, (impact,)))

    monkeypatch.setattr("finance_research_lab.workflow.trace_news_tool", trace)
    calls = {"financials": 0, "market": 0}

    class CompanyProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def financials(self, symbol):
            calls["financials"] += 1
            return (FinancialSnapshot(symbol, "2025-12-31", revenue=100),)

        def announcements(self, symbol, start_date="", end_date=""):
            return ()

    class MarketProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def market(self, symbol, lookback_days):
            calls["market"] += 1
            return MarketSnapshot(
                symbol,
                "2026-07-16",
                100,
                102,
                99,
                101,
                1,
                1000,
                10000,
                lookback_days,
            )

    monkeypatch.setattr("finance_research_lab.workflow.AkShareEvidenceProvider", CompanyProvider)
    monkeypatch.setattr("finance_research_lab.workflow.BaoStockMarketProvider", MarketProvider)
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        tmp_path / "daily-radar.md",
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
        llm_client=ChatCompletionsClient(),
    )

    assert run.steps[-1].status == "success"
    assert len(scopes) == 2
    assert len(set(scopes)) == 2
    assert calls == {"financials": 1, "market": 1}


def test_daily_radar_pro_failure_downgrades_only_current_event(
    tmp_path,
    monkeypatch,
) -> None:
    items = (
        _news("失败事件", "2026-07-16T11:00:00+08:00"),
        _news("成功事件", "2026-07-16T10:00:00+08:00"),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.ThsNewsSource",
        lambda cache_dir: type(
            "Source",
            (),
            {"fetch": lambda self, since, until: items},
        )(),
    )
    monkeypatch.setattr(
        "finance_research_lab.workflow.cluster_market_events",
        lambda news_items: tuple(MarketEvent(item.headline, (item,)) for item in news_items),
    )
    _force_pro_claims(monkeypatch)

    def trace(news, watchlist, universe, **kwargs):
        del watchlist, universe, kwargs
        if news.headline == "失败事件":
            return ToolResult("trace_news", "error", None, "pro unavailable")
        return ToolResult("trace_news", "success", _report(news))

    monkeypatch.setattr("finance_research_lab.workflow.trace_news_tool", trace)
    watchlist, universe = _research_inputs(tmp_path)

    run = run_daily_radar_workflow(
        tmp_path / "daily-radar.md",
        as_of=datetime(2026, 7, 16, 12),
        watchlist_path=watchlist,
        a_share_universe_path=universe,
    )

    analyze_steps = [
        step for step in run.steps if step.step_name.startswith("analyze_event:")
    ]
    assert [step.status for step in analyze_steps] == ["error", "success"]
    assert run.steps[-1].step_name == "write_report"
    assert run.steps[-1].status == "success"


def _news(
    headline: str,
    published_at: str,
    *,
    source: str = "同花顺财经直播",
    url: str = "",
) -> NewsItem:
    return NewsItem(headline, source, url, published_at)


def _event(title: str, published_at: datetime) -> MarketEvent:
    return MarketEvent(title, (_news(title, published_at.isoformat()),))


def _report(
    news: NewsItem,
    impacts: tuple[StockImpact, ...] = (),
) -> ResearchReport:
    return ResearchReport(
        raw_news=news,
        event=EventAnalysis(
            "资本开支 / 产能扩张",
            themes=("AI", "数据中心"),
            key_facts=("AI 资本开支增加",),
            reasoning="结构化研究结果",
        ),
        value_chain=ValueChainTrace(
            "云厂商",
            "光模块供应链",
            ("AI CapEx", "数据中心", "光模块"),
            "positive",
            "供应链需求传导",
        ),
        stock_impacts=impacts,
        validation_tasks=(ValidationTask("找到公司公告", "公告、财报和行情"),),
        stage="待判断",
        action_state="等验证",
    )


def _research_inputs(tmp_path):
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,market,themes,thesis,risks\n"
        "300308.SZ,中际旭创,A股,AI;数据中心;光模块,AI光模块供应链,需求不及预期\n",
        encoding="utf-8",
    )
    universe = tmp_path / "universe.csv"
    universe.write_text(
        "symbol,name,market,industry,themes,business_summary,source\n"
        "300308.SZ,中际旭创,A股,通信设备,AI;数据中心;光模块,高速光模块供应商,test\n",
        encoding="utf-8",
    )
    return watchlist, universe


def _empty_source(cache_dir):
    return type("Source", (), {"name": "ths_global_news", "fetch": lambda self, since, until: ()})()


def _one_item_source(cache_dir):
    item = _news("事件", "2026-07-16T11:00:00+08:00", url="https://example.com/event")
    return type(
        "Source",
        (),
        {"name": "ths_global_news", "fetch": lambda self, since, until: (item,)},
    )()


def _force_pro_claims(monkeypatch) -> None:
    def extract(_self, events):
        claims = tuple(
            Claim(
                id=f"claim:{market_event_id(event)}",
                event_id=market_event_id(event),
                source_item_ids=(stable_news_item_id(event.items[0]),),
                subject="中际旭创",
                predicate="发生",
                object="实际控制人发生变更",
                claim_type="fact",
                event_type="回购 / 减持 / 控制权",
                direction="positive",
                time_horizon="long",
                affected_symbols=("300308.SZ",),
                quantitative_facts=(),
                confidence="high",
                occurred_at=event.items[0].published_at,
            )
            for event in events
        )
        return ClaimPipelineResult(
            claims=claims,
            warnings=(),
            batches=(ClaimBatchResult(1, len(events), len(claims), "success"),),
            cache_hits=0,
            fallback_count=0,
        )

    monkeypatch.setattr("finance_research_lab.workflow.ClaimPipeline.extract", extract)
