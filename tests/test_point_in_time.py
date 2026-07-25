from __future__ import annotations

from dataclasses import dataclass

import pytest

from finance_research_lab.analysis_router import AnalysisRoute, AnalysisRouter
from finance_research_lab.claim_pipeline import stable_news_item_id
from finance_research_lab.claims import Claim
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.evidence_ledger import build_evidence_ledgers
from finance_research_lab.impact_assessment import ImpactAssessment
from finance_research_lab.impact_features import build_impact_assessments
from finance_research_lab.models import AShareCompany, MarketEvent, NewsItem
from finance_research_lab.point_in_time import (
    ImmutablePointInTimeError,
    build_point_in_time_payload,
    point_in_time_path,
    read_point_in_time,
    replay_point_in_time_scoring,
    write_point_in_time,
)


@dataclass(frozen=True)
class _Routed:
    event: MarketEvent
    route: AnalysisRoute
    assessments: tuple[ImpactAssessment, ...]
    fallback: str = ""
    warnings: tuple[str, ...] = ()


def test_point_in_time_is_immutable_and_versioned(tmp_path) -> None:
    events, claims, company, routed = _fixture()
    payload = build_point_in_time_payload(
        run_id="20260724T090000+0800",
        generated_at="2026-07-24T09:00:00+08:00",
        events=events,
        claims=claims,
        routed_analyses=routed,
    )
    path = point_in_time_path(
        tmp_path / "daily-radar.json",
        payload["run_id"],
        payload["scoring_version"],
    )

    write_point_in_time(payload, path)
    write_point_in_time(payload, path)

    assert read_point_in_time(path) == payload
    assert payload["events"][0]["news_item_ids"] == [
        stable_news_item_id(events[0].items[0])
    ]
    assert payload["events"][0]["claim_ids"] == [claims[0].id]
    assert payload["signals"][0]["symbol"] == company.symbol
    assert payload["signals"][0]["positive_magnitude"] > 0
    assert payload["schema_version"] == "1.1"
    assert payload["signals"][0]["positive_horizon"]["market"]["category"] == "long"
    assert payload["signals"][0]["positive_horizon"]["fundamental"]["category"] == "long"
    assert payload["signals"][0]["negative_horizon"] is None
    assert payload["result_labels_path"].endswith("/result-labels.json")

    changed = {**payload, "generated_at": "2026-07-24T09:01:00+08:00"}
    with pytest.raises(ImmutablePointInTimeError, match="different content"):
        write_point_in_time(changed, path)
    assert read_point_in_time(path) == payload

    versioned = {
        **payload,
        "scoring_version": "2.0",
        "signals": [
            {**signal, "scoring_version": "2.0"}
            for signal in payload["signals"]
        ],
    }
    versioned_path = point_in_time_path(
        tmp_path / "daily-radar.json",
        payload["run_id"],
        "2.0",
    )
    write_point_in_time(versioned, versioned_path)
    assert versioned_path != path


def test_point_in_time_replay_is_structurally_deterministic() -> None:
    events, claims, company, routed = _fixture()

    first = replay_point_in_time_scoring(events, claims, (company,))
    second = replay_point_in_time_scoring(events, claims, (company,))

    assert first == second
    assert first == routed[0].assessments


def test_point_in_time_rejects_identity_mismatch(tmp_path) -> None:
    events, claims, _, routed = _fixture()
    payload = build_point_in_time_payload(
        run_id="run-a",
        generated_at="2026-07-24T09:00:00+08:00",
        events=events,
        claims=claims,
        routed_analyses=routed,
    )
    path = point_in_time_path(tmp_path / "daily-radar.json", "run-b", "1.0")

    with pytest.raises(ValueError, match="identity"):
        write_point_in_time(payload, path)


def test_point_in_time_rejects_invalid_nested_horizon(tmp_path) -> None:
    events, claims, _, routed = _fixture()
    payload = build_point_in_time_payload(
        run_id="run-a",
        generated_at="2026-07-24T09:00:00+08:00",
        events=events,
        claims=claims,
        routed_analyses=routed,
    )
    payload["signals"][0]["positive_horizon"]["market"]["category"] = "invalid"
    path = point_in_time_path(tmp_path / "daily-radar.json", "run-a", "1.0")

    with pytest.raises(ValueError, match="positive_horizon.market.category"):
        write_point_in_time(payload, path)


def _fixture():
    news = NewsItem(
        "中际旭创签订重大合同",
        "公司公告",
        "https://example.com/announcement",
        "2026-07-24T08:00:00+08:00",
        "公司签订重大合同",
        "announcement",
    )
    event = MarketEvent(news.headline, (news,))
    claim = Claim(
        id="claim_fixture",
        event_id=market_event_id(event),
        source_item_ids=(stable_news_item_id(news),),
        subject="中际旭创",
        predicate="签订",
        object="重大合同",
        claim_type="fact",
        event_type="订单 / 合同",
        direction="positive",
        time_horizon="long",
        affected_symbols=("300308.SZ",),
        quantitative_facts=(),
        confidence="high",
        occurred_at="2026-07-24",
    )
    company = AShareCompany(
        "300308.SZ",
        "中际旭创",
        "A股",
        "通信设备",
        ("光模块",),
        "高速光模块供应商",
        "fixture",
    )
    ledgers = build_evidence_ledgers((event,), (claim,), (company,))
    assessments = build_impact_assessments((event,), ledgers, (company,))
    route = AnalysisRouter().route(assessments[0])
    routed = (_Routed(event, route, assessments),)
    return (event,), (claim,), company, routed
