from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .impact_horizon import DirectionalHorizons
from .models import ImpactDirection

SCORING_VERSION = "1.1"

PriorityLevel = Literal["critical", "high", "medium", "low", "verify_first"]
AnalysisTier = Literal["pro", "flash", "deterministic", "not_applicable"]


@dataclass(frozen=True)
class FeatureScore:
    value: int
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_score(self.value, "value")
        _validate_labels(self.reason_codes, "reason_codes")
        _validate_labels(self.evidence_refs, "evidence_refs")


@dataclass(frozen=True)
class EventImportanceFeatures:
    materiality: FeatureScore
    breadth: FeatureScore
    novelty: FeatureScore
    immediacy: FeatureScore


@dataclass(frozen=True)
class StockImpactFeatures:
    directness: FeatureScore
    exposure: FeatureScore
    economic_scale: FeatureScore
    duration: FeatureScore
    sensitivity: FeatureScore


@dataclass(frozen=True)
class ConfidenceFeatures:
    source_quality: FeatureScore
    corroboration: FeatureScore
    identity_verification: FeatureScore
    quantitative_completeness: FeatureScore
    consistency: FeatureScore


@dataclass(frozen=True)
class ImpactAssessment:
    event_id: str
    symbol: str
    direction: ImpactDirection
    event_importance: int
    positive_magnitude: int
    negative_magnitude: int
    confidence: int
    conflict_score: int
    event_features: EventImportanceFeatures
    positive_features: StockImpactFeatures | None
    negative_features: StockImpactFeatures | None
    positive_horizon: DirectionalHorizons | None
    negative_horizon: DirectionalHorizons | None
    confidence_features: ConfidenceFeatures
    priority_level: PriorityLevel
    analysis_tier: AnalysisTier
    reason_codes: tuple[str, ...]
    scoring_version: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        for field_name in (
            "event_importance",
            "positive_magnitude",
            "negative_magnitude",
            "confidence",
            "conflict_score",
        ):
            _validate_score(getattr(self, field_name), field_name)
        _validate_labels(self.reason_codes, "reason_codes")
        if not self.scoring_version.strip():
            raise ValueError("scoring_version must not be empty")


def cap_feature_score(
    feature: FeatureScore,
    maximum: int,
    reason_code: str,
) -> FeatureScore:
    _validate_score(maximum, "maximum")
    if feature.value <= maximum:
        return feature
    if not reason_code.strip():
        raise ValueError("reason_code must not be empty")
    return FeatureScore(
        maximum,
        _unique((*feature.reason_codes, reason_code)),
        feature.evidence_refs,
    )


def calculate_event_importance(features: EventImportanceFeatures) -> int:
    return _weighted_score(
        (
            (features.materiality, 35),
            (features.breadth, 25),
            (features.novelty, 20),
            (features.immediacy, 20),
        )
    )


def calculate_stock_impact_magnitude(features: StockImpactFeatures) -> int:
    return _weighted_score(
        (
            (features.directness, 25),
            (features.exposure, 25),
            (features.economic_scale, 25),
            (features.duration, 15),
            (features.sensitivity, 10),
        )
    )


def calculate_confidence(features: ConfidenceFeatures) -> int:
    return _weighted_score(
        (
            (features.source_quality, 35),
            (features.corroboration, 20),
            (features.identity_verification, 20),
            (features.quantitative_completeness, 15),
            (features.consistency, 10),
        )
    )


def resolve_impact_direction(
    positive_magnitude: int,
    negative_magnitude: int,
) -> ImpactDirection:
    _validate_score(positive_magnitude, "positive_magnitude")
    _validate_score(negative_magnitude, "negative_magnitude")
    if positive_magnitude >= negative_magnitude + 20:
        return "positive"
    if negative_magnitude >= positive_magnitude + 20:
        return "negative"
    if max(positive_magnitude, negative_magnitude) == 0:
        return "unknown"
    return "mixed"


def classify_priority(
    *,
    event_importance: int,
    positive_magnitude: int,
    negative_magnitude: int,
    confidence: int,
    official_major_announcement: bool = False,
    watchlist_hit: bool = False,
    hard_risk: bool = False,
    hard_upgrade: bool = False,
    multiple_independent_major_events: bool = False,
    verified_a_share_relation: bool = False,
    corroborated_by_high_quality_sources: bool = False,
) -> PriorityLevel:
    level, _ = _priority_decision(
        event_importance=event_importance,
        positive_magnitude=positive_magnitude,
        negative_magnitude=negative_magnitude,
        confidence=confidence,
        official_major_announcement=official_major_announcement,
        watchlist_hit=watchlist_hit,
        hard_risk=hard_risk,
        hard_upgrade=hard_upgrade,
        multiple_independent_major_events=multiple_independent_major_events,
        verified_a_share_relation=verified_a_share_relation,
        corroborated_by_high_quality_sources=corroborated_by_high_quality_sources,
    )
    return level


def analysis_tier_for_priority(
    priority_level: PriorityLevel,
    *,
    not_applicable: bool = False,
) -> AnalysisTier:
    if priority_level not in {"critical", "verify_first", "high", "medium", "low"}:
        raise ValueError(f"unsupported priority_level: {priority_level}")
    if not_applicable:
        return "not_applicable"
    if priority_level in {"critical", "verify_first", "high"}:
        return "pro"
    if priority_level == "medium":
        return "flash"
    return "deterministic"


def build_impact_assessment(
    *,
    event_id: str,
    symbol: str,
    event_features: EventImportanceFeatures,
    positive_features: StockImpactFeatures | None,
    negative_features: StockImpactFeatures | None,
    confidence_features: ConfidenceFeatures,
    positive_horizon: DirectionalHorizons | None = None,
    negative_horizon: DirectionalHorizons | None = None,
    official_major_announcement: bool = False,
    watchlist_hit: bool = False,
    hard_risk: bool = False,
    hard_upgrade: bool = False,
    multiple_independent_major_events: bool = False,
    verified_a_share_relation: bool = False,
    corroborated_by_high_quality_sources: bool = False,
    not_applicable: bool = False,
) -> ImpactAssessment:
    event_importance = calculate_event_importance(event_features)
    positive_magnitude = (
        calculate_stock_impact_magnitude(positive_features)
        if positive_features is not None
        else 0
    )
    negative_magnitude = (
        calculate_stock_impact_magnitude(negative_features)
        if negative_features is not None
        else 0
    )
    confidence = calculate_confidence(confidence_features)
    priority_level, priority_reasons = _priority_decision(
        event_importance=event_importance,
        positive_magnitude=positive_magnitude,
        negative_magnitude=negative_magnitude,
        confidence=confidence,
        official_major_announcement=official_major_announcement,
        watchlist_hit=watchlist_hit,
        hard_risk=hard_risk,
        hard_upgrade=hard_upgrade,
        multiple_independent_major_events=multiple_independent_major_events,
        verified_a_share_relation=verified_a_share_relation,
        corroborated_by_high_quality_sources=corroborated_by_high_quality_sources,
    )
    analysis_tier = analysis_tier_for_priority(
        priority_level,
        not_applicable=not_applicable,
    )
    feature_reasons = tuple(
        reason
        for feature in _assessment_features(
            event_features,
            positive_features,
            negative_features,
            confidence_features,
        )
        for reason in feature.reason_codes
    )
    return ImpactAssessment(
        event_id=event_id,
        symbol=symbol,
        direction=resolve_impact_direction(
            positive_magnitude,
            negative_magnitude,
        ),
        event_importance=event_importance,
        positive_magnitude=positive_magnitude,
        negative_magnitude=negative_magnitude,
        confidence=confidence,
        conflict_score=min(positive_magnitude, negative_magnitude),
        event_features=event_features,
        positive_features=positive_features,
        negative_features=negative_features,
        positive_horizon=positive_horizon,
        negative_horizon=negative_horizon,
        confidence_features=confidence_features,
        priority_level=priority_level,
        analysis_tier=analysis_tier,
        reason_codes=_unique(
            (
                *feature_reasons,
                *priority_reasons,
                f"analysis_tier:{analysis_tier}",
            )
        ),
        scoring_version=SCORING_VERSION,
    )


def _priority_decision(
    *,
    event_importance: int,
    positive_magnitude: int,
    negative_magnitude: int,
    confidence: int,
    official_major_announcement: bool,
    watchlist_hit: bool,
    hard_risk: bool,
    hard_upgrade: bool,
    multiple_independent_major_events: bool,
    verified_a_share_relation: bool,
    corroborated_by_high_quality_sources: bool,
) -> tuple[PriorityLevel, tuple[str, ...]]:
    for field_name, value in (
        ("event_importance", event_importance),
        ("positive_magnitude", positive_magnitude),
        ("negative_magnitude", negative_magnitude),
        ("confidence", confidence),
    ):
        _validate_score(value, field_name)
    magnitude = max(positive_magnitude, negative_magnitude)
    critical_reasons: list[str] = []
    if magnitude >= 75 and confidence >= 60:
        critical_reasons.append("critical:high_magnitude_high_confidence")
    if official_major_announcement and magnitude >= 60:
        critical_reasons.append("critical:official_major_announcement")
    if watchlist_hit and negative_magnitude >= 60:
        critical_reasons.append("critical:watchlist_negative")
    if positive_magnitude >= 60 and negative_magnitude >= 60:
        critical_reasons.append("critical:strong_two_sided_impact")
    if hard_risk:
        critical_reasons.append("critical:hard_risk")
    if hard_upgrade:
        critical_reasons.append("critical:hard_upgrade")
    if multiple_independent_major_events:
        critical_reasons.append("critical:multiple_independent_major_events")
    if critical_reasons:
        return "critical", tuple(critical_reasons)
    if magnitude >= 65 and confidence < 50:
        return "verify_first", ("verify_first:high_magnitude_low_confidence",)
    high_reasons: list[str] = []
    if magnitude >= 60 and confidence >= 50:
        high_reasons.append("high:material_stock_impact")
    if event_importance >= 75 and verified_a_share_relation:
        high_reasons.append("high:important_event_verified_relation")
    if corroborated_by_high_quality_sources:
        high_reasons.append("high:multiple_high_quality_sources")
    if high_reasons:
        return "high", tuple(high_reasons)
    if magnitude >= 35:
        return "medium", ("medium:moderate_stock_impact",)
    return "low", ("low:limited_stock_impact",)


def _weighted_score(features: Iterable[tuple[FeatureScore, int]]) -> int:
    weighted_sum = sum(feature.value * weight for feature, weight in features)
    return (weighted_sum + 50) // 100


def _assessment_features(
    event_features: EventImportanceFeatures,
    positive_features: StockImpactFeatures | None,
    negative_features: StockImpactFeatures | None,
    confidence_features: ConfidenceFeatures,
) -> tuple[FeatureScore, ...]:
    values = [
        event_features.materiality,
        event_features.breadth,
        event_features.novelty,
        event_features.immediacy,
    ]
    for stock_features in (positive_features, negative_features):
        if stock_features is not None:
            values.extend(
                (
                    stock_features.directness,
                    stock_features.exposure,
                    stock_features.economic_scale,
                    stock_features.duration,
                    stock_features.sensitivity,
                )
            )
    values.extend(
        (
            confidence_features.source_quality,
            confidence_features.corroboration,
            confidence_features.identity_verification,
            confidence_features.quantitative_completeness,
            confidence_features.consistency,
        )
    )
    return tuple(values)


def _validate_score(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if not 0 <= value <= 100:
        raise ValueError(f"{field_name} must be between 0 and 100")


def _validate_labels(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain non-empty values")


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
