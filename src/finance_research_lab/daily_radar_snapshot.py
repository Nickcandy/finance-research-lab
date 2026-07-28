from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from .agent_models import AgentStep
from .event_eligibility import market_event_exclusion_reason
from .impact_scoring import (
    combine_impact_directions,
    stock_impact_score,
    strongest_confidence,
    summarize_event_impact,
)
from .impact_assessment import FeatureScore, ImpactAssessment, SCORING_VERSION
from .impact_horizon import DirectionalHorizons, ImpactHorizon
from .models import MarketEvent, NewsItem, ResearchReport, StockImpact

SCHEMA_VERSION = "2.3"
DISCLAIMER = "研究辅助，不构成投资建议。"
SHANGHAI = ZoneInfo("Asia/Shanghai")
_STRENGTH_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "unknown"}
_CONFIDENCES = {"high", "medium", "low", "unknown"}
_ANALYSIS_TIERS = {"pro", "flash", "deterministic", "not_applicable"}
_PRIORITY_LEVELS = {"critical", "verify_first", "high", "medium", "low"}
_IMPORTANCE_LEVELS = {"high", "medium", "low"}


class InvalidRadarSnapshot(ValueError):
    """Raised when a persisted frontend snapshot violates the v2.3 contract."""


class RoutedAnalysis(Protocol):
    event: MarketEvent
    assessments: tuple[ImpactAssessment, ...]
    fallback: str
    warnings: tuple[str, ...]
    brief: Any
    report: ResearchReport | None

    @property
    def route(self) -> Any: ...


@dataclass(frozen=True)
class _ImpactContext:
    event_id: str
    event_title: str
    source_count: int
    latest_published_at: str
    impact: StockImpact
    news_items: tuple[NewsItem, ...]


def build_daily_radar_snapshot(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    steps: Sequence[AgentStep],
    window_start: datetime,
    window_end: datetime,
    *,
    all_events: Sequence[MarketEvent] | None = None,
    generated_at: datetime | None = None,
    routed_analyses: Sequence[RoutedAnalysis] = (),
) -> dict[str, Any]:
    """Build the explicit, versioned JSON contract consumed by the local web UI."""

    if len(events) != len(reports):
        raise ValueError("reports must align with events")
    if any(not event.items for event in events):
        raise ValueError("MarketEvent items must not be empty")
    all_events = tuple(all_events if all_events is not None else events)
    if any(not event.items for event in all_events):
        raise ValueError("MarketEvent items must not be empty")

    window_start = _shanghai_time(window_start)
    window_end = _shanghai_time(window_end)
    if window_start >= window_end:
        raise ValueError("window_start must be earlier than window_end")
    generated_at = _shanghai_time(generated_at or datetime.now(SHANGHAI))

    event_ids = [market_event_id(event) for event in events]
    routed_by_event = {market_event_id(routed.event): routed for routed in routed_analyses}
    event_payloads = [
        _event_payload(
            event,
            report,
            event_ids[index],
            index + 1,
            steps,
            routed_by_event.get(event_ids[index]),
        )
        for index, (event, report) in enumerate(zip(events, reports))
    ]
    event_payload_by_id = {payload["id"]: payload for payload in event_payloads}
    candidate_groups = _candidate_groups(events, reports, event_ids)
    _attach_assessment_fields(candidate_groups, routed_analyses)
    if routed_analyses:
        alerts = _watchlist_alerts(
            routed_analyses,
            reports,
            event_ids,
            generated_at,
        )
        research_candidates = _research_candidates(candidate_groups)
    else:
        alerts = _legacy_watchlist_alerts(events, reports, event_ids, generated_at)
        research_candidates = _legacy_research_candidates(
            events,
            reports,
            event_ids,
        )
    validation_tasks = _validation_tasks(reports, event_ids)
    warnings = _unique(
        [
            *(warning for step in steps for warning in _step_warnings(step)),
            *(
                warning
                for routed in routed_analyses
                for warning in routed.warnings
            ),
        ]
    )
    source_count = len(
        {
            (item.source_type, item.source.strip() or item.source_type)
            for event in all_events
            for item in event.items
        }
    )
    analyzed_status = {
        event_id: "succeeded" if report is not None else "failed"
        for event_id, report in zip(event_ids, reports)
    }
    all_event_payloads = [
        _event_summary_payload(
            event,
            market_event_id(event),
            index + 1,
            (
                "not_applicable"
                if market_event_exclusion_reason(event)
                else analyzed_status.get(market_event_id(event), "not_started")
            ),
            related_stocks=_related_stock_bindings(
                event_payload_by_id.get(market_event_id(event), {}).get("candidates", [])
            ),
        )
        for index, event in enumerate(all_events)
    ]
    run_id = generated_at.strftime("%Y%m%dT%H%M%S%z")

    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "id": run_id,
            "event_catalog_id": run_id,
            "status": "succeeded",
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "window_start": window_start.isoformat(timespec="seconds"),
            "window_end": window_end.isoformat(timespec="seconds"),
            "warnings": warnings,
            "steps": [
                {
                    "step_name": step.step_name,
                    "tool_name": step.tool_name,
                    "status": step.status,
                    "summary": step.summary,
                }
                for step in steps
            ],
        },
        "summary": {
            "total_event_count": len(all_events),
            "core_event_count": len(events),
            "verified_count": len(candidate_groups["verified"]),
            "unverified_count": len(candidate_groups["unverified"]),
            "excluded_count": len(candidate_groups["excluded"]),
            "source_count": source_count,
            "alert_count": len(alerts),
            "research_candidate_count": len(research_candidates),
            "critical_event_count": sum(
                routed.route.priority_level == "critical" for routed in routed_analyses
            ),
            "high_event_count": sum(
                routed.route.priority_level == "high" for routed in routed_analyses
            ),
            "verify_first_count": sum(
                routed.route.priority_level == "verify_first" for routed in routed_analyses
            ),
            "scoring_version": SCORING_VERSION,
        },
        "events": event_payloads,
        "all_events": all_event_payloads,
        "candidate_groups": candidate_groups,
        "alerts": alerts,
        "research_candidates": research_candidates,
        "validation_tasks": validation_tasks,
        "disclaimer": DISCLAIMER,
    }


def write_daily_radar_snapshot(payload: dict[str, Any], path: str | Path) -> Path:
    """Validate and atomically replace the latest successful JSON snapshot."""

    validate_daily_radar_snapshot(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def read_daily_radar_snapshot(path: str | Path) -> dict[str, Any]:
    """Read and validate a persisted DailyRadarSnapshot v2."""

    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidRadarSnapshot(f"invalid JSON snapshot: {exc}") from exc
    return validate_daily_radar_snapshot(payload)


def validate_daily_radar_snapshot(payload: object) -> dict[str, Any]:
    """Validate the stable top-level v2 contract without exposing internal models."""

    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot("snapshot must be a JSON object")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise InvalidRadarSnapshot(f"unsupported schema_version: {version!r}")
    required_types = {
        "run": dict,
        "summary": dict,
        "events": list,
        "all_events": list,
        "candidate_groups": dict,
        "alerts": list,
        "research_candidates": list,
        "validation_tasks": list,
        "disclaimer": str,
    }
    for field, expected_type in required_types.items():
        if not isinstance(payload.get(field), expected_type):
            raise InvalidRadarSnapshot(f"invalid {field} field")

    run = payload["run"]
    for field in (
        "id",
        "event_catalog_id",
        "status",
        "generated_at",
        "window_start",
        "window_end",
        "warnings",
        "steps",
    ):
        if field not in run:
            raise InvalidRadarSnapshot(f"missing run.{field}")
    if run["status"] != "succeeded":
        raise InvalidRadarSnapshot("latest snapshot must represent a succeeded run")
    if not isinstance(run["warnings"], list) or not isinstance(run["steps"], list):
        raise InvalidRadarSnapshot("invalid run warnings or steps")

    groups = payload["candidate_groups"]
    for name in ("verified", "unverified", "excluded", "watchlist"):
        if not isinstance(groups.get(name), list):
            raise InvalidRadarSnapshot(f"invalid candidate_groups.{name}")
    summary = payload["summary"]
    for name in (
        "total_event_count",
        "core_event_count",
        "alert_count",
        "research_candidate_count",
        "critical_event_count",
        "high_event_count",
        "verify_first_count",
    ):
        if isinstance(summary.get(name), bool) or not isinstance(summary.get(name), int):
            raise InvalidRadarSnapshot(f"invalid summary.{name}")
    if summary.get("scoring_version") != SCORING_VERSION:
        raise InvalidRadarSnapshot("invalid summary.scoring_version")
    for index, event in enumerate(payload["events"]):
        if not isinstance(event, dict):
            raise InvalidRadarSnapshot(f"invalid events.{index}")
        validate_radar_event_payload(event, f"events.{index}")
    for group_name in ("verified", "unverified", "excluded", "watchlist"):
        for index, candidate in enumerate(groups[group_name]):
            _validate_scored_candidate(
                candidate,
                f"candidate_groups.{group_name}.{index}",
            )
    for index, candidate in enumerate(payload["research_candidates"]):
        _validate_impact_fields(candidate, f"research_candidates.{index}")
    for index, alert in enumerate(payload["alerts"]):
        _validate_alert(alert, f"alerts.{index}")
    for index, event in enumerate(payload["all_events"]):
        if not isinstance(event, dict):
            raise InvalidRadarSnapshot(f"invalid all_events.{index}")
        if event.get("analysis_status") not in {
            "succeeded",
            "failed",
            "not_started",
            "queued",
            "running",
            "not_applicable",
        }:
            raise InvalidRadarSnapshot(f"invalid all_events.{index}.analysis_status")
        if event.get("exclusion_reason") not in {"", "pure_stock_price_update"}:
            raise InvalidRadarSnapshot(f"invalid all_events.{index}.exclusion_reason")
    return payload


def validate_radar_event_payload(
    payload: object,
    path: str = "event",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    _validate_scored_event(payload, path)
    if not isinstance(payload.get("candidates"), list):
        raise InvalidRadarSnapshot(f"invalid {path}.candidates")
    for index, candidate in enumerate(payload["candidates"]):
        _validate_impact_fields(candidate, f"{path}.candidates.{index}")
    return payload


def _validate_scored_event(payload: dict[str, Any], path: str) -> None:
    _score_0_to_100(payload.get("event_importance"), f"{path}.event_importance")
    _score_0_to_100(payload.get("confidence"), f"{path}.confidence")
    if payload.get("importance_level") not in _IMPORTANCE_LEVELS:
        raise InvalidRadarSnapshot(f"invalid {path}.importance_level")
    if payload.get("analysis_tier") not in _ANALYSIS_TIERS:
        raise InvalidRadarSnapshot(f"invalid {path}.analysis_tier")
    if not isinstance(payload.get("reason_codes"), list):
        raise InvalidRadarSnapshot(f"invalid {path}.reason_codes")
    if payload.get("overall_direction") not in _IMPACT_DIRECTIONS:
        raise InvalidRadarSnapshot(f"invalid {path}.overall_direction")


def _validate_scored_candidate(payload: object, path: str) -> None:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    for field in (
        "positive_magnitude",
        "negative_magnitude",
        "confidence",
        "conflict_score",
    ):
        _score_0_to_100(payload.get(field), f"{path}.{field}")
    if payload.get("priority_level") not in _PRIORITY_LEVELS:
        raise InvalidRadarSnapshot(f"invalid {path}.priority_level")
    if payload.get("analysis_tier") not in _ANALYSIS_TIERS:
        raise InvalidRadarSnapshot(f"invalid {path}.analysis_tier")
    if not isinstance(payload.get("feature_breakdown"), dict):
        raise InvalidRadarSnapshot(f"invalid {path}.feature_breakdown")
    if not isinstance(payload.get("reason_codes"), list):
        raise InvalidRadarSnapshot(f"invalid {path}.reason_codes")
    _validate_directional_horizon_field(payload, "positive_horizon", path)
    _validate_directional_horizon_field(payload, "negative_horizon", path)


def _score_0_to_100(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise InvalidRadarSnapshot(f"invalid {path}")


def _validate_impact_fields(
    payload: object,
    path: str,
    *,
    direction_field: str = "impact_direction",
) -> None:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    if payload.get(direction_field) not in _IMPACT_DIRECTIONS:
        raise InvalidRadarSnapshot(f"invalid {path}.{direction_field}")
    score = payload.get("impact_score")
    if score is not None and (
        not isinstance(score, int) or isinstance(score, bool) or not -100 <= score <= 100
    ):
        raise InvalidRadarSnapshot(f"invalid {path}.impact_score")
    if payload.get("confidence") not in _CONFIDENCES:
        raise InvalidRadarSnapshot(f"invalid {path}.confidence")
    _validate_directional_horizon_field(payload, "positive_horizon", path)
    _validate_directional_horizon_field(payload, "negative_horizon", path)


def _validate_alert(payload: object, path: str) -> None:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    if payload.get("direction") not in {"negative", "mixed"}:
        raise InvalidRadarSnapshot(f"invalid {path}.direction")
    score = payload.get("impact_score")
    if score is not None and (
        not isinstance(score, int) or isinstance(score, bool) or not -100 <= score <= 100
    ):
        raise InvalidRadarSnapshot(f"invalid {path}.impact_score")
    if payload.get("confidence") not in _CONFIDENCES:
        raise InvalidRadarSnapshot(f"invalid {path}.confidence")
    if payload.get("severity") not in {"high", "medium"}:
        raise InvalidRadarSnapshot(f"invalid {path}.severity")
    _validate_directional_horizon_field(payload, "negative_horizon", path)


def _validate_directional_horizon_field(
    payload: dict[str, Any],
    field: str,
    path: str,
) -> None:
    if field not in payload:
        raise InvalidRadarSnapshot(f"missing {path}.{field}")
    value = payload[field]
    if value is None:
        return
    if not isinstance(value, dict):
        raise InvalidRadarSnapshot(f"invalid {path}.{field}")
    validate_directional_horizon_payload(value, f"{path}.{field}")


def validate_directional_horizon_payload(payload: object, path: str) -> None:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    for layer in ("market", "fundamental"):
        _validate_horizon(payload.get(layer), f"{path}.{layer}")


def _validate_horizon(payload: object, path: str) -> None:
    if not isinstance(payload, dict):
        raise InvalidRadarSnapshot(f"invalid {path}")
    category = payload.get("category")
    if category not in {
        "immediate",
        "short",
        "medium",
        "long",
        "structural",
        "unknown",
    }:
        raise InvalidRadarSnapshot(f"invalid {path}.category")
    unit = payload.get("unit")
    if unit not in {"trading_day", "calendar_month", "unknown"}:
        raise InvalidRadarSnapshot(f"invalid {path}.unit")
    minimum = payload.get("min_duration")
    maximum = payload.get("max_duration")
    if category == "unknown":
        if minimum is not None or maximum is not None or unit != "unknown":
            raise InvalidRadarSnapshot(f"invalid {path} unknown duration")
    else:
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 0
            or unit == "unknown"
        ):
            raise InvalidRadarSnapshot(f"invalid {path}.min_duration")
        if maximum is not None and (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum < minimum
        ):
            raise InvalidRadarSnapshot(f"invalid {path}.max_duration")
    if payload.get("confidence") not in _CONFIDENCES:
        raise InvalidRadarSnapshot(f"invalid {path}.confidence")
    for field in ("basis", "evidence_refs", "invalidation_conditions"):
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise InvalidRadarSnapshot(f"invalid {path}.{field}")


def _event_summary_payload(
    event: MarketEvent,
    event_id: str,
    rank: int,
    analysis_status: str,
    *,
    related_stocks: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    exclusion_reason = market_event_exclusion_reason(event)
    sources: list[dict[str, str]] = []
    seen_sources: set[tuple[str, str]] = set()
    for item in event.items:
        name = item.source.strip() or item.source_type
        key = (item.source_type, name)
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append({"source_type": item.source_type, "name": name})
    return {
        "id": event_id,
        "rank": rank,
        "title": event.title,
        "latest_published_at": event.items[0].published_at,
        "report_count": len(event.items),
        "source_count": len(sources),
        "sources": sources,
        "source_urls": list(event.source_urls),
        "items": [
            {
                "headline": item.headline,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
                "source_type": item.source_type,
            }
            for item in event.items
        ],
        "analysis_status": analysis_status,
        "exclusion_reason": exclusion_reason,
        "related_stocks": list(related_stocks),
    }


def _related_stock_bindings(candidates: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    bindings = []
    for candidate in candidates:
        reason_codes = candidate.get("reason_codes", [])
        if "directness:explicit_company" in reason_codes:
            relation_type = "explicit_company"
        elif candidate.get("verification_status") == "verified":
            relation_type = "value_chain"
        else:
            relation_type = "unverified"
        bindings.append(
            {
                "symbol": candidate["symbol"],
                "name": candidate["name"],
                "relation_type": relation_type,
                "verification_status": candidate["verification_status"],
                "watchlist_hit": candidate.get("watchlist_hit", False),
                "reasoning": candidate.get("reasoning", ""),
                "evidence": candidate.get("evidence", []),
                "claim_ids": candidate.get("claim_ids", []),
                "source_item_ids": candidate.get("source_item_ids", []),
                "news_links": candidate.get("news_links", []),
            }
        )
    return bindings


def _event_payload(
    event: MarketEvent,
    report: ResearchReport | None,
    event_id: str,
    rank: int,
    steps: Sequence[AgentStep],
    routed: RoutedAnalysis | None = None,
) -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    seen_sources: set[tuple[str, str]] = set()
    for item in event.items:
        name = item.source.strip() or item.source_type
        key = (item.source_type, name)
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append({"source_type": item.source_type, "name": name})

    warnings = _unique(
        warning
        for step in steps
        if step.step_name.endswith(f":{rank}")
        for warning in _step_warnings(step)
    )
    if report is None and routed is None:
        warnings = _unique([*warnings, "事件分析失败，详见运行步骤。"])
        event_type = "待判断"
        themes: list[str] = []
        key_facts: list[str] = []
        report_confidence = "low"
        overall_direction = "unknown"
        impact_score = None
        reasoning = ""
        value_chain = {
            "payer": "",
            "receiver": "",
            "chain_steps": [],
            "direction": "unknown",
            "reasoning": "",
            "demand_driver": "",
            "bottleneck": "",
            "supporting_evidence": [],
            "counter_evidence": [],
            "downgrade_conditions": [],
        }
        candidates: list[dict[str, Any]] = []
    else:
        brief = getattr(routed, "brief", None) if routed is not None else None
        impact_summary = summarize_event_impact(report) if report is not None else None
        event_type = brief.event_type if brief is not None else report.event.event_type
        themes = list(brief.themes if brief is not None else report.event.themes)
        key_facts = list(brief.key_facts if brief is not None else report.event.key_facts)
        report_confidence = report.event.confidence if report is not None else "low"
        overall_direction, impact_score = _event_assessment_impact(
            routed.assessments if routed is not None else ()
        )
        if routed is None and impact_summary is not None:
            overall_direction = impact_summary.direction
            impact_score = impact_summary.score
        reasoning = brief.reasoning if brief is not None else report.event.reasoning
        chain = brief.value_chain if brief is not None else report.value_chain
        value_chain = {
            "payer": chain.payer,
            "receiver": chain.receiver,
            "chain_steps": list(chain.chain_steps),
            "direction": chain.impact_direction,
            "reasoning": chain.reasoning,
            "demand_driver": chain.demand_driver,
            "bottleneck": chain.bottleneck,
            "supporting_evidence": list(chain.supporting_evidence),
            "counter_evidence": list(chain.counter_evidence),
            "downgrade_conditions": list(chain.downgrade_conditions),
        }
        candidates = _event_candidates(report, routed, event_id, event.items)

    assessments = routed.assessments if routed is not None else ()
    _attach_candidate_horizons(candidates, assessments)
    event_importance = max(
        (assessment.event_importance for assessment in assessments),
        default=0,
    )
    confidence = max(
        (assessment.confidence for assessment in assessments),
        default=0,
    )
    analysis_tier = routed.route.analysis_tier if routed is not None else "deterministic"
    reason_codes = (
        list(routed.route.reason_codes)
        if routed is not None
        else ["route:deterministic", "route:missing_assessment"]
    )
    routed_warnings = list(routed.warnings) if routed is not None else []
    return {
        "id": event_id,
        "rank": rank,
        "title": event.title,
        "latest_published_at": event.items[0].published_at,
        "report_count": len(event.items),
        "source_count": len(sources),
        "sources": sources,
        "source_urls": list(event.source_urls),
        "event_type": event_type,
        "themes": themes,
        "key_facts": key_facts,
        "confidence": confidence,
        "report_confidence": report_confidence,
        "overall_direction": overall_direction,
        "impact_score": impact_score,
        "reasoning": reasoning,
        "value_chain": value_chain,
        "candidates": candidates,
        "analysis_status": "succeeded" if report is not None else "failed",
        "warnings": _unique([*warnings, *routed_warnings]),
        "event_importance": event_importance,
        "importance_level": _importance_level(event_importance),
        "analysis_tier": analysis_tier,
        "reason_codes": reason_codes,
    }


def build_radar_event_payload(
    event: MarketEvent,
    report: ResearchReport,
    event_id: str,
    rank: int,
    steps: Sequence[AgentStep],
    assessments: Sequence[ImpactAssessment] = (),
) -> dict[str, Any]:
    """Build one analyzed event using the frontend event contract."""

    payload = _event_payload(event, report, event_id, rank, steps)
    _attach_candidate_horizons(payload["candidates"], assessments)
    return payload


def _candidate_groups(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[_ImpactContext]] = {}
    for event, report, event_id in zip(events, reports, event_ids):
        if report is None:
            continue
        for impact in report.stock_impacts:
            if impact.market != "A股":
                continue
            grouped.setdefault(impact.symbol, []).append(
                _ImpactContext(
                    event_id,
                    event.title,
                    len(
                        {
                            (item.source_type, item.source.strip() or item.source_type)
                            for item in event.items
                        }
                    ),
                    event.items[0].published_at,
                    impact,
                    tuple(event.items),
                )
            )

    result: dict[str, list[dict[str, Any]]] = {
        "verified": [],
        "unverified": [],
        "excluded": [],
        "watchlist": [],
    }
    for contexts in grouped.values():
        payload, status = _aggregate_candidate(contexts)
        result[status].append(payload)
        if payload["watchlist_hit"]:
            result["watchlist"].append(payload)
    return result


def _attach_assessment_fields(
    groups: dict[str, list[dict[str, Any]]],
    routed_analyses: Sequence[RoutedAnalysis],
) -> None:
    assessments_by_symbol: dict[str, list[ImpactAssessment]] = {}
    for routed in routed_analyses:
        for assessment in routed.assessments:
            if assessment.symbol:
                assessments_by_symbol.setdefault(assessment.symbol, []).append(assessment)
    tier_order = {"pro": 0, "flash": 1, "deterministic": 2, "not_applicable": 3}
    priority_order = {
        "critical": 0,
        "verify_first": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }
    seen_payloads: set[int] = set()
    for candidates in groups.values():
        for candidate in candidates:
            if id(candidate) in seen_payloads:
                continue
            seen_payloads.add(id(candidate))
            assessments = tuple(assessments_by_symbol.get(candidate["symbol"], ()))
            if not assessments:
                candidate.update(
                    {
                        "positive_magnitude": 0,
                        "negative_magnitude": 0,
                        "confidence": 0,
                        "conflict_score": 0,
                        "priority_level": "low",
                        "analysis_tier": "deterministic",
                        "feature_breakdown": {},
                        "reason_codes": ["assessment:missing"],
                        "score_status": "insufficient_evidence",
                        "positive_horizon": None,
                        "negative_horizon": None,
                    }
                )
                continue
            positive = max(
                assessments,
                key=lambda assessment: assessment.positive_magnitude,
            )
            negative = max(
                assessments,
                key=lambda assessment: assessment.negative_magnitude,
            )
            confidence = max(
                assessments,
                key=lambda assessment: assessment.confidence,
            )
            strongest_priority = min(
                assessments,
                key=lambda assessment: priority_order[assessment.priority_level],
            )
            strongest_tier = min(
                assessments,
                key=lambda assessment: tier_order[assessment.analysis_tier],
            )
            candidate.update(
                {
                    "positive_magnitude": positive.positive_magnitude,
                    "negative_magnitude": negative.negative_magnitude,
                    "confidence": confidence.confidence,
                    "conflict_score": max(assessment.conflict_score for assessment in assessments),
                    "priority_level": strongest_priority.priority_level,
                    "analysis_tier": strongest_tier.analysis_tier,
                    "feature_breakdown": {
                        "positive": _stock_feature_payload(positive.positive_features),
                        "negative": _stock_feature_payload(negative.negative_features),
                        "confidence": _confidence_feature_payload(confidence),
                    },
                    "reason_codes": _unique(
                        reason for assessment in assessments for reason in assessment.reason_codes
                    ),
                    "score_status": (
                        "scored"
                        if any(_assessment_score_eligible(item) for item in assessments)
                        else "insufficient_evidence"
                    ),
                    "positive_horizon": _directional_horizon_payload(
                        positive.positive_horizon
                    ),
                    "negative_horizon": _directional_horizon_payload(
                        negative.negative_horizon
                    ),
                }
            )
            direction = combine_impact_directions(
                assessment.direction for assessment in assessments
            )
            candidate["impact_direction"] = direction
            candidate["impact_score"] = _signed_score(
                direction,
                positive.positive_magnitude,
                negative.negative_magnitude,
            )


def _stock_feature_payload(features: Any) -> dict[str, Any]:
    if features is None:
        return {}
    return {
        name: _feature_score_payload(getattr(features, name))
        for name in (
            "directness",
            "exposure",
            "economic_scale",
            "duration",
            "sensitivity",
        )
    }


def _confidence_feature_payload(
    assessment: ImpactAssessment,
) -> dict[str, Any]:
    return {
        name: _feature_score_payload(getattr(assessment.confidence_features, name))
        for name in (
            "source_quality",
            "corroboration",
            "identity_verification",
            "quantitative_completeness",
            "consistency",
        )
    }


def _feature_score_payload(feature: FeatureScore) -> dict[str, Any]:
    return {
        "value": feature.value,
        "reason_codes": list(feature.reason_codes),
        "evidence_refs": list(feature.evidence_refs),
    }


def _importance_level(value: int) -> str:
    if value >= 75:
        return "high"
    if value >= 50:
        return "medium"
    return "low"


def _event_assessment_impact(
    assessments: Sequence[ImpactAssessment],
) -> tuple[str, int | None]:
    if not assessments:
        return "unknown", None
    direction = combine_impact_directions(assessment.direction for assessment in assessments)
    positive = max(
        (assessment.positive_magnitude for assessment in assessments),
        default=0,
    )
    negative = max(
        (assessment.negative_magnitude for assessment in assessments),
        default=0,
    )
    return direction, _signed_score(direction, positive, negative)


def _signed_score(direction: str, positive: int, negative: int) -> int | None:
    if direction == "positive":
        return positive
    if direction == "negative":
        return -negative
    if direction == "neutral":
        return 0
    return None


def _event_candidates(
    report: ResearchReport | None,
    routed: RoutedAnalysis | None,
    event_id: str,
    news_items: Sequence[NewsItem],
) -> list[dict[str, Any]]:
    if report is None:
        return []
    impacts = {impact.symbol: impact for impact in report.stock_impacts}
    if routed is None:
        candidates = []
        for impact in report.stock_impacts:
            if impact.market != "A股":
                continue
            payload = _impact_payload(impact, [event_id])
            payload["news_links"] = _news_link_payload(news_items)
            candidates.append(payload)
        return candidates
    candidates: list[dict[str, Any]] = []
    ledgers = {
        ledger.symbol: ledger
        for ledger in getattr(routed, "ledgers", ())
        if ledger.symbol
    }
    for assessment in routed.assessments:
        impact = impacts.get(assessment.symbol)
        if impact is None or impact.market != "A股":
            continue
        payload = _impact_payload(impact, [event_id])
        ledger = ledgers.get(assessment.symbol)
        source_item_ids = (
            list(
                dict.fromkeys(
                    item_id
                    for claim in ledger.claims
                    for item_id in claim.source_item_ids
                )
            )
            if ledger is not None
            else []
        )
        payload.update(
            {
                "impact_direction": assessment.direction,
                "impact_score": _signed_score(
                    assessment.direction,
                    assessment.positive_magnitude,
                    assessment.negative_magnitude,
                ),
                "positive_magnitude": assessment.positive_magnitude,
                "negative_magnitude": assessment.negative_magnitude,
                "confidence_score": assessment.confidence,
                "feature_breakdown": {
                    "positive": _stock_feature_payload(assessment.positive_features),
                    "negative": _stock_feature_payload(assessment.negative_features),
                    "confidence": _confidence_feature_payload(assessment),
                },
                "reason_codes": list(assessment.reason_codes),
                "score_status": (
                    "scored"
                    if _assessment_score_eligible(assessment)
                    else "insufficient_evidence"
                ),
                "claim_ids": (
                    list(dict.fromkeys(claim.id for claim in ledger.claims))
                    if ledger is not None
                    else []
                ),
                "source_item_ids": source_item_ids,
                "news_links": _news_link_payload(news_items, source_item_ids),
            }
        )
        candidates.append(payload)
    return candidates


def _news_link_payload(
    items: Iterable[NewsItem],
    source_item_ids: Sequence[str] = (),
) -> list[dict[str, str]]:
    from .claim_pipeline import stable_news_item_id

    allowed = set(source_item_ids)
    links: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in items:
        if allowed and stable_news_item_id(item) not in allowed:
            continue
        if not item.url or item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        links.append(
            {
                "headline": item.headline,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
            }
        )
    return links


def _assessment_score_eligible(assessment: ImpactAssessment) -> bool:
    directional = assessment.positive_features or assessment.negative_features
    if directional is None:
        return False
    return (
        "directness:official_announcement" in directional.directness.reason_codes
        or directional.exposure.value > 20
        or directional.economic_scale.value > 30
        or directional.sensitivity.value > 60
    )


def _confidence_label(value: int) -> str:
    if value >= 70:
        return "high"
    if value >= 45:
        return "medium"
    return "low"


def _watchlist_alerts(
    routed_analyses: Sequence[RoutedAnalysis],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    alerts: list[tuple[tuple[int, int, float, str], dict[str, Any]]] = []
    reports_by_event = dict(zip(event_ids, reports))
    for routed in routed_analyses:
        event = routed.event
        event_id = market_event_id(event)
        report = getattr(routed, "report", None) or reports_by_event.get(event_id)
        if report is None:
            continue
        impacts = {impact.symbol: impact for impact in report.stock_impacts}
        for assessment in routed.assessments:
            impact = impacts.get(assessment.symbol)
            if not (
                impact is not None
                and impact.market == "A股"
                and impact.watchlist_hit
                and impact.verification_status == "verified"
                and assessment.direction in {"negative", "mixed"}
                and assessment.negative_magnitude >= 35
            ):
                continue
            score = _signed_score(
                assessment.direction,
                assessment.positive_magnitude,
                assessment.negative_magnitude,
            )
            severity = (
                "high"
                if assessment.negative_magnitude >= 60 and assessment.confidence >= 50
                else "medium"
            )
            payload = {
                "id": f"alert_{hashlib.sha256(f'{event_id}|{impact.symbol}'.encode()).hexdigest()[:16]}",
                "event_id": event_id,
                "event_title": event.title,
                "symbol": impact.symbol,
                "name": impact.name,
                "direction": assessment.direction,
                "impact_score": score,
                "confidence": _confidence_label(assessment.confidence),
                "severity": severity,
                "reasoning": impact.reasoning,
                "evidence": list(impact.evidence),
                "risks": list(impact.risks),
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "negative_horizon": _directional_horizon_payload(
                    assessment.negative_horizon
                ),
            }
            alerts.append(
                (
                    (
                        0 if severity == "high" else 1,
                        -abs(score or 0),
                        -_published_timestamp(event.items[0].published_at),
                        impact.symbol,
                    ),
                    payload,
                )
            )
    alerts.sort(key=lambda item: item[0])
    return [payload for _, payload in alerts]


def _research_candidates(
    groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    candidates = [
        candidate.copy()
        for candidate in groups["verified"]
        if candidate["impact_direction"] == "positive" and candidate["positive_magnitude"] >= 35
    ]
    for candidate in candidates:
        candidate["confidence_score"] = candidate["confidence"]
        candidate["confidence"] = _confidence_label(candidate["confidence"])
    candidates.sort(
        key=lambda candidate: (
            -candidate["positive_magnitude"],
            -candidate["confidence_score"],
            candidate["symbol"],
        )
    )
    return candidates[:10]


def _legacy_watchlist_alerts(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for event, report, event_id in zip(events, reports, event_ids):
        if report is None:
            continue
        for impact in report.stock_impacts:
            if not (
                impact.market == "A股"
                and impact.watchlist_hit
                and impact.verification_status == "verified"
                and impact.impact_direction in {"negative", "mixed"}
                and impact.impact_strength in {"medium", "high"}
            ):
                continue
            score = stock_impact_score(impact)
            severity = (
                "high"
                if impact.impact_direction == "negative"
                and impact.impact_strength == "high"
                and impact.confidence in {"medium", "high"}
                else "medium"
            )
            alerts.append(
                {
                    "id": f"alert_{hashlib.sha256(f'{event_id}|{impact.symbol}'.encode()).hexdigest()[:16]}",
                    "event_id": event_id,
                    "event_title": event.title,
                    "symbol": impact.symbol,
                    "name": impact.name,
                    "direction": impact.impact_direction,
                    "impact_score": score,
                    "confidence": impact.confidence,
                    "severity": severity,
                    "reasoning": impact.reasoning,
                    "evidence": list(impact.evidence),
                    "risks": list(impact.risks),
                    "generated_at": generated_at.isoformat(timespec="seconds"),
                    "negative_horizon": None,
                }
            )
    return alerts


def _legacy_research_candidates(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for event, report, event_id in zip(events, reports, event_ids):
        if report is None:
            continue
        for impact in report.stock_impacts:
            if not (
                impact.market == "A股"
                and impact.verification_status == "verified"
                and impact.impact_direction == "positive"
                and impact.impact_type in {"direct", "indirect"}
                and impact.impact_strength in {"medium", "high"}
            ):
                continue
            payload = _impact_payload(impact, [event_id])
            payload.update(
                {
                    "event_titles": [event.title],
                    "source_count": len(event.items),
                    "latest_published_at": event.items[0].published_at,
                }
            )
            candidates.append(payload)
    candidates.sort(
        key=lambda candidate: (
            -abs(candidate["impact_score"] or 0),
            candidate["symbol"],
        )
    )
    return candidates[:10]


def _aggregate_candidate(
    contexts: Sequence[_ImpactContext],
) -> tuple[dict[str, Any], str]:
    active = [
        context
        for context in contexts
        if context.impact.verification_status != "excluded"
        and context.impact.impact_type != "false_positive"
    ]
    verified = [context for context in active if context.impact.verification_status == "verified"]
    if verified:
        status = "verified"
        relevant = verified
    elif active:
        status = "unverified"
        relevant = active
    else:
        status = "excluded"
        relevant = list(contexts)

    selected = max(
        relevant,
        key=lambda context: _STRENGTH_ORDER.get(context.impact.impact_strength, 0),
    ).impact
    event_ids = _unique(context.event_id for context in contexts)
    payload = _impact_payload(selected, event_ids)
    directions = [context.impact.impact_direction for context in relevant]
    scores = [
        score for context in relevant if (score := stock_impact_score(context.impact)) is not None
    ]
    payload.update(
        {
            "event_titles": _unique(context.event_title for context in contexts),
            "verification_status": status,
            "verification_source": " / ".join(
                _unique(
                    context.impact.verification_source
                    for context in relevant
                    if context.impact.verification_source
                )
            ),
            "themes": _unique(theme for context in relevant for theme in context.impact.themes),
            "reasoning": "；".join(
                _unique(
                    context.impact.reasoning for context in relevant if context.impact.reasoning
                )
            ),
            "evidence": _unique(
                value for context in relevant for value in context.impact.evidence if value
            ),
            "risks": _unique(
                value for context in relevant for value in context.impact.risks if value
            ),
            "watchlist_hit": any(context.impact.watchlist_hit for context in contexts),
            "impact_direction": combine_impact_directions(directions),
            "impact_score": round(sum(scores) / len(scores)) if scores else None,
            "confidence": strongest_confidence(context.impact.confidence for context in relevant),
            "news_links": _news_link_payload(
                item for context in contexts for item in context.news_items
            ),
        }
    )
    return payload, status


def _impact_payload(impact: StockImpact, event_ids: list[str]) -> dict[str, Any]:
    return {
        "symbol": impact.symbol,
        "name": impact.name,
        "market": impact.market,
        "event_ids": event_ids,
        "impact_type": impact.impact_type,
        "impact_strength": impact.impact_strength,
        "impact_direction": impact.impact_direction,
        "impact_score": stock_impact_score(impact),
        "confidence": impact.confidence,
        "verification_status": impact.verification_status,
        "verification_source": impact.verification_source,
        "watchlist_hit": impact.watchlist_hit,
        "themes": list(impact.themes),
        "reasoning": impact.reasoning,
        "evidence": list(impact.evidence),
        "risks": list(impact.risks),
        "positive_horizon": None,
        "negative_horizon": None,
    }


def _attach_candidate_horizons(
    candidates: Sequence[dict[str, Any]],
    assessments: Sequence[ImpactAssessment],
) -> None:
    assessments_by_symbol: dict[str, list[ImpactAssessment]] = {}
    for assessment in assessments:
        if assessment.symbol:
            assessments_by_symbol.setdefault(assessment.symbol, []).append(assessment)
    for candidate in candidates:
        values = assessments_by_symbol.get(candidate["symbol"], ())
        positive = (
            max(values, key=lambda assessment: assessment.positive_magnitude)
            if values
            else None
        )
        negative = (
            max(values, key=lambda assessment: assessment.negative_magnitude)
            if values
            else None
        )
        candidate["positive_horizon"] = _directional_horizon_payload(
            positive.positive_horizon if positive is not None else None
        )
        candidate["negative_horizon"] = _directional_horizon_payload(
            negative.negative_horizon if negative is not None else None
        )


def _directional_horizon_payload(
    horizon: DirectionalHorizons | None,
) -> dict[str, Any] | None:
    if horizon is None:
        return None
    return {
        "market": _horizon_payload(horizon.market),
        "fundamental": _horizon_payload(horizon.fundamental),
    }


def _horizon_payload(horizon: ImpactHorizon) -> dict[str, Any]:
    return {
        "category": horizon.category,
        "min_duration": horizon.min_duration,
        "max_duration": horizon.max_duration,
        "unit": horizon.unit,
        "confidence": horizon.confidence,
        "basis": list(horizon.basis),
        "evidence_refs": list(horizon.evidence_refs),
        "invalidation_conditions": list(horizon.invalidation_conditions),
    }


def _validation_tasks(
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for report, event_id in zip(reports, event_ids):
        if report is None:
            continue
        for task in report.validation_tasks:
            key = (task.question, task.data_needed, task.status)
            grouped.setdefault(key, []).append(event_id)
    return [
        {
            "question": question,
            "data_needed": data_needed,
            "status": status,
            "event_ids": _unique(ids),
        }
        for (question, data_needed, status), ids in grouped.items()
    ]


def market_event_id(event: MarketEvent) -> str:
    signature = sorted(
        (
            _normalize(item.headline),
            item.source_type,
            _normalize(item.source),
            item.url.strip(),
            item.published_at.strip(),
        )
        for item in event.items
    )
    encoded = json.dumps(signature, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"evt_{digest}"


def _step_warnings(step: AgentStep) -> list[str]:
    if step.status == "error":
        return [step.summary.strip()] if step.summary.strip() else []
    return [warning for warning in step.warnings if warning.strip()]


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def _published_timestamp(value: str) -> float:
    normalized = value.strip().replace("Z", "+00:00")
    if not normalized:
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return float("-inf")
    return _shanghai_time(parsed).timestamp()
