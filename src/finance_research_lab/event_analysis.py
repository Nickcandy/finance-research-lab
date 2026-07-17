from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .daily_radar_snapshot import SHANGHAI, build_radar_event_payload
from .models import MarketEvent
from .report import render_research_report

ANALYSIS_SCHEMA_VERSION = "1.0"


class InvalidEventAnalysis(ValueError):
    """Raised when a persisted event analysis is invalid."""


def event_analysis_path(snapshot_path: str | Path, run_id: str, event_id: str) -> Path:
    return Path(snapshot_path).parent / "event-analyses" / run_id / f"{event_id}.json"


def generate_event_analysis(
    event: MarketEvent,
    *,
    run_id: str,
    event_id: str,
    rank: int,
    output_path: str | Path,
    watchlist_path: str | Path,
    a_share_universe_path: str | Path,
    evidence_cache_path: str | Path,
    market_cache_path: str | Path,
) -> dict[str, Any]:
    from .workflow import run_market_event_analysis

    outcome = run_market_event_analysis(
        event,
        watchlist_path=watchlist_path,
        a_share_universe_path=a_share_universe_path,
        evidence_cache_path=evidence_cache_path,
        market_cache_path=market_cache_path,
    )
    return write_successful_event_analysis(
        event,
        outcome.report,
        outcome.steps,
        outcome.warnings,
        run_id=run_id,
        event_id=event_id,
        rank=rank,
        output_path=output_path,
    )


def write_successful_event_analysis(
    event: MarketEvent,
    report: Any,
    steps: Any,
    warnings: Any,
    *,
    run_id: str,
    event_id: str,
    rank: int,
    output_path: str | Path,
) -> dict[str, Any]:
    generated_at = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    payload = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "run_id": run_id,
        "event_id": event_id,
        "status": "succeeded",
        "generated_at": generated_at,
        "event": build_radar_event_payload(
            event,
            report,
            event_id,
            rank,
            steps,
        ),
        "steps": [
            {
                "step_name": step.step_name,
                "tool_name": step.tool_name,
                "status": step.status,
                "summary": step.summary,
            }
            for step in steps
        ],
        "warnings": list(warnings),
        "error": "",
        "markdown": render_research_report(report),
    }
    write_event_analysis(payload, output_path)
    return payload


def write_failed_event_analysis(
    *,
    run_id: str,
    event_id: str,
    error: str,
    output_path: str | Path,
) -> dict[str, Any]:
    payload = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "run_id": run_id,
        "event_id": event_id,
        "status": "failed",
        "generated_at": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
        "event": None,
        "steps": [],
        "warnings": [],
        "error": error,
        "markdown": "",
    }
    write_event_analysis(payload, output_path)
    return payload


def write_event_analysis(payload: dict[str, Any], path: str | Path) -> Path:
    validate_event_analysis(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
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
    return target


def read_event_analysis(
    path: str | Path,
    *,
    run_id: str,
    event_id: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidEventAnalysis(f"invalid event analysis JSON: {exc}") from exc
    payload = validate_event_analysis(payload)
    if payload["run_id"] != run_id or payload["event_id"] != event_id:
        raise InvalidEventAnalysis("event analysis identity mismatch")
    return payload


def validate_event_analysis(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise InvalidEventAnalysis("unsupported event analysis schema")
    if payload.get("status") not in {"succeeded", "failed"}:
        raise InvalidEventAnalysis("invalid event analysis status")
    for field in ("run_id", "event_id", "generated_at", "error", "markdown"):
        if not isinstance(payload.get(field), str):
            raise InvalidEventAnalysis(f"invalid event analysis {field}")
    if not isinstance(payload.get("steps"), list) or not isinstance(payload.get("warnings"), list):
        raise InvalidEventAnalysis("invalid event analysis steps or warnings")
    if payload["status"] == "succeeded" and not isinstance(payload.get("event"), dict):
        raise InvalidEventAnalysis("successful event analysis requires event")
    return payload
