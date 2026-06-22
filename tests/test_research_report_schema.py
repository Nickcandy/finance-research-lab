import pytest

from finance_research_lab.models import WatchlistItem
from finance_research_lab.research_report_schema import (
    parse_research_report,
    research_report_json_schema,
)


def _valid_payload() -> dict[str, object]:
    return {
        "raw_news": {
            "headline": "AI capex increases",
            "source": "example",
            "url": "",
            "published_at": "",
            "body": "",
        },
        "event": {
            "event_type": "资本开支 / 产能扩张",
            "themes": ["AI", "数据中心"],
            "involved_entities": [],
            "key_facts": ["Microsoft raised capex guidance"],
            "source_quality": "待复核",
            "confidence": "low",
            "reasoning": "Structured agent analysis",
        },
        "value_chain": {
            "payer": "云厂商",
            "receiver": "光模块供应链",
            "chain_steps": ["AI CapEx", "数据中心", "光模块"],
            "impact_direction": "positive",
            "reasoning": "Capex may flow through data center supply chain",
        },
        "stock_impacts": [
            {
                "symbol": "300308.SZ",
                "name": "中际旭创",
                "market": "A股",
                "impact_type": "direct",
                "impact_strength": "high",
                "themes": ["AI", "光模块"],
                "reasoning": "Watchlist themes match the event",
                "evidence": ["Watchlist theme match"],
                "risks": ["估值拥挤"],
            }
        ],
        "validation_tasks": [
            {
                "question": "查官方文件",
                "data_needed": "官方公告",
                "status": "pending",
            }
        ],
        "stage": "待判断",
        "action_state": "等验证",
    }


def test_research_report_json_schema_is_strict() -> None:
    schema = research_report_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "raw_news",
        "event",
        "value_chain",
        "stock_impacts",
        "validation_tasks",
        "stage",
        "action_state",
    }


def test_parse_research_report_accepts_valid_payload() -> None:
    report = parse_research_report(
        _valid_payload(),
        watchlist=[WatchlistItem("300308.SZ", "中际旭创", "A股", ("AI", "光模块"))],
    )

    assert report.raw_news.headline == "AI capex increases"
    assert report.event.themes == ("AI", "数据中心")
    assert report.stock_impacts[0].symbol == "300308.SZ"
    assert report.validation_tasks[0].status == "pending"


def test_parse_research_report_rejects_missing_required_field() -> None:
    payload = _valid_payload()
    del payload["event"]

    with pytest.raises(ValueError, match="Missing required field: event"):
        parse_research_report(payload)


def test_parse_research_report_rejects_invalid_enum() -> None:
    payload = _valid_payload()
    payload["stock_impacts"][0]["impact_type"] = "maybe"

    with pytest.raises(ValueError, match="Invalid stock_impacts.0.impact_type"):
        parse_research_report(payload)


def test_parse_research_report_rejects_unknown_watchlist_symbol() -> None:
    payload = _valid_payload()

    with pytest.raises(ValueError, match="Unknown watchlist symbol"):
        parse_research_report(
            payload,
            watchlist=[WatchlistItem("601059.SH", "信达证券", "A股", ("券商",))],
        )
