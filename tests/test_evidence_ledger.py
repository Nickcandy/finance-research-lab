from __future__ import annotations

from finance_research_lab.claim_pipeline import stable_news_item_id
from finance_research_lab.claims import Claim
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.evidence_ledger import (
    build_evidence_ledgers,
    build_source_identities,
)
from finance_research_lab.models import AShareCompany, MarketEvent, NewsItem


def _news(
    headline: str,
    *,
    source: str = "测试媒体",
    url: str = "",
    body: str = "正文",
    source_type: str = "news",
) -> NewsItem:
    return NewsItem(
        headline=headline,
        source=source,
        url=url,
        published_at="2026-07-24T08:00:00+08:00",
        body=body,
        source_type=source_type,  # type: ignore[arg-type]
    )


def _claim(
    event: MarketEvent,
    items: tuple[NewsItem, ...],
    *,
    claim_id: str,
    subject: str = "中际旭创",
    direction: str = "positive",
    time_horizon: str = "medium",
    affected_symbols: tuple[str, ...] = ("300308.SZ",),
    extraction_method: str = "llm",
) -> Claim:
    return Claim(
        id=claim_id,
        event_id=market_event_id(event),
        source_item_ids=tuple(stable_news_item_id(item) for item in items),
        subject=subject,
        predicate="影响",
        object="公司经营",
        claim_type="fact",
        event_type="订单 / 合同",
        direction=direction,  # type: ignore[arg-type]
        time_horizon=time_horizon,  # type: ignore[arg-type]
        affected_symbols=affected_symbols,
        quantitative_facts=(),
        confidence="high",
        occurred_at="2026-07-24",
        extraction_method=extraction_method,  # type: ignore[arg-type]
    )


def _company() -> AShareCompany:
    return AShareCompany(
        symbol="300308.SZ",
        name="中际旭创",
        market="A股",
        industry="通信设备",
        themes=("光模块",),
        business_summary="光模块研发和销售",
        source="local",
    )


def test_source_identity_uses_fixed_quality_and_origin_rules() -> None:
    announcement = _news(
        "公司公告",
        source="巨潮资讯",
        url="https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1",
        source_type="announcement",
    )
    media = _news("媒体报道", source="未知媒体")
    event = MarketEvent("事件", (announcement, media))

    identities = build_source_identities((event,))

    assert identities[stable_news_item_id(announcement)].source_quality.value == 95
    assert identities[stable_news_item_id(announcement)].official is True
    assert identities[stable_news_item_id(media)].source_quality.value == 45
    assert identities[stable_news_item_id(media)].official is False


def test_fallback_claim_caps_total_confidence_at_35() -> None:
    announcement = _news(
        "公司公告",
        source="巨潮资讯",
        source_type="announcement",
    )
    event = MarketEvent("公司公告", (announcement,))
    claim = _claim(
        event,
        (announcement,),
        claim_id="claim:fallback",
        extraction_method="fallback",
    )

    ledger = build_evidence_ledgers((event,), (claim,), (_company(),))[0]

    assert ledger.confidence <= 35
    assert "fallback:confidence_cap" in (
        ledger.confidence_features.source_quality.reason_codes
    )


def test_ledger_dedupes_reprints_and_counts_independent_sources() -> None:
    first = _news(
        "重大合同",
        source="媒体 A",
        url="https://a.example.com/1",
        body="公司签订重大合同",
    )
    reprint = _news(
        "重大合同",
        source="媒体 B",
        url="https://b.example.com/2",
        body="公司签订重大合同",
    )
    independent = _news(
        "重大合同获确认",
        source="媒体 C",
        url="https://c.example.com/3",
        body="另一独立来源确认合同",
    )
    event = MarketEvent("重大合同", (first, reprint, independent))
    claims = (
        _claim(event, (first, reprint), claim_id="claim:1"),
        _claim(event, (independent,), claim_id="claim:2"),
    )

    ledger = build_evidence_ledgers((event,), claims, (_company(),))[0]

    assert ledger.independent_source_count == 2
    assert ledger.duplicate_source_count == 1
    assert ledger.confidence_features.corroboration.value == 70
    assert len(ledger.supporting_claims) == 2
    assert ledger.verified is True


def test_ledger_only_marks_same_horizon_opposites_as_strong_conflict() -> None:
    positive_news = _news("利好", url="https://a.example.com/positive")
    negative_news = _news("利空", url="https://b.example.com/negative")
    event = MarketEvent("影响分化", (positive_news, negative_news))
    positive = _claim(
        event,
        (positive_news,),
        claim_id="claim:positive",
        direction="positive",
    )
    negative = _claim(
        event,
        (negative_news,),
        claim_id="claim:negative",
        direction="negative",
    )

    conflict = build_evidence_ledgers(
        (event,),
        (positive, negative),
        (_company(),),
    )[0]
    different_horizon = build_evidence_ledgers(
        (event,),
        (
            positive,
            _claim(
                event,
                (negative_news,),
                claim_id="claim:long-negative",
                direction="negative",
                time_horizon="long",
            ),
        ),
        (_company(),),
    )[0]

    assert conflict.claim_conflict_score == 70
    assert conflict.confidence_features.consistency.value == 30
    assert different_horizon.claim_conflict_score == 0
    assert different_horizon.confidence_features.consistency.value == 60


def test_universe_gating_keeps_unverified_symbol_out_of_verified_state() -> None:
    news = _news("未知公司事项")
    event = MarketEvent(news.headline, (news,))
    claim = _claim(
        event,
        (news,),
        claim_id="claim:unknown",
        subject="未知公司",
        affected_symbols=("999999.SH",),
    )

    ledger = build_evidence_ledgers((event,), (claim,), (_company(),))[0]

    assert ledger.symbol == "999999.SH"
    assert ledger.verified is False
    assert ledger.confidence_features.identity_verification.value == 20


def test_unique_company_name_maps_claim_without_symbol() -> None:
    news = _news("中际旭创签订合同")
    event = MarketEvent(news.headline, (news,))
    claim = _claim(
        event,
        (news,),
        claim_id="claim:name",
        affected_symbols=(),
    )

    ledger = build_evidence_ledgers((event,), (claim,), (_company(),))[0]

    assert ledger.symbol == "300308.SZ"
    assert ledger.company_name == "中际旭创"
    assert ledger.verified is True
    assert ledger.confidence_features.identity_verification.value == 90
