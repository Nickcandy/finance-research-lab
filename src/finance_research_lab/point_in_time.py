from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from .claim_pipeline import stable_news_item_id
from .claims import Claim
from .daily_radar_snapshot import market_event_id
from .evidence_ledger import build_evidence_ledgers
from .impact_assessment import ImpactAssessment, SCORING_VERSION
from .impact_features import build_impact_assessments
from .models import AShareCompany, MarketEvent

PIT_SCHEMA_VERSION = "1.0"


class ImmutablePointInTimeError(RuntimeError):
    pass


class RoutedAnalysis(Protocol):
    event: MarketEvent
    assessments: tuple[ImpactAssessment, ...]
    fallback: str
    warnings: tuple[str, ...]

    @property
    def route(self) -> Any:
        ...


def point_in_time_path(
    snapshot_path: str | Path,
    run_id: str,
    scoring_version: str,
) -> Path:
    _validate_path_part(run_id, "run_id")
    _validate_path_part(scoring_version, "scoring_version")
    return (
        Path(snapshot_path).parent
        / "point-in-time"
        / run_id
        / f"scoring-{scoring_version}.json"
    )


def build_point_in_time_payload(
    *,
    run_id: str,
    generated_at: str,
    events: Sequence[MarketEvent],
    claims: Sequence[Claim],
    routed_analyses: Sequence[RoutedAnalysis],
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    claims_by_event: dict[str, list[Claim]] = {}
    for claim in claims:
        claims_by_event.setdefault(claim.event_id, []).append(claim)
    routed_by_event = {
        market_event_id(routed.event): routed for routed in routed_analyses
    }
    event_rows = []
    signal_rows = []
    for event in events:
        event_id = market_event_id(event)
        routed = routed_by_event.get(event_id)
        event_claims = claims_by_event.get(event_id, [])
        event_rows.append(
            {
                "event_id": event_id,
                "news_item_ids": [
                    stable_news_item_id(item) for item in event.items
                ],
                "claim_ids": [claim.id for claim in event_claims],
                "analysis_tier": (
                    routed.route.analysis_tier
                    if routed is not None
                    else "deterministic"
                ),
                "priority_level": (
                    routed.route.priority_level if routed is not None else "low"
                ),
                "fallback": routed.fallback if routed is not None else "",
                "warnings": list(routed.warnings) if routed is not None else [],
            }
        )
        if routed is not None:
            signal_rows.extend(
                _signal_payload(assessment) for assessment in routed.assessments
            )
    claim_rows = [_json_value(asdict(claim)) for claim in claims]
    return {
        "schema_version": PIT_SCHEMA_VERSION,
        "run_id": run_id,
        "scoring_version": SCORING_VERSION,
        "generated_at": generated_at,
        "events": event_rows,
        "claims": claim_rows,
        "signals": signal_rows,
        "event_catalog_path": f"event-catalogs/{run_id}.json",
        "snapshot": snapshot or {},
        "result_labels_path": (
            f"point-in-time/{run_id}/result-labels.json"
        ),
    }


def write_point_in_time(payload: dict[str, Any], path: str | Path) -> Path:
    validate_point_in_time(payload)
    target = Path(path)
    expected = point_in_time_path(
        target.parents[2] / "daily-radar.json",
        payload["run_id"],
        payload["scoring_version"],
    )
    if target != expected:
        raise ValueError("point-in-time path identity mismatch")
    encoded = _encoded(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == encoded:
            return target
        raise ImmutablePointInTimeError(
            "point-in-time file already exists with different content"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ImmutablePointInTimeError(
                    "point-in-time file already exists with different content"
                )
    finally:
        temporary.unlink(missing_ok=True)
    return target


def read_point_in_time(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid point-in-time JSON: {exc}") from exc
    return validate_point_in_time(payload)


def validate_point_in_time(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("point-in-time payload must be an object")
    if payload.get("schema_version") != PIT_SCHEMA_VERSION:
        raise ValueError("unsupported point-in-time schema")
    for field in (
        "run_id",
        "scoring_version",
        "generated_at",
        "result_labels_path",
        "event_catalog_path",
    ):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"invalid point-in-time {field}")
    for field in ("events", "claims", "signals"):
        if not isinstance(payload.get(field), list):
            raise ValueError(f"invalid point-in-time {field}")
    if not isinstance(payload.get("snapshot"), dict):
        raise ValueError("invalid point-in-time snapshot")
    run_id = payload["run_id"]
    scoring_version = payload["scoring_version"]
    if payload["event_catalog_path"] != f"event-catalogs/{run_id}.json":
        raise ValueError("point-in-time event catalog identity mismatch")
    if payload["result_labels_path"] != (
        f"point-in-time/{run_id}/result-labels.json"
    ):
        raise ValueError("point-in-time result labels identity mismatch")
    snapshot = payload["snapshot"]
    if snapshot and (
        snapshot.get("run", {}).get("id") != run_id
        or snapshot.get("summary", {}).get("scoring_version")
        != scoring_version
    ):
        raise ValueError("point-in-time snapshot identity mismatch")
    for index, signal in enumerate(payload["signals"]):
        _validate_signal(signal, index, scoring_version)
    return payload


def replay_point_in_time_scoring(
    events: Sequence[MarketEvent],
    claims: Sequence[Claim],
    a_share_universe: Sequence[AShareCompany],
    *,
    watchlist_symbols: Sequence[str] = (),
) -> tuple[ImpactAssessment, ...]:
    ledgers = build_evidence_ledgers(
        events,
        claims,
        a_share_universe,
        watchlist_symbols=watchlist_symbols,
    )
    return build_impact_assessments(events, ledgers, a_share_universe)


def _signal_payload(assessment: ImpactAssessment) -> dict[str, Any]:
    return {
        "event_id": assessment.event_id,
        "symbol": assessment.symbol,
        "event_importance": assessment.event_importance,
        "positive_magnitude": assessment.positive_magnitude,
        "negative_magnitude": assessment.negative_magnitude,
        "direction": assessment.direction,
        "confidence": assessment.confidence,
        "conflict_score": assessment.conflict_score,
        "priority_level": assessment.priority_level,
        "analysis_tier": assessment.analysis_tier,
        "feature_breakdown": {
            "event": _json_value(asdict(assessment.event_features)),
            "positive": _json_value(asdict(assessment.positive_features))
            if assessment.positive_features is not None
            else {},
            "negative": _json_value(asdict(assessment.negative_features))
            if assessment.negative_features is not None
            else {},
            "confidence": _json_value(asdict(assessment.confidence_features)),
        },
        "reason_codes": list(assessment.reason_codes),
        "scoring_version": assessment.scoring_version,
    }


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _encoded(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _validate_signal(
    signal: object,
    index: int,
    scoring_version: str,
) -> None:
    if not isinstance(signal, dict):
        raise ValueError(f"invalid point-in-time signals.{index}")
    for field in (
        "event_importance",
        "positive_magnitude",
        "negative_magnitude",
        "confidence",
        "conflict_score",
    ):
        value = signal.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"invalid point-in-time signals.{index}.{field}")
    if signal.get("scoring_version") != scoring_version:
        raise ValueError(f"invalid point-in-time signals.{index}.scoring_version")
    if signal.get("priority_level") not in {
        "critical",
        "verify_first",
        "high",
        "medium",
        "low",
    }:
        raise ValueError(f"invalid point-in-time signals.{index}.priority_level")


def _validate_path_part(value: str, field: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"invalid {field}")
