from types import SimpleNamespace

from finance_research_lab.event_brief import build_auditable_value_chain
from finance_research_lab.models import AShareCompany, MarketEvent, NewsItem


def test_value_chain_selects_verified_company_by_magnitude_then_symbol() -> None:
    event = MarketEvent(
        "云厂商扩建数据中心",
        (NewsItem("云厂商扩建数据中心", "公告"),),
    )
    claim = SimpleNamespace(
        id="claim-1",
        subject="云厂商",
        predicate="扩建",
        object="数据中心",
        event_type="资本开支",
    )
    ledgers = (
        SimpleNamespace(verified=True, symbol="300002.SZ", claims=(claim,)),
        SimpleNamespace(verified=True, symbol="300001.SZ", claims=(claim,)),
    )
    assessments = (
        SimpleNamespace(
            symbol="300002.SZ",
            positive_magnitude=80,
            negative_magnitude=0,
            confidence=70,
            direction="positive",
        ),
        SimpleNamespace(
            symbol="300001.SZ",
            positive_magnitude=80,
            negative_magnitude=0,
            confidence=70,
            direction="positive",
        ),
    )
    universe = [
        AShareCompany("300002.SZ", "乙公司", "A股", themes=("光芯片",)),
        AShareCompany("300001.SZ", "甲公司", "A股", themes=("光芯片",)),
    ]

    chain = build_auditable_value_chain(
        event,
        (claim,),
        ledgers,
        assessments,
        universe,
    )

    assert chain.chain_steps == (
        "光芯片",
        "光模块",
        "交换机/服务器",
        "数据中心/云厂商",
    )
    assert "300001.SZ" in chain.reasoning
    assert "claim-1" in chain.reasoning
    assert chain.payer == chain.receiver == ""


def test_value_chain_keeps_unknown_single_node_and_multi_graph_distinct() -> None:
    unknown = MarketEvent(
        "CrowdStrike 发布安全报告",
        (NewsItem("CrowdStrike 发布安全报告", "媒体"),),
    )
    single = MarketEvent(
        "动力电池价格上涨",
        (NewsItem("动力电池价格上涨", "媒体"),),
    )
    conflict = MarketEvent(
        "数据中心采购动力电池",
        (NewsItem("数据中心采购动力电池", "媒体"),),
    )

    assert build_auditable_value_chain(unknown, (), (), (), []).chain_steps == ()
    assert build_auditable_value_chain(single, (), (), (), []).chain_steps == ("电芯",)
    conflicted = build_auditable_value_chain(conflict, (), (), (), [])
    assert conflicted.chain_steps == ()
    assert "无法可靠消歧" in conflicted.reasoning
