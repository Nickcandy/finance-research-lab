import json

import pytest

from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.event_catalog import (
    InvalidEventCatalog,
    read_event_catalog,
    write_event_catalog,
)
from finance_research_lab.models import MarketEvent, NewsItem


def test_event_catalog_round_trips_full_market_event(tmp_path) -> None:
    news = NewsItem(
        "事件标题",
        "同花顺",
        "https://example.com/event",
        "2026-07-16T11:00:00+08:00",
        "完整正文",
    )
    event = MarketEvent(news.headline, (news,))
    path = tmp_path / "catalog.json"

    write_event_catalog((event,), "run-1", path)
    catalog = read_event_catalog(path, "run-1")

    assert catalog == {market_event_id(event): event}
    assert not list(tmp_path.glob("*.tmp"))


def test_event_catalog_rejects_wrong_run_and_tampered_event_id(tmp_path) -> None:
    news = NewsItem("事件标题", "同花顺", published_at="2026-07-16T11:00:00+08:00")
    event = MarketEvent(news.headline, (news,))
    path = tmp_path / "catalog.json"
    write_event_catalog((event,), "run-1", path)

    with pytest.raises(InvalidEventCatalog, match="run_id"):
        read_event_catalog(path, "run-2")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["events"][0]["id"] = "evt_bad"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InvalidEventCatalog, match="id"):
        read_event_catalog(path, "run-1")
