from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Stage = Literal["启动", "验证", "高潮", "分歧", "退潮", "待判断"]
ActionState = Literal["忽略", "放观察池", "等验证", "等回调", "可小仓试", "高潮勿追", "待判断"]


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    market: str
    themes: tuple[str, ...] = field(default_factory=tuple)
    thesis: str = ""
    risks: str = ""


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
