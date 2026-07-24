from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol, Sequence, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .claim_schema import (
    CLAIM_TYPES,
    CONFIDENCES,
    IMPACT_DIRECTIONS,
    TIME_HORIZONS,
    ParsedClaim,
    claim_response_json_schema,
    parse_claim_response,
)
from .claims import Claim, ClaimType, QuantitativeFact, TimeHorizon
from .daily_radar_snapshot import market_event_id
from .impact_scoring import infer_news_impact_direction
from .llm.base import LLMResponse
from .models import ConfidenceLevel, ImpactDirection, MarketEvent, NewsItem

CLAIM_CACHE_VERSION = "1.0"
CLAIM_PROMPT_VERSION = "1.0"
DEFAULT_BATCH_SIZE = 15
DEFAULT_BODY_CHAR_LIMIT = 400
_TRACKING_QUERY_KEYS = {"from", "source", "spm"}

CLAIM_EXTRACTION_SYSTEM_PROMPT = """你是 A 股新闻事实抽取器。你的任务是把一批 NewsItem 转换成可追溯 Claim。

必须遵守：
1. 只能使用输入正文中的信息，不得补造数字、日期、主体、证券代码或因果关系。
2. 每个 Claim 必须引用一个或多个 source_item_id，并保持对应 event_id。
3. 金额、比例、数量、周期必须写入 quantitative_facts，并保留原始单位和 source_item_id。
4. 媒体判断、预测、传闻必须分别标记为 opinion、forecast 或 risk，不能伪装为 fact。
5. affected_symbols 只输出原文明确出现的代码；只有公司名时保留 subject，不猜证券代码。
6. 不输出最终事件重要性、股票影响分、置信总分、目标价、收益概率或仓位建议。
7. 无法确定时使用 unknown 或空数组，不要猜。
8. 只返回符合给定 JSON Schema 的 JSON，不要返回 Markdown。"""

BatchStatus = Literal["success", "partial", "fallback"]


class StructuredCompletionClient(Protocol):
    def structured_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout: int | None = None,
        scope_id: str = "",
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class ClaimBatchResult:
    batch_index: int
    item_count: int
    claim_count: int
    status: BatchStatus


@dataclass(frozen=True)
class ClaimPipelineResult:
    claims: tuple[Claim, ...]
    warnings: tuple[str, ...]
    batches: tuple[ClaimBatchResult, ...]
    cache_hits: int
    fallback_count: int


@dataclass(frozen=True)
class _NewsEntry:
    event_id: str
    item: NewsItem
    item_id: str


@dataclass(frozen=True)
class _ContentGroup:
    content_hash: str
    entries: tuple[_NewsEntry, ...]

    @property
    def representative(self) -> _NewsEntry:
        return self.entries[0]


@dataclass(frozen=True)
class _QuantitativeFactTemplate:
    metric: str
    value: float
    unit: str
    period: str


@dataclass(frozen=True)
class _ClaimTemplate:
    subject: str
    predicate: str
    object: str
    claim_type: ClaimType
    event_type: str
    direction: ImpactDirection
    time_horizon: TimeHorizon
    affected_symbols: tuple[str, ...]
    quantitative_facts: tuple[_QuantitativeFactTemplate, ...]
    confidence: ConfidenceLevel
    occurred_at: str


class ClaimPipeline:
    def __init__(
        self,
        client: StructuredCompletionClient | None,
        cache_dir: str | Path,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        body_char_limit: int = DEFAULT_BODY_CHAR_LIMIT,
    ) -> None:
        if not 1 <= batch_size <= 20:
            raise ValueError("batch_size must be between 1 and 20")
        if not 200 <= body_char_limit <= 400:
            raise ValueError("body_char_limit must be between 200 and 400")
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.batch_size = batch_size
        self.body_char_limit = body_char_limit

    def extract(self, events: Sequence[MarketEvent]) -> ClaimPipelineResult:
        groups = _content_groups(events)
        templates: dict[str, tuple[_ClaimTemplate, ...]] = {}
        warnings: list[str] = []
        pending: list[_ContentGroup] = []
        cache_hits = 0
        for group in groups:
            cached, warning = _read_cached_templates(self.cache_dir, group.content_hash)
            if warning:
                warnings.append(warning)
            if cached is None:
                pending.append(group)
                continue
            templates[group.content_hash] = cached
            cache_hits += 1

        batch_results: list[ClaimBatchResult] = []
        fallback_hashes: set[str] = set()
        for batch_index, batch in enumerate(_batches(pending, self.batch_size), start=1):
            extracted, batch_warnings = self._extract_batch(batch, batch_index)
            warnings.extend(batch_warnings)
            missing = []
            for group in batch:
                group_templates = extracted.get(group.content_hash)
                if not group_templates:
                    missing.append(group)
                    fallback_hashes.add(group.content_hash)
                    templates[group.content_hash] = (_fallback_template(group.representative.item),)
                    continue
                templates[group.content_hash] = group_templates
                try:
                    _write_cached_templates(
                        self.cache_dir,
                        group.content_hash,
                        group_templates,
                    )
                except OSError as exc:
                    warnings.append(
                        f"claim cache write failed for {group.content_hash[:12]}: {exc}"
                    )
            status: BatchStatus
            if len(missing) == len(batch):
                status = "fallback"
            elif missing:
                status = "partial"
            else:
                status = "success"
            batch_results.append(
                ClaimBatchResult(
                    batch_index=batch_index,
                    item_count=len(batch),
                    claim_count=sum(
                        len(templates[group.content_hash]) for group in batch
                    ),
                    status=status,
                )
            )

        claims: list[Claim] = []
        fallback_count = 0
        for group in groups:
            group_templates = templates.get(group.content_hash)
            if group_templates is None:
                group_templates = (_fallback_template(group.representative.item),)
                fallback_hashes.add(group.content_hash)
            for event_id, entries in _entries_by_event(group.entries):
                source_item_ids = tuple(
                    dict.fromkeys(entry.item_id for entry in entries)
                )
                if group.content_hash in fallback_hashes:
                    fallback_count += 1
                claims.extend(
                    _materialize_claim(
                        template,
                        event_id,
                        source_item_ids,
                        fallback=group.content_hash in fallback_hashes,
                    )
                    for template in group_templates
                )
        return ClaimPipelineResult(
            claims=tuple(claims),
            warnings=tuple(dict.fromkeys(warnings)),
            batches=tuple(batch_results),
            cache_hits=cache_hits,
            fallback_count=fallback_count,
        )

    def _extract_batch(
        self,
        batch: tuple[_ContentGroup, ...],
        batch_index: int,
    ) -> tuple[dict[str, tuple[_ClaimTemplate, ...]], tuple[str, ...]]:
        if self.client is None:
            return {}, (f"claim batch {batch_index} fallback: LLM client unavailable",)
        messages = _claim_messages(batch, self.body_char_limit)
        expected_items = {
            group.representative.item_id: group.representative.event_id
            for group in batch
        }
        warnings: list[str] = []
        for attempt in range(2):
            try:
                response = self.client.structured_completion(
                    messages=messages,
                    schema_name="news_claims",
                    schema=claim_response_json_schema(),
                    temperature=0,
                    scope_id=f"claim-batch:{batch_index}",
                )
                parsed = parse_claim_response(response.content, expected_items)
                return _templates_by_content_hash(parsed, batch), tuple(warnings)
            except (RuntimeError, ValueError) as exc:
                if attempt == 0:
                    warnings.append(f"claim batch {batch_index} retry: {exc}")
                    continue
                warnings.append(f"claim batch {batch_index} fallback: {exc}")
        return {}, tuple(warnings)


def stable_news_item_id(item: NewsItem) -> str:
    signature = "\n".join(
        (
            item.source_type,
            _canonical_url(item.url),
            _normalize_text(item.headline),
            item.published_at.strip(),
        )
    )
    return f"item_{_digest(signature)[:24]}"


def news_content_hash(item: NewsItem) -> str:
    content = "\n".join(
        (
            _normalize_text(item.headline),
            _normalize_text(item.body),
        )
    )
    return _digest(content)


def news_origin_key(item: NewsItem) -> str:
    canonical_url = _canonical_url(item.url)
    return f"url:{canonical_url}" if canonical_url else ""


def claim_cache_path(cache_dir: str | Path, content_hash: str) -> Path:
    return Path(cache_dir) / f"{content_hash}.json"


def _content_groups(events: Sequence[MarketEvent]) -> tuple[_ContentGroup, ...]:
    grouped: dict[str, list[_NewsEntry]] = {}
    for event in events:
        event_id = market_event_id(event)
        for item in event.items:
            content_hash = news_content_hash(item)
            grouped.setdefault(content_hash, []).append(
                _NewsEntry(
                    event_id=event_id,
                    item=item,
                    item_id=stable_news_item_id(item),
                )
            )
    return tuple(
        _ContentGroup(content_hash, tuple(entries))
        for content_hash, entries in grouped.items()
    )


def _claim_messages(
    batch: tuple[_ContentGroup, ...],
    body_char_limit: int,
) -> list[dict[str, str]]:
    payload = {
        "schema_version": CLAIM_PROMPT_VERSION,
        "items": [
            {
                "event_id": group.representative.event_id,
                "item_id": group.representative.item_id,
                "headline": group.representative.item.headline,
                "body_excerpt": _excerpt(group.representative.item.body, body_char_limit),
                "source": group.representative.item.source,
                "url": group.representative.item.url,
                "published_at": group.representative.item.published_at,
                "source_type": group.representative.item.source_type,
                "origin_key": news_origin_key(group.representative.item),
            }
            for group in batch
        ],
    }
    return [
        {"role": "system", "content": CLAIM_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _templates_by_content_hash(
    claims: tuple[ParsedClaim, ...],
    batch: tuple[_ContentGroup, ...],
) -> dict[str, tuple[_ClaimTemplate, ...]]:
    content_hash_by_item_id = {
        group.representative.item_id: group.content_hash for group in batch
    }
    grouped: dict[str, list[_ClaimTemplate]] = {}
    for claim in claims:
        content_hashes = {
            content_hash_by_item_id[source_item_id]
            for source_item_id in claim.source_item_ids
        }
        if len(content_hashes) != 1:
            raise ValueError("claim must reference one content group")
        content_hash = next(iter(content_hashes))
        grouped.setdefault(content_hash, []).append(_template_from_parsed(claim))
    return {
        content_hash: tuple(group_templates)
        for content_hash, group_templates in grouped.items()
    }


def _template_from_parsed(claim: ParsedClaim) -> _ClaimTemplate:
    return _ClaimTemplate(
        subject=claim.subject,
        predicate=claim.predicate,
        object=claim.object,
        claim_type=claim.claim_type,
        event_type=claim.event_type,
        direction=claim.direction,
        time_horizon=claim.time_horizon,
        affected_symbols=claim.affected_symbols,
        quantitative_facts=tuple(
            _QuantitativeFactTemplate(
                metric=fact.metric,
                value=fact.value,
                unit=fact.unit,
                period=fact.period,
            )
            for fact in claim.quantitative_facts
        ),
        confidence=claim.confidence,
        occurred_at=claim.occurred_at,
    )


def _fallback_template(item: NewsItem) -> _ClaimTemplate:
    return _ClaimTemplate(
        subject=item.headline.strip() or "未命名事件",
        predicate="报道",
        object=_excerpt(item.body, DEFAULT_BODY_CHAR_LIMIT) or item.headline.strip(),
        claim_type=(
            "fact" if item.source_type in {"announcement", "policy"} else "opinion"
        ),
        event_type="政策 / 监管" if item.source_type == "policy" else "待判断",
        direction=infer_news_impact_direction(f"{item.headline} {item.body}"),
        time_horizon="unknown",
        affected_symbols=(),
        quantitative_facts=(),
        confidence="low",
        occurred_at=item.published_at,
    )


def _materialize_claim(
    template: _ClaimTemplate,
    event_id: str,
    source_item_ids: tuple[str, ...],
    *,
    fallback: bool,
) -> Claim:
    quantitative_facts = tuple(
        QuantitativeFact(
            metric=fact.metric,
            value=fact.value,
            unit=fact.unit,
            period=fact.period,
            source_item_id=source_item_ids[0],
        )
        for fact in template.quantitative_facts
    )
    signature = json.dumps(
        {
            "event_id": event_id,
            "source_item_ids": source_item_ids,
            "template": asdict(template),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return Claim(
        id=f"claim_{_digest(signature)[:24]}",
        event_id=event_id,
        source_item_ids=source_item_ids,
        subject=template.subject,
        predicate=template.predicate,
        object=template.object,
        claim_type=template.claim_type,
        event_type=template.event_type,
        direction=template.direction,
        time_horizon=template.time_horizon,
        affected_symbols=template.affected_symbols,
        quantitative_facts=quantitative_facts,
        confidence=template.confidence,
        occurred_at=template.occurred_at,
        extraction_method="fallback" if fallback else "llm",
    )


def _entries_by_event(
    entries: tuple[_NewsEntry, ...],
) -> tuple[tuple[str, tuple[_NewsEntry, ...]], ...]:
    grouped: dict[str, list[_NewsEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.event_id, []).append(entry)
    return tuple(
        (event_id, tuple(event_entries))
        for event_id, event_entries in grouped.items()
    )


def _read_cached_templates(
    cache_dir: Path,
    content_hash: str,
) -> tuple[tuple[_ClaimTemplate, ...] | None, str]:
    path = claim_cache_path(cache_dir, content_hash)
    if not path.exists():
        return None, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != CLAIM_CACHE_VERSION
            or payload.get("prompt_version") != CLAIM_PROMPT_VERSION
            or payload.get("content_hash") != content_hash
        ):
            raise ValueError("cache metadata mismatch")
        rows = payload.get("claims")
        if not isinstance(rows, list) or not rows:
            raise ValueError("cache claims missing")
        templates = tuple(_template_from_cache(row) for row in rows)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return None, f"claim cache invalid for {content_hash[:12]}: {exc}"
    return templates, ""


def _template_from_cache(value: object) -> _ClaimTemplate:
    if not isinstance(value, dict):
        raise ValueError("claim template must be an object")
    quantitative_rows = value.get("quantitative_facts")
    if not isinstance(quantitative_rows, list):
        raise ValueError("quantitative_facts must be an array")
    return _ClaimTemplate(
        subject=_cache_string(value, "subject"),
        predicate=_cache_string(value, "predicate"),
        object=_cache_string(value, "object"),
        claim_type=cast(
            ClaimType,
            _cache_enum(value, "claim_type", CLAIM_TYPES),
        ),
        event_type=_cache_string(value, "event_type"),
        direction=cast(
            ImpactDirection,
            _cache_enum(value, "direction", IMPACT_DIRECTIONS),
        ),
        time_horizon=cast(
            TimeHorizon,
            _cache_enum(value, "time_horizon", TIME_HORIZONS),
        ),
        affected_symbols=tuple(_cache_string_array(value, "affected_symbols")),
        quantitative_facts=tuple(
            _quantitative_template_from_cache(row) for row in quantitative_rows
        ),
        confidence=cast(
            ConfidenceLevel,
            _cache_enum(value, "confidence", CONFIDENCES),
        ),
        occurred_at=_cache_string(value, "occurred_at", allow_empty=True),
    )


def _quantitative_template_from_cache(value: object) -> _QuantitativeFactTemplate:
    if not isinstance(value, dict):
        raise ValueError("quantitative fact template must be an object")
    number = value.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise ValueError("quantitative fact value must be numeric")
    return _QuantitativeFactTemplate(
        metric=_cache_string(value, "metric"),
        value=float(number),
        unit=_cache_string(value, "unit"),
        period=_cache_string(value, "period", allow_empty=True),
    )


def _cache_string(
    value: dict[str, Any],
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    field_value = value.get(field)
    if not isinstance(field_value, str) or (not allow_empty and not field_value.strip()):
        raise ValueError(f"invalid cached {field}")
    return field_value


def _cache_string_array(value: dict[str, Any], field: str) -> list[str]:
    rows = value.get(field)
    if not isinstance(rows, list) or any(
        not isinstance(row, str) or not row.strip() for row in rows
    ):
        raise ValueError(f"invalid cached {field}")
    return rows


def _cache_enum(value: dict[str, Any], field: str, allowed: set[str]) -> str:
    field_value = _cache_string(value, field)
    if field_value not in allowed:
        raise ValueError(f"invalid cached {field}")
    return field_value


def _write_cached_templates(
    cache_dir: Path,
    content_hash: str,
    templates: tuple[_ClaimTemplate, ...],
) -> None:
    target = claim_cache_path(cache_dir, content_hash)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CLAIM_CACHE_VERSION,
        "prompt_version": CLAIM_PROMPT_VERSION,
        "content_hash": content_hash,
        "claims": [asdict(template) for template in templates],
    }
    _atomic_write_json(payload, target)


def _atomic_write_json(payload: dict[str, Any], target: Path) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
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


def _canonical_url(value: str) -> str:
    if not value.strip():
        return ""
    parts = urlsplit(value.strip())
    query = urlencode(
        sorted(
            (key, item_value)
            for key, item_value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in _TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path,
            query,
            "",
        )
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _excerpt(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _batches(
    values: Sequence[_ContentGroup],
    size: int,
) -> Iterable[tuple[_ContentGroup, ...]]:
    for index in range(0, len(values), size):
        yield tuple(values[index : index + size])
