from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Sequence

from .claims import Claim, TimeHorizon
from .models import ConfidenceLevel, MarketEvent

HorizonCategory = Literal[
    "immediate",
    "short",
    "medium",
    "long",
    "structural",
    "unknown",
]
DurationUnit = Literal["trading_day", "calendar_month", "unknown"]
EventKind = Literal[
    "order",
    "earnings",
    "corporate_action",
    "risk",
    "capex",
    "commodity",
    "policy",
    "approval",
    "sentiment",
    "unknown",
]

_CONFIDENCE_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_MARKET_RANGES: dict[HorizonCategory, tuple[int | None, int | None]] = {
    "immediate": (0, 5),
    "short": (6, 20),
    "medium": (21, 60),
    "long": (61, 250),
    "structural": (250, None),
    "unknown": (None, None),
}
_FUNDAMENTAL_RANGES: dict[HorizonCategory, tuple[int | None, int | None]] = {
    "immediate": (0, 1),
    "short": (1, 3),
    "medium": (3, 6),
    "long": (6, 24),
    "structural": (24, None),
    "unknown": (None, None),
}
_DEFAULT_HORIZONS: dict[EventKind, tuple[HorizonCategory, HorizonCategory]] = {
    "order": ("short", "long"),
    "earnings": ("short", "medium"),
    "corporate_action": ("short", "medium"),
    "risk": ("short", "medium"),
    "capex": ("short", "long"),
    "commodity": ("short", "medium"),
    "policy": ("medium", "long"),
    "approval": ("short", "medium"),
    "sentiment": ("immediate", "unknown"),
    "unknown": ("unknown", "unknown"),
}
_INVALIDATION_CONDITIONS: dict[EventKind, tuple[str, ...]] = {
    "order": ("合同取消、延期或金额下调", "交付或收入确认明显低于预期"),
    "earnings": ("后续财报或指引显著低于当前判断",),
    "corporate_action": ("方案终止、审批失败或执行比例明显不足",),
    "risk": ("风险事项解除、整改完成或影响范围被证伪",),
    "capex": ("项目延期或取消", "投产爬坡或产能利用率明显低于预期"),
    "commodity": ("供需缺口修复或价格趋势反转",),
    "policy": ("政策延期、撤回或实际执行力度明显低于预期",),
    "approval": ("客户验证、量产或商业化进度明显低于预期",),
    "sentiment": ("缺少新增事实或市场关注度快速消退",),
    "unknown": ("补充证据后原有周期假设不成立",),
}
_EXPLICIT_RANGE_RE = re.compile(
    r"(?P<minimum>\d+(?:\.\d+)?)\s*[-~～至到]\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>个?交易日|个?工作日|天|日|周|个?月|个月|个?季度|季度|年)"
)
_EXPLICIT_SINGLE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>个?交易日|个?工作日|天|日|周|个?月|个月|个?季度|季度|年)"
)
_YEAR_RANGE_RE = re.compile(
    r"(?P<start>(?:19|20)\d{2})\s*[-~～至到]\s*(?P<end>(?:19|20)\d{2})"
)


@dataclass(frozen=True)
class ImpactHorizon:
    category: HorizonCategory
    min_duration: int | None
    max_duration: int | None
    unit: DurationUnit
    confidence: ConfidenceLevel
    basis: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.basis or any(not value.strip() for value in self.basis):
            raise ValueError("basis must contain non-empty values")
        if not self.evidence_refs or any(
            not value.strip() for value in self.evidence_refs
        ):
            raise ValueError("evidence_refs must contain non-empty values")
        if not self.invalidation_conditions or any(
            not value.strip() for value in self.invalidation_conditions
        ):
            raise ValueError("invalidation_conditions must contain non-empty values")
        if self.category == "unknown":
            if (
                self.min_duration is not None
                or self.max_duration is not None
                or self.unit != "unknown"
            ):
                raise ValueError("unknown horizon must not have a duration")
            return
        if self.unit == "unknown" or self.min_duration is None:
            raise ValueError("known horizon must have a duration and unit")
        if self.min_duration < 0:
            raise ValueError("min_duration must not be negative")
        if self.max_duration is not None and self.max_duration < self.min_duration:
            raise ValueError("max_duration must not be less than min_duration")


@dataclass(frozen=True)
class DirectionalHorizons:
    market: ImpactHorizon
    fundamental: ImpactHorizon


@dataclass(frozen=True)
class _ExplicitDuration:
    minimum: int
    maximum: int
    unit: DurationUnit
    source_text: str
    claim: Claim


def assess_directional_horizons(
    event: MarketEvent,
    claims: Sequence[Claim],
    *,
    verified_relation: bool,
) -> DirectionalHorizons | None:
    if not claims:
        return None
    kind = infer_event_kind(claims)
    official = any(
        _claim_is_official(event, claim)
        for claim in claims
    )
    refs = _claim_refs(claims)
    conditions = _INVALIDATION_CONDITIONS[kind]
    market_default, fundamental_default = _DEFAULT_HORIZONS[kind]
    market_explicit, market_conflict = _best_explicit_duration(claims, market=True)
    fundamental_explicit, fundamental_conflict = _best_explicit_duration(
        claims,
        market=False,
    )
    market = (
        _explicit_horizon(
            market_explicit,
            conditions,
            _claim_is_official(event, market_explicit.claim),
            conflict=market_conflict,
        )
        if market_explicit is not None
        else _claim_or_default_horizon(
            market_default,
            market=True,
            kind=kind,
            claims=claims,
            verified_relation=verified_relation,
            event=event,
            official=official,
            refs=refs,
            conditions=conditions,
        )
    )
    fundamental = (
        _explicit_horizon(
            fundamental_explicit,
            conditions,
            _claim_is_official(event, fundamental_explicit.claim),
            conflict=fundamental_conflict,
        )
        if fundamental_explicit is not None
        else _claim_or_default_horizon(
            fundamental_default,
            market=False,
            kind=kind,
            claims=claims,
            verified_relation=verified_relation,
            event=event,
            official=official,
            refs=refs,
            conditions=conditions,
        )
    )
    return DirectionalHorizons(market, fundamental)


def infer_event_kind(claims: Sequence[Claim]) -> EventKind:
    text = " ".join(claim.event_type for claim in claims)
    if any(marker in text for marker in ("订单", "合同")):
        return "order"
    if any(marker in text for marker in ("业绩", "指引", "财务")):
        return "earnings"
    if any(marker in text for marker in ("回购", "减持", "控制权", "增发")):
        return "corporate_action"
    if any(marker in text for marker in ("风险", "诉讼", "处罚", "停产")):
        return "risk"
    if any(marker in text for marker in ("资本开支", "扩产")):
        return "capex"
    if any(marker in text for marker in ("涨价", "供需", "商品")):
        return "commodity"
    if any(marker in text for marker in ("政策", "监管")):
        return "policy"
    if any(marker in text for marker in ("获批", "研发", "临床", "产品")):
        return "approval"
    if any(marker in text for marker in ("情绪", "题材", "概念")):
        return "sentiment"
    return "unknown"


def _claim_or_default_horizon(
    default: HorizonCategory,
    *,
    market: bool,
    kind: EventKind,
    claims: Sequence[Claim],
    verified_relation: bool,
    event: MarketEvent,
    official: bool,
    refs: tuple[str, ...],
    conditions: tuple[str, ...],
) -> ImpactHorizon:
    known_claims = tuple(claim for claim in claims if claim.time_horizon != "unknown")
    if known_claims:
        highest_confidence = max(
            _CONFIDENCE_ORDER[claim.confidence] for claim in known_claims
        )
        comparable_claims = tuple(
            claim
            for claim in known_claims
            if _CONFIDENCE_ORDER[claim.confidence] == highest_confidence
        )
        claim = max(
            comparable_claims,
            key=lambda value: (
                _horizon_order(value.time_horizon),
            ),
        )
        confidence: ConfidenceLevel = (
            "high"
            if _claim_is_official(event, claim)
            and verified_relation
            and claim.confidence == "high"
            else "medium"
            if claim.confidence in {"high", "medium"}
            else "low"
        )
        horizon_orders = {
            _horizon_order(value.time_horizon) for value in comparable_claims
        }
        if len(horizon_orders) > 1:
            confidence = _lower_confidence(confidence)
        return _range_horizon(
            claim.time_horizon,
            market=market,
            confidence=confidence,
            basis=(f"Claim 判断为 {claim.time_horizon}",),
            evidence_refs=(f"claim:{claim.id}",),
            conditions=conditions,
        )
    return _default_horizon(
        default,
        market=market,
        kind=kind,
        claims=claims,
        verified_relation=verified_relation,
        official=official,
        refs=refs,
        conditions=conditions,
    )


def _default_horizon(
    category: HorizonCategory,
    *,
    market: bool,
    kind: EventKind,
    claims: Sequence[Claim],
    verified_relation: bool,
    official: bool,
    refs: tuple[str, ...],
    conditions: tuple[str, ...],
) -> ImpactHorizon:
    confidence: ConfidenceLevel = (
        "medium"
        if category != "unknown" and verified_relation and official
        else "low"
        if category != "unknown"
        else "unknown"
    )
    layer = "市场反应" if market else "基本面兑现"
    event_type = next(
        (claim.event_type for claim in claims if claim.event_type.strip()),
        "待判断",
    )
    return _range_horizon(
        category,
        market=market,
        confidence=confidence,
        basis=(f"{event_type}事件默认{layer}周期",),
        evidence_refs=refs,
        conditions=conditions,
    )


def _explicit_horizon(
    explicit: _ExplicitDuration,
    conditions: tuple[str, ...],
    official: bool,
    *,
    conflict: bool,
) -> ImpactHorizon:
    category = (
        _market_category(explicit.maximum)
        if explicit.unit == "trading_day"
        else _fundamental_category(explicit.maximum)
    )
    confidence: ConfidenceLevel = "high" if official else "medium"
    if conflict:
        confidence = _lower_confidence(confidence)
    return ImpactHorizon(
        category=category,
        min_duration=explicit.minimum,
        max_duration=explicit.maximum,
        unit=explicit.unit,
        confidence=confidence,
        basis=(f"原文明确周期：{explicit.source_text}",),
        evidence_refs=(f"claim:{explicit.claim.id}",),
        invalidation_conditions=conditions,
    )


def _range_horizon(
    category: HorizonCategory,
    *,
    market: bool,
    confidence: ConfidenceLevel,
    basis: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    conditions: tuple[str, ...],
) -> ImpactHorizon:
    minimum, maximum = (
        _MARKET_RANGES[category] if market else _FUNDAMENTAL_RANGES[category]
    )
    return ImpactHorizon(
        category=category,
        min_duration=minimum,
        max_duration=maximum,
        unit=(
            "unknown"
            if category == "unknown"
            else "trading_day"
            if market
            else "calendar_month"
        ),
        confidence=confidence,
        basis=basis,
        evidence_refs=evidence_refs,
        invalidation_conditions=conditions,
    )


def _best_explicit_duration(
    claims: Sequence[Claim],
    *,
    market: bool,
) -> tuple[_ExplicitDuration | None, bool]:
    candidates = [
        explicit
        for claim in claims
        if (
            (market and claim.claim_type == "market_reaction")
            or (not market and claim.claim_type != "market_reaction")
        )
        for text in _period_texts(claim)
        if (explicit := _parse_duration(text, claim, market=market)) is not None
    ]
    if not candidates:
        return None, False
    highest_confidence = max(
        _CONFIDENCE_ORDER[value.claim.confidence] for value in candidates
    )
    comparable_candidates = tuple(
        value
        for value in candidates
        if _CONFIDENCE_ORDER[value.claim.confidence] == highest_confidence
    )
    selected = max(
        comparable_candidates,
        key=lambda value: value.maximum,
    )
    categories = {
        (
            _market_category(value.maximum)
            if value.unit == "trading_day"
            else _fundamental_category(value.maximum)
        )
        for value in comparable_candidates
    }
    return selected, len(categories) > 1


def _period_texts(claim: Claim) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *(fact.period.strip() for fact in claim.quantitative_facts if fact.period.strip()),
                claim.object.strip(),
            )
        )
    )


def _parse_duration(
    text: str,
    claim: Claim,
    *,
    market: bool,
) -> _ExplicitDuration | None:
    normalized = unicodedata.normalize("NFKC", text)
    if not market:
        year_match = _YEAR_RANGE_RE.search(normalized)
        if year_match:
            months = (int(year_match.group("end")) - int(year_match.group("start"))) * 12
            if months > 0:
                return _ExplicitDuration(months, months, "calendar_month", text, claim)
    match = _EXPLICIT_RANGE_RE.search(normalized)
    if match:
        return _converted_duration(
            float(match.group("minimum")),
            float(match.group("maximum")),
            match.group("unit"),
            text,
            claim,
            market=market,
        )
    match = _EXPLICIT_SINGLE_RE.search(normalized)
    if not match:
        return None
    value = float(match.group("value"))
    return _converted_duration(
        value,
        value,
        match.group("unit"),
        text,
        claim,
        market=market,
    )


def _converted_duration(
    minimum: float,
    maximum: float,
    raw_unit: str,
    text: str,
    claim: Claim,
    *,
    market: bool,
) -> _ExplicitDuration | None:
    unit = raw_unit.replace("个", "")
    if market:
        if unit in {"交易日", "工作日", "天", "日"}:
            return _ExplicitDuration(
                math.ceil(minimum),
                math.ceil(maximum),
                "trading_day",
                text,
                claim,
            )
        if unit == "周":
            return _ExplicitDuration(
                math.ceil(minimum * 5),
                math.ceil(maximum * 5),
                "trading_day",
                text,
                claim,
            )
        return None
    multiplier = {
        "天": 1 / 30,
        "日": 1 / 30,
        "交易日": 1 / 20,
        "工作日": 1 / 20,
        "周": 1 / 4,
        "月": 1,
        "个月": 1,
        "季度": 3,
        "年": 12,
    }.get(unit)
    if multiplier is None:
        return None
    return _ExplicitDuration(
        max(1, math.ceil(minimum * multiplier)),
        max(1, math.ceil(maximum * multiplier)),
        "calendar_month",
        text,
        claim,
    )


def _market_category(maximum: int) -> HorizonCategory:
    if maximum <= 5:
        return "immediate"
    if maximum <= 20:
        return "short"
    if maximum <= 60:
        return "medium"
    if maximum <= 250:
        return "long"
    return "structural"


def _fundamental_category(maximum: int) -> HorizonCategory:
    if maximum <= 1:
        return "immediate"
    if maximum <= 3:
        return "short"
    if maximum <= 6:
        return "medium"
    if maximum <= 24:
        return "long"
    return "structural"


def _horizon_order(value: TimeHorizon) -> int:
    return {
        "unknown": 0,
        "immediate": 1,
        "short": 2,
        "medium": 3,
        "long": 4,
    }[value]


def _lower_confidence(value: ConfidenceLevel) -> ConfidenceLevel:
    return {
        "high": "medium",
        "medium": "low",
        "low": "low",
        "unknown": "unknown",
    }[value]


def _claim_refs(claims: Sequence[Claim]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(f"claim:{claim.id}" for claim in claims))


def _claim_is_official(event: MarketEvent, claim: Claim) -> bool:
    from .claim_pipeline import stable_news_item_id

    official_item_ids = {
        stable_news_item_id(item)
        for item in event.items
        if item.source_type in {"announcement", "policy"}
    }
    return any(item_id in official_item_ids for item_id in claim.source_item_ids)
