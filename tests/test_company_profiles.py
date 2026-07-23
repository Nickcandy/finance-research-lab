from __future__ import annotations

import json
from pathlib import Path

from finance_research_lab import company_profiles
from finance_research_lab.a_share_universe import write_a_share_universe
from finance_research_lab.company_profiles import sync_company_profiles
from finance_research_lab.models import AShareCompany
from finance_research_lab.news_trace import load_a_share_universe


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orientation):
        assert orientation == "records"
        return self.rows


class _Query:
    fields = ["updateDate", "code", "code_name", "industry", "industryClassification"]
    error_code = "0"
    error_msg = "success"

    def __init__(self):
        self.rows = [
            ["2026-07-13", "sz.300308", "中际旭创", "C39电子设备制造业", "证监会行业分类"]
        ]
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class _BaoStock:
    def __init__(self):
        self.logout_calls = 0

    def login(self):
        return type("Result", (), {"error_code": "0", "error_msg": "success"})()

    def query_stock_industry(self):
        return _Query()

    def logout(self):
        self.logout_calls += 1


class _AkShare:
    def stock_profile_cninfo(self, symbol):
        assert symbol == "300308"
        return _Frame(
            [
                {
                    "所属行业": "通信设备",
                    "主营业务": "高速光通信收发模块研发和销售",
                    "经营范围": "光通信设备制造",
                    "机构简介": "光模块厂商",
                }
            ]
        )

    def stock_zyjs_ths(self, symbol):
        assert symbol == "300308"
        return _Frame(
            [
                {
                    "主营业务": "高端光通信收发模块的研发、生产及销售",
                    "产品类型": "光通信收发模块、光组件",
                    "产品名称": "800G光模块、汽车光电子",
                    "经营范围": "光电子器件制造",
                }
            ]
        )

    def stock_zygc_em(self, symbol):
        assert symbol == "SZ300308"
        return _Frame(
            [
                {
                    "报告日期": "2025-12-31",
                    "分类类型": "按产品分类",
                    "主营构成": "高速光通信模块",
                    "收入比例": 0.85,
                    "毛利率": 0.32,
                },
                {
                    "报告日期": "2025-12-31",
                    "分类类型": "按产品分类",
                    "主营构成": "其他",
                    "收入比例": 0.05,
                    "毛利率": 0.1,
                },
            ]
        )


def _write_universe(path: Path) -> None:
    write_a_share_universe(
        [
            AShareCompany("300308.SZ", "中际旭创", "A股", source="akshare"),
            AShareCompany("001309.SZ", "德明利", "A股", source="akshare"),
        ],
        path,
    )


def test_sync_company_profiles_fills_one_company_and_preserves_others(tmp_path, monkeypatch) -> None:
    universe = tmp_path / "universe.csv"
    cache = tmp_path / "cache"
    _write_universe(universe)
    bs = _BaoStock()
    monkeypatch.setattr(company_profiles, "_baostock", lambda: bs)
    monkeypatch.setattr(company_profiles, "_akshare", lambda: _AkShare())
    monkeypatch.setattr(company_profiles, "_sleep", lambda _: None)
    monkeypatch.setattr(company_profiles, "_monotonic", lambda: 0.0)

    result = sync_company_profiles(
        universe,
        cache,
        universe,
        symbols=("300308.SZ",),
    )
    companies = load_a_share_universe(universe)

    assert result.processed == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.pending == 1
    assert bs.logout_calls == 1
    assert companies[0].industry == "C39电子设备制造业"
    assert "光模块" in companies[0].themes
    assert "高端光通信收发模块" in companies[0].business_summary
    assert companies[0].source == "baostock+akshare"
    assert companies[1] == AShareCompany("001309.SZ", "德明利", "A股", source="akshare")


def test_sync_company_profiles_reuses_cache_and_refresh_failure_keeps_old_data(
    tmp_path, monkeypatch
) -> None:
    universe = tmp_path / "universe.csv"
    cache = tmp_path / "cache"
    _write_universe(universe)
    monkeypatch.setattr(company_profiles, "_baostock", lambda: _BaoStock())
    monkeypatch.setattr(company_profiles, "_akshare", lambda: _AkShare())
    monkeypatch.setattr(company_profiles, "_sleep", lambda _: None)
    monkeypatch.setattr(company_profiles, "_monotonic", lambda: 0.0)
    sync_company_profiles(universe, cache, universe, symbols=("300308.SZ",))

    def fail_provider():
        raise RuntimeError("provider down")

    monkeypatch.setattr(company_profiles, "_fetch_baostock_industries", fail_provider)
    monkeypatch.setattr(company_profiles, "_fetch_cninfo_profile", lambda _: fail_provider())
    monkeypatch.setattr(company_profiles, "_fetch_ths_profile", lambda _: fail_provider())
    monkeypatch.setattr(company_profiles, "_fetch_eastmoney_segments", lambda _: fail_provider())

    cached_result = sync_company_profiles(universe, cache, universe, symbols=("300308.SZ",))
    refreshed_result = sync_company_profiles(
        universe,
        cache,
        universe,
        symbols=("300308.SZ",),
        refresh=True,
    )
    company = load_a_share_universe(universe)[0]

    assert cached_result.failed == 0
    assert refreshed_result.failed == 2
    assert "光模块" in company.themes
    assert json.loads((cache / "last-run.json").read_text(encoding="utf-8"))["failures"]


def test_sync_company_profiles_caches_normal_no_data(tmp_path, monkeypatch) -> None:
    universe = tmp_path / "universe.csv"
    cache = tmp_path / "cache"
    write_a_share_universe(
        [AShareCompany("001309.SZ", "德明利", "A股", source="akshare")], universe
    )
    monkeypatch.setattr(company_profiles, "_baostock", lambda: _BaoStock())
    empty = type(
        "EmptyAkShare",
        (),
        {
            "stock_profile_cninfo": lambda self, symbol: _Frame([]),
            "stock_zyjs_ths": lambda self, symbol: _Frame([]),
            "stock_zygc_em": lambda self, symbol: _Frame([]),
        },
    )()
    monkeypatch.setattr(company_profiles, "_akshare", lambda: empty)
    monkeypatch.setattr(company_profiles, "_sleep", lambda _: None)
    monkeypatch.setattr(company_profiles, "_monotonic", lambda: 0.0)

    result = sync_company_profiles(universe, cache, universe, symbols=("001309.SZ",))

    assert result.no_data == 1
    assert result.failed == 0
    assert result.pending == 0
    assert json.loads((cache / "cninfo" / "001309_SZ.json").read_text())["status"] == "no_data"


def test_retry_fetch_retries_transient_key_error(monkeypatch) -> None:
    attempts = 0

    def fetch():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise KeyError("count")
        return {"main_business": "锂离子电池隔膜"}

    monkeypatch.setattr(company_profiles, "_sleep", lambda _: None)

    result = company_profiles._retry_fetch(fetch, company_profiles._RateLimiter(interval=0))

    assert result == {"main_business": "锂离子电池隔膜"}
    assert attempts == 2


def test_fetch_eastmoney_segments_treats_empty_frame_key_error_as_no_data(monkeypatch) -> None:
    class EmptyEastmoneyAkShare:
        def stock_zygc_em(self, symbol):
            assert symbol == "SZ300029"
            raise KeyError("None of [Index(['股票代码'])] are in the [columns]")

    monkeypatch.setattr(company_profiles, "_akshare", lambda: EmptyEastmoneyAkShare())

    assert company_profiles._fetch_eastmoney_segments("300029.SZ") is None
