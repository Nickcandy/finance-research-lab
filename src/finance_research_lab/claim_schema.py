from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .claims import ClaimType, TimeHorizon
from .models import ConfidenceLevel, ImpactDirection

CLAIM_TYPES = {
    "fact",
    "forecast",
    "opinion",
    "risk",
    "denial",
    "market_reaction",
}
TIME_HORIZONS = {"immediate", "short", "medium", "long", "unknown"}
IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "unknown"}
CONFIDENCES = {"high", "medium", "low", "unknown"}


@dataclass(frozen=True)
class ParsedQuantitativeFact:
    metric: str
    value: float
    unit: str
    period: str
    source_item_id: str


@dataclass(frozen=True)
class ParsedClaim:
    event_id: str
    source_item_ids: tuple[str, ...]
    subject: str
    predicate: str
    object: str
    claim_type: ClaimType
    event_type: str
    direction: ImpactDirection
    time_horizon: TimeHorizon
    affected_symbols: tuple[str, ...]
    quantitative_facts: tuple[ParsedQuantitativeFact, ...]
    confidence: ConfidenceLevel
    occurred_at: str


def claim_response_json_schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    quantitative_fact = _object_schema(
        {
            "metric": {"type": "string"},
            "value": {"type": "number"},
            "unit": {"type": "string"},
            "period": {"type": "string"},
            "source_item_id": {"type": "string"},
        }
    )
    claim = _object_schema(
        {
            "event_id": {"type": "string"},
            "source_item_ids": string_array,
            "subject": {"type": "string"},
            "predicate": {"type": "string"},
            "object": {"type": "string"},
            "claim_type": {"type": "string", "enum": sorted(CLAIM_TYPES)},
            "event_type": {"type": "string"},
            "direction": {"type": "string", "enum": sorted(IMPACT_DIRECTIONS)},
            "time_horizon": {"type": "string", "enum": sorted(TIME_HORIZONS)},
            "affected_symbols": string_array,
            "quantitative_facts": {
                "type": "array",
                "items": quantitative_fact,
            },
            "confidence": {"type": "string", "enum": sorted(CONFIDENCES)},
            "occurred_at": {"type": "string"},
        }
    )
    return _object_schema({"claims": {"type": "array", "items": claim}})


def parse_claim_response(
    content: str,
    expected_items: dict[str, str],
) -> tuple[ParsedClaim, ...]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid claim JSON: {exc}") from exc
    root = _exact_object(payload, "root", {"claims"})
    rows = _array(root["claims"], "claims")
    claims = tuple(
        _parse_claim(row, f"claims.{index}", expected_items)
        for index, row in enumerate(rows)
    )
    return claims


def _parse_claim(
    value: object,
    path: str,
    expected_items: dict[str, str],
) -> ParsedClaim:
    required = {
        "event_id",
        "source_item_ids",
        "subject",
        "predicate",
        "object",
        "claim_type",
        "event_type",
        "direction",
        "time_horizon",
        "affected_symbols",
        "quantitative_facts",
        "confidence",
        "occurred_at",
    }
    data = _exact_object(value, path, required)
    source_item_ids = tuple(_non_empty_string_array(data["source_item_ids"], f"{path}.source_item_ids"))
    event_id = _non_empty_string(data["event_id"], f"{path}.event_id")
    for source_item_id in source_item_ids:
        expected_event_id = expected_items.get(source_item_id)
        if expected_event_id is None:
            raise ValueError(f"unknown source item at {path}.source_item_ids")
        if expected_event_id != event_id:
            raise ValueError(f"event mismatch at {path}.event_id")
    quantitative_facts = tuple(
        _parse_quantitative_fact(item, f"{path}.quantitative_facts.{index}", source_item_ids)
        for index, item in enumerate(_array(data["quantitative_facts"], f"{path}.quantitative_facts"))
    )
    return ParsedClaim(
        event_id=event_id,
        source_item_ids=source_item_ids,
        subject=_non_empty_string(data["subject"], f"{path}.subject"),
        predicate=_non_empty_string(data["predicate"], f"{path}.predicate"),
        object=_non_empty_string(data["object"], f"{path}.object"),
        claim_type=_enum(data["claim_type"], f"{path}.claim_type", CLAIM_TYPES),
        event_type=_non_empty_string(data["event_type"], f"{path}.event_type"),
        direction=_enum(data["direction"], f"{path}.direction", IMPACT_DIRECTIONS),
        time_horizon=_enum(data["time_horizon"], f"{path}.time_horizon", TIME_HORIZONS),
        affected_symbols=tuple(
            _optional_non_empty_string_array(
                data["affected_symbols"],
                f"{path}.affected_symbols",
            )
        ),
        quantitative_facts=quantitative_facts,
        confidence=_enum(data["confidence"], f"{path}.confidence", CONFIDENCES),
        occurred_at=_string(data["occurred_at"], f"{path}.occurred_at"),
    )


def _parse_quantitative_fact(
    value: object,
    path: str,
    source_item_ids: tuple[str, ...],
) -> ParsedQuantitativeFact:
    data = _exact_object(
        value,
        path,
        {"metric", "value", "unit", "period", "source_item_id"},
    )
    source_item_id = _non_empty_string(data["source_item_id"], f"{path}.source_item_id")
    if source_item_id not in source_item_ids:
        raise ValueError(f"quantitative fact source is not in claim at {path}")
    number = data["value"]
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise ValueError(f"Expected number at {path}.value")
    return ParsedQuantitativeFact(
        metric=_non_empty_string(data["metric"], f"{path}.metric"),
        value=float(number),
        unit=_non_empty_string(data["unit"], f"{path}.unit"),
        period=_string(data["period"], f"{path}.period"),
        source_item_id=source_item_id,
    )


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _exact_object(value: object, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object at {path}")
    keys = set(value)
    missing = fields - keys
    extra = keys - fields
    if missing:
        raise ValueError(f"Missing required field at {path}: {sorted(missing)[0]}")
    if extra:
        raise ValueError(f"Unexpected field at {path}: {sorted(extra)[0]}")
    return value


def _array(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Expected array at {path}")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected string at {path}")
    return value


def _non_empty_string(value: object, path: str) -> str:
    text = _string(value, path)
    if not text.strip():
        raise ValueError(f"Expected non-empty string at {path}")
    return text


def _string_array(value: object, path: str) -> list[str]:
    items = _array(value, path)
    return [_string(item, f"{path}.{index}") for index, item in enumerate(items)]


def _non_empty_string_array(value: object, path: str) -> list[str]:
    items = _array(value, path)
    if not items:
        raise ValueError(f"Expected non-empty array at {path}")
    return [_non_empty_string(item, f"{path}.{index}") for index, item in enumerate(items)]


def _optional_non_empty_string_array(value: object, path: str) -> list[str]:
    items = _array(value, path)
    return [_non_empty_string(item, f"{path}.{index}") for index, item in enumerate(items)]


def _enum(value: object, path: str, allowed: set[str]) -> Any:
    text = _string(value, path)
    if text not in allowed:
        raise ValueError(f"Unsupported value at {path}: {text}")
    return text
