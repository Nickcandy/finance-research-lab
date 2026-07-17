from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Stage = Literal["启动", "验证", "高潮", "分歧", "退潮", "待判断"]
ActionState = Literal["忽略", "放观察池", "等验证", "等回调", "可小仓试", "高潮勿追", "待判断"]
ImpactType = Literal["direct", "indirect", "sentiment", "negative", "false_positive"]
ImpactStrength = Literal["high", "medium", "low", "unknown"]
ImpactDirection = Literal["positive", "negative", "mixed", "neutral", "unknown"]
ConfidenceLevel = Literal["high", "medium", "low", "unknown"]
VerificationStatus = Literal["verified", "unverified", "excluded"]
ValidationStatus = Literal["pending", "done", "blocked"]
EventSourceType = Literal["news", "announcement", "market_anomaly", "policy"]
EvidenceSourceType = Literal[
    "news",
    "watchlist",
    "stock_impact",
    "agent",
    "company_announcement",
    "financial_report",
    "market_snapshot",
]
EventType = Literal[
    "订单 / 合同",
    "业绩 / 指引",
    "政策 / 监管",
    "涨价 / 供需",
    "资本开支",
    "产品发布",
    "风险暴露",
    "纯情绪题材",
    "待判断",
]
EvidenceTool = Literal[
    "company_announcements",
    "financial_reports",
    "market_snapshot",
    "value_chain",
]


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    market: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    thesis: str = ""
    risks: str = ""
    industry: str = ""


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
class NewsItem:
    headline: str
    source: str
    url: str = ""
    published_at: str = ""
    body: str = ""
    source_type: EventSourceType = "news"


@dataclass(frozen=True)
class MarketEvent:
    title: str
    items: tuple[NewsItem, ...]
    summary: str = ""
    themes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def source_urls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.url for item in self.items if item.url))


@dataclass(frozen=True)
class Theme:
    name: str
    events: tuple[MarketEvent, ...]


@dataclass(frozen=True)
class EventAnalysis:
    event_type: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    involved_entities: tuple[str, ...] = field(default_factory=tuple)
    key_facts: tuple[str, ...] = field(default_factory=tuple)
    source_quality: str = "待复核"
    confidence: ConfidenceLevel = "low"
    reasoning: str = ""


@dataclass(frozen=True)
class ValueChainTrace:
    payer: str
    receiver: str
    chain_steps: tuple[str, ...] = field(default_factory=tuple)
    impact_direction: ImpactDirection = "unknown"
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
    impact_direction: ImpactDirection = "unknown"
    confidence: ConfidenceLevel = "unknown"


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
class EventClassification:
    event_type: EventType
    candidate_symbols: tuple[str, ...] = field(default_factory=tuple)
    confidence: str = "low"
    reasoning: str = ""


@dataclass(frozen=True)
class EvidencePlan:
    event_type: EventType
    candidate_symbols: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[EvidenceTool, ...] = field(default_factory=tuple)
    questions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompanyAnnouncement:
    symbol: str
    title: str
    announcement_type: str
    published_at: str
    url: str = ""
    summary: str = ""
    provider: str = ""
    source_url: str = ""
    fetched_at: str = ""


@dataclass(frozen=True)
class FinancialSnapshot:
    symbol: str
    report_period: str
    revenue: float | None = None
    revenue_yoy: float | None = None
    net_profit: float | None = None
    net_profit_yoy: float | None = None
    gross_margin: float | None = None
    operating_cash_flow: float | None = None
    provider: str = ""
    source_url: str = ""
    fetched_at: str = ""


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    pct_chg: float
    volume: float
    amount: float
    lookback_days: int
    period_return_pct: float | None = None
    volume_ratio: float | None = None
    provider: str = ""
    source_url: str = ""
    fetched_at: str = ""


@dataclass(frozen=True)
class ValueChainScore:
    symbol: str
    upstream_relevance_score: int
    downstream_relevance_score: int
    revenue_elasticity_score: int
    reasoning: str = ""


@dataclass(frozen=True)
class ResearchReport:
    raw_news: NewsItem
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
    classification: EventClassification | None = None
    evidence_plan: EvidencePlan | None = None
    company_announcements: tuple[CompanyAnnouncement, ...] = field(default_factory=tuple)
    financial_snapshots: tuple[FinancialSnapshot, ...] = field(default_factory=tuple)
    market_snapshots: tuple[MarketSnapshot, ...] = field(default_factory=tuple)
    value_chain_scores: tuple[ValueChainScore, ...] = field(default_factory=tuple)
    evidence_warnings: tuple[str, ...] = field(default_factory=tuple)
