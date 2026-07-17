from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .agent_models import AgentStep
from .event_eligibility import market_event_exclusion_reason
from .impact_scoring import (
    combine_impact_directions,
    stock_impact_score,
    strongest_confidence,
    summarize_event_impact,
)
from .models import MarketEvent, ResearchReport, StockImpact

SCHEMA_VERSION = "2.1"
DISCLAIMER = "研究辅助，不构成投资建议。"
SHANGHAI = ZoneInfo("Asia/Shanghai")
_WARNING_WORDS = ("fallback", "warning", "unavailable", "失败", "不可用", "异常", "纠正")
_STRENGTH_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "unknown"}
_CONFIDENCES = {"high", "medium", "low", "unknown"}


class InvalidRadarSnapshot(ValueError):
    """Raised when a persisted frontend snapshot violates the v2.1 contract."""


@dataclass(frozen=True)
class _ImpactContext:
    event_id: str
    event_title: str
    source_count: int
    latest_published_at: str
    impact: StockImpact


def build_daily_radar_snapshot(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    steps: Sequence[AgentStep],
    window_start: datetime,
    window_end: datetime,
    *,
    all_events: Sequence[MarketEvent] | None = None,
    generated_at: datetime | None = None,
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
    event_payloads = [
        _event_payload(event, report, event_ids[index], index + 1, steps)
        for index, (event, report) in enumerate(zip(events, reports))
    ]
    candidate_groups = _candidate_groups(events, reports, event_ids)
    alerts = _watchlist_alerts(events, reports, event_ids, generated_at)
    research_candidates = _research_candidates(events, reports, event_ids)
    validation_tasks = _validation_tasks(reports, event_ids)
    warnings = _unique(
        warning for step in steps for warning in _step_warnings(step)
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
    ):
        if not isinstance(summary.get(name), int):
            raise InvalidRadarSnapshot(f"invalid summary.{name}")
    for index, event in enumerate(payload["events"]):
        if not isinstance(event, dict):
            raise InvalidRadarSnapshot(f"invalid events.{index}")
        _validate_impact_fields(event, f"events.{index}", direction_field="overall_direction")
        if not isinstance(event.get("candidates"), list):
            raise InvalidRadarSnapshot(f"invalid events.{index}.candidates")
        for candidate_index, candidate in enumerate(event["candidates"]):
            _validate_impact_fields(
                candidate,
                f"events.{index}.candidates.{candidate_index}",
            )
    for group_name in ("verified", "unverified", "excluded", "watchlist"):
        for index, candidate in enumerate(groups[group_name]):
            _validate_impact_fields(
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


def _event_summary_payload(
    event: MarketEvent,
    event_id: str,
    rank: int,
    analysis_status: str,
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
    }


def _event_payload(
    event: MarketEvent,
    report: ResearchReport | None,
    event_id: str,
    rank: int,
    steps: Sequence[AgentStep],
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
    if report is None:
        warnings = _unique([*warnings, "事件分析失败，详见运行步骤。"])
        event_type = "待判断"
        themes: list[str] = []
        key_facts: list[str] = []
        confidence = "low"
        overall_direction = "unknown"
        impact_score = None
        reasoning = ""
        value_chain = {
            "payer": "",
            "receiver": "",
            "chain_steps": [],
            "direction": "unknown",
            "reasoning": "",
        }
        candidates: list[dict[str, Any]] = []
    else:
        impact_summary = summarize_event_impact(report)
        event_type = report.event.event_type
        themes = list(report.event.themes)
        key_facts = list(report.event.key_facts)
        confidence = report.event.confidence
        overall_direction = impact_summary.direction
        impact_score = impact_summary.score
        reasoning = report.event.reasoning
        value_chain = {
            "payer": report.value_chain.payer,
            "receiver": report.value_chain.receiver,
            "chain_steps": list(report.value_chain.chain_steps),
            "direction": report.value_chain.impact_direction,
            "reasoning": report.value_chain.reasoning,
        }
        candidates = [
            _impact_payload(impact, [event_id])
            for impact in report.stock_impacts
            if impact.market == "A股"
        ]

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
        "overall_direction": overall_direction,
        "impact_score": impact_score,
        "reasoning": reasoning,
        "value_chain": value_chain,
        "candidates": candidates,
        "analysis_status": "succeeded" if report is not None else "failed",
        "warnings": warnings,
    }


def build_radar_event_payload(
    event: MarketEvent,
    report: ResearchReport,
    event_id: str,
    rank: int,
    steps: Sequence[AgentStep],
) -> dict[str, Any]:
    """Build one analyzed event using the frontend event contract."""

    return _event_payload(event, report, event_id, rank, steps)


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


def _watchlist_alerts(
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    alerts: list[tuple[tuple[int, int, float, str], dict[str, Any]]] = []
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
            payload = {
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
    events: Sequence[MarketEvent],
    reports: Sequence[ResearchReport | None],
    event_ids: Sequence[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[_ImpactContext]] = {}
    for event, report, event_id in zip(events, reports, event_ids):
        if report is None:
            continue
        source_count = len(
            {
                (item.source_type, item.source.strip() or item.source_type)
                for item in event.items
            }
        )
        for impact in report.stock_impacts:
            if not (
                impact.market == "A股"
                and impact.verification_status == "verified"
                and impact.impact_direction == "positive"
                and impact.impact_type in {"direct", "indirect"}
                and impact.impact_strength in {"medium", "high"}
                and stock_impact_score(impact) is not None
            ):
                continue
            grouped.setdefault(impact.symbol, []).append(
                _ImpactContext(
                    event_id,
                    event.title,
                    source_count,
                    event.items[0].published_at,
                    impact,
                )
            )

    ranked: list[tuple[tuple[int, int, int, float, str], dict[str, Any]]] = []
    confidence_order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    for contexts in grouped.values():
        selected = min(
            contexts,
            key=lambda context: (
                -(stock_impact_score(context.impact) or 0),
                -confidence_order[context.impact.confidence],
                -context.source_count,
                -_published_timestamp(context.latest_published_at),
                context.impact.symbol,
            ),
        )
        payload = _impact_payload(
            selected.impact,
            _unique(context.event_id for context in contexts),
        )
        payload.update(
            {
                "event_titles": _unique(context.event_title for context in contexts),
                "source_count": max(context.source_count for context in contexts),
                "latest_published_at": max(
                    context.latest_published_at for context in contexts
                ),
                "reasoning": "；".join(
                    _unique(
                        context.impact.reasoning
                        for context in contexts
                        if context.impact.reasoning
                    )
                ),
                "evidence": _unique(
                    evidence
                    for context in contexts
                    for evidence in context.impact.evidence
                    if evidence
                ),
                "risks": _unique(
                    risk
                    for context in contexts
                    for risk in context.impact.risks
                    if risk
                ),
                "watchlist_hit": any(
                    context.impact.watchlist_hit for context in contexts
                ),
            }
        )
        score = stock_impact_score(selected.impact) or 0
        ranked.append(
            (
                (
                    -score,
                    -confidence_order[selected.impact.confidence],
                    -selected.source_count,
                    -_published_timestamp(selected.latest_published_at),
                    selected.impact.symbol,
                ),
                payload,
            )
        )
    ranked.sort(key=lambda item: item[0])
    return [payload for _, payload in ranked[:10]]


def _aggregate_candidate(
    contexts: Sequence[_ImpactContext],
) -> tuple[dict[str, Any], str]:
    active = [
        context
        for context in contexts
        if context.impact.verification_status != "excluded"
        and context.impact.impact_type != "false_positive"
    ]
    verified = [
        context
        for context in active
        if context.impact.verification_status == "verified"
    ]
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
        score
        for context in relevant
        if (score := stock_impact_score(context.impact)) is not None
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
            "themes": _unique(
                theme for context in relevant for theme in context.impact.themes
            ),
            "reasoning": "；".join(
                _unique(
                    context.impact.reasoning
                    for context in relevant
                    if context.impact.reasoning
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
            "confidence": strongest_confidence(
                context.impact.confidence for context in relevant
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
    summary = step.summary.strip()
    if not summary:
        return []
    if step.status == "error":
        return [summary]
    parts = [part.strip() for part in re.split(r"[;；]\s*", summary) if part.strip()]
    return [
        part
        for part in parts
        if any(word in part.casefold() for word in _WARNING_WORDS)
    ]


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
