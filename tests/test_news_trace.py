from finance_research_lab.news_trace import build_trace, infer_themes
from finance_research_lab.models import WatchlistItem


def test_infer_themes_for_ai_capex() -> None:
    themes = infer_themes("Microsoft raises AI data center capex guidance")
    assert "AI" in themes
    assert "数据中心" in themes


def test_build_trace_maps_watchlist_items() -> None:
    watchlist = [
        WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "数据中心", "光模块")),
        WatchlistItem("601059.SH", "信达证券", "A股", ("券商",)),
    ]
    trace = build_trace("AI data center capex increases optical module demand", "example", watchlist)
    assert trace.news_type == "资本开支 / 产能扩张"
    assert [item.name for item in trace.direct_beneficiaries] == ["中际旭创"]
