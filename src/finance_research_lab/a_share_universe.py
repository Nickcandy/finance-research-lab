from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import AShareCompany

A_SHARE_UNIVERSE_FIELDS = (
    "symbol",
    "name",
    "market",
    "industry",
    "themes",
    "business_summary",
    "source",
)

RawCompanyRow = Mapping[str, Any]
CompanyFetcher = Callable[[], Iterable[RawCompanyRow]]


def sync_a_share_universe_from_akshare(
    output_path: str | Path,
    *,
    fetcher: CompanyFetcher | None = None,
) -> list[AShareCompany]:
    """Fetch A-share basics from AkShare and persist them as the local universe CSV."""

    rows = list((fetcher or _fetch_akshare_stock_basics)())
    companies = [_company_from_row(row) for row in rows]
    companies = [company for company in companies if company.symbol and company.name]
    write_a_share_universe(companies, output_path)
    return companies


def write_a_share_universe(companies: Iterable[AShareCompany], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=A_SHARE_UNIVERSE_FIELDS)
        writer.writeheader()
        for company in companies:
            writer.writerow(
                {
                    "symbol": company.symbol,
                    "name": company.name,
                    "market": company.market,
                    "industry": company.industry,
                    "themes": ";".join(company.themes),
                    "business_summary": company.business_summary,
                    "source": company.source,
                }
            )


def _fetch_akshare_stock_basics() -> Iterable[RawCompanyRow]:
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "AkShare is not installed. Install it with: "
            "pip install 'finance-research-lab[akshare]'"
        ) from exc

    data = ak.stock_info_a_code_name()
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return data


def _company_from_row(row: RawCompanyRow) -> AShareCompany:
    symbol = _normalize_a_share_symbol(_first_present(row, "symbol", "code", "代码"))
    name = _first_present(row, "name", "名称")
    industry = _first_present(row, "industry", "行业")
    business_summary = _first_present(row, "business_summary", "主营业务", "公司简介")
    return AShareCompany(
        symbol=symbol,
        name=name,
        market="A股",
        industry=industry,
        themes=(),
        business_summary=business_summary,
        source="akshare",
    )


def _first_present(row: RawCompanyRow, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_a_share_symbol(raw_symbol: str) -> str:
    symbol = raw_symbol.strip().upper()
    if not symbol:
        return ""
    if "." in symbol:
        code, exchange = symbol.split(".", 1)
        return f"{code}.{exchange}"
    if len(symbol) != 6 or not symbol.isdigit():
        return symbol
    if symbol.startswith("6"):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8", "9")):
        return f"{symbol}.BJ"
    return symbol
