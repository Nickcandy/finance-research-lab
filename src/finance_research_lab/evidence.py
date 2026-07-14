from __future__ import annotations

from .akshare_evidence import AkShareEvidenceProvider
from .market_evidence import MarketEvidenceProvider
from .models import (
    CompanyAnnouncement,
    EventClassification,
    EvidencePlan,
    FinancialSnapshot,
    MarketSnapshot,
    NewsItem,
    ValueChainScore,
    WatchlistItem,
)
from .news_trace import infer_themes


def classify_event(
    news: NewsItem,
    watchlist: list[WatchlistItem],
) -> EventClassification:
    text = f"{news.headline} {news.body}".lower()
    event_type = "待判断"
    if any(word in text for word in ["订单", "合同", "contract", "order"]):
        event_type = "订单 / 合同"
    elif any(word in text for word in ["财报", "业绩", "guidance", "earnings"]):
        event_type = "业绩 / 指引"
    elif any(word in text for word in ["政策", "监管", "regulation", "policy", "法案"]):
        event_type = "政策 / 监管"
    elif any(word in text for word in ["涨价", "提价", "供需", "库存", "price increase"]):
        event_type = "涨价 / 供需"
    elif any(word in text for word in ["capex", "资本开支", "投资", "扩产", "data center"]):
        event_type = "资本开支"
    elif any(word in text for word in ["发布", "launch", "product", "模型"]):
        event_type = "产品发布"
    elif any(word in text for word in ["诉讼", "调查", "处罚", "risk", "风险"]):
        event_type = "风险暴露"
    elif infer_themes(f"{news.headline} {news.body}"):
        event_type = "纯情绪题材"

    candidates = tuple(
        item.symbol
        for item in watchlist
        if score_value_chain_relevance(news, item).revenue_elasticity_score > 0
    )
    confidence = "medium" if event_type != "待判断" and candidates else "low"
    return EventClassification(
        event_type=event_type,
        candidate_symbols=candidates,
        confidence=confidence,
        reasoning="基于新闻关键词和股票池主题重合度的事件分类 fallback。",
    )


def build_evidence_plan(
    classification: EventClassification,
    candidate_symbols: tuple[str, ...] | None = None,
) -> EvidencePlan:
    required_tools = ["market_snapshot", "value_chain"]
    questions = [
        "相关公司是否处在事件上下游的关键位置？",
        "今天或本周价格、成交量、成交额是否已经异常反应？",
    ]

    if classification.event_type in {"订单 / 合同", "资本开支", "产品发布", "风险暴露"}:
        required_tools.append("company_announcements")
        questions.append("公司公告是否披露订单、客户、项目、风险或商业化进展？")
    if classification.event_type in {"业绩 / 指引", "涨价 / 供需", "资本开支"}:
        required_tools.append("financial_reports")
        questions.append("最近财报是否支持收入、利润、现金流或毛利率改善？")
    if classification.event_type in {"政策 / 监管", "纯情绪题材", "待判断"}:
        questions.append("是否只是情绪映射，缺少公司层面的可验证证据？")

    return EvidencePlan(
        event_type=classification.event_type,
        candidate_symbols=candidate_symbols if candidate_symbols is not None else classification.candidate_symbols,
        required_tools=tuple(dict.fromkeys(required_tools)),
        questions=tuple(questions),
    )


def fetch_company_announcements(
    symbol: str,
    start_date: str,
    end_date: str,
    provider: AkShareEvidenceProvider | None = None,
) -> tuple[CompanyAnnouncement, ...]:
    return (provider or AkShareEvidenceProvider()).announcements(symbol, start_date, end_date)


def fetch_financial_reports(
    symbol: str,
    periods: tuple[str, ...],
    provider: AkShareEvidenceProvider | None = None,
) -> tuple[FinancialSnapshot, ...]:
    del periods
    return (provider or AkShareEvidenceProvider()).financials(symbol)


def fetch_market_snapshot(
    symbol: str,
    lookback_days: int,
    provider: MarketEvidenceProvider | None = None,
) -> MarketSnapshot:
    return (provider or AkShareEvidenceProvider()).market(symbol, lookback_days)


def score_value_chain_relevance(
    news: NewsItem,
    item: WatchlistItem,
) -> ValueChainScore:
    themes = infer_themes(f"{news.headline} {news.body}")
    overlap = themes.intersection(item.themes)
    if len(overlap) >= 2:
        score = 3
        reasoning = "新闻主题与股票池主题高度重合，可能存在直接产业链或收入弹性。"
    elif len(overlap) == 1:
        score = 2
        reasoning = "新闻主题与股票池主题存在交集，但收入弹性仍需公告和财报验证。"
    elif any(theme.lower() in item.thesis.lower() for theme in themes):
        score = 1
        reasoning = "关注逻辑提到相关主题，当前更接近情绪映射。"
    else:
        score = 0
        reasoning = "未发现明确主题或关注逻辑关联。"

    return ValueChainScore(
        symbol=item.symbol,
        upstream_relevance_score=score,
        downstream_relevance_score=score,
        revenue_elasticity_score=score,
        reasoning=reasoning,
    )
