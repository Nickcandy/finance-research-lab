import csv

import pytest

from finance_research_lab.watchlist_store import (
    WatchlistConflict,
    WatchlistStore,
    WatchlistSymbolNotFound,
)


def test_watchlist_store_search_add_and_remove(tmp_path) -> None:
    watchlist = tmp_path / "watchlist.csv"
    universe = tmp_path / "universe.csv"
    _write_csv(watchlist, [
        {"symbol": "COIN", "name": "Coinbase", "market": "美股", "themes": "Crypto", "thesis": "", "risks": ""},
    ])
    _write_csv(universe, [
        {"symbol": "300308.SZ", "name": "中际旭创", "market": "A股", "industry": "通信", "themes": "AI;光模块", "business_summary": "光模块", "source": "cache"},
    ])
    store = WatchlistStore(watchlist, universe)

    assert [item.symbol for item in store.search("中际")] == ["300308.SZ"]
    added = store.add("300308.sz")
    assert added.name == "中际旭创"
    assert [item.symbol for item in store.list()] == ["COIN", "300308.SZ"]
    assert store.remove("COIN").name == "Coinbase"
    assert [item.symbol for item in store.list()] == ["300308.SZ"]
    assert b"\r\n" not in watchlist.read_bytes()


def test_watchlist_store_rejects_duplicate_and_unknown_symbol(tmp_path) -> None:
    watchlist = tmp_path / "watchlist.csv"
    universe = tmp_path / "universe.csv"
    _write_csv(watchlist, [
        {"symbol": "300308.SZ", "name": "中际旭创", "market": "A股", "themes": "AI", "thesis": "", "risks": ""},
    ])
    _write_csv(universe, [
        {"symbol": "300308.SZ", "name": "中际旭创", "market": "A股", "industry": "通信", "themes": "AI", "business_summary": "", "source": "cache"},
    ])
    store = WatchlistStore(watchlist, universe)

    with pytest.raises(WatchlistConflict):
        store.add("300308.SZ")
    with pytest.raises(WatchlistSymbolNotFound):
        store.add("999999.SH")
    with pytest.raises(WatchlistSymbolNotFound):
        store.remove("999999.SH")


def _write_csv(path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
