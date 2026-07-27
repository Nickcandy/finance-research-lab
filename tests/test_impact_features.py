from __future__ import annotations

import hashlib

import pytest

from finance_research_lab.claim_pipeline import stable_news_item_id
from finance_research_lab.claims import Claim, QuantitativeFact
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.evidence_ledger import build_evidence_ledgers
from finance_research_lab.impact_features import (
    aggregate_daily_stock_impacts,
    build_impact_assessments,
    derive_event_rule_features,
)
from finance_research_lab.models import (
    AShareCompany,
    FinancialSnapshot,
    MarketEvent,
    NewsItem,
)


def _event(
    title: str,
    *,
    body: str = "",
    source_type: str = "announcement",
) -> MarketEvent:
    item_key = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()[:16]
    item = NewsItem(
        headline=title,
        source="测试来源",
        url=f"https://example.com/{item_key}",
        published_at="2026-07-24T08:00:00+08:00",
        body=body,
        source_type=source_type,  # type: ignore[arg-type]
    )
    return MarketEvent(title, (item,))


def _claim(
    event: MarketEvent,
    *,
    event_type: str,
    direction: str = "positive",
    claim_type: str = "fact",
    time_horizon: str = "medium",
    facts: tuple[QuantitativeFact, ...] = (),
    object_text: str = "事项落地",
    symbol: str = "300308.SZ",
) -> Claim:
    item_id = stable_news_item_id(event.items[0])
    rebound_facts = tuple(
        QuantitativeFact(
            fact.metric,
            fact.value,
            fact.unit,
            fact.period,
            item_id,
        )
        for fact in facts
    )
    return Claim(
        id=f"claim:{event.title}:{event_type}",
        event_id=market_event_id(event),
        source_item_ids=(item_id,),
        subject="中际旭创",
        predicate="发生",
        object=object_text,
        claim_type=claim_type,  # type: ignore[arg-type]
        event_type=event_type,
        direction=direction,  # type: ignore[arg-type]
        time_horizon=time_horizon,  # type: ignore[arg-type]
        affected_symbols=(symbol,) if symbol else (),
        quantitative_facts=rebound_facts,
        confidence="high",
        occurred_at="2026-07-24",
    )


def _fact(metric: str, value: float, unit: str = "%") -> QuantitativeFact:
    return QuantitativeFact(metric, value, unit, "", "placeholder")


def _company(
    symbol: str = "300308.SZ",
    name: str = "中际旭创",
    themes: tuple[str, ...] = ("光模块",),
    business_summary: str = "光模块研发和销售",
) -> AShareCompany:
    return AShareCompany(
        symbol=symbol,
        name=name,
        market="A股",
        industry="通信设备",
        themes=themes,
        business_summary=business_summary,
        source="local",
    )


def _annual_financial(revenue: float = 2_500_000_000) -> FinancialSnapshot:
    return FinancialSnapshot(
        symbol="300308.SZ",
        report_period="2025-12-31",
        revenue=revenue,
        net_profit=300_000_000,
        provider="fixture",
    )


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (1.9, 15),
        (2, 35),
        (10, 60),
        (30, 80),
        (50, 80),
        (50.1, 95),
    ],
)
def test_order_contract_ratio_boundaries(ratio: float, expected: int) -> None:
    event = _event("重大合同")
    amount = 2_500_000_000 * ratio / 100
    claim = _claim(
        event,
        event_type="订单 / 合同",
        facts=(_fact("contract_amount", amount, "元"),),
    )

    features = derive_event_rule_features((claim,), (_annual_financial(),))

    assert features.economic_scale.value == expected


def test_order_without_revenue_denominator_is_capped() -> None:
    event = _event("重大合同")
    claim = _claim(
        event,
        event_type="订单 / 合同",
        facts=(_fact("contract_amount", 20, "亿元"),),
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 50
    assert "missing:ttm_revenue" in features.economic_scale.reason_codes


def test_earnings_opinion_without_benchmark_cannot_claim_high_scale() -> None:
    event = _event("业绩超预期")
    claim = _claim(
        event,
        event_type="业绩 / 指引",
        claim_type="opinion",
        facts=(_fact("net_profit_yoy_pct", 80),),
        object_text="媒体称业绩超预期",
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 50
    assert "missing:expectation_benchmark" in features.economic_scale.reason_codes


def test_control_change_is_hard_upgrade() -> None:
    event = _event("控制权变更")
    claim = _claim(
        event,
        event_type="回购 / 减持 / 控制权",
        object_text="实际控制人发生变更",
        facts=(_fact("share_change_pct", 6),),
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 80
    assert features.hard_upgrade is True


def test_core_license_suspension_is_hard_risk() -> None:
    event = _event("核心资质暂停")
    claim = _claim(
        event,
        event_type="风险暴露",
        direction="negative",
        object_text="核心经营资质被暂停",
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 95
    assert features.hard_upgrade is True


def test_capex_plan_without_timeline_caps_immediacy() -> None:
    event = _event("扩产规划")
    claim = _claim(
        event,
        event_type="资本开支",
        time_horizon="unknown",
        object_text="公司规划扩产，资金和时间表尚未明确",
        facts=(
            _fact("capex_amount", 30, "亿元"),
            _fact("total_assets", 100, "亿元"),
        ),
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 80
    assert features.immediacy.value == 40


def test_commodity_price_change_uses_absolute_move() -> None:
    event = _event("原材料涨价")
    claim = _claim(
        event,
        event_type="涨价 / 供需",
        facts=(_fact("commodity_price_change_pct", -12),),
    )

    features = derive_event_rule_features((claim,), ())

    assert features.economic_scale.value == 80


def test_policy_consultation_and_effective_policy_have_different_immediacy() -> None:
    consultation = _claim(
        _event("政策征求意见", source_type="policy"),
        event_type="政策 / 监管",
        object_text="政策正在征求意见",
    )
    effective = _claim(
        _event("政策正式生效", source_type="policy"),
        event_type="政策 / 监管",
        object_text="政策已正式发布并生效",
        time_horizon="immediate",
    )

    assert derive_event_rule_features((consultation,), ()).immediacy.value == 40
    assert derive_event_rule_features((effective,), ()).immediacy.value == 95


def test_early_research_and_formal_approval_do_not_share_score() -> None:
    early = _claim(
        _event("早期研发"),
        event_type="产品获批 / 研发",
        claim_type="forecast",
        object_text="处于早期研发阶段",
        time_horizon="long",
    )
    approved = _claim(
        _event("正式获批"),
        event_type="产品获批 / 研发",
        object_text="产品已正式获批",
        time_horizon="immediate",
    )

    early_features = derive_event_rule_features((early,), ())
    approved_features = derive_event_rule_features((approved,), ())

    assert early_features.economic_scale.value == 20
    assert approved_features.economic_scale.value == 90
    assert early_features.immediacy.value < approved_features.immediacy.value


def test_full_assessment_uses_verified_company_and_order_ratio() -> None:
    event = _event("中际旭创重大合同", body="公司签订20亿元重大合同")
    claim = _claim(
        event,
        event_type="订单 / 合同",
        facts=(_fact("contract_amount", 20, "亿元"),),
    )
    company = _company()
    ledgers = build_evidence_ledgers((event,), (claim,), (company,))

    assessment = build_impact_assessments(
        (event,),
        ledgers,
        (company,),
        financial_snapshots=(_annual_financial(),),
    )[0]

    assert assessment.positive_features is not None
    assert assessment.positive_features.directness.value == 100
    assert assessment.positive_features.economic_scale.value == 95
    assert assessment.positive_magnitude == 70
    assert assessment.priority_level == "critical"
    assert assessment.scoring_version == "1.1"


def test_commodity_event_can_be_positive_upstream_and_negative_downstream() -> None:
    event = _event("碳酸锂涨价", body="碳酸锂价格上涨12%")
    upstream = _company("000001.SZ", "上游公司", ("锂电资源",), "锂矿和碳酸锂生产")
    downstream = _company("000002.SZ", "下游公司", ("电芯",), "动力电池电芯生产")
    positive = _claim(
        event,
        event_type="涨价 / 供需",
        direction="positive",
        facts=(_fact("commodity_price_change_pct", 12),),
        symbol=upstream.symbol,
    )
    negative = _claim(
        event,
        event_type="涨价 / 供需",
        direction="negative",
        facts=(_fact("commodity_price_change_pct", 12),),
        symbol=downstream.symbol,
    )
    ledgers = build_evidence_ledgers(
        (event,),
        (positive, negative),
        (upstream, downstream),
    )

    assessments = build_impact_assessments(
        (event,),
        ledgers,
        (upstream, downstream),
    )

    assert {assessment.symbol: assessment.direction for assessment in assessments} == {
        "000001.SZ": "positive",
        "000002.SZ": "negative",
    }


def test_daily_stock_aggregate_keeps_max_sides_instead_of_average() -> None:
    company = _company()
    positive_event = _event("正面事件")
    negative_event = _event("负面事件")
    positive_claim = _claim(
        positive_event,
        event_type="产品获批 / 研发",
        object_text="产品已正式获批",
        time_horizon="immediate",
    )
    negative_claim = _claim(
        negative_event,
        event_type="风险暴露",
        direction="negative",
        object_text="核心经营资质被暂停",
    )
    events = (positive_event, negative_event)
    ledgers = build_evidence_ledgers(
        events,
        (positive_claim, negative_claim),
        (company,),
    )
    assessments = build_impact_assessments(events, ledgers, (company,))

    summary = aggregate_daily_stock_impacts(assessments)[0]

    assert summary.max_positive_magnitude == max(
        assessment.positive_magnitude for assessment in assessments
    )
    assert summary.max_negative_magnitude == max(
        assessment.negative_magnitude for assessment in assessments
    )
    assert summary.event_count == 2
    assert summary.direction == "mixed"
