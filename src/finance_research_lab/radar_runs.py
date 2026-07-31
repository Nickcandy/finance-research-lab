from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .claim_pipeline import news_content_hash, stable_news_item_id
from .event_sources import SHANGHAI
from .models import NewsItem

RUN_SCHEMA_VERSION = "1.0"
ACTIVE_STATUSES = {"queued", "running"}
RESUMABLE_STATUSES = {"interrupted", "failed"}


class RadarRunStore:
    def __init__(self, snapshot_path: str | Path) -> None:
        self.root = Path(snapshot_path).parent / "radar-runs"
        self.current_path = self.root / "current.json"
        self._lock = Lock()

    def create(self, window_start: datetime, window_end: datetime) -> dict[str, Any]:
        run_id = window_end.strftime("%Y%m%dT%H%M%S%z")
        now = _now()
        payload = {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "queued",
            "stage": "fetch_news",
            "window_start": window_start.isoformat(timespec="seconds"),
            "window_end": window_end.isoformat(timespec="seconds"),
            "started_at": now,
            "updated_at": now,
            "progress": {"completed": 0, "total": 0, "unit": "page"},
            "error": "",
            "claim_statuses": {},
            "active_claim_hashes": [],
            "completed_event_ids": [],
            "partial_events": [],
            "event_resume": {},
        }
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            _write_json(self.checkpoint_path(run_id), payload)
            _write_json(self.current_path, {"run_id": run_id})
        return payload

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            try:
                pointer = _read_json(self.current_path)
                return _read_json(self.checkpoint_path(str(pointer["run_id"])))
            except (FileNotFoundError, KeyError, TypeError, ValueError):
                return None

    def update(self, run_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            payload = _read_json(self.checkpoint_path(run_id))
            payload.update(changes)
            payload["updated_at"] = _now()
            _write_json(self.checkpoint_path(run_id), payload)
            return payload

    def save_input(self, run_id: str, items: tuple[NewsItem, ...]) -> None:
        payload = {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "items": [asdict(item) for item in items],
        }
        with self._lock:
            _write_json(self.input_path(run_id), payload)

    def load_input(self, run_id: str) -> tuple[NewsItem, ...]:
        payload = _read_json(self.input_path(run_id))
        rows = payload.get("items")
        if not isinstance(rows, list):
            raise ValueError("invalid radar run input")
        return tuple(NewsItem(**row) for row in rows if isinstance(row, dict))

    def mark_stale_interrupted(self) -> None:
        current = self.current()
        if current is None or current.get("status") not in ACTIVE_STATUSES:
            return
        self.update(
            str(current["run_id"]),
            status="interrupted",
            error="服务重启，更新已中断，可继续运行。",
            active_claim_hashes=[],
        )

    def public_payload(self, checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
        checkpoint = checkpoint or self.current()
        if checkpoint is None:
            raise FileNotFoundError("radar run not found")
        run_id = str(checkpoint["run_id"])
        try:
            items = self.load_input(run_id)
        except (FileNotFoundError, TypeError, ValueError):
            items = ()
        claim_statuses = checkpoint.get("claim_statuses", {})
        active_hashes = set(checkpoint.get("active_claim_hashes", []))
        news = []
        for item in items:
            content_hash = news_content_hash(item)
            status = claim_statuses.get(content_hash, "pending")
            if checkpoint["status"] == "succeeded" and status == "pending":
                status = "fallback"
            if content_hash in active_hashes:
                status = "running"
            news.append(
                {
                    "item_id": stable_news_item_id(item),
                    "headline": item.headline,
                    "source": item.source,
                    "url": item.url,
                    "published_at": item.published_at,
                    "analysis_status": status,
                }
            )
        status = str(checkpoint["status"])
        return {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "status": status,
            "stage": checkpoint["stage"],
            "window_start": checkpoint["window_start"],
            "window_end": checkpoint["window_end"],
            "started_at": checkpoint["started_at"],
            "updated_at": checkpoint["updated_at"],
            "progress": checkpoint["progress"],
            "error": checkpoint.get("error", ""),
            "resumable": status in RESUMABLE_STATUSES,
            "news": news,
            "partial_events": checkpoint.get("partial_events", []),
        }

    def checkpoint_path(self, run_id: str) -> Path:
        return self.root / run_id / "checkpoint.json"

    def input_path(self, run_id: str) -> Path:
        return self.root / run_id / "input.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version", RUN_SCHEMA_VERSION) != RUN_SCHEMA_VERSION:
        raise ValueError("invalid radar run payload")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")
