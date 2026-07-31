from __future__ import annotations

from datetime import datetime

from finance_research_lab.claim_pipeline import news_content_hash
from finance_research_lab.event_sources import SHANGHAI
from finance_research_lab.models import NewsItem
from finance_research_lab.radar_runs import RadarRunStore


def test_run_store_persists_input_progress_and_public_news_status(tmp_path) -> None:
    store = RadarRunStore(tmp_path / "daily-radar.json")
    start = datetime(2026, 7, 30, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 31, 12, tzinfo=SHANGHAI)
    checkpoint = store.create(start, end)
    item = NewsItem(
        "测试新闻",
        "测试来源",
        "https://example.com/news",
        "2026-07-31T11:00:00+08:00",
        "测试正文",
    )
    store.save_input(checkpoint["run_id"], (item,))
    store.update(
        checkpoint["run_id"],
        status="running",
        stage="extract_claims",
        progress={"completed": 1, "total": 1, "unit": "news"},
        claim_statuses={news_content_hash(item): "succeeded"},
    )

    payload = store.public_payload()

    assert payload["status"] == "running"
    assert payload["news"][0]["analysis_status"] == "succeeded"
    assert payload["news"][0]["headline"] == "测试新闻"


def test_run_store_marks_stale_active_run_interrupted(tmp_path) -> None:
    snapshot_path = tmp_path / "daily-radar.json"
    store = RadarRunStore(snapshot_path)
    checkpoint = store.create(
        datetime(2026, 7, 30, 12, tzinfo=SHANGHAI),
        datetime(2026, 7, 31, 12, tzinfo=SHANGHAI),
    )
    store.save_input(checkpoint["run_id"], ())
    store.update(checkpoint["run_id"], status="running")

    restarted = RadarRunStore(snapshot_path)
    restarted.mark_stale_interrupted()

    payload = restarted.public_payload()
    assert payload["status"] == "interrupted"
    assert payload["resumable"] is True
    assert "服务重启" in payload["error"]
