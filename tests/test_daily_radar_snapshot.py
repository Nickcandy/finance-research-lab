from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime

import pytest

from finance_research_lab.agent_models import AgentStep
from finance_research_lab.analysis_router import AnalysisRoute, AnalysisRouter
from finance_research_lab.daily_radar_snapshot import (
    InvalidRadarSnapshot,
    build_daily_radar_snapshot,
    market_event_id,
    read_daily_radar_snapshot,
    validate_daily_radar_snapshot,
    write_daily_radar_snapshot,
)
from finance_research_lab.event_sources import SHANGHAI
from finance_research_lab.impact_assessment import (
    ConfidenceFeatures,
    EventImportanceFeatures,
    FeatureScore,
    ImpactAssessment,
    StockImpactFeatures,
    build_impact_assessment,
)
from finance_research_lab.impact_horizon import DirectionalHorizons, ImpactHorizon
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
            impact_direction="positive",
            confidence="high",
        ),
        StockImpact(
            "688327.SH",
            "云从科技",
            "A股",
            "indirect",
            "medium",
            reasoning="仍需确认订单传导",
            verification_status="unverified",
            impact_direction="unknown",
            confidence="low",
        ),
    )
    report = _report(primary, impacts)
    steps = (
        AgentStep("fetch_event_source", "ths_global_news", "success", "2 item(s)"),
        AgentStep(
            "route_event:1",
            "route_event_analysis",
            "success",
            "fallback:confidence_cap",
        ),
        AgentStep(
            "verify_event_candidates:1",
            "verify_event_candidates",
            "success",
            "ResearchReport",
            warnings=("market fallback: primary source unavailable",),
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

    assert snapshot["schema_version"] == "2.3"
    assert snapshot["run"]["id"] == "20260716T120000+0800"
    assert snapshot["run"]["window_start"] == "2026-07-15T12:00:00+08:00"
    assert snapshot["summary"] == {
        "total_event_count": 1,
        "core_event_count": 1,
        "verified_count": 1,
        "unverified_count": 1,
        "excluded_count": 0,
        "source_count": 2,
        "alert_count": 0,
        "research_candidate_count": 1,
        "critical_event_count": 0,
        "high_event_count": 0,
        "verify_first_count": 0,
        "scoring_version": "1.1",
    }
    assert snapshot["run"]["warnings"] == ["market fallback: primary source unavailable"]
    assert "fallback:confidence_cap" not in snapshot["run"]["warnings"]
    event_payload = snapshot["events"][0]
    assert snapshot["all_events"][0]["id"] == event_payload["id"]
    assert snapshot["all_events"][0]["analysis_status"] == "succeeded"
    assert snapshot["all_events"][0]["items"][0]["headline"] == "AI 数据中心扩产"
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
    assert event_payload["overall_direction"] == "positive"
    assert event_payload["impact_score"] == 80
    assert event_payload["candidates"][0]["impact_direction"] == "positive"
    assert event_payload["candidates"][0]["impact_score"] == 80
    assert event_payload["candidates"][0]["confidence"] == "high"
    assert event_payload["candidates"][0]["news_links"] == [
        {
            "headline": "AI 数据中心扩产",
            "source": "同花顺财经",
            "url": "https://example.com/ai-1",
            "published_at": "2026-07-16T11:30:00+08:00",
        },
        {
            "headline": "AI 数据中心扩产获确认",
            "source": "公司公告",
            "url": "https://example.com/ai-2",
            "published_at": "2026-07-16T10:30:00+08:00",
        },
    ]
    assert event_payload["warnings"] == ["market fallback: primary source unavailable"]
    assert snapshot["candidate_groups"]["verified"][0]["symbol"] == "300308.SZ"
    assert snapshot["candidate_groups"]["verified"][0]["news_links"][0]["url"] == "https://example.com/ai-1"
    assert snapshot["candidate_groups"]["watchlist"][0]["symbol"] == "300308.SZ"
    assert snapshot["alerts"] == []
    assert snapshot["research_candidates"][0]["symbol"] == "300308.SZ"
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
        impact_direction="positive",
        confidence="high",
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

    assert [item["symbol"] for item in snapshot["candidate_groups"]["verified"]] == ["300308.SZ"]
    assert snapshot["candidate_groups"]["excluded"] == []
    assert len(snapshot["candidate_groups"]["verified"][0]["event_ids"]) == 2


def test_candidate_aggregation_marks_conflicting_directions_as_mixed() -> None:
    first_news = NewsItem("事件一", "来源", published_at="2026-07-16T11:00:00+08:00")
    second_news = NewsItem("事件二", "来源", published_at="2026-07-16T10:00:00+08:00")
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
        "300308.SZ",
        "中际旭创",
        "A股",
        "direct",
        "medium",
        impact_direction="negative",
        confidence="medium",
    )
    window_start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    window_end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        (
            MarketEvent(first_news.headline, (first_news,)),
            MarketEvent(second_news.headline, (second_news,)),
        ),
        (_report(first_news, (positive,)), _report(second_news, (negative,))),
        (),
        window_start,
        window_end,
        generated_at=window_end,
    )

    candidate = snapshot["candidate_groups"]["verified"][0]
    assert candidate["impact_direction"] == "mixed"
    assert candidate["impact_score"] == 12
    assert candidate["confidence"] == 0


def test_snapshot_builds_watchlist_alerts_and_research_candidates() -> None:
    news = NewsItem(
        "存储公司订单与供应风险并存",
        "同花顺",
        published_at="2026-07-16T11:00:00+08:00",
    )
    negative_watchlist = StockImpact(
        "001309.SZ",
        "德明利",
        "A股",
        "direct",
        "high",
        reasoning="供应中断风险直接影响交付",
        evidence=("公司公告",),
        risks=("恢复时间待确认",),
        verification_status="verified",
        watchlist_hit=True,
        impact_direction="negative",
        confidence="high",
    )
    positive_candidate = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "indirect",
        "medium",
        reasoning="需求沿产业链传导",
        evidence=("本地产品节点：光模块",),
        verification_status="verified",
        impact_direction="positive",
        confidence="medium",
    )
    unknown_upstream = StockImpact(
        "688327.SH",
        "云从科技",
        "A股",
        "indirect",
        "high",
        verification_status="verified",
        impact_direction="unknown",
        confidence="low",
    )
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        (MarketEvent(news.headline, (news,)),),
        (_report(news, (negative_watchlist, positive_candidate, unknown_upstream)),),
        (),
        start,
        end,
        generated_at=end,
    )

    assert snapshot["summary"]["alert_count"] == 1
    assert snapshot["alerts"][0] == {
        "id": snapshot["alerts"][0]["id"],
        "event_id": snapshot["events"][0]["id"],
        "event_title": news.headline,
        "symbol": "001309.SZ",
        "name": "德明利",
        "direction": "negative",
        "impact_score": -80,
        "confidence": "high",
        "severity": "high",
        "reasoning": "供应中断风险直接影响交付",
        "evidence": ["公司公告"],
        "risks": ["恢复时间待确认"],
        "generated_at": "2026-07-16T12:00:00+08:00",
        "negative_horizon": None,
    }
    assert snapshot["summary"]["research_candidate_count"] == 1
    assert [item["symbol"] for item in snapshot["research_candidates"]] == ["300308.SZ"]
    assert snapshot["research_candidates"][0]["impact_score"] == 45


def test_pure_stock_price_event_remains_in_catalog_but_is_not_applicable() -> None:
    news = NewsItem(
        "中际旭创盘中涨超10%",
        "同花顺",
        published_at="2026-07-16T11:00:00+08:00",
        body="股价盘中涨超10%，成交额超50亿元。",
    )
    event = MarketEvent(news.headline, (news,))
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        (),
        (),
        (),
        start,
        end,
        all_events=(event,),
        generated_at=end,
    )

    assert snapshot["summary"]["total_event_count"] == 1
    assert snapshot["summary"]["core_event_count"] == 0
    assert snapshot["all_events"][0]["analysis_status"] == "not_applicable"
    assert snapshot["all_events"][0]["exclusion_reason"] == ("pure_stock_price_update")


def test_snapshot_write_is_atomic_and_read_validates_schema(tmp_path) -> None:
    path = tmp_path / "daily-radar.json"
    payload = _minimal_snapshot()

    write_daily_radar_snapshot(payload, path)

    assert read_daily_radar_snapshot(path) == payload
    assert not list(tmp_path.glob("*.tmp"))

    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(InvalidRadarSnapshot, match="invalid JSON"):
        read_daily_radar_snapshot(path)

    path.write_text(json.dumps({**payload, "schema_version": "3.0"}), encoding="utf-8")
    with pytest.raises(InvalidRadarSnapshot, match="unsupported schema_version"):
        read_daily_radar_snapshot(path)


def test_snapshot_v23_exposes_routes_and_keeps_max_positive_and_negative() -> None:
    first_news = NewsItem(
        "中际旭创获得重大订单",
        "公司公告",
        published_at="2026-07-16T11:00:00+08:00",
        source_type="announcement",
    )
    second_news = NewsItem(
        "中际旭创供应风险",
        "可靠媒体",
        published_at="2026-07-16T10:00:00+08:00",
    )
    events = (
        MarketEvent(first_news.headline, (first_news,)),
        MarketEvent(second_news.headline, (second_news,)),
    )
    positive = _assessment(events[0], positive=82, negative=0, confidence=80)
    negative = _assessment(events[1], positive=0, negative=71, confidence=42)
    routed = (
        _Routed(
            events[0],
            AnalysisRouter().route(positive),
            (positive,),
            fallback="deterministic",
            warnings=("部分新闻事实由规则降级提取，置信度上限为 35，请核验原始来源。",),
        ),
        _Routed(events[1], AnalysisRouter().route(negative), (negative,)),
    )
    impacts = (
        StockImpact(
            "300308.SZ",
            "中际旭创",
            "A股",
            "direct",
            "high",
            impact_direction="positive",
            confidence="high",
        ),
    )
    reports = (_report(first_news, impacts), _report(second_news, impacts))
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        events,
        reports,
        (),
        start,
        end,
        generated_at=end,
        routed_analyses=routed,
    )

    assert snapshot["summary"]["critical_event_count"] == 1
    assert snapshot["summary"]["verify_first_count"] == 1
    assert snapshot["summary"]["scoring_version"] == "1.1"
    assert snapshot["events"][0]["analysis_tier"] == "pro"
    assert snapshot["events"][0]["event_importance"] == positive.event_importance
    assert snapshot["events"][0]["impact_score"] == 82
    assert snapshot["events"][0]["candidates"][0]["score_status"] == "scored"
    assert snapshot["all_events"][0]["related_stocks"][0]["symbol"] == "300308.SZ"
    assert snapshot["events"][1]["impact_score"] == -71
    assert snapshot["events"][0]["warnings"] == [
        "部分新闻事实由规则降级提取，置信度上限为 35，请核验原始来源。"
    ]
    assert all("analysis fallback" not in warning for warning in snapshot["run"]["warnings"])
    candidate = snapshot["candidate_groups"]["verified"][0]
    assert candidate["positive_magnitude"] == 82
    assert candidate["negative_magnitude"] == 71
    assert candidate["confidence"] == 80
    assert candidate["conflict_score"] == 0
    assert candidate["priority_level"] == "critical"
    assert candidate["analysis_tier"] == "pro"
    assert candidate["score_status"] == "scored"
    assert candidate["impact_direction"] == "mixed"
    assert candidate["impact_score"] is None
    assert candidate["feature_breakdown"]["positive"]["directness"]["value"] == 82
    assert (
        "fixture:evidence"
        in candidate["feature_breakdown"]["positive"]["directness"]["evidence_refs"]
    )
    assert candidate["positive_horizon"]["market"]["category"] == "short"
    assert candidate["positive_horizon"]["fundamental"]["category"] == "long"
    assert candidate["negative_horizon"]["market"]["category"] == "immediate"
    assert candidate["negative_horizon"]["fundamental"]["category"] == "medium"


def test_watchlist_alert_keeps_current_event_negative_horizon() -> None:
    first_news = NewsItem(
        "第一项风险",
        "公司公告",
        published_at="2026-07-16T11:00:00+08:00",
        source_type="announcement",
    )
    second_news = NewsItem(
        "第二项风险",
        "公司公告",
        published_at="2026-07-16T10:00:00+08:00",
        source_type="announcement",
    )
    events = (
        MarketEvent(first_news.headline, (first_news,)),
        MarketEvent(second_news.headline, (second_news,)),
    )
    first = replace(
        _assessment(events[0], positive=0, negative=80, confidence=80),
        negative_horizon=_horizons("immediate", "medium"),
    )
    second = replace(
        _assessment(events[1], positive=0, negative=75, confidence=80),
        negative_horizon=_horizons("long", "long"),
    )
    routed = (
        _Routed(events[0], AnalysisRouter().route(first), (first,)),
        _Routed(events[1], AnalysisRouter().route(second), (second,)),
    )
    impact = StockImpact(
        "300308.SZ",
        "中际旭创",
        "A股",
        "negative",
        "high",
        verification_status="verified",
        watchlist_hit=True,
        impact_direction="negative",
        confidence="high",
    )
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)

    snapshot = build_daily_radar_snapshot(
        events,
        (_report(first_news, (impact,)), _report(second_news, (impact,))),
        (),
        start,
        end,
        generated_at=end,
        routed_analyses=routed,
    )

    alerts = {alert["event_id"]: alert for alert in snapshot["alerts"]}
    assert alerts[market_event_id(events[0])]["negative_horizon"]["market"][
        "category"
    ] == "immediate"
    assert alerts[market_event_id(events[1])]["negative_horizon"]["market"][
        "category"
    ] == "long"


@pytest.mark.parametrize("invalid", [True, -1, 101, 1.5, "80"])
def test_snapshot_v23_rejects_invalid_zero_to_hundred_values(invalid) -> None:
    payload = _minimal_snapshot()
    payload["events"] = [
        {
            "event_importance": invalid,
            "importance_level": "low",
            "confidence": 0,
            "analysis_tier": "deterministic",
            "reason_codes": [],
            "candidates": [],
            "overall_direction": "unknown",
            "impact_score": None,
        }
    ]

    with pytest.raises(InvalidRadarSnapshot, match="event_importance"):
        validate_daily_radar_snapshot(payload)


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
        "schema_version": "2.3",
        "run": {
            "id": "20260716T120000+0800",
            "event_catalog_id": "20260716T120000+0800",
            "status": "succeeded",
            "generated_at": "2026-07-16T12:00:00+08:00",
            "window_start": "2026-07-15T12:00:00+08:00",
            "window_end": "2026-07-16T12:00:00+08:00",
            "warnings": [],
            "steps": [],
        },
        "summary": {
            "total_event_count": 0,
            "core_event_count": 0,
            "verified_count": 0,
            "unverified_count": 0,
            "excluded_count": 0,
            "source_count": 0,
            "alert_count": 0,
            "research_candidate_count": 0,
            "critical_event_count": 0,
            "high_event_count": 0,
            "verify_first_count": 0,
            "scoring_version": "1.1",
        },
        "events": [],
        "all_events": [],
        "candidate_groups": {
            "verified": [],
            "unverified": [],
            "excluded": [],
            "watchlist": [],
        },
        "alerts": [],
        "research_candidates": [],
        "validation_tasks": [],
        "disclaimer": "研究辅助，不构成投资建议。",
    }


@dataclass(frozen=True)
class _Routed:
    event: MarketEvent
    route: AnalysisRoute
    assessments: tuple[ImpactAssessment, ...]
    fallback: str = ""
    warnings: tuple[str, ...] = ()


def _score(value: int) -> FeatureScore:
    return FeatureScore(value, (f"fixture:{value}",), ("fixture:evidence",))


def _assessment(
    event: MarketEvent,
    *,
    positive: int,
    negative: int,
    confidence: int,
) -> ImpactAssessment:
    def stock(value: int) -> StockImpactFeatures | None:
        if value == 0:
            return None
        return StockImpactFeatures(
            directness=_score(value),
            exposure=_score(value),
            economic_scale=_score(value),
            duration=_score(value),
            sensitivity=_score(value),
        )

    return build_impact_assessment(
        event_id=market_event_id(event),
        symbol="300308.SZ",
        event_features=EventImportanceFeatures(
            materiality=_score(max(positive, negative)),
            breadth=_score(50),
            novelty=_score(50),
            immediacy=_score(50),
        ),
        positive_features=stock(positive),
        negative_features=stock(negative),
        positive_horizon=_horizons("short", "long") if positive else None,
        negative_horizon=_horizons("immediate", "medium") if negative else None,
        confidence_features=ConfidenceFeatures(
            source_quality=_score(confidence),
            corroboration=_score(confidence),
            identity_verification=_score(confidence),
            quantitative_completeness=_score(confidence),
            consistency=_score(confidence),
        ),
    )


def _horizons(market: str, fundamental: str) -> DirectionalHorizons:
    ranges = {
        "immediate": (0, 5, "trading_day"),
        "short": (6, 20, "trading_day"),
        "medium": (3, 6, "calendar_month"),
        "long": (6, 24, "calendar_month"),
    }

    def horizon(category: str, *, layer: str) -> ImpactHorizon:
        minimum, maximum, unit = ranges[category]
        if layer == "fundamental" and unit == "trading_day":
            unit = "calendar_month"
        return ImpactHorizon(
            category=category,  # type: ignore[arg-type]
            min_duration=minimum,
            max_duration=maximum,
            unit=unit,  # type: ignore[arg-type]
            confidence="medium",
            basis=("fixture basis",),
            evidence_refs=("claim:fixture",),
            invalidation_conditions=("fixture invalidation",),
        )

    return DirectionalHorizons(
        market=horizon(market, layer="market"),
        fundamental=horizon(fundamental, layer="fundamental"),
    )
