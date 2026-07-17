from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

from .impact_scoring import infer_news_impact_direction
from .models import (
    AShareCompany,
    ConfidenceLevel,
    EventAnalysis,
    ImpactDirection,
    NewsTrace,
    NewsItem,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
    WatchlistItem,
)
from .value_chains import (
    ValueChainNode,
    ValueChainRelation,
    best_value_chain_relation,
    infer_value_chain_nodes,
    normalize_semantic_text,
)

MAX_MAPPED_CANDIDATES = 10

THEME_KEYWORDS = {
    "AI": ["ai", "人工智能", "大模型", "算力", "gpu", "nvidia", "openai", "xai"],
    "数据中心": ["data center", "数据中心", "capex", "资本开支", "云", "cloud"],
    "光模块": ["光模块", "optical", "800g", "1.6t", "交换机"],
    "稳定币": ["stablecoin", "稳定币", "usdc", "usdt", "circle", "tether"],
    "支付": ["payment", "支付", "清结算", "结算", "onramp"],
    "券商": ["券商", "证券", "并购", "成交额", "牛市"],
    "CXO": ["cxo", "创新药", "药明", "biotech", "biosecure"],
    "商业航天": ["spacex", "starlink", "卫星", "火箭", "商业航天"],
}


def load_watchlist(path: str | Path) -> list[WatchlistItem]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        items: list[WatchlistItem] = []
        for row in rows:
            themes = tuple(t.strip() for t in row.get("themes", "").split(";") if t.strip())
            items.append(
                WatchlistItem(
                    symbol=row["symbol"].strip(),
                    name=row["name"].strip(),
                    market=row.get("market", "").strip(),
                    themes=themes,
                    thesis=row.get("thesis", "").strip(),
                    risks=row.get("risks", "").strip(),
                    industry=(row.get("industry") or row.get("sector") or "").strip(),
                )
            )
    return items


def load_a_share_universe(path: str | Path) -> list[AShareCompany]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        companies: list[AShareCompany] = []
        for row in rows:
            themes = tuple(t.strip() for t in row.get("themes", "").split(";") if t.strip())
            companies.append(
                AShareCompany(
                    symbol=row["symbol"].strip(),
                    name=row["name"].strip(),
                    market=row.get("market", "A股").strip(),
                    industry=row.get("industry", "").strip(),
                    themes=themes,
                    business_summary=row.get("business_summary", "").strip(),
                    source=row.get("source", "").strip(),
                )
            )
    return companies


def infer_themes(headline: str) -> set[str]:
    text = headline.lower()
    matched: set[str] = set()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            matched.add(theme)
    return matched


def classify_news_type(headline: str) -> str:
    text = headline.lower()
    if any(k in text for k in ["capex", "资本开支", "投资", "扩产"]):
        return "资本开支 / 产能扩张"
    if any(k in text for k in ["订单", "合同", "contract", "order"]):
        return "订单 / 合同"
    if any(k in text for k in ["监管", "法案", "regulation", "policy", "政策"]):
        return "政策 / 监管"
    if any(k in text for k in ["财报", "业绩", "guidance", "earnings"]):
        return "业绩 / 指引"
    if any(k in text for k in ["发布", "launch", "product", "模型"]):
        return "产品发布 / 概念验证"
    return "待人工分类"


def build_trace(headline: str, source: str, watchlist: list[WatchlistItem]) -> NewsTrace:
    themes = infer_themes(headline)
    direct: list[WatchlistItem] = []
    indirect: list[WatchlistItem] = []
    sentiment: list[WatchlistItem] = []

    for item in watchlist:
        overlap = themes.intersection(item.themes)
        if len(overlap) >= 2:
            direct.append(item)
        elif len(overlap) == 1:
            indirect.append(item)
        elif any(theme.lower() in item.thesis.lower() for theme in themes):
            sentiment.append(item)

    if {"AI", "数据中心", "光模块"}.intersection(themes):
        payer = "云厂商 / AI 平台 / 数据中心投资方"
        receiver = "GPU、服务器、交换机、光模块、PCB、液冷、电力设备等供应链"
        chain = ["AI CapEx", "数据中心", "GPU/ASIC", "交换机", "光模块", "PCB", "液冷", "电力设备"]
    elif {"稳定币", "支付"}.intersection(themes):
        payer = "交易所、支付公司、商户、用户、稳定币发行方"
        receiver = "合规发行、托管、清结算、支付网关、链上基础设施"
        chain = ["监管框架", "稳定币发行", "托管/储备", "支付网关", "商户结算", "链上清结算"]
    else:
        payer = "待人工判断"
        receiver = "待人工判断"
        chain = ["新闻事件", "产业链", "标的映射", "验证点"]

    action = "等验证" if source.lower() in {"manual", "example"} else "放观察池"
    return NewsTrace(
        headline=headline,
        source=source,
        news_type=classify_news_type(headline),
        payer=payer,
        receiver=receiver,
        value_chain=chain,
        direct_beneficiaries=direct,
        indirect_beneficiaries=indirect,
        sentiment_mappings=sentiment,
        stage="待判断",
        action_state=action,
        verification_points=[
            "找到最早官方来源或可靠媒体原文",
            "检查是否有真实订单、收入、资本开支或监管落地",
            "观察相关标的成交额、公告、财报和板块持续性",
            "判断热度阶段：启动、验证、高潮、分歧或退潮",
        ],
    )


def build_research_report(
    news: NewsItem,
    watchlist: list[WatchlistItem],
    a_share_universe: list[AShareCompany] | None = None,
    proposed_impacts: tuple[StockImpact, ...] = (),
) -> ResearchReport:
    news_text = f"{news.headline} {news.body}"
    themes = infer_themes(news_text)
    payer, receiver, chain = _value_chain_for_themes(themes)
    impact_direction = infer_news_impact_direction(news_text)
    stock_impacts = _build_stock_impacts(
        themes=themes,
        watchlist=watchlist,
        a_share_universe=a_share_universe,
        proposed_impacts=proposed_impacts,
        news_text=news_text,
        chain_steps=tuple(chain),
        event_direction=impact_direction,
        event_confidence="low",
    )

    return ResearchReport(
        raw_news=news,
        event=EventAnalysis(
            event_type=classify_news_type(news_text),
            themes=tuple(sorted(themes)),
            key_facts=_key_facts_for_themes(themes),
            source_quality="待复核",
            confidence="low",
            reasoning="基于标题关键词的规则 fallback，后续可替换为 Agent 结构化分析。",
        ),
        value_chain=ValueChainTrace(
            payer=payer,
            receiver=receiver,
            chain_steps=tuple(chain),
            impact_direction=impact_direction,
            reasoning="基于新闻中的显式方向词做保守判断；未命中时保持待判断。",
        ),
        stock_impacts=tuple(stock_impacts),
        validation_tasks=(
            ValidationTask("找到最早官方来源或可靠媒体原文", "官方公告、监管文件或可靠媒体原文"),
            ValidationTask("检查是否有真实订单、收入、资本开支或监管落地", "公告、财报、订单金额或政策原文"),
            ValidationTask("观察相关标的成交额、公告、财报和板块持续性", "行情、成交额、公告和财报数据"),
            ValidationTask("判断热度阶段：启动、验证、高潮、分歧或退潮", "价格位置、成交额变化和板块扩散情况"),
        ),
        stage="待判断",
        action_state="放观察池",
    )


def verify_research_report_candidates(
    report: ResearchReport,
    watchlist: list[WatchlistItem],
    a_share_universe: list[AShareCompany],
) -> ResearchReport:
    stock_impacts = _build_stock_impacts(
        themes=set(report.event.themes),
        watchlist=watchlist,
        a_share_universe=a_share_universe,
        proposed_impacts=report.stock_impacts,
        news_text=f"{report.raw_news.headline} {report.raw_news.body}",
        chain_steps=report.value_chain.chain_steps,
        event_direction=report.value_chain.impact_direction,
        event_confidence=report.event.confidence,
    )
    return ResearchReport(
        raw_news=report.raw_news,
        event=report.event,
        value_chain=report.value_chain,
        stock_impacts=tuple(stock_impacts),
        validation_tasks=report.validation_tasks,
        stage=report.stage,
        action_state=report.action_state,
    )


def _value_chain_for_themes(themes: set[str]) -> tuple[str, str, list[str]]:
    if {"AI", "数据中心", "光模块"}.intersection(themes):
        return (
            "云厂商 / AI 平台 / 数据中心投资方",
            "GPU、服务器、交换机、光模块、PCB、液冷、电力设备等供应链",
            ["AI CapEx", "数据中心", "GPU/ASIC", "交换机", "光模块", "PCB", "液冷", "电力设备"],
        )
    if {"稳定币", "支付"}.intersection(themes):
        return (
            "交易所、支付公司、商户、用户、稳定币发行方",
            "合规发行、托管、清结算、支付网关、链上基础设施",
            ["监管框架", "稳定币发行", "托管/储备", "支付网关", "商户结算", "链上清结算"],
        )
    return "待人工判断", "待人工判断", ["新闻事件", "产业链", "标的映射", "验证点"]


def _key_facts_for_themes(themes: set[str]) -> tuple[str, ...]:
    if not themes:
        return ("标题未命中内置主题，需要人工补充事件理解",)
    return (f"标题命中主题：{'、'.join(sorted(themes))}",)


def _build_stock_impacts(
    *,
    themes: set[str],
    watchlist: list[WatchlistItem],
    a_share_universe: list[AShareCompany] | None,
    proposed_impacts: tuple[StockImpact, ...],
    news_text: str = "",
    chain_steps: tuple[str, ...] = (),
    event_direction: ImpactDirection = "unknown",
    event_confidence: ConfidenceLevel = "unknown",
) -> list[StockImpact]:
    if a_share_universe is None:
        return list(proposed_impacts) or _map_stock_impacts(themes, watchlist)

    watchlist_by_symbol = {item.symbol: item for item in watchlist}
    universe_by_symbol = {company.symbol: company for company in a_share_universe}
    universe_by_name: dict[str, list[AShareCompany]] = {}
    for company in a_share_universe:
        universe_by_name.setdefault(_normalize_company_name(company.name), []).append(company)
    event_nodes = infer_value_chain_nodes(" ".join((*sorted(themes), news_text)))
    if not event_nodes:
        event_nodes = infer_value_chain_nodes(" ".join(chain_steps))
    ranked_impacts: list[tuple[tuple[int, int, str], StockImpact]] = []
    seen: set[str] = set()

    for impact in proposed_impacts:
        company = universe_by_symbol.get(impact.symbol)
        symbol_matches_name = company is not None and (
            _normalize_company_name(company.name) == _normalize_company_name(impact.name)
        )
        name_matches = universe_by_name.get(_normalize_company_name(impact.name), [])
        corrected = False
        if not symbol_matches_name and len(name_matches) == 1:
            company = name_matches[0]
            corrected = company.symbol != impact.symbol
        elif not symbol_matches_name:
            company = None

        if company is None:
            ranked_impacts.append(((9, 1, impact.symbol), _unverified_impact(impact)))
        else:
            match = _match_company(company, themes, news_text, event_nodes)
            if match is None:
                unresolved = _unverified_impact(
                    replace(impact, symbol=company.symbol, name=company.name)
                )
                if corrected:
                    unresolved = replace(
                        unresolved,
                        evidence=unresolved.evidence
                        + (
                            f"A 股 universe 按公司名纠正证券代码："
                            f"{impact.symbol} -> {company.symbol}",
                        ),
                    )
                ranked_impacts.append(((8, 1, company.symbol), unresolved))
                seen.add(company.symbol)
                continue
            verified = _impact_from_match(
                company,
                match,
                watchlist_by_symbol,
                impact,
                event_direction,
                event_confidence,
            )
            if corrected:
                verified = replace(
                    verified,
                    evidence=verified.evidence
                    + (
                        f"A 股 universe 按公司名纠正证券代码：{impact.symbol} -> {company.symbol}",
                    ),
                )
            ranked_impacts.append((_impact_sort_key(match, verified), verified))
            seen.add(company.symbol)

    for company in a_share_universe:
        if company.symbol in seen:
            continue
        match = _match_company(company, themes, news_text, event_nodes)
        if match is None:
            continue
        impact = _impact_from_match(
            company,
            match,
            watchlist_by_symbol,
            None,
            event_direction,
            event_confidence,
        )
        ranked_impacts.append((_impact_sort_key(match, impact), impact))
        seen.add(company.symbol)

    ranked_impacts.sort(key=lambda item: item[0])
    return [impact for _, impact in ranked_impacts[:MAX_MAPPED_CANDIDATES]]


def _map_stock_impacts(themes: set[str], watchlist: list[WatchlistItem]) -> list[StockImpact]:
    impacts: list[StockImpact] = []
    for item in watchlist:
        overlap = themes.intersection(item.themes)
        if len(overlap) >= 2:
            impact_type = "direct"
            strength = "high"
            reasoning = "股票池主题与新闻主题重合度较高。"
        elif len(overlap) == 1:
            impact_type = "indirect"
            strength = "medium"
            reasoning = "股票池主题与新闻主题存在单一交集。"
        elif any(theme.lower() in item.thesis.lower() for theme in themes):
            impact_type = "sentiment"
            strength = "low"
            reasoning = "股票池关注逻辑提到新闻主题，但主题标签未直接匹配。"
        else:
            continue

        impacts.append(
            StockImpact(
                symbol=item.symbol,
                name=item.name,
                market=item.market,
                impact_type=impact_type,
                impact_strength=strength,
                themes=item.themes,
                reasoning=reasoning,
                evidence=(f"股票池主题：{' / '.join(item.themes) or '未标注主题'}",),
                risks=(item.risks,) if item.risks else (),
                verification_status="verified",
                verification_source="watchlist",
                watchlist_hit=True,
            )
        )
    return impacts


@dataclass(frozen=True)
class _CompanyMatch:
    priority: int
    impact_type: str
    impact_strength: str
    reasoning: str
    evidence: tuple[str, ...]
    relation: ValueChainRelation | None = None
    explicit: bool = False


def _match_company(
    company: AShareCompany,
    themes: set[str],
    news_text: str,
    event_nodes: tuple[ValueChainNode, ...],
) -> _CompanyMatch | None:
    normalized_news = normalize_semantic_text(news_text)
    explicit = bool(
        normalize_semantic_text(company.name)
        and normalize_semantic_text(company.name) in normalized_news
    )
    company_nodes = infer_value_chain_nodes(
        " ".join((*company.themes, company.business_summary))
    )
    relation = best_value_chain_relation(company_nodes, event_nodes)
    overlap = themes.intersection(company.themes)
    base_evidence = (
        f"A 股 universe 主题匹配：{' / '.join(company.themes) or '未标注主题'}",
        f"行业：{company.industry or '未提供'}",
    )
    if explicit:
        return _CompanyMatch(
            0,
            "direct",
            "high",
            "新闻明确提及该公司，本地 A 股 universe 已确认标准身份。",
            base_evidence + (f"新闻明确提及公司：{company.name}",),
            relation,
            True,
        )
    if relation is not None:
        relation_evidence = (
            f"本地产业链映射：{relation.chain_label}；公司节点={relation.company_node}；"
            f"事件节点={relation.event_node}；关系={relation.relation}；距离={relation.distance}",
        )
        if relation.relation == "同环节":
            return _CompanyMatch(
                1,
                "direct",
                "high",
                "公司产品与事件位于同一产业链节点。",
                base_evidence + relation_evidence,
                relation,
            )
        if relation.distance == 1:
            return _CompanyMatch(
                2,
                "indirect",
                "medium",
                f"公司位于事件节点的{relation.relation}一跳位置。",
                base_evidence + relation_evidence,
                relation,
            )
        return _CompanyMatch(
            3,
            "indirect",
            "low",
            f"公司与事件存在多跳{relation.relation}产业链关系。",
            base_evidence + relation_evidence,
            relation,
        )
    if len(overlap) >= 2:
        return _CompanyMatch(
            4,
            "direct",
            "high",
            "A 股 universe 主题与新闻主题重合度较高。",
            base_evidence,
        )
    if len(overlap) == 1:
        return _CompanyMatch(
            4,
            "indirect",
            "medium",
            "A 股 universe 主题与新闻主题存在单一交集。",
            base_evidence,
        )
    if any(normalize_semantic_text(theme) in normalize_semantic_text(company.business_summary) for theme in themes):
        return _CompanyMatch(
            5,
            "sentiment",
            "low",
            "公司业务摘要提到新闻主题，但主题标签未直接匹配。",
            base_evidence,
        )
    return None


def _impact_from_match(
    company: AShareCompany,
    match: _CompanyMatch,
    watchlist_by_symbol: dict[str, WatchlistItem],
    proposed: StockImpact | None = None,
    event_direction: ImpactDirection = "unknown",
    event_confidence: ConfidenceLevel = "unknown",
) -> StockImpact:
    watchlist_item = watchlist_by_symbol.get(company.symbol)
    watchlist_risks = (watchlist_item.risks,) if watchlist_item and watchlist_item.risks else ()
    proposed_risks = proposed.risks if proposed else ()
    impact_type = (
        proposed.impact_type
        if proposed and match.explicit and proposed.impact_type != "negative"
        else match.impact_type
    )
    impact_strength = (
        proposed.impact_strength if proposed and match.explicit else match.impact_strength
    )
    proposed_direction = proposed.impact_direction if proposed else "unknown"
    if proposed and proposed.impact_type == "negative" and proposed_direction == "unknown":
        proposed_direction = "negative"
    can_inherit_event_direction = match.priority <= 1
    impact_direction = (
        proposed_direction
        if proposed_direction != "unknown"
        else event_direction if can_inherit_event_direction else "unknown"
    )
    confidence = proposed.confidence if proposed else "unknown"
    if confidence == "unknown" and impact_direction != "unknown":
        confidence = event_confidence
    return StockImpact(
        symbol=company.symbol,
        name=company.name,
        market=company.market,
        impact_type=impact_type,
        impact_strength=impact_strength,
        themes=company.themes or (proposed.themes if proposed else ()),
        reasoning=(proposed.reasoning if proposed and proposed.reasoning else match.reasoning),
        evidence=(proposed.evidence if proposed else ()) + match.evidence,
        risks=tuple(dict.fromkeys((*proposed_risks, *watchlist_risks))),
        verification_status="verified",
        verification_source=company.source or "a_share_universe",
        watchlist_hit=watchlist_item is not None,
        impact_direction=impact_direction,
        confidence=confidence,
    )


def _impact_sort_key(match: _CompanyMatch, impact: StockImpact) -> tuple[int, int, str]:
    return (
        match.priority,
        0 if impact.watchlist_hit else 1,
        impact.symbol,
    )


def _unverified_impact(impact: StockImpact) -> StockImpact:
    return StockImpact(
        symbol=impact.symbol,
        name=impact.name,
        market=impact.market,
        impact_type=impact.impact_type,
        impact_strength=impact.impact_strength,
        themes=impact.themes,
        reasoning=impact.reasoning,
        evidence=impact.evidence,
        risks=impact.risks,
        verification_status="unverified",
        verification_source="",
        watchlist_hit=impact.watchlist_hit,
        impact_direction=impact.impact_direction,
        confidence=impact.confidence,
    )


def _normalize_company_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())
