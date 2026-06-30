from __future__ import annotations

from typing import Any

from .models import (
    EventAnalysis,
    RawNews,
    ResearchReport,
    StockImpact,
    ValidationTask,
    ValueChainTrace,
)

STAGES = {"启动", "验证", "高潮", "分歧", "退潮", "待判断"}
ACTION_STATES = {"忽略", "放观察池", "等验证", "等回调", "可小仓试", "高潮勿追", "待判断"}
IMPACT_TYPES = {"direct", "indirect", "sentiment", "negative", "false_positive"}
IMPACT_STRENGTHS = {"high", "medium", "low", "unknown"}
VERIFICATION_STATUSES = {"verified", "unverified", "excluded"}
VALIDATION_STATUSES = {"pending", "done", "blocked"}
CONFIDENCES = {"high", "medium", "low", "unknown"}
IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "unknown"}


def research_report_json_schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "raw_news",
            "event",
            "value_chain",
            "stock_impacts",
            "validation_tasks",
            "stage",
            "action_state",
        ],
        "properties": {
            "raw_news": _object_schema(
                {
                    "headline": {"type": "string"},
                    "source": {"type": "string"},
                    "url": {"type": "string"},
                    "published_at": {"type": "string"},
                    "body": {"type": "string"},
                }
            ),
            "event": _object_schema(
                {
                    "event_type": {"type": "string"},
                    "themes": string_array,
                    "involved_entities": string_array,
                    "key_facts": string_array,
                    "source_quality": {"type": "string"},
                    "confidence": {"type": "string", "enum": sorted(CONFIDENCES)},
                    "reasoning": {"type": "string"},
                }
            ),
            "value_chain": _object_schema(
                {
                    "payer": {"type": "string"},
                    "receiver": {"type": "string"},
                    "chain_steps": string_array,
                    "impact_direction": {"type": "string", "enum": sorted(IMPACT_DIRECTIONS)},
                    "reasoning": {"type": "string"},
                }
            ),
            "stock_impacts": {
                "type": "array",
                "items": _object_schema(
                    {
                        "symbol": {"type": "string"},
                        "name": {"type": "string"},
                        "market": {"type": "string"},
                        "impact_type": {"type": "string", "enum": sorted(IMPACT_TYPES)},
                        "impact_strength": {"type": "string", "enum": sorted(IMPACT_STRENGTHS)},
                        "themes": string_array,
                        "reasoning": {"type": "string"},
                        "evidence": string_array,
                        "risks": string_array,
                        "verification_status": {
                            "type": "string",
                            "enum": sorted(VERIFICATION_STATUSES),
                        },
                        "verification_source": {"type": "string"},
                        "watchlist_hit": {"type": "boolean"},
                    }
                ),
            },
            "validation_tasks": {
                "type": "array",
                "items": _object_schema(
                    {
                        "question": {"type": "string"},
                        "data_needed": {"type": "string"},
                        "status": {"type": "string", "enum": sorted(VALIDATION_STATUSES)},
                    }
                ),
            },
            "stage": {"type": "string", "enum": sorted(STAGES)},
            "action_state": {"type": "string", "enum": sorted(ACTION_STATES)},
        },
    }


def parse_research_report(data: dict[str, Any]) -> ResearchReport:
    root = _object(data, "root")
    _require(root, "raw_news")
    _require(root, "event")
    _require(root, "value_chain")
    _require(root, "stock_impacts")
    _require(root, "validation_tasks")
    _require(root, "stage")
    _require(root, "action_state")

    raw_news = _parse_raw_news(_object(root["raw_news"], "raw_news"))
    event = _parse_event(_object(root["event"], "event"))
    value_chain = _parse_value_chain(_object(root["value_chain"], "value_chain"))
    stock_impacts = tuple(
        _parse_stock_impact(_object(item, f"stock_impacts.{index}"), f"stock_impacts.{index}")
        for index, item in enumerate(_array(root["stock_impacts"], "stock_impacts"))
    )
    validation_tasks = tuple(
        _parse_validation_task(_object(item, f"validation_tasks.{index}"), f"validation_tasks.{index}")
        for index, item in enumerate(_array(root["validation_tasks"], "validation_tasks"))
    )

    return ResearchReport(
        raw_news=raw_news,
        event=event,
        value_chain=value_chain,
        stock_impacts=stock_impacts,
        validation_tasks=validation_tasks,
        stage=_enum(root["stage"], "stage", STAGES),
        action_state=_enum(root["action_state"], "action_state", ACTION_STATES),
    )


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _parse_raw_news(data: dict[str, Any]) -> RawNews:
    return RawNews(
        headline=_string(data.get("headline"), "raw_news.headline"),
        source=_string(data.get("source"), "raw_news.source"),
        url=_string(data.get("url"), "raw_news.url"),
        published_at=_string(data.get("published_at"), "raw_news.published_at"),
        body=_string(data.get("body"), "raw_news.body"),
    )


def _parse_event(data: dict[str, Any]) -> EventAnalysis:
    return EventAnalysis(
        event_type=_string(data.get("event_type"), "event.event_type"),
        themes=tuple(_string_array(data.get("themes"), "event.themes")),
        involved_entities=tuple(
            _string_array(data.get("involved_entities"), "event.involved_entities")
        ),
        key_facts=tuple(_string_array(data.get("key_facts"), "event.key_facts")),
        source_quality=_string(data.get("source_quality"), "event.source_quality"),
        confidence=_enum(data.get("confidence"), "event.confidence", CONFIDENCES),
        reasoning=_string(data.get("reasoning"), "event.reasoning"),
    )


def _parse_value_chain(data: dict[str, Any]) -> ValueChainTrace:
    return ValueChainTrace(
        payer=_string(data.get("payer"), "value_chain.payer"),
        receiver=_string(data.get("receiver"), "value_chain.receiver"),
        chain_steps=tuple(_string_array(data.get("chain_steps"), "value_chain.chain_steps")),
        impact_direction=_enum(
            data.get("impact_direction"),
            "value_chain.impact_direction",
            IMPACT_DIRECTIONS,
        ),
        reasoning=_string(data.get("reasoning"), "value_chain.reasoning"),
    )


def _parse_stock_impact(data: dict[str, Any], path: str) -> StockImpact:
    return StockImpact(
        symbol=_string(data.get("symbol"), f"{path}.symbol"),
        name=_string(data.get("name"), f"{path}.name"),
        market=_string(data.get("market"), f"{path}.market"),
        impact_type=_enum(data.get("impact_type"), f"{path}.impact_type", IMPACT_TYPES),
        impact_strength=_enum(
            data.get("impact_strength"),
            f"{path}.impact_strength",
            IMPACT_STRENGTHS,
        ),
        themes=tuple(_string_array(data.get("themes"), f"{path}.themes")),
        reasoning=_string(data.get("reasoning"), f"{path}.reasoning"),
        evidence=tuple(_string_array(data.get("evidence"), f"{path}.evidence")),
        risks=tuple(_string_array(data.get("risks"), f"{path}.risks")),
        verification_status=_enum(
            data.get("verification_status"),
            f"{path}.verification_status",
            VERIFICATION_STATUSES,
        ),
        verification_source=_string(data.get("verification_source"), f"{path}.verification_source"),
        watchlist_hit=_bool(data.get("watchlist_hit"), f"{path}.watchlist_hit"),
    )


def _parse_validation_task(data: dict[str, Any], path: str) -> ValidationTask:
    return ValidationTask(
        question=_string(data.get("question"), f"{path}.question"),
        data_needed=_string(data.get("data_needed"), f"{path}.data_needed"),
        status=_enum(data.get("status"), f"{path}.status", VALIDATION_STATUSES),
    )


def _require(data: dict[str, Any], key: str) -> None:
    if key not in data:
        raise ValueError(f"Missing required field: {key}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object at {path}")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Expected array at {path}")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected string at {path}")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Expected bool at {path}")
    return value


def _string_array(value: Any, path: str) -> list[str]:
    items = _array(value, path)
    for index, item in enumerate(items):
        _string(item, f"{path}.{index}")
    return items


def _enum(value: Any, path: str, allowed: set[str]) -> Any:
    text = _string(value, path)
    if text not in allowed:
        raise ValueError(f"Invalid {path}: {text}")
    return text
