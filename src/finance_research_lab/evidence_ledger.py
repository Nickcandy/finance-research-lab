from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import urlsplit

from .claim_pipeline import (
    news_content_hash,
    news_origin_key,
    stable_news_item_id,
)
from .claims import Claim
from .daily_radar_snapshot import market_event_id
from .impact_assessment import ConfidenceFeatures, FeatureScore, calculate_confidence
from .models import AShareCompany, MarketEvent, NewsItem

_RELIABLE_MEDIA = {
    "上海证券报",
    "中国证券报",
    "证券时报",
    "新华社",
    "第一财经",
    "财联社",
}
_OFFICIAL_HOST_MARKERS = (
    ".gov.cn",
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
)


@dataclass(frozen=True)
class SourceIdentity:
    item_id: str
    content_hash: str
    origin_key: str
    source_type: str
    source_name: str
    official: bool
    source_quality: FeatureScore


@dataclass(frozen=True)
class EvidenceLedger:
    event_id: str
    symbol: str
    company_name: str
    verified: bool
    watchlist_hit: bool
    supporting_claims: tuple[Claim, ...]
    opposing_claims: tuple[Claim, ...]
    neutral_claims: tuple[Claim, ...]
    source_identities: tuple[SourceIdentity, ...]
    independent_source_count: int
    duplicate_source_count: int
    claim_conflict_score: int
    confidence_features: ConfidenceFeatures
    confidence: int

    @property
    def claims(self) -> tuple[Claim, ...]:
        return (
            *self.supporting_claims,
            *self.opposing_claims,
            *self.neutral_claims,
        )


def build_source_identities(
    events: Sequence[MarketEvent],
) -> dict[str, SourceIdentity]:
    identities: dict[str, SourceIdentity] = {}
    for event in events:
        for item in event.items:
            item_id = stable_news_item_id(item)
            identity = _source_identity(item)
            existing = identities.get(item_id)
            if existing is not None and existing.content_hash != identity.content_hash:
                raise ValueError(f"news item id collision: {item_id}")
            identities[item_id] = identity
    return identities


def build_evidence_ledgers(
    events: Sequence[MarketEvent],
    claims: Sequence[Claim],
    a_share_universe: Sequence[AShareCompany],
    *,
    watchlist_symbols: Iterable[str] = (),
) -> tuple[EvidenceLedger, ...]:
    events_by_id = {market_event_id(event): event for event in events}
    identities = build_source_identities(events)
    companies_by_symbol = {company.symbol: company for company in a_share_universe}
    companies_by_name: dict[str, list[AShareCompany]] = {}
    for company in a_share_universe:
        companies_by_name.setdefault(_normalize(company.name), []).append(company)
    watchlist = set(watchlist_symbols)
    grouped: dict[tuple[str, str], list[Claim]] = {}
    company_for_key: dict[tuple[str, str], AShareCompany | None] = {}
    for claim in claims:
        if claim.event_id not in events_by_id:
            raise ValueError(f"unknown claim event_id: {claim.event_id}")
        if any(item_id not in identities for item_id in claim.source_item_ids):
            raise ValueError(f"claim references unknown source item: {claim.id}")
        targets = _claim_targets(claim, companies_by_symbol, companies_by_name)
        for symbol, company in targets:
            key = (claim.event_id, symbol)
            grouped.setdefault(key, []).append(claim)
            company_for_key[key] = company
    ledgers = [
        _build_ledger(
            event_id,
            symbol,
            tuple(grouped[(event_id, symbol)]),
            company_for_key[(event_id, symbol)],
            identities,
            symbol in watchlist,
        )
        for event_id, symbol in grouped
    ]
    return tuple(ledgers)


def _source_identity(item: NewsItem) -> SourceIdentity:
    host = urlsplit(item.url).netloc.casefold()
    official_host = any(marker in host for marker in _OFFICIAL_HOST_MARKERS)
    if item.source_type == "policy" or (official_host and ".gov.cn" in host):
        value = 100
        reason = "source:government_or_regulator"
        official = True
    elif item.source_type == "announcement" or official_host:
        value = 95
        reason = "source:company_or_exchange_announcement"
        official = True
    elif item.source in _RELIABLE_MEDIA:
        value = 70
        reason = "source:reliable_media"
        official = False
    elif item.source_type == "market_anomaly":
        value = 20
        reason = "source:market_reaction_only"
        official = False
    elif item.source.strip():
        value = 45
        reason = "source:unverified_media"
        official = False
    else:
        value = 20
        reason = "source:unknown"
        official = False
    item_id = stable_news_item_id(item)
    return SourceIdentity(
        item_id=item_id,
        content_hash=news_content_hash(item),
        origin_key=news_origin_key(item),
        source_type=item.source_type,
        source_name=item.source,
        official=official,
        source_quality=FeatureScore(
            value,
            (reason,),
            (f"item:{item_id}",),
        ),
    )


def _claim_targets(
    claim: Claim,
    companies_by_symbol: dict[str, AShareCompany],
    companies_by_name: dict[str, list[AShareCompany]],
) -> tuple[tuple[str, AShareCompany | None], ...]:
    if claim.affected_symbols:
        return tuple(
            (symbol, companies_by_symbol.get(symbol))
            for symbol in dict.fromkeys(claim.affected_symbols)
        )
    matches = companies_by_name.get(_normalize(claim.subject), [])
    if len(matches) == 1:
        return ((matches[0].symbol, matches[0]),)
    return (("", None),)


def _build_ledger(
    event_id: str,
    symbol: str,
    claims: tuple[Claim, ...],
    company: AShareCompany | None,
    identities: dict[str, SourceIdentity],
    watchlist_hit: bool,
) -> EvidenceLedger:
    source_identities = tuple(
        identities[item_id]
        for item_id in dict.fromkeys(
            item_id for claim in claims for item_id in claim.source_item_ids
        )
    )
    unique_content: dict[str, SourceIdentity] = {}
    for identity in source_identities:
        unique_content.setdefault(identity.content_hash, identity)
    duplicate_count = len(source_identities) - len(unique_content)
    origins = {
        identity.origin_key or f"content:{identity.content_hash}"
        for identity in unique_content.values()
    }
    independent_source_count = len(origins)
    strong_conflict = any(
        _strong_conflict(first, second)
        for index, first in enumerate(claims)
        for second in claims[index + 1 :]
    )
    has_positive = any(claim.direction == "positive" for claim in claims)
    has_negative = any(claim.direction == "negative" for claim in claims)
    source_quality = _source_quality_feature(tuple(unique_content.values()))
    corroboration = _corroboration_feature(
        independent_source_count,
        tuple(unique_content.values()),
    )
    identity_verification = _identity_feature(symbol, company, claims, source_identities)
    quantitative_completeness = _quantitative_feature(claims)
    consistency = _consistency_feature(
        claims,
        strong_conflict,
        has_positive,
        has_negative,
    )
    if any(claim.extraction_method == "fallback" for claim in claims):
        source_quality = _cap_fallback_confidence(source_quality)
        corroboration = _cap_fallback_confidence(corroboration)
        identity_verification = _cap_fallback_confidence(identity_verification)
        quantitative_completeness = _cap_fallback_confidence(
            quantitative_completeness
        )
        consistency = _cap_fallback_confidence(consistency)
    confidence_features = ConfidenceFeatures(
        source_quality=source_quality,
        corroboration=corroboration,
        identity_verification=identity_verification,
        quantitative_completeness=quantitative_completeness,
        consistency=consistency,
    )
    return EvidenceLedger(
        event_id=event_id,
        symbol=symbol,
        company_name=company.name if company is not None else "",
        verified=company is not None,
        watchlist_hit=watchlist_hit,
        supporting_claims=tuple(
            claim for claim in claims if claim.direction == "positive"
        ),
        opposing_claims=tuple(
            claim for claim in claims if claim.direction == "negative"
        ),
        neutral_claims=tuple(
            claim
            for claim in claims
            if claim.direction not in {"positive", "negative"}
        ),
        source_identities=source_identities,
        independent_source_count=independent_source_count,
        duplicate_source_count=duplicate_count,
        claim_conflict_score=70 if strong_conflict else 0,
        confidence_features=confidence_features,
        confidence=calculate_confidence(confidence_features),
    )


def _cap_fallback_confidence(feature: FeatureScore) -> FeatureScore:
    return FeatureScore(
        min(feature.value, 35),
        tuple(dict.fromkeys((*feature.reason_codes, "fallback:confidence_cap"))),
        feature.evidence_refs,
    )


def _source_quality_feature(
    identities: tuple[SourceIdentity, ...],
) -> FeatureScore:
    if not identities:
        return FeatureScore(20, ("source:missing",), ("source:missing",))
    strongest = max(identities, key=lambda identity: identity.source_quality.value)
    return FeatureScore(
        strongest.source_quality.value,
        strongest.source_quality.reason_codes,
        tuple(f"item:{identity.item_id}" for identity in identities),
    )


def _corroboration_feature(
    independent_source_count: int,
    identities: tuple[SourceIdentity, ...],
) -> FeatureScore:
    if independent_source_count == 0:
        value = 0
    elif independent_source_count == 1:
        value = 40
    elif independent_source_count == 2:
        value = 70
    else:
        value = 90
    return FeatureScore(
        value,
        (f"corroboration:independent_sources:{min(independent_source_count, 3)}",),
        tuple(f"item:{identity.item_id}" for identity in identities) or ("source:missing",),
    )


def _identity_feature(
    symbol: str,
    company: AShareCompany | None,
    claims: tuple[Claim, ...],
    identities: tuple[SourceIdentity, ...],
) -> FeatureScore:
    evidence = tuple(f"claim:{claim.id}" for claim in claims)
    if company is None:
        value = 20 if symbol else 0
        reason = "identity:unverified_symbol" if symbol else "identity:unresolved"
    elif any(
        identity.official and _normalize(claim.subject) == _normalize(company.name)
        for identity in identities
        for claim in claims
    ):
        value = 100
        reason = "identity:official_subject_match"
    else:
        value = 90
        reason = "identity:local_universe_match"
    return FeatureScore(value, (reason,), evidence or ("identity:unresolved",))


def _quantitative_feature(claims: tuple[Claim, ...]) -> FeatureScore:
    fact_count = sum(len(claim.quantitative_facts) for claim in claims)
    value = 80 if fact_count else 30
    reason = (
        "quantitative:source_linked_facts"
        if fact_count
        else "quantitative:missing"
    )
    return FeatureScore(
        value,
        (reason,),
        tuple(f"claim:{claim.id}" for claim in claims),
    )


def _consistency_feature(
    claims: tuple[Claim, ...],
    strong_conflict: bool,
    has_positive: bool,
    has_negative: bool,
) -> FeatureScore:
    if strong_conflict:
        value = 30
        reason = "consistency:strong_conflict"
    elif has_positive and has_negative:
        value = 60
        reason = "consistency:different_horizon_or_scope"
    else:
        value = 90
        reason = "consistency:no_strong_conflict"
    return FeatureScore(
        value,
        (reason,),
        tuple(f"claim:{claim.id}" for claim in claims),
    )


def _strong_conflict(first: Claim, second: Claim) -> bool:
    if {first.direction, second.direction} != {"positive", "negative"}:
        return False
    return (
        _normalize(first.subject) == _normalize(second.subject)
        and _normalize(first.predicate) == _normalize(second.predicate)
        and first.event_type == second.event_type
        and first.time_horizon == second.time_horizon
        and first.occurred_at == second.occurred_at
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())
