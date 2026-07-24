from __future__ import annotations

from dataclasses import dataclass

from .impact_assessment import AnalysisTier, ImpactAssessment, PriorityLevel


@dataclass(frozen=True)
class AnalysisRoute:
    event_id: str
    analysis_tier: AnalysisTier
    priority_level: PriorityLevel
    reason_codes: tuple[str, ...]
    verify_first: bool


class AnalysisRouter:
    def route(self, assessment: ImpactAssessment) -> AnalysisRoute:
        reason_codes = tuple(
            dict.fromkeys(
                (
                    f"route:{assessment.analysis_tier}",
                    f"priority:{assessment.priority_level}",
                    *assessment.reason_codes,
                )
            )
        )
        return AnalysisRoute(
            event_id=assessment.event_id,
            analysis_tier=assessment.analysis_tier,
            priority_level=assessment.priority_level,
            reason_codes=reason_codes,
            verify_first=assessment.priority_level == "verify_first",
        )
