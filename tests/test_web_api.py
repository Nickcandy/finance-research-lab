from __future__ import annotations

import json
from contextlib import contextmanager
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from finance_research_lab.web_api import create_server


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


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run": {
            "id": "20260716T120000+0800",
            "status": "succeeded",
            "generated_at": "2026-07-16T12:00:00+08:00",
            "window_start": "2026-07-15T12:00:00+08:00",
            "window_end": "2026-07-16T12:00:00+08:00",
            "warnings": [],
            "steps": [],
        },
        "summary": {
            "event_count": 0,
            "verified_count": 0,
            "unverified_count": 0,
            "excluded_count": 0,
            "source_count": 0,
        },
        "events": [],
        "candidate_groups": {
            "verified": [],
            "unverified": [],
            "excluded": [],
            "watchlist": [],
        },
        "validation_tasks": [],
        "disclaimer": "研究辅助，不构成投资建议。",
    }
