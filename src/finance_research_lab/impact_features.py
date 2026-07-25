from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

from .claims import Claim
from .daily_radar_snapshot import market_event_id
from .evidence_ledger import EvidenceLedger
from .impact_assessment import (
    EventImportanceFeatures,
    FeatureScore,
    ImpactAssessment,
    PriorityLevel,
    StockImpactFeatures,
    build_impact_assessment,
    resolve_impact_direction,
)
from .impact_horizon import assess_directional_horizons, infer_event_kind
from .models import AShareCompany, CompanyAnnouncement, FinancialSnapshot, MarketEvent
from .value_chains import best_value_chain_relation, infer_value_chain_nodes


@dataclass(frozen=True)
class EventRuleFeatures:
    economic_scale: FeatureScore
    immediacy: FeatureScore
    hard_upgrade: bool = False


@dataclass(frozen=True)
class DailyStockImpactSummary:
    symbol: str
    direction: str
    max_positive_magnitude: int
    max_negative_magnitude: int
    confidence: int
    conflict_score: int
    priority_level: PriorityLevel
    event_count: int
    event_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


def derive_event_rule_features(
    claims: Sequence[Claim],
    financial_snapshots: Sequence[FinancialSnapshot],
) -> EventRuleFeatures:
    if not claims:
        raise ValueError("claims must not be empty")
    kind = infer_event_kind(claims)
    if kind == "order":
        economic_scale = _order_scale(claims, financial_snapshots)
    elif kind == "earnings":
        economic_scale = _earnings_scale(claims, financial_snapshots)
    elif kind == "corporate_action":
        economic_scale = _corporate_action_scale(claims)
    elif kind == "risk":
        economic_scale = _risk_scale(claims, financial_snapshots)
    elif kind == "capex":
        economic_scale = _capex_scale(claims)
    elif kind == "commodity":
        economic_scale = _commodity_scale(claims)
    elif kind == "policy":
        economic_scale = _policy_scale(claims)
    elif kind == "approval":
        economic_scale = _approval_scale(claims)
    else:
        economic_scale = _generic_scale(claims)
    immediacy = _immediacy(claims, kind)
    text = _claim_text(claims)
    hard_upgrade = any(
        marker in text
        for marker in (
            "控制权变更",
            "实际控制人发生变更",
            "核心经营资质被暂停",
            "核心资质暂停",
            "主要工厂停产",
            "退市风险",
            "重大偿付风险",
        )
    )
    return EventRuleFeatures(economic_scale, immediacy, hard_upgrade)


def build_impact_assessments(
    events: Sequence[MarketEvent],
    ledgers: Sequence[EvidenceLedger],
    a_share_universe: Sequence[AShareCompany],
    *,
    company_announcements: Sequence[CompanyAnnouncement] = (),
    financial_snapshots: Sequence[FinancialSnapshot] = (),
) -> tuple[ImpactAssessment, ...]:
    events_by_id = {market_event_id(event): event for event in events}
    companies = {company.symbol: company for company in a_share_universe}
    prepared: list[
        tuple[
            EvidenceLedger,
            StockImpactFeatures | None,
            StockImpactFeatures | None,
            EventRuleFeatures,
            EventRuleFeatures,
        ]
    ] = []
    economic_by_event: dict[str, list[FeatureScore]] = {}
    immediacy_by_event: dict[str, list[FeatureScore]] = {}
    for ledger in ledgers:
        event = events_by_id.get(ledger.event_id)
        if event is None:
            raise ValueError(f"unknown ledger event_id: {ledger.event_id}")
        company = companies.get(ledger.symbol)
        financials = tuple(
            snapshot
            for snapshot in financial_snapshots
            if snapshot.symbol == ledger.symbol
        )
        positive_rule = _rule_or_empty(ledger.supporting_claims, financials)
        negative_rule = _rule_or_empty(ledger.opposing_claims, financials)
        positive_features = _stock_features(
            event,
            ledger,
            company,
            ledger.supporting_claims,
            positive_rule,
        )
        negative_features = _stock_features(
            event,
            ledger,
            company,
            ledger.opposing_claims,
            negative_rule,
        )
        prepared.append(
            (
                ledger,
                positive_features,
                negative_features,
                positive_rule,
                negative_rule,
            )
        )
        for rule in (positive_rule, negative_rule):
            economic_by_event.setdefault(ledger.event_id, []).append(rule.economic_scale)
            immediacy_by_event.setdefault(ledger.event_id, []).append(rule.immediacy)

    verified_count_by_event: dict[str, int] = {}
    for ledger in ledgers:
        if ledger.verified and ledger.symbol:
            verified_count_by_event[ledger.event_id] = (
                verified_count_by_event.get(ledger.event_id, 0) + 1
            )
    assessments: list[ImpactAssessment] = []
    for ledger, positive_features, negative_features, positive_rule, negative_rule in prepared:
        event = events_by_id[ledger.event_id]
        event_features = _event_features(
            event,
            tuple(economic_by_event[ledger.event_id]),
            tuple(immediacy_by_event[ledger.event_id]),
            verified_count_by_event.get(ledger.event_id, 0),
            ledgers,
        )
        announcements = tuple(
            announcement
            for announcement in company_announcements
            if announcement.symbol == ledger.symbol
        )
        official_announcement = bool(announcements) or any(
            identity.official and identity.source_type == "announcement"
            for identity in ledger.source_identities
        )
        high_quality_origins = {
            identity.origin_key or f"content:{identity.content_hash}"
            for identity in ledger.source_identities
            if identity.source_quality.value >= 70
        }
        assessments.append(
            build_impact_assessment(
                event_id=ledger.event_id,
                symbol=ledger.symbol,
                event_features=event_features,
                positive_features=positive_features,
                negative_features=negative_features,
                positive_horizon=assess_directional_horizons(
                    event,
                    ledger.supporting_claims,
                    verified_relation=ledger.verified,
                ),
                negative_horizon=assess_directional_horizons(
                    event,
                    ledger.opposing_claims,
                    verified_relation=ledger.verified,
                ),
                confidence_features=ledger.confidence_features,
                official_major_announcement=official_announcement,
                watchlist_hit=ledger.watchlist_hit,
                hard_upgrade=positive_rule.hard_upgrade or negative_rule.hard_upgrade,
                verified_a_share_relation=ledger.verified,
                corroborated_by_high_quality_sources=len(high_quality_origins) >= 2,
                not_applicable=all(
                    claim.claim_type == "market_reaction" for claim in ledger.claims
                ),
            )
        )
    return tuple(assessments)


def aggregate_daily_stock_impacts(
    assessments: Sequence[ImpactAssessment],
) -> tuple[DailyStockImpactSummary, ...]:
    grouped: dict[str, list[ImpactAssessment]] = {}
    for assessment in assessments:
        if assessment.symbol:
            grouped.setdefault(assessment.symbol, []).append(assessment)
    summaries = []
    priority_order = {
        "critical": 0,
        "verify_first": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }
    for symbol, values in grouped.items():
        positive = max(value.positive_magnitude for value in values)
        negative = max(value.negative_magnitude for value in values)
        priority = min(
            (value.priority_level for value in values),
            key=lambda value: priority_order[value],
        )
        summaries.append(
            DailyStockImpactSummary(
                symbol=symbol,
                direction=resolve_impact_direction(positive, negative),
                max_positive_magnitude=positive,
                max_negative_magnitude=negative,
                confidence=max(value.confidence for value in values),
                conflict_score=max(value.conflict_score for value in values),
                priority_level=priority,
                event_count=len({value.event_id for value in values}),
                event_ids=tuple(dict.fromkeys(value.event_id for value in values)),
                reason_codes=tuple(
                    dict.fromkeys(
                        reason
                        for value in values
                        for reason in value.reason_codes
                    )
                ),
            )
        )
    summaries.sort(
        key=lambda value: (
            -max(value.max_positive_magnitude, value.max_negative_magnitude),
            -value.confidence,
            value.symbol,
        )
    )
    return tuple(summaries)


def _rule_or_empty(
    claims: tuple[Claim, ...],
    financials: tuple[FinancialSnapshot, ...],
) -> EventRuleFeatures:
    if claims:
        return derive_event_rule_features(claims, financials)
    return EventRuleFeatures(
        FeatureScore(0, ("economic_scale:no_directional_claim",), ("claim:none",)),
        FeatureScore(0, ("immediacy:no_directional_claim",), ("claim:none",)),
    )


def _stock_features(
    event: MarketEvent,
    ledger: EvidenceLedger,
    company: AShareCompany | None,
    claims: tuple[Claim, ...],
    rule: EventRuleFeatures,
) -> StockImpactFeatures | None:
    if not claims:
        return None
    directness = _directness(event, ledger, company, claims)
    exposure = _exposure(event, company, claims)
    duration = _duration(claims)
    sensitivity = _sensitivity(company, claims)
    economic_scale = rule.economic_scale
    if company is None:
        directness = _cap(directness, 20, "missing:verified_company")
        exposure = _cap(exposure, 20, "missing:verified_company")
        economic_scale = _cap(economic_scale, 50, "missing:verified_company")
    return StockImpactFeatures(
        directness=directness,
        exposure=exposure,
        economic_scale=economic_scale,
        duration=duration,
        sensitivity=sensitivity,
    )


def _event_features(
    event: MarketEvent,
    economic_values: tuple[FeatureScore, ...],
    immediacy_values: tuple[FeatureScore, ...],
    verified_company_count: int,
    ledgers: Sequence[EvidenceLedger],
) -> EventImportanceFeatures:
    materiality = max(economic_values, key=lambda feature: feature.value)
    if verified_company_count <= 1:
        breadth_value = 50
        breadth_reason = "breadth:single_company"
    elif verified_company_count <= 5:
        breadth_value = 65
        breadth_reason = "breadth:industry_segment"
    elif verified_company_count <= 20:
        breadth_value = 80
        breadth_reason = "breadth:broad_industry"
    else:
        breadth_value = 95
        breadth_reason = "breadth:market_wide"
    event_ledgers = [ledger for ledger in ledgers if ledger.event_id == market_event_id(event)]
    duplicate_count = sum(ledger.duplicate_source_count for ledger in event_ledgers)
    independent_count = max(
        (ledger.independent_source_count for ledger in event_ledgers),
        default=1,
    )
    if independent_count == 0:
        novelty_value = 10
        novelty_reason = "novelty:no_independent_source"
    elif duplicate_count > independent_count:
        novelty_value = 40
        novelty_reason = "novelty:mostly_reprints"
    else:
        novelty_value = 70
        novelty_reason = "novelty:new_in_current_catalog"
    immediacy = max(immediacy_values, key=lambda feature: feature.value)
    event_ref = f"event:{market_event_id(event)}"
    return EventImportanceFeatures(
        materiality=materiality,
        breadth=FeatureScore(breadth_value, (breadth_reason,), (event_ref,)),
        novelty=FeatureScore(novelty_value, (novelty_reason,), (event_ref,)),
        immediacy=immediacy,
    )


def _directness(
    event: MarketEvent,
    ledger: EvidenceLedger,
    company: AShareCompany | None,
    claims: tuple[Claim, ...],
) -> FeatureScore:
    evidence = tuple(f"claim:{claim.id}" for claim in claims)
    if any(
        identity.official and identity.source_type == "announcement"
        for identity in ledger.source_identities
    ):
        return FeatureScore(100, ("directness:official_announcement",), evidence)
    if any(
        identity.official and identity.source_type == "policy"
        for identity in ledger.source_identities
    ):
        return FeatureScore(95, ("directness:official_policy",), evidence)
    if company is not None and (
        any(company.symbol in claim.affected_symbols for claim in claims)
        or _normalize(company.name) in _normalize(_claim_text(claims))
    ):
        return FeatureScore(85, ("directness:explicit_company",), evidence)
    if company is not None:
        company_nodes = infer_value_chain_nodes(
            " ".join((*company.themes, company.business_summary))
        )
        event_nodes = infer_value_chain_nodes(
            " ".join((event.title, event.summary, _claim_text(claims)))
        )
        relation = best_value_chain_relation(company_nodes, event_nodes)
        if relation is not None and relation.distance == 0:
            return FeatureScore(70, ("directness:same_value_chain_node",), evidence)
        if relation is not None and relation.distance == 1:
            return FeatureScore(45, ("directness:one_hop_value_chain",), evidence)
        if relation is not None:
            return FeatureScore(25, ("directness:multi_hop_value_chain",), evidence)
        if any(
            _normalize(theme) in _normalize(_claim_text(claims))
            for theme in company.themes
        ):
            return FeatureScore(10, ("directness:theme_only",), evidence)
    return FeatureScore(0, ("directness:unverified",), evidence)


def _exposure(
    event: MarketEvent,
    company: AShareCompany | None,
    claims: tuple[Claim, ...],
) -> FeatureScore:
    evidence = tuple(f"claim:{claim.id}" for claim in claims)
    ratio = _fact_value(claims, {"related_revenue_ratio_pct", "相关业务收入占比"})
    if ratio is not None:
        value = _exposure_score(abs(ratio))
        return FeatureScore(value, ("exposure:reported_ratio",), evidence)
    if company is None:
        return FeatureScore(0, ("exposure:unverified_company",), evidence)
    event_text = _normalize(" ".join((event.title, event.summary, _claim_text(claims))))
    matches = sum(
        bool(_normalize(theme) and _normalize(theme) in event_text)
        for theme in company.themes
    )
    if matches >= 2:
        return FeatureScore(45, ("exposure:multiple_product_matches",), evidence)
    if matches == 1 or (
        company.business_summary
        and any(
            token in _normalize(company.business_summary)
            for token in _event_tokens(event_text)
        )
    ):
        return FeatureScore(35, ("exposure:product_relation_ratio_unknown",), evidence)
    return FeatureScore(20, ("exposure:industry_only",), evidence)


def _duration(claims: tuple[Claim, ...]) -> FeatureScore:
    scores = {
        "immediate": 20,
        "short": 35,
        "medium": 65,
        "long": 90,
        "unknown": 30,
    }
    claim = max(claims, key=lambda value: scores[value.time_horizon])
    return FeatureScore(
        scores[claim.time_horizon],
        (f"duration:{claim.time_horizon}",),
        (f"claim:{claim.id}",),
    )


def _sensitivity(
    company: AShareCompany | None,
    claims: tuple[Claim, ...],
) -> FeatureScore:
    evidence = tuple(f"claim:{claim.id}" for claim in claims)
    text = _claim_text(claims)
    if any(marker in text for marker in ("核心资质", "唯一供应商", "独家", "正式获批")):
        return FeatureScore(90, ("sensitivity:core_barrier",), evidence)
    if company is not None and company.business_summary:
        return FeatureScore(60, ("sensitivity:business_evidence",), evidence)
    return FeatureScore(30, ("sensitivity:insufficient_business_evidence",), evidence)


def _order_scale(
    claims: Sequence[Claim],
    financials: Sequence[FinancialSnapshot],
) -> FeatureScore:
    evidence = _claim_refs(claims)
    ratio = _fact_value(claims, {"contract_revenue_ratio_pct", "合同金额营收占比"})
    if ratio is None:
        amount = _amount_value(claims, {"contract_amount", "合同金额"})
        revenue = _ttm_value(financials, "revenue")
        ratio = amount / revenue * 100 if amount is not None and revenue else None
    if ratio is None:
        return FeatureScore(
            50,
            ("economic_scale:order_estimate_cap", "missing:ttm_revenue"),
            evidence,
        )
    value = _ratio_scale(ratio)
    feature = FeatureScore(value, ("economic_scale:contract_revenue_ratio",), evidence)
    if any(marker in _claim_text(claims) for marker in ("框架协议", "意向协议")):
        return _cap(feature, 60, "economic_scale:non_binding_agreement")
    return feature


def _earnings_scale(
    claims: Sequence[Claim],
    financials: Sequence[FinancialSnapshot],
) -> FeatureScore:
    evidence = _claim_refs(claims)
    changes = [
        abs(value)
        for value in (
            _fact_value(claims, {"revenue_yoy_pct", "营业收入同比"}),
            _fact_value(claims, {"net_profit_yoy_pct", "净利润同比"}),
            *(snapshot.revenue_yoy for snapshot in financials),
            *(snapshot.net_profit_yoy for snapshot in financials),
        )
        if value is not None
    ]
    value = _percentage_scale(max(changes)) if changes else 30
    feature = FeatureScore(value, ("economic_scale:earnings_change",), evidence)
    text = _claim_text(claims)
    has_benchmark = _fact_value(
        claims,
        {"expectation_delta_pct", "相对预期偏差"},
    ) is not None
    if "超预期" in text and not has_benchmark:
        return _cap(feature, 50, "missing:expectation_benchmark")
    return feature


def _corporate_action_scale(claims: Sequence[Claim]) -> FeatureScore:
    evidence = _claim_refs(claims)
    ratio = _fact_value(
        claims,
        {"share_change_pct", "股份变动比例", "股份数量占总股本"},
    )
    if ratio is None:
        amount = _amount_value(
            claims,
            {"buyback_amount", "reduction_amount", "回购金额", "减持金额"},
        )
        market_cap = _amount_value(claims, {"market_cap", "市值"})
        ratio = amount / market_cap * 100 if amount is not None and market_cap else None
    value = _share_ratio_scale(abs(ratio)) if ratio is not None else 40
    return FeatureScore(value, ("economic_scale:corporate_action",), evidence)


def _risk_scale(
    claims: Sequence[Claim],
    financials: Sequence[FinancialSnapshot],
) -> FeatureScore:
    evidence = _claim_refs(claims)
    text = _claim_text(claims)
    if any(
        marker in text
        for marker in (
            "核心资质",
            "核心经营资质",
            "主要工厂停产",
            "退市风险",
            "重大偿付风险",
        )
    ):
        return FeatureScore(95, ("economic_scale:core_operating_risk",), evidence)
    amount = _amount_value(claims, {"litigation_amount", "涉案金额", "penalty_amount"})
    net_assets = _amount_value(claims, {"net_assets", "净资产"})
    net_profit = _ttm_value(financials, "net_profit")
    denominator = net_assets or net_profit
    if amount is None or not denominator:
        return FeatureScore(
            50,
            ("economic_scale:risk_estimate_cap", "missing:risk_denominator"),
            evidence,
        )
    return FeatureScore(
        _ratio_scale(amount / abs(denominator) * 100),
        ("economic_scale:risk_financial_ratio",),
        evidence,
    )


def _capex_scale(claims: Sequence[Claim]) -> FeatureScore:
    evidence = _claim_refs(claims)
    amount = _amount_value(claims, {"capex_amount", "投资金额"})
    assets = _amount_value(claims, {"total_assets", "总资产"})
    if amount is None or not assets:
        return FeatureScore(
            50,
            ("economic_scale:capex_estimate_cap", "missing:total_assets"),
            evidence,
        )
    return FeatureScore(
        _ratio_scale(amount / assets * 100),
        ("economic_scale:capex_assets_ratio",),
        evidence,
    )


def _commodity_scale(claims: Sequence[Claim]) -> FeatureScore:
    evidence = _claim_refs(claims)
    change = _fact_value(
        claims,
        {"commodity_price_change_pct", "price_change_pct", "价格变化幅度"},
    )
    if change is None:
        return FeatureScore(
            40,
            ("economic_scale:commodity_change_unknown",),
            evidence,
        )
    return FeatureScore(
        _commodity_percentage_scale(abs(change)),
        ("economic_scale:commodity_price_change",),
        evidence,
    )


def _policy_scale(claims: Sequence[Claim]) -> FeatureScore:
    evidence = _claim_refs(claims)
    text = _claim_text(claims)
    if "已生效" in text or "正式生效" in text:
        value = 90
        reason = "economic_scale:effective_policy"
    elif "正式发布" in text:
        value = 70
        reason = "economic_scale:formal_policy"
    elif "征求意见" in text:
        value = 30
        reason = "economic_scale:policy_consultation"
    else:
        value = 40
        reason = "economic_scale:policy_statement"
    return FeatureScore(value, (reason,), evidence)


def _approval_scale(claims: Sequence[Claim]) -> FeatureScore:
    evidence = _claim_refs(claims)
    text = _claim_text(claims)
    if "正式获批" in text or "已获批" in text:
        value = 90
        reason = "economic_scale:formal_approval"
    elif "三期" in text or "iii期" in text.casefold():
        value = 70
        reason = "economic_scale:late_stage_research"
    elif "二期" in text or "ii期" in text.casefold():
        value = 50
        reason = "economic_scale:mid_stage_research"
    elif "早期研发" in text or any(claim.claim_type == "forecast" for claim in claims):
        value = 20
        reason = "economic_scale:early_research"
    else:
        value = 40
        reason = "economic_scale:product_progress"
    return FeatureScore(value, (reason,), evidence)


def _generic_scale(claims: Sequence[Claim]) -> FeatureScore:
    values = [
        abs(fact.value)
        for claim in claims
        for fact in claim.quantitative_facts
        if fact.unit == "%"
    ]
    value = _percentage_scale(max(values)) if values else 30
    return FeatureScore(value, ("economic_scale:generic",), _claim_refs(claims))


def _immediacy(claims: Sequence[Claim], kind: str) -> FeatureScore:
    evidence = _claim_refs(claims)
    text = _claim_text(claims)
    if kind == "policy" and ("已生效" in text or "正式生效" in text):
        return FeatureScore(95, ("immediacy:effective",), evidence)
    if kind == "policy" and "征求意见" in text:
        return FeatureScore(40, ("immediacy:consultation",), evidence)
    if kind == "approval" and ("正式获批" in text or "已获批" in text):
        return FeatureScore(95, ("immediacy:approved",), evidence)
    if kind == "capex" and any(
        marker in text for marker in ("时间表尚未明确", "没有时间表", "规划")
    ):
        return FeatureScore(40, ("immediacy:capex_plan_without_timeline",), evidence)
    if kind == "order" and any(marker in text for marker in ("框架协议", "意向协议")):
        return FeatureScore(40, ("immediacy:non_binding_agreement",), evidence)
    scores = {
        "immediate": 95,
        "short": 80,
        "medium": 60,
        "long": 35,
        "unknown": 20,
    }
    claim = max(claims, key=lambda value: scores[value.time_horizon])
    return FeatureScore(
        scores[claim.time_horizon],
        (f"immediacy:{claim.time_horizon}",),
        (f"claim:{claim.id}",),
    )


def _ratio_scale(value: float) -> int:
    value = abs(value)
    if value < 2:
        return 15
    if value < 10:
        return 35
    if value < 30:
        return 60
    if value <= 50:
        return 80
    return 95


def _share_ratio_scale(value: float) -> int:
    if value < 0.5:
        return 15
    if value < 2:
        return 35
    if value < 5:
        return 60
    if value < 10:
        return 80
    return 95


def _percentage_scale(value: float) -> int:
    if value < 5:
        return 15
    if value < 15:
        return 35
    if value < 30:
        return 60
    if value < 50:
        return 80
    return 95


def _commodity_percentage_scale(value: float) -> int:
    if value < 2:
        return 15
    if value < 5:
        return 35
    if value < 10:
        return 60
    if value < 20:
        return 80
    return 95


def _exposure_score(value: float) -> int:
    if value < 10:
        return 35
    if value < 30:
        return 50
    if value < 60:
        return 70
    return 90


def _fact_value(claims: Sequence[Claim], metrics: set[str]) -> float | None:
    normalized_metrics = {_normalize(metric) for metric in metrics}
    values = [
        fact.value
        for claim in claims
        for fact in claim.quantitative_facts
        if _normalize(fact.metric) in normalized_metrics
    ]
    return max(values, key=abs) if values else None


def _amount_value(claims: Sequence[Claim], metrics: set[str]) -> float | None:
    normalized_metrics = {_normalize(metric) for metric in metrics}
    values = [
        _to_cny(fact.value, fact.unit)
        for claim in claims
        for fact in claim.quantitative_facts
        if _normalize(fact.metric) in normalized_metrics
    ]
    values = [value for value in values if value is not None]
    return max(values, key=abs) if values else None


def _to_cny(value: float, unit: str) -> float | None:
    normalized = unicodedata.normalize("NFKC", unit).strip().casefold()
    multipliers = {
        "元": 1,
        "人民币元": 1,
        "万元": 10_000,
        "亿元": 100_000_000,
    }
    multiplier = multipliers.get(normalized)
    return value * multiplier if multiplier is not None else None


def _ttm_value(
    financials: Sequence[FinancialSnapshot],
    field: str,
) -> float | None:
    values = [
        (snapshot.report_period, getattr(snapshot, field))
        for snapshot in financials
        if getattr(snapshot, field) is not None
    ]
    if not values:
        return None
    latest_period, latest_value = max(values, key=lambda item: item[0])
    if latest_period.endswith("12-31"):
        return float(latest_value)
    if len(values) >= 4:
        return float(sum(value for _, value in sorted(values, reverse=True)[:4]))
    return None


def _claim_text(claims: Sequence[Claim]) -> str:
    return " ".join(
        f"{claim.subject} {claim.predicate} {claim.object}"
        for claim in claims
    )


def _claim_refs(claims: Sequence[Claim]) -> tuple[str, ...]:
    return tuple(f"claim:{claim.id}" for claim in claims)


def _cap(feature: FeatureScore, maximum: int, reason: str) -> FeatureScore:
    if feature.value <= maximum:
        return feature
    return FeatureScore(
        maximum,
        tuple(dict.fromkeys((*feature.reason_codes, reason))),
        feature.evidence_refs,
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _event_tokens(normalized_text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", normalized_text)
        if len(token) >= 2
    )
