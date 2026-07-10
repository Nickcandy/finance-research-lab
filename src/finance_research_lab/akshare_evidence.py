from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .market_evidence import is_fresh_cache
from .models import CompanyAnnouncement, FinancialSnapshot, MarketSnapshot


class AkShareEvidenceProvider:
    """Fetch and cache the small evidence set used by the research workflow."""

    def __init__(self, cache_dir: str | Path = "data/akshare_cache", refresh: bool = False) -> None:
        self.cache_dir = Path(cache_dir)
        self.refresh = refresh
        self.fetched_at = datetime.now().isoformat(timespec="seconds")

    def announcements(self, symbol: str, start_date: str = "", end_date: str = "") -> tuple[CompanyAnnouncement, ...]:
        end = end_date or date.today().isoformat()
        start = start_date or (date.today() - timedelta(days=30)).isoformat()
        path = self._path(f"announcements-{start}-{end}", symbol)
        cached = self._read(path)
        if cached is not None and not self.refresh:
            return tuple(CompanyAnnouncement(**item) for item in cached)

        ak = _akshare()
        try:
            frame = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=_plain_symbol(symbol), market="沪深京", start_date=start, end_date=end
            )
        except KeyError as exc:
            if "announcementId" not in str(exc):
                raise
            announcements: tuple[CompanyAnnouncement, ...] = ()
            self._write(path, announcements)
            return announcements
        announcements = tuple(
            CompanyAnnouncement(
                symbol=symbol,
                title=_text(row, "公告标题"),
                announcement_type=_text(row, "公告类型"),
                published_at=_text(row, "公告时间"),
                url=_text(row, "公告链接"),
                provider="akshare/cninfo",
                source_url=_text(row, "公告链接"),
                fetched_at=self.fetched_at,
            )
            for row in _records(frame)
            if _text(row, "公告标题")
        )
        self._write(path, announcements)
        return announcements

    def financials(self, symbol: str) -> tuple[FinancialSnapshot, ...]:
        path = self._path("financials", symbol)
        cached = self._read(path)
        if cached is not None and not self.refresh:
            return tuple(FinancialSnapshot(**item) for item in cached)

        ak = _akshare()
        rows = _records(ak.stock_financial_analysis_indicator_em(symbol=symbol, indicator="按报告期"))
        cash_flow_rows = _records(
            ak.stock_financial_cash_new_ths(symbol=_plain_symbol(symbol), indicator="按报告期")
        )
        cash_flows = {
            _date_key(_text(row, "report_date")): _number(row, "value")
            for row in cash_flow_rows
            if _text(row, "metric_name") == "经营活动产生的现金流量净额"
        }
        rows.sort(key=lambda row: _date_key(_text(row, "REPORT_DATE")), reverse=True)
        snapshots = tuple(
            FinancialSnapshot(
                symbol=symbol,
                report_period=_date_key(_text(row, "REPORT_DATE")),
                revenue=_number(row, "TOTALOPERATEREVE"),
                revenue_yoy=_number(row, "TOTALOPERATEREVETZ"),
                net_profit=_number(row, "PARENTNETPROFIT"),
                net_profit_yoy=_number(row, "PARENTNETPROFITTZ"),
                gross_margin=_number(row, "XSMLL"),
                operating_cash_flow=cash_flows.get(_date_key(_text(row, "REPORT_DATE"))),
                provider="akshare/eastmoney",
                source_url="https://emweb.securities.eastmoney.com/",
                fetched_at=self.fetched_at,
            )
            for row in rows[:4]
            if _date_key(_text(row, "REPORT_DATE"))
        )
        self._write(path, snapshots)
        return snapshots

    def market(self, symbol: str, lookback_days: int) -> MarketSnapshot:
        path = self._path(f"market-{lookback_days}", symbol)
        if not self.refresh and is_fresh_cache(path):
            return MarketSnapshot(**self._read(path))

        ak = _akshare()
        start = (date.today() - timedelta(days=max(lookback_days * 4, 30))).strftime("%Y%m%d")
        end = date.today().strftime("%Y%m%d")
        rows = _records(
            ak.stock_zh_a_hist(
                symbol=_plain_symbol(symbol), period="daily", start_date=start, end_date=end, adjust=""
            )
        )
        rows.sort(key=lambda row: _text(row, "日期"))
        window = rows[-lookback_days:]
        if not window:
            raise ValueError(f"AkShare returned no market data for {symbol}")
        latest = window[-1]
        first_close = _number(window[0], "收盘")
        close = _required_number(latest, "收盘")
        prior_volumes = [_number(row, "成交量") for row in window[:-1]]
        prior_volumes = [value for value in prior_volumes if value is not None]
        average_volume = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        volume = _required_number(latest, "成交量")
        snapshot = MarketSnapshot(
            symbol=symbol,
            trade_date=_text(latest, "日期"),
            open=_required_number(latest, "开盘"),
            high=_required_number(latest, "最高"),
            low=_required_number(latest, "最低"),
            close=close,
            pct_chg=_required_number(latest, "涨跌幅"),
            volume=volume,
            amount=_required_number(latest, "成交额"),
            lookback_days=len(window),
            period_return_pct=round((close / first_close - 1) * 100, 4) if first_close else None,
            volume_ratio=(volume / average_volume) if average_volume else None,
            provider="akshare/eastmoney",
            source_url="https://quote.eastmoney.com/",
            fetched_at=self.fetched_at,
        )
        self._write(path, snapshot)
        return snapshot

    def _path(self, kind: str, symbol: str) -> Path:
        return self.cache_dir / kind / f"{symbol.replace('.', '_')}.json"

    def _read(self, path: Path) -> Any | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, tuple):
            data = [asdict(item) for item in value]
        else:
            data = asdict(value)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _akshare() -> Any:
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("AkShare is not installed. Install it with: pip install -e '.[akshare]'") from exc
    return ak


def _plain_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0].strip()


def _date_key(value: str) -> str:
    return value[:10]


def _records(frame: Any) -> list[dict[str, Any]]:
    if not hasattr(frame, "to_dict"):
        raise ValueError("AkShare returned an unsupported response")
    return list(frame.to_dict("records"))


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or str(value).lower() == "nan":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _required_number(row: dict[str, Any], key: str) -> float:
    value = _number(row, key)
    if value is None:
        raise ValueError(f"AkShare market row is missing {key}")
    return value
