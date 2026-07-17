from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from .daily_radar_snapshot import market_event_id
from .models import MarketEvent, NewsItem

CATALOG_SCHEMA_VERSION = "1.0"


class InvalidEventCatalog(ValueError):
    """Raised when an event catalog cannot be used for analysis."""


def event_catalog_path(snapshot_path: str | Path, run_id: str) -> Path:
    return Path(snapshot_path).parent / "event-catalogs" / f"{run_id}.json"


def write_event_catalog(
    events: Sequence[MarketEvent],
    run_id: str,
    path: str | Path,
) -> Path:
    payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "run_id": run_id,
        "events": [
            {
                "id": market_event_id(event),
                "title": event.title,
                "items": [asdict(item) for item in event.items],
            }
            for event in events
        ],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(payload, target)
    return target


def read_event_catalog(path: str | Path, expected_run_id: str) -> dict[str, MarketEvent]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidEventCatalog(f"invalid event catalog JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise InvalidEventCatalog("unsupported event catalog schema")
    if payload.get("run_id") != expected_run_id:
        raise InvalidEventCatalog("event catalog run_id does not match radar")
    rows = payload.get("events")
    if not isinstance(rows, list):
        raise InvalidEventCatalog("invalid event catalog events")

    events: dict[str, MarketEvent] = {}
    try:
        for row in rows:
            items = tuple(NewsItem(**item) for item in row["items"])
            event = MarketEvent(row["title"], items)
            event_id = row["id"]
            if not items or event_id != market_event_id(event) or event_id in events:
                raise InvalidEventCatalog("invalid or duplicate event catalog id")
            events[event_id] = event
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, InvalidEventCatalog):
            raise
        raise InvalidEventCatalog(f"invalid event catalog entry: {exc}") from exc
    return events


def _atomic_write_json(payload: dict[str, Any], target: Path) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
