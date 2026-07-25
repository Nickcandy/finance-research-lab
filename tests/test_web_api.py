from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from threading import Event, Thread
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from finance_research_lab.web_api import create_server
from finance_research_lab.daily_radar_snapshot import build_daily_radar_snapshot, write_daily_radar_snapshot
from finance_research_lab.event_analysis import generate_event_analysis, write_event_analysis
from finance_research_lab.event_catalog import event_catalog_path, write_event_catalog
from finance_research_lab.event_sources import SHANGHAI
from finance_research_lab.models import MarketEvent, NewsItem


def test_health_reports_snapshot_availability(tmp_path) -> None:
    snapshot_path = tmp_path / "daily-radar.json"

    with _running_server(snapshot_path) as base_url:
        assert _get_json(f"{base_url}/api/health") == {
            "status": "ok",
            "radar_available": False,
        }

    snapshot_path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    with _running_server(snapshot_path) as base_url:
        assert _get_json(f"{base_url}/api/health") == {
            "status": "ok",
            "radar_available": True,
        }


def test_latest_radar_returns_valid_snapshot(tmp_path) -> None:
    snapshot_path = tmp_path / "daily-radar.json"
    snapshot_path.write_text(json.dumps(_snapshot()), encoding="utf-8")

    with _running_server(snapshot_path) as base_url:
        assert _get_json(f"{base_url}/api/radars/latest") == _snapshot()


def test_latest_radar_returns_not_found_when_snapshot_is_missing(tmp_path) -> None:
    with _running_server(tmp_path / "missing.json") as base_url:
        status, payload = _get_error(f"{base_url}/api/radars/latest")

    assert status == 404
    assert payload["error"] == "radar_not_found"


@pytest.mark.parametrize(
    "content",
    (
        "{broken",
        '{"schema_version":"2.0"}',
    ),
)
def test_latest_radar_rejects_invalid_snapshot(tmp_path, content) -> None:
    snapshot_path = tmp_path / "daily-radar.json"
    snapshot_path.write_text(content, encoding="utf-8")

    with _running_server(snapshot_path) as base_url:
        status, payload = _get_error(f"{base_url}/api/radars/latest")

    assert status == 500
    assert payload["error"] == "invalid_radar_snapshot"


def test_latest_radar_rejects_non_utf8_snapshot(tmp_path) -> None:
    snapshot_path = tmp_path / "daily-radar.json"
    snapshot_path.write_bytes(b"\xff")

    with _running_server(snapshot_path) as base_url:
        status, payload = _get_error(f"{base_url}/api/radars/latest")

    assert status == 500
    assert payload["error"] == "invalid_radar_snapshot"


def test_event_analysis_runs_in_background_and_serves_markdown(tmp_path, monkeypatch) -> None:
    snapshot_path, event_id = _write_event_radar(tmp_path)

    def fake_generate(event, **kwargs):
        payload = {
            "schema_version": "1.1",
            "run_id": kwargs["run_id"],
            "event_id": kwargs["event_id"],
            "status": "succeeded",
            "generated_at": "2026-07-16T12:01:00+08:00",
            "event": {
                "title": event.title,
                "event_importance": 50,
                "confidence": 50,
                "importance_level": "medium",
                "analysis_tier": "flash",
                "reason_codes": ["fixture"],
                "overall_direction": "unknown",
                "impact_score": None,
                "candidates": [],
            },
            "steps": [],
            "warnings": [],
            "error": "",
            "markdown": "# 单事件报告",
        }
        write_event_analysis(payload, kwargs["output_path"])
        return payload

    monkeypatch.setattr("finance_research_lab.web_api.generate_event_analysis", fake_generate)
    with _running_server(snapshot_path) as base_url:
        status, payload = _request_json(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis",
            method="POST",
        )
        assert status == 202
        assert payload["status"] in {"queued", "running"}
        completed = _wait_for_analysis(base_url, event_id)
        assert completed["status"] == "succeeded"
        with urlopen(f"{base_url}/api/radars/latest/events/{event_id}/report", timeout=2) as response:
            assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
            assert response.read().decode("utf-8") == "# 单事件报告"
        status, existing = _request_json(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis",
            method="POST",
        )
        assert status == 200
        assert existing["status"] == "succeeded"


def test_event_analysis_reports_missing_catalog(tmp_path) -> None:
    snapshot_path, event_id = _write_event_radar(tmp_path)
    event_catalog_path(snapshot_path, "20260716T120000+0800").unlink()

    with _running_server(snapshot_path) as base_url:
        status, payload = _request_error(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis",
            method="POST",
        )

    assert status == 422
    assert payload["error"] == "event_catalog_unavailable"


def test_event_analysis_rejects_pure_stock_price_update(tmp_path) -> None:
    snapshot_path, event_id = _write_pure_price_event_radar(tmp_path)

    with _running_server(snapshot_path) as base_url:
        status, payload = _request_error(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis",
            method="POST",
        )

    assert status == 422
    assert payload["error"] == "analysis_not_applicable"


def test_event_analysis_persists_failure_and_allows_retry(tmp_path, monkeypatch) -> None:
    snapshot_path, event_id = _write_event_radar(tmp_path)
    monkeypatch.setattr(
        "finance_research_lab.web_api.generate_event_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    with _running_server(snapshot_path) as base_url:
        _request_json(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis",
            method="POST",
        )
        failed = _wait_for_analysis(base_url, event_id)

    assert failed["status"] == "failed"
    assert failed["error"] == "provider unavailable"


def test_generated_failed_event_analysis_keeps_usage_markdown(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_USAGE_STORE", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setattr(
        "finance_research_lab.workflow.run_market_event_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("analysis failed")),
    )
    event = MarketEvent("AI 事件", (NewsItem("AI 事件", "同花顺"),))

    payload = generate_event_analysis(
        event,
        run_id="run-1",
        event_id="event-1",
        rank=1,
        output_path=tmp_path / "analysis.json",
        watchlist_path=tmp_path / "watchlist.csv",
        a_share_universe_path=tmp_path / "universe.csv",
        evidence_cache_path=tmp_path / "evidence",
        market_cache_path=tmp_path / "market",
    )

    assert payload["status"] == "failed"
    assert "## LLM 使用与费用" in payload["markdown"]


def test_event_analysis_rejects_a_second_concurrent_event(tmp_path, monkeypatch) -> None:
    snapshot_path, event_ids = _write_two_event_radar(tmp_path)
    release = Event()

    def blocking_generate(*args, **kwargs):
        release.wait(timeout=2)
        raise RuntimeError("stopped")

    monkeypatch.setattr("finance_research_lab.web_api.generate_event_analysis", blocking_generate)
    with _running_server(snapshot_path) as base_url:
        first_status, _ = _request_json(
            f"{base_url}/api/radars/latest/events/{event_ids[0]}/analysis",
            method="POST",
        )
        second_status, payload = _request_error(
            f"{base_url}/api/radars/latest/events/{event_ids[1]}/analysis",
            method="POST",
        )
        release.set()

    assert first_status == 202
    assert second_status == 409
    assert payload["error"] == "analysis_in_progress"


@contextmanager
def _running_server(snapshot_path):
    server = create_server("127.0.0.1", 0, snapshot_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=2) as response:
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
        assert response.headers["Cache-Control"] == "no-store"
        return json.loads(response.read().decode("utf-8"))


def _get_error(url: str) -> tuple[int, dict[str, object]]:
    with pytest.raises(HTTPError) as caught:
        urlopen(url, timeout=2)
    response = caught.value
    return response.code, json.loads(response.read().decode("utf-8"))


def _request_json(url: str, *, method: str = "GET") -> tuple[int, dict[str, object]]:
    with urlopen(Request(url, method=method), timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _request_error(url: str, *, method: str) -> tuple[int, dict[str, object]]:
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url, method=method), timeout=2)
    return caught.value.code, json.loads(caught.value.read().decode("utf-8"))


def _wait_for_analysis(base_url: str, event_id: str) -> dict[str, object]:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        _, payload = _request_json(
            f"{base_url}/api/radars/latest/events/{event_id}/analysis"
        )
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        sleep(0.01)
    raise AssertionError("event analysis did not finish")


def _write_event_radar(tmp_path) -> tuple[object, str]:
    snapshot_path = tmp_path / "daily-radar.json"
    news = NewsItem(
        "AI 事件",
        "同花顺",
        "https://example.com/event",
        "2026-07-16T11:00:00+08:00",
        "事件正文",
    )
    event = MarketEvent(news.headline, (news,))
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)
    snapshot = build_daily_radar_snapshot(
        (event,),
        (None,),
        (),
        start,
        end,
        all_events=(event,),
        generated_at=end,
    )
    write_daily_radar_snapshot(snapshot, snapshot_path)
    run_id = snapshot["run"]["id"]
    write_event_catalog((event,), run_id, event_catalog_path(snapshot_path, run_id))
    return snapshot_path, snapshot["all_events"][0]["id"]


def _write_two_event_radar(tmp_path) -> tuple[object, list[str]]:
    snapshot_path = tmp_path / "daily-radar.json"
    events = tuple(
        MarketEvent(
            f"事件 {index}",
            (NewsItem(f"事件 {index}", "同花顺", published_at=f"2026-07-16T1{index}:00:00+08:00"),),
        )
        for index in range(2)
    )
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)
    snapshot = build_daily_radar_snapshot(
        events,
        (None, None),
        (),
        start,
        end,
        all_events=events,
        generated_at=end,
    )
    write_daily_radar_snapshot(snapshot, snapshot_path)
    run_id = snapshot["run"]["id"]
    write_event_catalog(events, run_id, event_catalog_path(snapshot_path, run_id))
    return snapshot_path, [event["id"] for event in snapshot["all_events"]]


def _write_pure_price_event_radar(tmp_path) -> tuple[object, str]:
    snapshot_path = tmp_path / "daily-radar.json"
    news = NewsItem(
        "中际旭创盘中涨超10%",
        "同花顺",
        published_at="2026-07-16T11:00:00+08:00",
        body="股价盘中涨超10%，成交额超50亿元。",
    )
    event = MarketEvent(news.headline, (news,))
    start = datetime(2026, 7, 15, 12, tzinfo=SHANGHAI)
    end = datetime(2026, 7, 16, 12, tzinfo=SHANGHAI)
    snapshot = build_daily_radar_snapshot(
        (),
        (),
        (),
        start,
        end,
        all_events=(event,),
        generated_at=end,
    )
    write_daily_radar_snapshot(snapshot, snapshot_path)
    run_id = snapshot["run"]["id"]
    write_event_catalog((event,), run_id, event_catalog_path(snapshot_path, run_id))
    return snapshot_path, snapshot["all_events"][0]["id"]


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": "2.3",
        "run": {
            "id": "20260716T120000+0800",
            "event_catalog_id": "20260716T120000+0800",
            "status": "succeeded",
            "generated_at": "2026-07-16T12:00:00+08:00",
            "window_start": "2026-07-15T12:00:00+08:00",
            "window_end": "2026-07-16T12:00:00+08:00",
            "warnings": [],
            "steps": [],
        },
        "summary": {
            "total_event_count": 0,
            "core_event_count": 0,
            "verified_count": 0,
            "unverified_count": 0,
            "excluded_count": 0,
            "source_count": 0,
            "alert_count": 0,
            "research_candidate_count": 0,
            "critical_event_count": 0,
            "high_event_count": 0,
            "verify_first_count": 0,
            "scoring_version": "1.1",
        },
        "events": [],
        "all_events": [],
        "candidate_groups": {
            "verified": [],
            "unverified": [],
            "excluded": [],
            "watchlist": [],
        },
        "alerts": [],
        "research_candidates": [],
        "validation_tasks": [],
        "disclaimer": "研究辅助，不构成投资建议。",
    }
