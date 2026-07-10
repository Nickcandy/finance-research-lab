import pytest

from finance_research_lab.market_evidence import FallbackMarketProvider
from finance_research_lab.models import MarketSnapshot


class _Provider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def market(self, symbol, lookback_days):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _snapshot(provider):
    return MarketSnapshot(
        "300308.SZ", "2026-07-10", 100, 101, 99, 100, 0, 100, 1000, 5, provider=provider
    )


def test_fallback_market_provider_stops_after_primary_success() -> None:
    primary = _Provider(_snapshot("baostock"))
    fallback = _Provider(_snapshot("akshare"))

    result = FallbackMarketProvider(primary, fallback).market("300308.SZ", 5)

    assert result.provider == "baostock"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_market_provider_uses_fallback_and_preserves_source(caplog) -> None:
    primary = _Provider(error=RuntimeError("primary down"))
    fallback = _Provider(_snapshot("akshare"))

    result = FallbackMarketProvider(primary, fallback).market("300308.SZ", 5)

    assert result.provider == "akshare"
    assert fallback.calls == 1
    assert "primary down" in caplog.text


def test_fallback_market_provider_preserves_both_errors() -> None:
    provider = FallbackMarketProvider(
        _Provider(error=RuntimeError("primary down")),
        _Provider(error=RuntimeError("fallback down")),
    )

    with pytest.raises(RuntimeError, match="baostock: primary down; akshare: fallback down"):
        provider.market("300308.SZ", 5)
