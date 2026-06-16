from __future__ import annotations

import csv
from pathlib import Path

from .models import NewsTrace, WatchlistItem

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
