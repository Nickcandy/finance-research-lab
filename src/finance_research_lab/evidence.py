from __future__ import annotations

from .models import (
    CompanyAnnouncement,
    EventClassification,
    EvidencePlan,
    FinancialSnapshot,
    MarketSnapshot,
    RawNews,
    ValueChainScore,
    WatchlistItem,
)
from .news_trace import infer_themes


def classify_event(
    news: RawNews,
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


def build_evidence_plan(classification: EventClassification) -> EvidencePlan:
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
        candidate_symbols=classification.candidate_symbols,
        required_tools=tuple(dict.fromkeys(required_tools)),
        questions=tuple(questions),
    )


def fetch_company_announcements(
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[CompanyAnnouncement, ...]:
    del start_date, end_date
    return (
        CompanyAnnouncement(
            symbol=symbol,
            title=f"{symbol} 相关公告摘要待接入",
            announcement_type="mock",
            published_at="待补充",
            summary="V1.5 mock provider：后续接入巨潮、交易所或 Tushare 公告列表。",
        ),
    )


def fetch_financial_reports(
    symbol: str,
    periods: tuple[str, ...],
) -> tuple[FinancialSnapshot, ...]:
    report_period = periods[0] if periods else "latest"
    return (
        FinancialSnapshot(
            symbol=symbol,
            report_period=report_period,
            revenue=100.0,
            revenue_yoy=12.0,
            net_profit=10.0,
            net_profit_yoy=8.0,
            gross_margin=30.0,
            operating_cash_flow=6.0,
        ),
    )


def fetch_market_snapshot(symbol: str, lookback_days: int) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        trade_date="待接入",
        open=100.0,
        high=108.0,
        low=98.0,
        close=106.0,
        pct_chg=5.6,
        volume=1200000.0,
        amount=250000000.0,
        lookback_days=lookback_days,
    )


def score_value_chain_relevance(
    news: RawNews,
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
