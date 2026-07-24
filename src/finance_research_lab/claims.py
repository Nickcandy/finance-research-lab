from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import ConfidenceLevel, ImpactDirection

ClaimType = Literal[
    "fact",
    "forecast",
    "opinion",
    "risk",
    "denial",
    "market_reaction",
]
TimeHorizon = Literal["immediate", "short", "medium", "long", "unknown"]
ExtractionMethod = Literal["llm", "fallback"]


@dataclass(frozen=True)
class QuantitativeFact:
    metric: str
    value: float
    unit: str
    period: str
    source_item_id: str


@dataclass(frozen=True)
class Claim:
    id: str
    event_id: str
    source_item_ids: tuple[str, ...]
    subject: str
    predicate: str
    object: str
    claim_type: ClaimType
    event_type: str
    direction: ImpactDirection
    time_horizon: TimeHorizon
    affected_symbols: tuple[str, ...]
    quantitative_facts: tuple[QuantitativeFact, ...]
    confidence: ConfidenceLevel
    occurred_at: str
    extraction_method: ExtractionMethod = "llm"
