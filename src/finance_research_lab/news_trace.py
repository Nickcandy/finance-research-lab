from __future__ import annotations

import csv
from pathlib import Path

from .models import (
    AShareCompany,
    EventAnalysis,
    NewsTrace,
    RawNews,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
    WatchlistItem,
)

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
    news: RawNews,
    watchlist: list[WatchlistItem],
    a_share_universe: list[AShareCompany] | None = None,
    proposed_impacts: tuple[StockImpact, ...] = (),
) -> ResearchReport:
    themes = infer_themes(f"{news.headline} {news.body}")
    payer, receiver, chain = _value_chain_for_themes(themes)
    stock_impacts = _build_stock_impacts(
        themes=themes,
        watchlist=watchlist,
        a_share_universe=a_share_universe,
        proposed_impacts=proposed_impacts,
    )

    return ResearchReport(
        raw_news=news,
        event=EventAnalysis(
            event_type=classify_news_type(f"{news.headline} {news.body}"),
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
            impact_direction="positive" if themes else "unknown",
            reasoning="基于已识别主题匹配内置产业链模板。",
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
) -> list[StockImpact]:
    if a_share_universe is None:
        return list(proposed_impacts) or _map_stock_impacts(themes, watchlist)

    watchlist_by_symbol = {item.symbol: item for item in watchlist}
    universe_by_symbol = {company.symbol: company for company in a_share_universe}
    impacts: list[StockImpact] = []
    seen: set[str] = set()

    for impact in proposed_impacts:
        company = universe_by_symbol.get(impact.symbol)
        if company is None:
            impacts.append(_unverified_impact(impact))
        else:
            impacts.append(_verified_impact(company, themes, watchlist_by_symbol, impact))
        seen.add(impact.symbol)

    for company in a_share_universe:
        if company.symbol in seen:
            continue
        impact = _impact_from_company(themes, company, watchlist_by_symbol)
        if impact is None:
            continue
        impacts.append(impact)
        seen.add(company.symbol)

    return impacts


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


def _impact_from_company(
    themes: set[str],
    company: AShareCompany,
    watchlist_by_symbol: dict[str, WatchlistItem],
) -> StockImpact | None:
    overlap = themes.intersection(company.themes)
    if len(overlap) >= 2:
        impact_type = "direct"
        strength = "high"
        reasoning = "A 股 universe 主题与新闻主题重合度较高。"
    elif len(overlap) == 1:
        impact_type = "indirect"
        strength = "medium"
        reasoning = "A 股 universe 主题与新闻主题存在单一交集。"
    elif any(theme.lower() in company.business_summary.lower() for theme in themes):
        impact_type = "sentiment"
        strength = "low"
        reasoning = "公司业务摘要提到新闻主题，但主题标签未直接匹配。"
    else:
        return None

    watchlist_item = watchlist_by_symbol.get(company.symbol)
    risks = (watchlist_item.risks,) if watchlist_item and watchlist_item.risks else ()
    evidence = (
        f"A 股 universe 主题匹配：{' / '.join(company.themes) or '未标注主题'}",
        f"行业：{company.industry or '未提供'}",
    )
    return StockImpact(
        symbol=company.symbol,
        name=company.name,
        market=company.market,
        impact_type=impact_type,
        impact_strength=strength,
        themes=company.themes,
        reasoning=reasoning,
        evidence=evidence,
        risks=risks,
        verification_status="verified",
        verification_source=company.source or "a_share_universe",
        watchlist_hit=watchlist_item is not None,
    )


def _verified_impact(
    company: AShareCompany,
    themes: set[str],
    watchlist_by_symbol: dict[str, WatchlistItem],
    proposed: StockImpact,
) -> StockImpact:
    base = _impact_from_company(themes, company, watchlist_by_symbol)
    if base is not None:
        return base
    watchlist_item = watchlist_by_symbol.get(company.symbol)
    return StockImpact(
        symbol=company.symbol,
        name=company.name,
        market=company.market,
        impact_type=proposed.impact_type,
        impact_strength=proposed.impact_strength,
        themes=company.themes or proposed.themes,
        reasoning=proposed.reasoning or "候选公司已在 A 股 universe 中校验，但相关性仍需补充。",
        evidence=proposed.evidence + (f"A 股 universe 已确认公司：{company.name}",),
        risks=proposed.risks,
        verification_status="verified",
        verification_source=company.source or "a_share_universe",
        watchlist_hit=watchlist_item is not None,
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
    )
