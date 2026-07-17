from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .a_share_universe import write_a_share_universe
from .models import AShareCompany
from .news_trace import load_a_share_universe
from .value_chains import canonical_theme_labels

SHANGHAI = ZoneInfo("Asia/Shanghai")
PROFILE_SCHEMA_VERSION = "1.0"
INDUSTRY_TTL = timedelta(days=7)
PROFILE_TTL = timedelta(days=30)
RETRY_DELAYS = (2, 5, 15)
REQUEST_INTERVAL_SECONDS = 1.0
PROFILE_SOURCES = ("cninfo", "ths", "eastmoney")

_sleep = time.sleep
_monotonic = time.monotonic


@dataclass(frozen=True)
class CompanyProfileSyncResult:
    processed: int
    succeeded: int
    no_data: int
    failed: int
    pending: int
    output_path: str


class _RateLimiter:
    def __init__(self, interval: float = REQUEST_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self.last_request_at: float | None = None

    def wait(self) -> None:
        now = _monotonic()
        if self.last_request_at is not None:
            remaining = self.interval - (now - self.last_request_at)
            if remaining > 0:
                _sleep(remaining)
        self.last_request_at = _monotonic()


def sync_company_profiles(
    universe_path: str | Path,
    cache_path: str | Path,
    output_path: str | Path,
    symbols: tuple[str, ...] = (),
    limit: int = 100,
    refresh: bool = False,
) -> CompanyProfileSyncResult:
    if limit < 1:
        raise ValueError("limit must be positive")
    universe = load_a_share_universe(universe_path)
    if not universe:
        raise ValueError("A-share universe is empty")
    cache_dir = Path(cache_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    universe_by_symbol = {company.symbol: company for company in universe}
    requested = tuple(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    unknown = [symbol for symbol in requested if symbol not in universe_by_symbol]
    if unknown:
        raise ValueError(f"symbols are not present in A-share universe: {', '.join(unknown)}")

    failures: list[dict[str, str]] = []
    industry_path = cache_dir / "baostock" / "industry.json"
    industry_envelope, industry_error = _ensure_cache(
        industry_path,
        provider="baostock/industry",
        symbol="ALL",
        ttl=INDUSTRY_TTL,
        refresh=refresh,
        fetcher=_fetch_baostock_industries,
        limiter=_RateLimiter(),
    )
    if industry_error:
        failures.append({"provider": "baostock/industry", "symbol": "ALL", "error": industry_error})

    pending_before = [
        company
        for company in universe
        if refresh or _profile_is_pending(cache_dir, company.symbol)
    ]
    targets = (
        [universe_by_symbol[symbol] for symbol in requested]
        if requested
        else pending_before[:limit]
    )
    limiter = _RateLimiter()
    succeeded = 0
    no_data = 0
    company_failures = 0
    for company in targets:
        statuses: list[str] = []
        company_failed = False
        for source, provider, fetcher in (
            ("cninfo", "akshare/cninfo", _fetch_cninfo_profile),
            ("ths", "akshare/ths", _fetch_ths_profile),
            ("eastmoney", "akshare/eastmoney", _fetch_eastmoney_segments),
        ):
            envelope, error = _ensure_cache(
                _profile_cache_path(cache_dir, source, company.symbol),
                provider=provider,
                symbol=company.symbol,
                ttl=PROFILE_TTL,
                refresh=refresh,
                fetcher=lambda fetcher=fetcher, symbol=company.symbol: fetcher(symbol),
                limiter=limiter,
            )
            if envelope is not None:
                statuses.append(str(envelope.get("status", "")))
            if error:
                company_failed = True
                failures.append({"provider": provider, "symbol": company.symbol, "error": error})
        if company_failed:
            company_failures += 1
        elif statuses and all(status == "no_data" for status in statuses):
            no_data += 1
        else:
            succeeded += 1

    merged = [
        _merge_company_profile(company, cache_dir, industry_envelope)
        for company in universe
    ]
    write_a_share_universe(merged, output_path)
    pending = sum(_profile_is_pending(cache_dir, company.symbol) for company in universe)
    failed = company_failures + (1 if industry_error else 0)
    result = CompanyProfileSyncResult(
        processed=len(targets),
        succeeded=succeeded,
        no_data=no_data,
        failed=failed,
        pending=pending,
        output_path=str(output_path),
    )
    _atomic_write_json(
        cache_dir / "last-run.json",
        {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "finished_at": _now_iso(),
            "result": asdict(result),
            "failures": failures,
        },
    )
    return result


def _profile_is_pending(cache_dir: Path, symbol: str) -> bool:
    return any(
        not _is_fresh(_read_envelope(_profile_cache_path(cache_dir, source, symbol)), PROFILE_TTL)
        for source in PROFILE_SOURCES
    )


def _ensure_cache(
    path: Path,
    *,
    provider: str,
    symbol: str,
    ttl: timedelta,
    refresh: bool,
    fetcher: Callable[[], dict[str, Any] | None],
    limiter: _RateLimiter,
) -> tuple[dict[str, Any] | None, str]:
    cached = _read_envelope(path)
    if not refresh and _is_fresh(cached, ttl):
        return cached, ""
    try:
        data = _retry_fetch(fetcher, limiter)
    except Exception as exc:
        return cached, str(exc)
    envelope = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "provider": provider,
        "symbol": symbol,
        "fetched_at": _now_iso(),
        "status": "success" if data else "no_data",
        "data": data or {},
    }
    _atomic_write_json(path, envelope)
    return envelope, ""


def _retry_fetch(fetcher: Callable[[], dict[str, Any] | None], limiter: _RateLimiter) -> dict[str, Any] | None:
    for attempt in range(len(RETRY_DELAYS) + 1):
        limiter.wait()
        try:
            return fetcher()
        except (KeyError, TypeError, ValueError):
            raise
        except Exception:
            if attempt == len(RETRY_DELAYS):
                raise
            _sleep(RETRY_DELAYS[attempt])
    raise RuntimeError("unreachable retry state")


def _fetch_baostock_industries() -> dict[str, Any]:
    bs = _baostock()
    login = bs.login()
    try:
        _raise_baostock_error(login, "login")
        query = bs.query_stock_industry()
        _raise_baostock_error(query, "industry query")
        fields = list(query.fields)
        industries: dict[str, str] = {}
        while query.next():
            row = dict(zip(fields, query.get_row_data()))
            symbol = _from_baostock_symbol(_text(row, "code"))
            industry = _text(row, "industry")
            if symbol and industry:
                industries[symbol] = industry
        return {"industries": industries}
    finally:
        bs.logout()


def _fetch_cninfo_profile(symbol: str) -> dict[str, Any] | None:
    rows = _records(_akshare().stock_profile_cninfo(symbol=_plain_symbol(symbol)))
    if not rows:
        return None
    row = rows[0]
    return {
        "industry": _text(row, "所属行业"),
        "main_business": _text(row, "主营业务"),
        "business_scope": _text(row, "经营范围"),
        "organization_summary": _text(row, "机构简介"),
    }


def _fetch_ths_profile(symbol: str) -> dict[str, Any] | None:
    rows = _records(_akshare().stock_zyjs_ths(symbol=_plain_symbol(symbol)))
    if not rows:
        return None
    row = rows[0]
    return {
        "main_business": _text(row, "主营业务"),
        "product_types": _split_products(_text(row, "产品类型")),
        "product_names": _split_products(_text(row, "产品名称")),
        "business_scope": _text(row, "经营范围"),
    }


def _fetch_eastmoney_segments(symbol: str) -> dict[str, Any] | None:
    rows = _records(_akshare().stock_zygc_em(symbol=_eastmoney_symbol(symbol)))
    if not rows:
        return None
    report_dates = sorted({_date_text(row.get("报告日期")) for row in rows if row.get("报告日期")})
    if not report_dates:
        raise ValueError(f"Eastmoney business segments have no report date for {symbol}")
    latest = report_dates[-1]
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if _date_text(row.get("报告日期")) != latest or "产品" not in _text(row, "分类类型"):
            continue
        name = _text(row, "主营构成")
        share = _share(row.get("收入比例"))
        if name and share is not None:
            candidates.append(
                {
                    "name": name,
                    "revenue_share": share,
                    "gross_margin": _optional_float(row.get("毛利率")),
                }
            )
    candidates.sort(key=lambda item: (-item["revenue_share"], item["name"]))
    selected = [
        item for index, item in enumerate(candidates) if index < 3 or item["revenue_share"] >= 0.1
    ][:10]
    return {"report_date": latest, "segments": selected} if selected else None


def _merge_company_profile(
    company: AShareCompany,
    cache_dir: Path,
    industry_envelope: dict[str, Any] | None,
) -> AShareCompany:
    cninfo = _cache_data(_read_envelope(_profile_cache_path(cache_dir, "cninfo", company.symbol)))
    ths = _cache_data(_read_envelope(_profile_cache_path(cache_dir, "ths", company.symbol)))
    eastmoney = _cache_data(
        _read_envelope(_profile_cache_path(cache_dir, "eastmoney", company.symbol))
    )
    industries = _cache_data(industry_envelope).get("industries", {})
    industry = str(industries.get(company.symbol, "")).strip() or str(
        cninfo.get("industry", "")
    ).strip()
    main_business = str(ths.get("main_business", "")).strip() or str(
        cninfo.get("main_business", "")
    ).strip()
    products = _unique_texts(
        [
            *ths.get("product_types", []),
            *ths.get("product_names", []),
            *(segment.get("name", "") for segment in eastmoney.get("segments", [])),
        ]
    )
    summary_parts = [main_business] if main_business else []
    if products:
        summary_parts.append(f"产品：{'、'.join(products)}")
    business_summary = " ".join(summary_parts).strip() or company.business_summary
    derived_themes = canonical_theme_labels(tuple([main_business, *products]))
    themes = tuple(dict.fromkeys((*company.themes, *derived_themes)))
    has_profile = bool(industry or business_summary or themes)
    return replace(
        company,
        industry=industry or company.industry,
        themes=themes,
        business_summary=business_summary,
        source="baostock+akshare" if has_profile else company.source,
    )


def _profile_cache_path(cache_dir: Path, source: str, symbol: str) -> Path:
    return cache_dir / source / f"{symbol.replace('.', '_')}.json"


def _read_envelope(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != PROFILE_SCHEMA_VERSION:
        return None
    if payload.get("status") not in {"success", "no_data"} or not isinstance(payload.get("data"), dict):
        return None
    return payload


def _cache_data(envelope: dict[str, Any] | None) -> dict[str, Any]:
    if envelope is None or envelope.get("status") != "success":
        return {}
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


def _is_fresh(envelope: dict[str, Any] | None, ttl: timedelta) -> bool:
    if envelope is None:
        return False
    try:
        fetched_at = datetime.fromisoformat(str(envelope["fetched_at"]))
    except (KeyError, ValueError):
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=SHANGHAI)
    return datetime.now(SHANGHAI) - fetched_at.astimezone(SHANGHAI) <= ttl


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _records(frame: Any) -> list[dict[str, Any]]:
    if not hasattr(frame, "to_dict"):
        raise ValueError("AkShare returned an unsupported response")
    records = frame.to_dict("records")
    if not isinstance(records, list):
        raise ValueError("AkShare returned unsupported records")
    return records


def _split_products(value: str) -> list[str]:
    return _unique_texts(re.split(r"[,，;；、|]+", value))


def _unique_texts(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text.lower() == "nan" or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value).lower() == "nan":
        return ""
    return str(value).strip()


def _date_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:10]
    return str(value).strip()[:10]


def _share(value: Any) -> float | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number > 1:
        if number <= 100:
            return number / 100
        return None
    return number


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).lower() == "nan":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plain_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0]


def _eastmoney_symbol(symbol: str) -> str:
    code, exchange = symbol.split(".", 1)
    if exchange not in {"SH", "SZ", "BJ"}:
        raise ValueError(f"unsupported A-share symbol: {symbol}")
    return f"{exchange}{code}"


def _from_baostock_symbol(symbol: str) -> str:
    if "." not in symbol:
        return ""
    exchange, code = symbol.split(".", 1)
    if exchange.lower() not in {"sh", "sz"}:
        return ""
    return f"{code}.{exchange.upper()}"


def _raise_baostock_error(result: Any, operation: str) -> None:
    code = str(getattr(result, "error_code", ""))
    if code != "0":
        message = str(getattr(result, "error_msg", "unknown error"))
        raise RuntimeError(f"BaoStock {operation} failed: {code} {message}")


def _akshare() -> Any:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Install it with: pip install -e '.[akshare]'") from exc
    return ak


def _baostock() -> Any:
    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError("BaoStock is not installed. Install it with: pip install -e '.[baostock]'") from exc
    return bs


def _now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")
