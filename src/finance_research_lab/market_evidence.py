from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

from .models import MarketSnapshot

MARKET_CACHE_TTL_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


class MarketEvidenceProvider(Protocol):
    def market(self, symbol: str, lookback_days: int) -> MarketSnapshot: ...


class FallbackMarketProvider:
    def __init__(
        self,
        primary: MarketEvidenceProvider,
        fallback: MarketEvidenceProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    def market(self, symbol: str, lookback_days: int) -> MarketSnapshot:
        try:
            return self.primary.market(symbol, lookback_days)
        except Exception as primary_error:
            logger.warning("primary market provider failed for %s: %s", symbol, primary_error)
            try:
                return self.fallback.market(symbol, lookback_days)
            except Exception as fallback_error:
                raise RuntimeError(
                    f"market providers failed for {symbol}: "
                    f"baostock: {primary_error}; akshare: {fallback_error}"
                ) from fallback_error


def is_fresh_cache(path: Path, ttl_seconds: int = MARKET_CACHE_TTL_SECONDS) -> bool:
    if not path.exists():
        return False
    return time.time() - path.stat().st_mtime < ttl_seconds
