import os
import time

from finance_research_lab import akshare_evidence
from finance_research_lab.akshare_evidence import AkShareEvidenceProvider


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class _AkShare:
    def __init__(self):
        self.market_calls = 0
        self.announcement_calls = 0

    def stock_zh_a_hist(self, **kwargs):
        self.market_calls += 1
        assert kwargs["symbol"] == "300308"
        return _Frame(
            [
                {"日期": "2026-06-01", "开盘": 100, "最高": 101, "最低": 99, "收盘": 100, "涨跌幅": 0, "成交量": 100, "成交额": 1000},
                {"日期": "2026-06-02", "开盘": 101, "最高": 105, "最低": 100, "收盘": 104, "涨跌幅": 4, "成交量": 200, "成交额": 2000},
            ]
        )

    def stock_financial_analysis_indicator_em(self, **kwargs):
        assert kwargs["symbol"] == "300308.SZ"
        return _Frame(
            [
                {
                    "REPORT_DATE": "2025-12-31",
                    "TOTALOPERATEREVE": 100,
                    "TOTALOPERATEREVETZ": 5,
                    "PARENTNETPROFIT": 10,
                    "PARENTNETPROFITTZ": 2,
                    "XSMLL": 30,
                },
                {
                    "REPORT_DATE": "2026-03-31",
                    "TOTALOPERATEREVE": 120,
                    "TOTALOPERATEREVETZ": 10,
                    "PARENTNETPROFIT": 12,
                    "PARENTNETPROFITTZ": 8,
                    "XSMLL": 31,
                },
            ]
        )

    def stock_financial_cash_new_ths(self, **kwargs):
        assert kwargs["symbol"] == "300308"
        return _Frame(
            [
                {
                    "report_date": "2026-03-31",
                    "metric_name": "经营活动产生的现金流量净额",
                    "value": 15,
                }
            ]
        )

    def stock_zh_a_disclosure_report_cninfo(self, **kwargs):
        self.announcement_calls += 1
        assert kwargs["symbol"] == "300308"
        return _Frame(
            [
                {
                    "公告标题": "关于订单的公告",
                    "公告时间": "2026-06-02",
                    "公告链接": "https://www.cninfo.com.cn/a",
                }
            ]
        )


def test_akshare_provider_maps_and_caches_evidence(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)
    provider = AkShareEvidenceProvider(tmp_path)

    announcements = provider.announcements("300308.SZ", "2026-06-01", "2026-06-10")
    financials = provider.financials("300308.SZ")
    market = provider.market("300308.SZ", 2)

    assert announcements[0].url == "https://www.cninfo.com.cn/a"
    assert announcements[0].provider == "akshare/cninfo"
    assert financials[0].report_period == "2026-03-31"
    assert financials[0].revenue == 120.0
    assert financials[0].operating_cash_flow == 15.0
    assert market.period_return_pct == 4.0
    assert market.volume_ratio == 2.0

    cached_market = AkShareEvidenceProvider(tmp_path).market("300308.SZ", 2)
    assert cached_market.trade_date == "2026-06-02"
    assert ak.market_calls == 1


def test_akshare_provider_rejects_market_rows_with_missing_required_fields(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)
    ak.stock_zh_a_hist = lambda **kwargs: _Frame([{"日期": "2026-06-02"}])

    provider = AkShareEvidenceProvider(tmp_path)

    try:
        provider.market("300308.SZ", 5)
    except ValueError as exc:
        assert "收盘" in str(exc)
    else:
        raise AssertionError("expected missing market fields to fail")


def test_akshare_provider_treats_empty_cninfo_result_as_no_announcements(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)

    def empty_announcements(**kwargs):
        raise KeyError("announcementId")

    ak.stock_zh_a_disclosure_report_cninfo = empty_announcements

    assert AkShareEvidenceProvider(tmp_path).announcements("300308.SZ") == ()


def test_akshare_provider_keeps_announcement_ranges_in_separate_caches(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)
    provider = AkShareEvidenceProvider(tmp_path)

    provider.announcements("300308.SZ", "2026-06-01", "2026-06-10")
    provider.announcements("300308.SZ", "2026-05-01", "2026-05-31")
    provider.announcements("300308.SZ", "2026-06-01", "2026-06-10")

    assert ak.announcement_calls == 2


def test_akshare_provider_refreshes_existing_cache(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)

    AkShareEvidenceProvider(tmp_path).market("300308.SZ", 2)
    AkShareEvidenceProvider(tmp_path, refresh=True).market("300308.SZ", 2)

    assert ak.market_calls == 2


def test_akshare_provider_refreshes_market_cache_after_twenty_four_hours(tmp_path, monkeypatch) -> None:
    ak = _AkShare()
    monkeypatch.setattr(akshare_evidence, "_akshare", lambda: ak)
    provider = AkShareEvidenceProvider(tmp_path)
    provider.market("300308.SZ", 2)
    cache = tmp_path / "market-2" / "300308_SZ.json"
    old = time.time() - 25 * 60 * 60
    os.utime(cache, (old, old))

    provider.market("300308.SZ", 2)

    assert ak.market_calls == 2
