from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .models import ConfidenceLevel, ImpactDirection, ResearchReport, StockImpact

_POSITIVE_MARKERS = (
    "利好",
    "上调",
    "超预期",
    "需求增长",
    "扭亏",
    "中标",
    "获批",
    "增持",
    "回购",
    "涨停",
    "大涨",
    "上涨",
    "走高",
    "创新高",
    "站上",
)
_NEGATIVE_MARKERS = (
    "利空",
    "下调",
    "不及预期",
    "亏损",
    "减持",
    "立案",
    "处罚",
    "违约",
    "召回",
    "停产",
    "退市",
    "跌停",
    "大跌",
    "下跌",
    "下挫",
    "走低",
    "失守",
)
_NEUTRAL_MARKERS = ("持平", "维持不变", "暂无影响")
_STRENGTH_SCORE = {"high": 80, "medium": 55, "low": 30}
_TYPE_PENALTY = {"direct": 0, "negative": 0, "indirect": 10, "sentiment": 20}
_CONFIDENCE_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_DIRECTION_LABELS = {
    "positive": "利好",
    "negative": "利空",
    "mixed": "多空分化",
    "neutral": "中性",
    "unknown": "待判断",
}


@dataclass(frozen=True)
class EventImpactSummary:
    direction: ImpactDirection
    score: int | None
    confidence: ConfidenceLevel


def impact_direction_label(direction: ImpactDirection) -> str:
    return _DIRECTION_LABELS[direction]


def format_impact_score(score: int | None) -> str:
    return "待判断" if score is None else f"{score:+d}"


def infer_news_impact_direction(text: str) -> ImpactDirection:
    """Conservatively classify explicit language; absence of a marker stays unknown."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    positive = any(marker in normalized for marker in _POSITIVE_MARKERS)
    negative = any(marker in normalized for marker in _NEGATIVE_MARKERS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    if any(marker in normalized for marker in _NEUTRAL_MARKERS):
        return "neutral"
    return "unknown"


def stock_impact_score(impact: StockImpact) -> int | None:
    """Return a transparent research impact index, not a price-return forecast."""

    if impact.verification_status == "excluded" or impact.impact_type == "false_positive":
        return None
    if impact.impact_direction == "neutral":
        return 0
    if impact.impact_direction in {"mixed", "unknown"}:
        return None
    base = _STRENGTH_SCORE.get(impact.impact_strength)
    penalty = _TYPE_PENALTY.get(impact.impact_type)
    if base is None or penalty is None:
        return None
    magnitude = max(10, base - penalty)
    return magnitude if impact.impact_direction == "positive" else -magnitude


def combine_impact_directions(
    directions: Iterable[ImpactDirection],
) -> ImpactDirection:
    values = {direction for direction in directions if direction != "unknown"}
    if not values:
        return "unknown"
    if "mixed" in values or {"positive", "negative"}.issubset(values):
        return "mixed"
    if values == {"neutral"}:
        return "neutral"
    if "positive" in values:
        return "positive"
    if "negative" in values:
        return "negative"
    return "neutral"


def strongest_confidence(values: Iterable[ConfidenceLevel]) -> ConfidenceLevel:
    return max(values, key=lambda value: _CONFIDENCE_ORDER[value], default="unknown")


def summarize_event_impact(report: ResearchReport) -> EventImpactSummary:
    impacts = tuple(
        impact
        for impact in report.stock_impacts
        if impact.verification_status != "excluded" and impact.impact_type != "false_positive"
    )
    scores = tuple(score for impact in impacts if (score := stock_impact_score(impact)) is not None)
    candidate_direction = combine_impact_directions(
        impact.impact_direction for impact in impacts
    )
    direction = (
        candidate_direction
        if candidate_direction != "unknown"
        else report.value_chain.impact_direction
    )
    score = round(sum(scores) / len(scores)) if scores else None
    return EventImpactSummary(direction, score, report.event.confidence)
