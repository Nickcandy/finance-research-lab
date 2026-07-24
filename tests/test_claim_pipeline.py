from __future__ import annotations

import json
from typing import Any

from finance_research_lab.claim_pipeline import (
    CLAIM_EXTRACTION_SYSTEM_PROMPT,
    ClaimPipeline,
    claim_cache_path,
    news_content_hash,
    news_origin_key,
    stable_news_item_id,
)
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.llm.base import LLMResponse
from finance_research_lab.models import MarketEvent, NewsItem


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def structured_completion(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, LLMResponse):
            return outcome
        if callable(outcome):
            outcome = outcome(kwargs)
        return LLMResponse(json.dumps(outcome, ensure_ascii=False), "flash-test")


def _news(
    headline: str,
    *,
    source: str = "测试媒体",
    url: str = "",
    published_at: str = "2026-07-24T08:00:00+08:00",
    body: str = "正文",
    source_type: str = "news",
) -> NewsItem:
    return NewsItem(
        headline=headline,
        source=source,
        url=url,
        published_at=published_at,
        body=body,
        source_type=source_type,  # type: ignore[arg-type]
    )


def _event(news: NewsItem) -> MarketEvent:
    return MarketEvent(news.headline, (news,))


def _response_from_request(
    kwargs: dict[str, Any],
    *,
    quantitative: bool = False,
) -> dict[str, object]:
    payload = json.loads(kwargs["messages"][-1]["content"])
    claims: list[dict[str, object]] = []
    for item in payload["items"]:
        quantitative_facts: list[dict[str, object]] = []
        if quantitative:
            quantitative_facts.append(
                {
                    "metric": "contract_amount",
                    "value": 20,
                    "unit": "亿元",
                    "period": "三年",
                    "source_item_id": item["item_id"],
                }
            )
        claims.append(
            {
                "event_id": item["event_id"],
                "source_item_ids": [item["item_id"]],
                "subject": item["headline"],
                "predicate": "签订",
                "object": "重大合同",
                "claim_type": "fact",
                "event_type": "订单 / 合同",
                "direction": "positive",
                "time_horizon": "medium",
                "affected_symbols": ["300308.SZ"],
                "quantitative_facts": quantitative_facts,
                "confidence": "high",
                "occurred_at": item["published_at"],
            }
        )
    return {"claims": claims}


def test_news_identity_is_stable_and_removes_tracking_parameters() -> None:
    first = _news(
        " 重大合同 ",
        url="HTTPS://Example.COM/news/1?utm_source=x&id=2#fragment",
        body="公司  签订 20 亿元合同",
    )
    second = _news(
        "重大合同",
        url="https://example.com/news/1?id=2",
        body="公司 签订 20 亿元合同",
    )

    assert stable_news_item_id(first) == stable_news_item_id(second)
    assert news_content_hash(first) == news_content_hash(second)
    assert news_origin_key(first) == news_origin_key(second)
    assert news_origin_key(first) == "url:https://example.com/news/1?id=2"


def test_pipeline_extracts_quantitative_claims_and_reuses_cache(tmp_path) -> None:
    news = _news("公司签订重大合同", body="公司签订 20 亿元合同，分三年执行。")
    event = _event(news)
    client = _Client([lambda kwargs: _response_from_request(kwargs, quantitative=True)])
    pipeline = ClaimPipeline(client, tmp_path / "claims", batch_size=10)

    first = pipeline.extract((event,))
    second = pipeline.extract((event,))

    assert len(client.calls) == 1
    assert first.claims == second.claims
    assert second.cache_hits == 1
    assert second.fallback_count == 0
    assert first.claims[0].event_id == market_event_id(event)
    assert first.claims[0].source_item_ids == (stable_news_item_id(news),)
    assert first.claims[0].quantitative_facts[0].value == 20
    assert first.claims[0].quantitative_facts[0].unit == "亿元"
    assert first.claims[0].quantitative_facts[0].source_item_id == stable_news_item_id(news)


def test_pipeline_retries_invalid_json_once(tmp_path) -> None:
    event = _event(_news("重大合同"))
    client = _Client(
        [
            LLMResponse("not json", "unused"),
            lambda kwargs: _response_from_request(kwargs),
        ]
    )
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    result = pipeline.extract((event,))

    assert len(client.calls) == 2
    assert result.fallback_count == 0
    assert result.batches[0].status == "success"
    assert any("retry" in warning for warning in result.warnings)


def test_pipeline_retries_claim_with_missing_required_field(tmp_path) -> None:
    event = _event(_news("重大合同"))

    def missing_predicate(kwargs: dict[str, Any]) -> dict[str, object]:
        response = _response_from_request(kwargs)
        claims = response["claims"]
        assert isinstance(claims, list)
        del claims[0]["predicate"]
        return response

    client = _Client(
        [
            missing_predicate,
            lambda kwargs: _response_from_request(kwargs),
        ]
    )
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    result = pipeline.extract((event,))

    assert len(client.calls) == 2
    assert result.fallback_count == 0
    assert any("Missing required field" in warning for warning in result.warnings)


def test_pipeline_falls_back_after_second_failure(tmp_path) -> None:
    news = _news("传闻公司或获重大订单", body="市场传闻，尚无明确来源。")
    client = _Client([RuntimeError("timeout"), ValueError("invalid JSON")])
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    result = pipeline.extract((_event(news),))

    assert len(client.calls) == 2
    assert result.fallback_count == 1
    assert result.claims[0].extraction_method == "fallback"
    assert result.batches[0].status == "fallback"
    assert result.claims[0].claim_type == "opinion"
    assert result.claims[0].confidence == "low"
    assert result.claims[0].affected_symbols == ()
    assert not claim_cache_path(tmp_path / "claims", news_content_hash(news)).exists()


def test_one_failed_batch_does_not_drop_other_batches(tmp_path) -> None:
    events = tuple(_event(_news(f"事件 {index}")) for index in range(3))
    client = _Client(
        [
            lambda kwargs: _response_from_request(kwargs),
            RuntimeError("timeout"),
            RuntimeError("timeout again"),
            lambda kwargs: _response_from_request(kwargs),
        ]
    )
    pipeline = ClaimPipeline(client, tmp_path / "claims", batch_size=1)

    result = pipeline.extract(events)

    assert len(result.claims) == 3
    assert [batch.status for batch in result.batches] == [
        "success",
        "fallback",
        "success",
    ]
    assert result.fallback_count == 1


def test_missing_item_in_valid_response_uses_partial_fallback(tmp_path) -> None:
    events = tuple(_event(_news(f"事件 {index}")) for index in range(2))

    def first_only(kwargs: dict[str, Any]) -> dict[str, object]:
        response = _response_from_request(kwargs)
        response["claims"] = response["claims"][:1]  # type: ignore[index]
        return response

    client = _Client([first_only])
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    result = pipeline.extract(events)

    assert len(result.claims) == 2
    assert result.batches[0].status == "partial"
    assert result.fallback_count == 1


def test_corrupted_cache_warns_and_is_rebuilt_atomically(tmp_path) -> None:
    news = _news("重大合同")
    cache_dir = tmp_path / "claims"
    path = claim_cache_path(cache_dir, news_content_hash(news))
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    client = _Client([lambda kwargs: _response_from_request(kwargs)])
    pipeline = ClaimPipeline(client, cache_dir)

    result = pipeline.extract((_event(news),))

    assert len(client.calls) == 1
    assert any("cache" in warning and "invalid" in warning for warning in result.warnings)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "1.0"
    assert not list(cache_dir.glob("*.tmp"))


def test_cache_write_failure_keeps_extracted_claims(tmp_path, monkeypatch) -> None:
    news = _news("重大合同")
    client = _Client([lambda kwargs: _response_from_request(kwargs)])
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    def fail_write(*args: object) -> None:
        del args
        raise OSError("disk full")

    monkeypatch.setattr(
        "finance_research_lab.claim_pipeline._atomic_write_json",
        fail_write,
    )

    result = pipeline.extract((_event(news),))

    assert len(result.claims) == 1
    assert result.batches[0].status == "success"
    assert any("cache write failed" in warning for warning in result.warnings)


def test_duplicate_content_is_sent_once_and_keeps_all_source_ids(tmp_path) -> None:
    first = _news(
        "重大合同",
        source="媒体 A",
        url="https://a.example.com/1",
        body="公司签订重大合同。",
    )
    second = _news(
        "重大合同",
        source="媒体 B",
        url="https://b.example.com/2",
        body="公司签订重大合同。",
    )
    event = MarketEvent("重大合同", (first, second))
    client = _Client([lambda kwargs: _response_from_request(kwargs)])
    pipeline = ClaimPipeline(client, tmp_path / "claims")

    result = pipeline.extract((event,))

    request_payload = json.loads(client.calls[0]["messages"][-1]["content"])
    assert len(request_payload["items"]) == 1
    assert len(result.claims) == 1
    assert result.claims[0].source_item_ids == (
        stable_news_item_id(first),
        stable_news_item_id(second),
    )


def test_prompt_is_self_contained_and_body_excerpt_is_bounded(tmp_path) -> None:
    long_body = "数字20亿元。" * 100
    news = _news("重大合同", body=long_body)
    client = _Client([lambda kwargs: _response_from_request(kwargs)])
    pipeline = ClaimPipeline(client, tmp_path / "claims", body_char_limit=200)

    pipeline.extract((_event(news),))

    messages = client.calls[0]["messages"]
    payload = json.loads(messages[-1]["content"])
    assert len(messages) == 2
    assert messages[0] == {
        "role": "system",
        "content": CLAIM_EXTRACTION_SYSTEM_PROMPT,
    }
    assert messages[1]["role"] == "user"
    assert len(payload["items"][0]["body_excerpt"]) == 200
    assert "不得补造" in messages[0]["content"]
    assert "最终" in messages[0]["content"]
