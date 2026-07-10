from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .market_evidence import is_fresh_cache
from .models import MarketSnapshot

BAOSTOCK_FIELDS = "date,open,high,low,close,pctChg,volume,amount"


class BaoStockMarketProvider:
    def __init__(self, cache_dir: str | Path = "data/baostock_cache", refresh: bool = False) -> None:
        self.cache_dir = Path(cache_dir)
        self.refresh = refresh

    def market(self, symbol: str, lookback_days: int) -> MarketSnapshot:
        if lookback_days < 1:
            raise ValueError("lookback_days must be positive")
        path = self.cache_dir / f"market-{lookback_days}" / f"{symbol.replace('.', '_')}.json"
        if not self.refresh and is_fresh_cache(path):
            return MarketSnapshot(**json.loads(path.read_text(encoding="utf-8")))

        bs = _baostock()
        login_result = bs.login()
        try:
            _raise_baostock_error(login_result, "login")
            end = date.today()
            start = end - timedelta(days=max(lookback_days * 4, 30))
            query = bs.query_history_k_data_plus(
                _baostock_symbol(symbol),
                BAOSTOCK_FIELDS,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                frequency="d",
                adjustflag="3",
            )
            _raise_baostock_error(query, "market query")
            rows = _query_rows(query)
        finally:
            bs.logout()

        rows.sort(key=lambda row: row["date"])
        window = rows[-lookback_days:]
        if not window:
            raise ValueError(f"BaoStock returned no market data for {symbol}")
        latest = window[-1]
        first_close = _required_number(window[0], "close")
        close = _required_number(latest, "close")
        prior_volumes = [_number(row, "volume") for row in window[:-1]]
        prior_volumes = [value for value in prior_volumes if value is not None]
        average_volume = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
        volume = _required_number(latest, "volume")
        snapshot = MarketSnapshot(
            symbol=symbol,
            trade_date=latest["date"],
            open=_required_number(latest, "open"),
            high=_required_number(latest, "high"),
            low=_required_number(latest, "low"),
            close=close,
            pct_chg=_required_number(latest, "pctChg"),
            volume=volume,
            amount=_required_number(latest, "amount"),
            lookback_days=len(window),
            period_return_pct=round((close / first_close - 1) * 100, 4) if first_close else None,
            volume_ratio=volume / average_volume if average_volume else None,
            provider="baostock",
            source_url="https://www.baostock.com/",
            fetched_at=datetime.now().isoformat(timespec="seconds"),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot


def _baostock() -> Any:
    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError(
            "BaoStock is not installed. Install it with: pip install -e '.[baostock]'"
        ) from exc
    return bs


def _baostock_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SH"):
        return f"sh.{normalized[:-3]}"
    if normalized.endswith(".SZ"):
        return f"sz.{normalized[:-3]}"
    raise ValueError(f"BaoStock does not support symbol: {symbol}")


def _raise_baostock_error(result: Any, operation: str) -> None:
    error_code = str(getattr(result, "error_code", ""))
    if error_code != "0":
        error_msg = str(getattr(result, "error_msg", "unknown error"))
        raise RuntimeError(f"BaoStock {operation} failed: {error_code} {error_msg}")


def _query_rows(query: Any) -> list[dict[str, str]]:
    fields = list(getattr(query, "fields", BAOSTOCK_FIELDS.split(",")))
    rows: list[dict[str, str]] = []
    while query.next():
        rows.append(dict(zip(fields, query.get_row_data())))
    return rows


def _number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _required_number(row: dict[str, str], key: str) -> float:
    value = _number(row, key)
    if value is None:
        raise ValueError(f"BaoStock market row is missing {key}")
    return value
