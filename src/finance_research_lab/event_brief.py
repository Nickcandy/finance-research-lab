from __future__ import annotations

from dataclasses import dataclass

from .claims import Claim
from .evidence_ledger import EvidenceLedger
from .impact_assessment import ImpactAssessment
from .models import (
    AShareCompany,
    ImpactDirection,
    MarketEvent,
    ValidationTask,
    ValueChainTrace,
)
from .value_chains import (
    ValueChainNode,
    best_value_chain_relation,
    canonical_theme_labels,
    infer_value_chain_nodes,
)


@dataclass(frozen=True)
class EventBrief:
    event_type: str
    themes: tuple[str, ...]
    key_facts: tuple[str, ...]
    reasoning: str
    value_chain: ValueChainTrace
    validation_tasks: tuple[ValidationTask, ...]


def build_event_brief(
    event: MarketEvent,
    claims: tuple[Claim, ...],
    ledgers: tuple[EvidenceLedger, ...],
    assessments: tuple[ImpactAssessment, ...],
    universe: list[AShareCompany],
) -> EventBrief:
    claim_texts = tuple(
        value
        for claim in claims
        for value in (claim.subject, claim.predicate, claim.object, claim.event_type)
        if value.strip()
    )
    facts = tuple(
        dict.fromkeys(
            " ".join((claim.subject, claim.predicate, claim.object)).strip()
            for claim in claims
            if any((claim.subject.strip(), claim.predicate.strip(), claim.object.strip()))
        )
    )
    event_type = next(
        (claim.event_type for claim in claims if claim.event_type.strip()),
        "待判断",
    )
    themes = canonical_theme_labels((event.title, event.summary, *claim_texts))
    value_chain = build_auditable_value_chain(
        event,
        claims,
        ledgers,
        assessments,
        universe,
    )
    claim_refs = tuple(dict.fromkeys(claim.id for claim in claims))
    reasoning = "基于 Claim、EvidenceLedger、公司资料和固定评分规则生成。"
    if claim_refs:
        reasoning += f" Claim 引用：{', '.join(claim_refs)}。"
    return EventBrief(
        event_type=event_type,
        themes=themes,
        key_facts=facts[:5] or (event.summary or event.title,),
        reasoning=reasoning,
        value_chain=value_chain,
        validation_tasks=(
            ValidationTask(
                question="事件关键事实是否有公告或监管文件确认？",
                data_needed="公告、监管文件或原始新闻来源",
            ),
            ValidationTask(
                question="候选公司的业务暴露是否与已识别产业节点一致？",
                data_needed="公司业务构成、订单或客户披露",
            ),
        ),
    )


def build_auditable_value_chain(
    event: MarketEvent,
    claims: tuple[Claim, ...],
    ledgers: tuple[EvidenceLedger, ...],
    assessments: tuple[ImpactAssessment, ...],
    universe: list[AShareCompany],
) -> ValueChainTrace:
    event_text = " ".join(
        (
            event.title,
            event.summary,
            *(
                value
                for claim in claims
                for value in (
                    claim.subject,
                    claim.predicate,
                    claim.object,
                    claim.event_type,
                )
            ),
        )
    )
    event_nodes = _unique_nodes(infer_value_chain_nodes(event_text))
    event_graphs = {node.chain_id for node in event_nodes}
    if len(event_graphs) > 1:
        return _unknown_chain("事件文本同时命中多张产业链图，无法可靠消歧。")
    if not event_nodes:
        return _unknown_chain("未识别到可验证价值链。")

    companies = {company.symbol: company for company in universe}
    assessments_by_symbol = {assessment.symbol: assessment for assessment in assessments}
    candidates: list[
        tuple[tuple[int, int, int, str, str, str], tuple[str, ...], ImpactDirection, str]
    ] = []
    for ledger in ledgers:
        if not ledger.verified:
            continue
        company = companies.get(ledger.symbol)
        assessment = assessments_by_symbol.get(ledger.symbol)
        if company is None or assessment is None:
            continue
        company_nodes = _unique_nodes(
            infer_value_chain_nodes(" ".join((*company.themes, company.business_summary)))
        )
        relation = best_value_chain_relation(company_nodes, event_nodes)
        if relation is None:
            continue
        magnitude = max(
            assessment.positive_magnitude,
            assessment.negative_magnitude,
        )
        references = tuple(dict.fromkeys(claim.id for claim in ledger.claims))
        reasoning = (
            f"图谱：{relation.chain_label}；标的：{company.symbol} {company.name}；"
            f"关系：{relation.relation}；距离：{relation.distance}。"
        )
        if references:
            reasoning += f" Claim 引用：{', '.join(references)}。"
        candidates.append(
            (
                (
                    -magnitude,
                    -assessment.confidence,
                    relation.distance,
                    company.symbol,
                    relation.chain_label,
                    relation.company_node,
                ),
                relation.path,
                assessment.direction,
                reasoning,
            )
        )
    if candidates:
        _, path, direction, reasoning = min(candidates, key=lambda item: item[0])
        return ValueChainTrace(
            payer="",
            receiver="",
            chain_steps=path,
            impact_direction=direction,
            reasoning=reasoning,
        )

    unique_labels = tuple(dict.fromkeys(node.label for node in event_nodes))
    if len(unique_labels) == 1:
        return ValueChainTrace(
            payer="",
            receiver="",
            chain_steps=unique_labels,
            impact_direction="unknown",
            reasoning="仅识别到事件产业节点，尚无已验证公司传导关系。",
        )
    return _unknown_chain("识别到多个产业节点，但没有已验证公司关系可用于消歧。")


def _unique_nodes(nodes: tuple[ValueChainNode, ...]) -> tuple[ValueChainNode, ...]:
    return tuple({(node.chain_id, node.node_id): node for node in nodes}.values())


def _unknown_chain(reasoning: str) -> ValueChainTrace:
    return ValueChainTrace(
        payer="",
        receiver="",
        chain_steps=(),
        impact_direction="unknown",
        reasoning=reasoning,
    )
