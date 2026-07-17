from __future__ import annotations

import re
import unicodedata

from .models import MarketEvent, NewsItem

PURE_STOCK_PRICE_UPDATE = "pure_stock_price_update"

_MOVE_RE = re.compile(
    r"(?:触及)?(?:涨停|跌停)|(?:涨|跌)超\s*\d|(?:上涨|下跌|大涨|大跌|跳水|"
    r"走高|走低|拉升|下挫|股价涨|股价跌|涨幅|跌幅)"
)
_CLAUSE_SPLIT_RE = re.compile(r"[。！？；;\n]+")
_NON_STOCK_SUBJECTS = (
    "板块",
    "概念",
    "指数",
    "股指",
    "沪指",
    "深成指",
    "创业板指",
    "科创50",
    "综指",
    "港股",
    "期货",
    "现货",
    "主力合约",
    "人民币",
    "美元指数",
    "黄金",
    "白银",
    "原油",
    "国债",
    "债券",
    "收益率",
)
_CAUSE_MARKERS = (
    "消息面",
    "由于",
    "原因",
    "受益于",
    "受影响",
    "公告",
    "立案",
    "调查",
    "检方",
    "业绩",
    "财报",
    "订单",
    "合同",
    "中标",
    "政策",
    "监管",
    "事故",
    "停产",
    "召回",
    "减持",
    "增持",
    "回购",
    "处罚",
    "亏损",
    "扭亏",
    "获批",
    "合作",
    "终止上市",
    "退市",
)
_MARKET_FACT_MARKERS = (
    "涨",
    "跌",
    "股价",
    "成交额",
    "成交量",
    "封单",
    "市值",
    "换手率",
    "振幅",
    "现报",
    "报",
    "开盘",
    "收盘",
    "盘中",
    "盘前",
    "尾盘",
    "一度",
    "截至",
    "最高",
    "最低",
)


def news_item_exclusion_reason(item: NewsItem) -> str:
    headline = _normalize(item.headline)
    body = _normalize(item.body)
    combined = f"{headline}。{body}" if body else headline
    if not _MOVE_RE.search(headline):
        return ""
    if any(subject in headline for subject in _NON_STOCK_SUBJECTS):
        return ""
    if any(marker in combined for marker in _CAUSE_MARKERS):
        return ""
    if body and not _contains_only_market_facts(body):
        return ""
    return PURE_STOCK_PRICE_UPDATE


def market_event_exclusion_reason(event: MarketEvent) -> str:
    if not event.items:
        return ""
    reasons = {news_item_exclusion_reason(item) for item in event.items}
    return PURE_STOCK_PRICE_UPDATE if reasons == {PURE_STOCK_PRICE_UPDATE} else ""


def is_market_event_researchable(event: MarketEvent) -> bool:
    return not market_event_exclusion_reason(event)


def _contains_only_market_facts(body: str) -> bool:
    clauses = [clause.strip(" ，,：:") for clause in _CLAUSE_SPLIT_RE.split(body)]
    return all(
        not clause or any(marker in clause for marker in _MARKET_FACT_MARKERS)
        for clause in clauses
    )


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()
