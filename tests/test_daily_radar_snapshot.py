from __future__ import annotations

import json
from datetime import datetime

import pytest

from finance_research_lab.agent_models import AgentStep
from finance_research_lab.daily_radar_snapshot import (
    InvalidRadarSnapshot,
    build_daily_radar_snapshot,
    read_daily_radar_snapshot,
    write_daily_radar_snapshot,
)
from finance_research_lab.event_sources import SHANGHAI
from finance_research_lab.models import (
    EventAnalysis,
    MarketEvent,
    NewsItem,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
)


def test_build_daily_radar_snapshot_exposes_stable_frontend_contract() -> None:
    primary = NewsItem(
        "AI 数据中心扩产",
        "同花顺财经",
        "https://example.com/ai-1",
        "2026-07-16T11:30:00+08:00",
        source_type="news",
    )
    confirmation = NewsItem(
        "AI 数据中心扩产获确认",
        "公司公告",
        "https://example.com/ai-2",
        "2026-07-16T10:30:00+08:00",
        source_type="announcement",
    )
    event = MarketEvent(primary.headline, (primary, confirmation))
    impacts = (
        StockImpact(
            "300308.SZ",
            "中际旭创",
            "A股",
            "direct",
            "high",
            reasoning="光模块需求增加",
            evidence=("财报和行情证据齐全",),
            risks=("扩产不及预期",),
            verification_status="verified",
            verification_source="AkShare + BaoStock",
            watchlist_hit=True,
        ),
        StockImpact(
            "688327.SH",
            "云从科技",
            "A股",
            "indirect",
            "medium",
            reasoning="仍需确认订单传导",
            verification_status="unverified",
        ),
    )
    report = _report(primary, impacts)
    steps = (
        AgentStep("fetch_event_source", "ths_global_news", "success", "2 item(s)"),
        AgentStep(
            "verify_event_candidates:1",
            "verify_event_candidates",
            "success",
            "ResearchReport; market fallback: primary source unavailable",
        ),
    )
    window_start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    window_end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        (event,),
        (report,),
        steps,
        window_start,
        window_end,
        generated_at=window_end,
    )

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["run"]["id"] == "20260716T120000+0800"
    assert snapshot["run"]["window_start"] == "2026-07-15T12:00:00+08:00"
    assert snapshot["summary"] == {
        "event_count": 1,
        "verified_count": 1,
        "unverified_count": 1,
        "excluded_count": 0,
        "source_count": 2,
    }
    assert snapshot["run"]["warnings"] == [
        "market fallback: primary source unavailable"
    ]
    event_payload = snapshot["events"][0]
    assert event_payload["id"].startswith("evt_")
    assert event_payload["rank"] == 1
    assert event_payload["report_count"] == 2
    assert event_payload["source_count"] == 2
    assert event_payload["source_urls"] == [
        "https://example.com/ai-1",
        "https://example.com/ai-2",
    ]
    assert event_payload["sources"] == [
        {"source_type": "news", "name": "同花顺财经"},
        {"source_type": "announcement", "name": "公司公告"},
    ]
    assert event_payload["event_type"] == "资本开支"
    assert event_payload["themes"] == ["AI", "光模块"]
    assert event_payload["value_chain"]["chain_steps"] == [
        "云厂商",
        "数据中心",
        "光模块",
    ]
    assert event_payload["analysis_status"] == "succeeded"
    assert event_payload["warnings"] == ["market fallback: primary source unavailable"]
    assert snapshot["candidate_groups"]["verified"][0]["symbol"] == "300308.SZ"
    assert snapshot["candidate_groups"]["watchlist"][0]["symbol"] == "300308.SZ"
    assert snapshot["validation_tasks"] == [
        {
            "question": "订单是否落地？",
            "data_needed": "公司公告",
            "status": "pending",
            "event_ids": [event_payload["id"]],
        }
    ]
    assert snapshot["disclaimer"] == "研究辅助，不构成投资建议。"


def test_snapshot_event_id_is_independent_of_item_order() -> None:
    first = NewsItem("事件", "来源甲", "https://example.com/1", "2026-07-16T11:00:00+08:00")
    second = NewsItem("事件更新", "来源乙", "", "2026-07-16T10:00:00+08:00")
    window_start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    window_end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    forward = build_daily_radar_snapshot(
        (MarketEvent(first.headline, (first, second)),),
        (None,),
        (),
        window_start,
        window_end,
        generated_at=window_end,
    )
    reversed_items = build_daily_radar_snapshot(
        (MarketEvent(first.headline, (second, first)),),
        (None,),
        (),
        window_start,
        window_end,
        generated_at=window_end,
    )

    assert forward["events"][0]["id"] == reversed_items["events"][0]["id"]
    assert forward["events"][0]["analysis_status"] == "failed"
    assert forward["events"][0]["source_urls"] == ["https://example.com/1"]


def test_candidate_aggregation_does_not_let_false_positive_override_verified() -> None:
    first_news = NewsItem("事件一", "来源", published_at="2026-07-16T11:00:00+08:00")
    second_news = NewsItem("事件二", "来源", published_at="2026-07-16T10:00:00+08:00")
    verified = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "high",
        verification_status="verified",
    )
    false_positive = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "false_positive",
        "low",
        verification_status="excluded",
    )
    window_start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    window_end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        (
            MarketEvent(first_news.headline, (first_news,)),
            MarketEvent(second_news.headline, (second_news,)),
        ),
        (_report(first_news, (verified,)), _report(second_news, (false_positive,))),
        (),
        window_start,
        window_end,
        generated_at=window_end,
    )

    assert [item["symbol"] for item in snapshot["candidate_groups"]["verified"]] == [
        "300308.SZ"
    ]
    assert snapshot["candidate_groups"]["excluded"] == []
    assert len(snapshot["candidate_groups"]["verified"][0]["event_ids"]) == 2


def test_snapshot_write_is_atomic_and_read_validates_schema(tmp_path) -> None:
    path = tmp_path / "daily-radar.json"
    payload = _minimal_snapshot()

    write_daily_radar_snapshot(payload, path)

    assert read_daily_radar_snapshot(path) == payload
    assert not list(tmp_path.glob("*.tmp"))

    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(InvalidRadarSnapshot, match="invalid JSON"):
        read_daily_radar_snapshot(path)

    path.write_text(json.dumps({**payload, "schema_version": "2.0"}), encoding="utf-8")
    with pytest.raises(InvalidRadarSnapshot, match="unsupported schema_version"):
        read_daily_radar_snapshot(path)


def test_build_snapshot_rejects_misaligned_reports() -> None:
    news = NewsItem("事件", "来源", published_at="2026-07-16T11:00:00+08:00")
    with pytest.raises(ValueError, match="reports must align with events"):
        build_daily_radar_snapshot(
            (MarketEvent(news.headline, (news,)),),
            (),
            (),
            datetime(2026, 7, 15, 12, tzinfo=SHANGHAI),
            datetime(2026, 7, 16, 12, tzinfo=SHANGHAI),
        )


def _report(news: NewsItem, impacts: tuple[StockImpact, ...]) -> ResearchReport:
    return ResearchReport(
        raw_news=news,
        event=EventAnalysis(
            "资本开支",
            ("AI", "光模块"),
            ("云厂商", "数据中心"),
            ("扩产计划已发布",),
            "多来源确认",
            "high",
            "需求与供给链路明确",
        ),
        value_chain=ValueChainTrace(
            "云厂商",
            "光模块厂商",
            ("云厂商", "数据中心", "光模块"),
            "positive",
            "资本开支向上游传导",
        ),
        stock_impacts=impacts,
        validation_tasks=(ValidationTask("订单是否落地？", "公司公告"),),
        stage="验证",
        action_state="等验证",
    )


def _minimal_snapshot() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run": {
            "id": "20260716T120000+0800",
            "status": "succeeded",
            "generated_at": "2026-07-16T12:00:00+08:00",
            "window_start": "2026-07-15T12:00:00+08:00",
            "window_end": "2026-07-16T12:00:00+08:00",
            "warnings": [],
            "steps": [],
        },
        "summary": {
            "event_count": 0,
            "verified_count": 0,
            "unverified_count": 0,
            "excluded_count": 0,
            "source_count": 0,
        },
        "events": [],
        "candidate_groups": {
            "verified": [],
            "unverified": [],
            "excluded": [],
            "watchlist": [],
        },
        "validation_tasks": [],
        "disclaimer": "研究辅助，不构成投资建议。",
    }
