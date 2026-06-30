from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Stage = Literal["启动", "验证", "高潮", "分歧", "退潮", "待判断"]
ActionState = Literal["忽略", "放观察池", "等验证", "等回调", "可小仓试", "高潮勿追", "待判断"]
ImpactType = Literal["direct", "indirect", "sentiment", "negative", "false_positive"]
ImpactStrength = Literal["high", "medium", "low", "unknown"]
VerificationStatus = Literal["verified", "unverified", "excluded"]
ValidationStatus = Literal["pending", "done", "blocked"]
EvidenceSourceType = Literal["news", "watchlist", "stock_impact", "agent"]


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    market: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    thesis: str = ""
    risks: str = ""


@dataclass(frozen=True)
class AShareCompany:
    symbol: str
    name: str
    market: str
    industry: str = ""
    themes: tuple[str, ...] = field(default_factory=tuple)
    business_summary: str = ""
    source: str = ""


@dataclass(frozen=True)
class NewsTrace:
    headline: str
    source: str
    news_type: str
    payer: str
    receiver: str
    value_chain: list[str]
    direct_beneficiaries: list[WatchlistItem]
    indirect_beneficiaries: list[WatchlistItem]
    sentiment_mappings: list[WatchlistItem]
    stage: Stage
    action_state: ActionState
    verification_points: list[str]


@dataclass(frozen=True)
class RawNews:
    headline: str
    source: str
    url: str = ""
    published_at: str = ""
    body: str = ""


@dataclass(frozen=True)
class EventAnalysis:
    event_type: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    involved_entities: tuple[str, ...] = field(default_factory=tuple)
    key_facts: tuple[str, ...] = field(default_factory=tuple)
    source_quality: str = "待复核"
    confidence: str = "low"
    reasoning: str = ""


@dataclass(frozen=True)
class ValueChainTrace:
    payer: str
    receiver: str
    chain_steps: tuple[str, ...] = field(default_factory=tuple)
    impact_direction: str = "unknown"
    reasoning: str = ""


@dataclass(frozen=True)
class StockImpact:
    symbol: str
    name: str
    market: str
    impact_type: ImpactType
    impact_strength: ImpactStrength = "unknown"
    themes: tuple[str, ...] = field(default_factory=tuple)
    reasoning: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    risks: tuple[str, ...] = field(default_factory=tuple)
    verification_status: VerificationStatus = "verified"
    verification_source: str = ""
    watchlist_hit: bool = False


@dataclass(frozen=True)
class ValidationTask:
    question: str
    data_needed: str
    status: ValidationStatus = "pending"


@dataclass(frozen=True)
class ResearchTask:
    question: str
    rationale: str
    data_needed: str
    status: ValidationStatus = "pending"


@dataclass(frozen=True)
class Evidence:
    source_type: EvidenceSourceType
    title: str
    url: str
    summary: str
    supports: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResearchReport:
    raw_news: RawNews
    event: EventAnalysis
    value_chain: ValueChainTrace
    stock_impacts: tuple[StockImpact, ...]
    validation_tasks: tuple[ValidationTask, ...]
    stage: Stage
    action_state: ActionState


@dataclass(frozen=True)
class ResearchAgentResult:
    tasks: tuple[ResearchTask, ...]
    evidence: tuple[Evidence, ...]
    report: ResearchReport
