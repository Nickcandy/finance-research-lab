from __future__ import annotations

from finance_research_lab.claim_pipeline import stable_news_item_id
from finance_research_lab.claims import Claim, QuantitativeFact
from finance_research_lab.daily_radar_snapshot import market_event_id
from finance_research_lab.impact_horizon import assess_directional_horizons
from finance_research_lab.models import MarketEvent, NewsItem


def _event(
    title: str,
    *,
    body: str = "",
    source_type: str = "announcement",
) -> MarketEvent:
    return MarketEvent(
        title,
        (
            NewsItem(
                headline=title,
                source="测试来源",
                url="https://example.com/news",
                published_at="2026-07-24T08:00:00+08:00",
                body=body,
                source_type=source_type,  # type: ignore[arg-type]
            ),
        ),
    )


def _claim(
    event: MarketEvent,
    *,
    event_type: str,
    direction: str = "positive",
    time_horizon: str = "unknown",
    confidence: str = "high",
    period: str = "",
    claim_type: str = "fact",
) -> Claim:
    item_id = stable_news_item_id(event.items[0])
    facts = (
        (
            QuantitativeFact(
                metric="履行期限",
                value=0,
                unit="",
                period=period,
                source_item_id=item_id,
            ),
        )
        if period
        else ()
    )
    return Claim(
        id=f"claim:{direction}:{event_type}",
        event_id=market_event_id(event),
        source_item_ids=(item_id,),
        subject="测试公司",
        predicate="发生",
        object=f"{event_type}事项",
        claim_type=claim_type,  # type: ignore[arg-type]
        event_type=event_type,
        direction=direction,  # type: ignore[arg-type]
        time_horizon=time_horizon,  # type: ignore[arg-type]
        affected_symbols=("300308.SZ",),
        quantitative_facts=facts,
        confidence=confidence,  # type: ignore[arg-type]
        occurred_at="2026-07-24",
    )


def test_order_uses_short_market_and_long_fundamental_defaults() -> None:
    event = _event("公司签订重大合同")
    horizons = assess_directional_horizons(
        event,
        (_claim(event, event_type="订单 / 合同"),),
        verified_relation=True,
    )

    assert horizons is not None
    assert horizons.market.category == "short"
    assert (horizons.market.min_duration, horizons.market.max_duration) == (6, 20)
    assert horizons.market.unit == "trading_day"
    assert horizons.fundamental.category == "long"
    assert (horizons.fundamental.min_duration, horizons.fundamental.max_duration) == (6, 24)
    assert horizons.fundamental.unit == "calendar_month"
    assert horizons.market.confidence == "medium"


def test_explicit_multi_year_period_overrides_claim_horizon() -> None:
    event = _event("公司签订长期合同")
    claim = _claim(
        event,
        event_type="订单 / 合同",
        time_horizon="short",
        period="2026-2029",
    )

    horizons = assess_directional_horizons(event, (claim,), verified_relation=True)

    assert horizons is not None
    assert horizons.fundamental.category == "structural"
    assert horizons.fundamental.min_duration == 36
    assert horizons.fundamental.max_duration == 36
    assert horizons.fundamental.confidence == "high"
    assert horizons.fundamental.basis == ("原文明确周期：2026-2029",)
    assert horizons.fundamental.evidence_refs == (f"claim:{claim.id}",)


def test_market_reaction_with_explicit_trading_days_uses_exact_range() -> None:
    event = _event("板块短期异动", source_type="finance_news")
    claim = _claim(
        event,
        event_type="纯情绪题材",
        claim_type="market_reaction",
        period="3-10个交易日",
    )

    horizons = assess_directional_horizons(event, (claim,), verified_relation=False)

    assert horizons is not None
    assert horizons.market.category == "short"
    assert (horizons.market.min_duration, horizons.market.max_duration) == (3, 10)
    assert horizons.market.confidence == "medium"
    assert horizons.fundamental.category == "unknown"


def test_unknown_event_does_not_invent_fundamental_duration() -> None:
    event = _event("缺少执行信息", source_type="finance_news")
    horizons = assess_directional_horizons(
        event,
        (_claim(event, event_type="待判断", confidence="low"),),
        verified_relation=False,
    )

    assert horizons is not None
    assert horizons.market.category == "unknown"
    assert horizons.market.confidence == "unknown"
    assert horizons.fundamental.category == "unknown"
    assert horizons.fundamental.min_duration is None
    assert horizons.fundamental.max_duration is None
    assert horizons.fundamental.unit == "unknown"


def test_claim_horizon_precedes_event_default_for_both_layers() -> None:
    event = _event("公司签订重大合同")
    horizons = assess_directional_horizons(
        event,
        (
            _claim(
                event,
                event_type="订单 / 合同",
                time_horizon="medium",
            ),
        ),
        verified_relation=True,
    )

    assert horizons is not None
    assert horizons.market.category == "medium"
    assert horizons.fundamental.category == "medium"


def test_no_directional_claim_has_no_horizon() -> None:
    assert assess_directional_horizons(_event("空事件"), (), verified_relation=True) is None


def test_event_type_controls_invalidation_conditions() -> None:
    event = _event("扩产项目")
    horizons = assess_directional_horizons(
        event,
        (_claim(event, event_type="资本开支 / 扩产"),),
        verified_relation=True,
    )

    assert horizons is not None
    assert horizons.fundamental.invalidation_conditions == (
        "项目延期或取消",
        "投产爬坡或产能利用率明显低于预期",
    )


def test_conflicting_explicit_periods_choose_longer_and_lower_confidence() -> None:
    event = _event("合同周期存在冲突")
    horizons = assess_directional_horizons(
        event,
        (
            _claim(event, event_type="订单 / 合同", period="1个月"),
            _claim(event, event_type="重大合同", period="2026-2029"),
        ),
        verified_relation=True,
    )

    assert horizons is not None
    assert horizons.fundamental.category == "structural"
    assert horizons.fundamental.confidence == "medium"


def test_adjacent_claim_horizons_choose_longer_and_lower_confidence() -> None:
    event = _event("订单周期判断存在冲突")
    horizons = assess_directional_horizons(
        event,
        (
            _claim(event, event_type="订单 / 合同", time_horizon="short"),
            _claim(event, event_type="重大合同", time_horizon="medium"),
        ),
        verified_relation=True,
    )

    assert horizons is not None
    assert horizons.market.category == "medium"
    assert horizons.market.confidence == "medium"
    assert horizons.fundamental.category == "medium"
    assert horizons.fundamental.confidence == "medium"
