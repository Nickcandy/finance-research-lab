from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from finance_research_lab.claims import Claim, QuantitativeFact
from finance_research_lab.impact_assessment import (
    SCORING_VERSION,
    ConfidenceFeatures,
    EventImportanceFeatures,
    FeatureScore,
    StockImpactFeatures,
    analysis_tier_for_priority,
    build_impact_assessment,
    calculate_confidence,
    calculate_event_importance,
    calculate_stock_impact_magnitude,
    cap_feature_score,
    classify_priority,
    resolve_impact_direction,
)


def _feature(value: int, reason: str = "test_reason") -> FeatureScore:
    return FeatureScore(value, (reason,), ("claim:test",))


def _event_features(
    materiality: int = 90,
    breadth: int = 50,
    novelty: int = 90,
    immediacy: int = 80,
) -> EventImportanceFeatures:
    return EventImportanceFeatures(
        materiality=_feature(materiality, "materiality"),
        breadth=_feature(breadth, "breadth"),
        novelty=_feature(novelty, "novelty"),
        immediacy=_feature(immediacy, "immediacy"),
    )


def _stock_features(
    directness: int = 100,
    exposure: int = 90,
    economic_scale: int = 95,
    duration: int = 75,
    sensitivity: int = 60,
) -> StockImpactFeatures:
    return StockImpactFeatures(
        directness=_feature(directness, "directness"),
        exposure=_feature(exposure, "exposure"),
        economic_scale=_feature(economic_scale, "economic_scale"),
        duration=_feature(duration, "duration"),
        sensitivity=_feature(sensitivity, "sensitivity"),
    )


def _confidence_features(
    source_quality: int = 95,
    corroboration: int = 80,
    identity_verification: int = 100,
    quantitative_completeness: int = 90,
    consistency: int = 90,
) -> ConfidenceFeatures:
    return ConfidenceFeatures(
        source_quality=_feature(source_quality, "source_quality"),
        corroboration=_feature(corroboration, "corroboration"),
        identity_verification=_feature(
            identity_verification,
            "identity_verification",
        ),
        quantitative_completeness=_feature(
            quantitative_completeness,
            "quantitative_completeness",
        ),
        consistency=_feature(consistency, "consistency"),
    )


def test_claim_keeps_quantitative_fact_source_reference() -> None:
    fact = QuantitativeFact(
        metric="contract_amount",
        value=20,
        unit="亿元",
        period="2026-2028",
        source_item_id="news:1",
    )
    claim = Claim(
        id="claim:1",
        event_id="event:1",
        source_item_ids=("news:1",),
        subject="测试公司",
        predicate="签订",
        object="重大合同",
        claim_type="fact",
        event_type="订单 / 合同",
        direction="positive",
        time_horizon="medium",
        affected_symbols=("300308.SZ",),
        quantitative_facts=(fact,),
        confidence="high",
        occurred_at="2026-07-24T08:00:00+08:00",
    )

    assert claim.quantitative_facts[0].source_item_id == "news:1"
    with pytest.raises(FrozenInstanceError):
        claim.subject = "不可修改"  # type: ignore[misc]


@pytest.mark.parametrize("value", [-1, 101, True, 1.5])
def test_feature_score_rejects_invalid_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        FeatureScore(value, ("reason",), ("claim:1",))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("reason_codes", "evidence_refs"),
    [
        ((), ("claim:1",)),
        (("reason",), ()),
        (("",), ("claim:1",)),
        (("reason",), ("",)),
    ],
)
def test_feature_score_requires_explanations(
    reason_codes: tuple[str, ...],
    evidence_refs: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        FeatureScore(50, reason_codes, evidence_refs)


def test_weighted_scores_use_half_up_rounding() -> None:
    assert calculate_event_importance(_event_features()) == 78
    assert calculate_stock_impact_magnitude(_stock_features()) == 89
    assert calculate_confidence(_confidence_features()) == 92

    half_point = _stock_features(1, 1, 0, 0, 0)
    assert calculate_stock_impact_magnitude(half_point) == 1


def test_feature_cap_keeps_explanation_and_records_reason() -> None:
    original = _feature(90, "raw_estimate")

    capped = cap_feature_score(original, 60, "missing_relative_metric")

    assert capped.value == 60
    assert capped.reason_codes == ("raw_estimate", "missing_relative_metric")
    assert capped.evidence_refs == ("claim:test",)
    assert cap_feature_score(_feature(40), 60, "unused") == _feature(40)


@pytest.mark.parametrize(
    ("positive", "negative", "expected"),
    [
        (80, 0, "positive"),
        (0, 80, "negative"),
        (80, 60, "positive"),
        (60, 80, "negative"),
        (80, 61, "mixed"),
        (60, 60, "mixed"),
        (0, 0, "unknown"),
    ],
)
def test_direction_preserves_positive_and_negative_sides(
    positive: int,
    negative: int,
    expected: str,
) -> None:
    assert resolve_impact_direction(positive, negative) == expected


def test_priority_rules_cover_hard_upgrades_and_confidence_gap() -> None:
    assert (
        classify_priority(
            event_importance=60,
            positive_magnitude=60,
            negative_magnitude=0,
            confidence=40,
            official_major_announcement=True,
        )
        == "critical"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=0,
            negative_magnitude=60,
            confidence=20,
            watchlist_hit=True,
        )
        == "critical"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=60,
            negative_magnitude=60,
            confidence=70,
        )
        == "critical"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=80,
            negative_magnitude=0,
            confidence=20,
        )
        == "verify_first"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=80,
            negative_magnitude=0,
            confidence=55,
        )
        == "high"
    )
    assert (
        classify_priority(
            event_importance=80,
            positive_magnitude=20,
            negative_magnitude=0,
            confidence=70,
            verified_a_share_relation=True,
        )
        == "high"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=45,
            negative_magnitude=0,
            confidence=30,
        )
        == "medium"
    )
    assert (
        classify_priority(
            event_importance=40,
            positive_magnitude=20,
            negative_magnitude=0,
            confidence=80,
        )
        == "low"
    )


def test_analysis_tier_is_deterministic() -> None:
    assert analysis_tier_for_priority("critical") == "pro"
    assert analysis_tier_for_priority("verify_first") == "pro"
    assert analysis_tier_for_priority("high") == "pro"
    assert analysis_tier_for_priority("medium") == "flash"
    assert analysis_tier_for_priority("low") == "deterministic"
    assert analysis_tier_for_priority("low", not_applicable=True) == "not_applicable"
    with pytest.raises(ValueError):
        analysis_tier_for_priority("invalid")  # type: ignore[arg-type]


def test_build_assessment_keeps_breakdown_and_is_repeatable() -> None:
    inputs = {
        "event_id": "evt_1",
        "symbol": "300308.SZ",
        "event_features": _event_features(),
        "positive_features": _stock_features(),
        "negative_features": None,
        "confidence_features": _confidence_features(),
        "official_major_announcement": True,
        "verified_a_share_relation": True,
    }

    first = build_impact_assessment(**inputs)
    second = build_impact_assessment(**inputs)

    assert first == second
    assert first.scoring_version == SCORING_VERSION == "1.1"
    assert first.event_importance == 78
    assert first.positive_magnitude == 89
    assert first.negative_magnitude == 0
    assert first.confidence == 92
    assert first.conflict_score == 0
    assert first.direction == "positive"
    assert first.priority_level == "critical"
    assert first.analysis_tier == "pro"
    assert first.event_features.materiality.reason_codes == ("materiality",)
    assert "materiality" in first.reason_codes
