import os
import time

import pytest

from finance_research_lab import baostock_market
from finance_research_lab.baostock_market import BaoStockMarketProvider, _baostock_symbol


class _Result:
    def __init__(self, error_code="0", error_msg="success"):
        self.error_code = error_code
        self.error_msg = error_msg


class _Query(_Result):
    fields = baostock_market.BAOSTOCK_FIELDS.split(",")

    def __init__(self, rows=(), error_code="0", error_msg="success"):
        super().__init__(error_code, error_msg)
        self.rows = list(rows)
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class _BaoStock:
    def __init__(self, rows=(), login_result=None, query_result=None):
        self.rows = rows
        self.login_result = login_result or _Result()
        self.query_result = query_result
        self.query_calls = []
        self.logout_calls = 0

    def login(self):
        return self.login_result

    def logout(self):
        self.logout_calls += 1

    def query_history_k_data_plus(self, symbol, fields, **kwargs):
        self.query_calls.append((symbol, fields, kwargs))
        return self.query_result or _Query(self.rows)


ROWS = [
    ["2026-07-08", "100", "102", "99", "100", "0", "100", "1000"],
    ["2026-07-09", "101", "105", "100", "104", "4", "200", "2000"],
]


def test_baostock_symbol_maps_sh_and_sz_and_rejects_bj() -> None:
    assert _baostock_symbol("600519.SH") == "sh.600519"
    assert _baostock_symbol("300308.SZ") == "sz.300308"

    with pytest.raises(ValueError, match="does not support"):
        _baostock_symbol("920000.BJ")


def test_baostock_provider_maps_market_data_and_uses_fresh_cache(tmp_path, monkeypatch) -> None:
    bs = _BaoStock(ROWS)
    monkeypatch.setattr(baostock_market, "_baostock", lambda: bs)

    snapshot = BaoStockMarketProvider(tmp_path).market("300308.SZ", 2)
    cached = BaoStockMarketProvider(tmp_path).market("300308.SZ", 2)

    assert bs.query_calls[0][0] == "sz.300308"
    assert bs.query_calls[0][2]["frequency"] == "d"
    assert bs.query_calls[0][2]["adjustflag"] == "3"
    assert snapshot.close == 104
    assert snapshot.period_return_pct == 4
    assert snapshot.volume_ratio == 2
    assert snapshot.provider == "baostock"
    assert cached == snapshot
    assert len(bs.query_calls) == 1
    assert bs.logout_calls == 1


@pytest.mark.parametrize(
    ("bs", "message"),
    [
        (_BaoStock(login_result=_Result("1", "login unavailable")), "login failed"),
        (_BaoStock(query_result=_Query(error_code="2", error_msg="query unavailable")), "query failed"),
        (_BaoStock(), "no market data"),
        (_BaoStock([["2026-07-09", "", "105", "100", "104", "4", "200", "2000"]]), "missing open"),
    ],
)
def test_baostock_provider_reports_failures_and_always_logs_out(tmp_path, monkeypatch, bs, message) -> None:
    monkeypatch.setattr(baostock_market, "_baostock", lambda: bs)

    with pytest.raises((RuntimeError, ValueError), match=message):
        BaoStockMarketProvider(tmp_path).market("300308.SZ", 2)

    assert bs.logout_calls == 1


def test_baostock_provider_refreshes_stale_cache_and_honors_force_refresh(tmp_path, monkeypatch) -> None:
    bs = _BaoStock(ROWS)
    monkeypatch.setattr(baostock_market, "_baostock", lambda: bs)
    provider = BaoStockMarketProvider(tmp_path)
    provider.market("300308.SZ", 2)
    cache = tmp_path / "market-2" / "300308_SZ.json"

    old = time.time() - 25 * 60 * 60
    os.utime(cache, (old, old))
    provider.market("300308.SZ", 2)
    BaoStockMarketProvider(tmp_path, refresh=True).market("300308.SZ", 2)

    assert len(bs.query_calls) == 3


def test_baostock_provider_logs_out_when_symbol_is_unsupported(tmp_path, monkeypatch) -> None:
    bs = _BaoStock(ROWS)
    monkeypatch.setattr(baostock_market, "_baostock", lambda: bs)

    with pytest.raises(ValueError, match="does not support"):
        BaoStockMarketProvider(tmp_path).market("920000.BJ", 2)

    assert bs.logout_calls == 1
