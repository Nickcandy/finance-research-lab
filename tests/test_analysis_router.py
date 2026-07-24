from __future__ import annotations

import pytest

from finance_research_lab.analysis_router import AnalysisRouter
from finance_research_lab.impact_assessment import (
    ConfidenceFeatures,
    EventImportanceFeatures,
    FeatureScore,
    StockImpactFeatures,
    build_impact_assessment,
)


def _score(value: int) -> FeatureScore:
    return FeatureScore(value, (f"fixture:{value}",), ("fixture:evidence",))


def _assessment(
    *,
    magnitude: int,
    confidence: int,
    not_applicable: bool = False,
):
    stock = StockImpactFeatures(
        directness=_score(magnitude),
        exposure=_score(magnitude),
        economic_scale=_score(magnitude),
        duration=_score(magnitude),
        sensitivity=_score(magnitude),
    )
    confidence_features = ConfidenceFeatures(
        source_quality=_score(confidence),
        corroboration=_score(confidence),
        identity_verification=_score(confidence),
        quantitative_completeness=_score(confidence),
        consistency=_score(confidence),
    )
    return build_impact_assessment(
        event_id="evt_test",
        symbol="300308.SZ",
        event_features=EventImportanceFeatures(
            materiality=_score(magnitude),
            breadth=_score(50),
            novelty=_score(50),
            immediacy=_score(50),
        ),
        positive_features=stock,
        negative_features=None,
        confidence_features=confidence_features,
        not_applicable=not_applicable,
    )


@pytest.mark.parametrize(
    ("magnitude", "confidence", "expected_tier", "verify_first"),
    [
        (80, 80, "pro", False),
        (70, 40, "pro", True),
        (65, 60, "pro", False),
        (45, 60, "flash", False),
        (20, 60, "deterministic", False),
    ],
)
def test_router_uses_only_deterministic_assessment(
    magnitude: int,
    confidence: int,
    expected_tier: str,
    verify_first: bool,
) -> None:
    route = AnalysisRouter().route(
        _assessment(magnitude=magnitude, confidence=confidence)
    )

    assert route.analysis_tier == expected_tier
    assert route.verify_first is verify_first
    assert route.reason_codes[0] == f"route:{expected_tier}"


def test_router_preserves_not_applicable() -> None:
    route = AnalysisRouter().route(
        _assessment(magnitude=80, confidence=80, not_applicable=True)
    )

    assert route.analysis_tier == "not_applicable"
