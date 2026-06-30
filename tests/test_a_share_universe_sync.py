from __future__ import annotations

from finance_research_lab.a_share_universe import sync_a_share_universe_from_akshare
from finance_research_lab.news_trace import load_a_share_universe


def test_sync_a_share_universe_from_akshare_writes_local_csv(tmp_path) -> None:
    output = tmp_path / "a_share_universe.csv"

    companies = sync_a_share_universe_from_akshare(
        output,
        fetcher=lambda: [
            {"代码": "600519", "名称": "贵州茅台", "行业": "白酒"},
            {"代码": "300308", "名称": "中际旭创", "行业": "通信设备"},
        ],
    )

    loaded = load_a_share_universe(output)

    assert [company.symbol for company in companies] == ["600519.SH", "300308.SZ"]
    assert [company.name for company in loaded] == ["贵州茅台", "中际旭创"]
    assert loaded[0].industry == "白酒"
    assert loaded[0].source == "akshare"
