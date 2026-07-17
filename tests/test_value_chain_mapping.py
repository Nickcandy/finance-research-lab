from __future__ import annotations

from finance_research_lab.models import AShareCompany, NewsItem, StockImpact
from finance_research_lab.news_trace import build_research_report, verify_research_report_candidates


def test_cpo_event_maps_same_node_and_upstream_in_stable_order() -> None:
    news = NewsItem("CPO需求增长，800G光模块景气度提升", "同花顺")
    companies = [
        AShareCompany(
            "300502.SZ",
            "新易盛",
            "A股",
            themes=("光模块",),
            business_summary="高速光模块",
            source="baostock+akshare",
        ),
        AShareCompany(
            "688048.SH",
            "长光华芯",
            "A股",
            themes=("光芯片",),
            business_summary="半导体激光器芯片",
            source="baostock+akshare",
        ),
        AShareCompany(
            "000063.SZ",
            "中兴通讯",
            "A股",
            industry="C39电子设备制造业",
            source="baostock+akshare",
        ),
    ]

    forward = build_research_report(news, [], companies).stock_impacts
    reverse = build_research_report(news, [], list(reversed(companies))).stock_impacts

    assert [impact.symbol for impact in forward] == ["300502.SZ", "688048.SH"]
    assert [impact.symbol for impact in reverse] == ["300502.SZ", "688048.SH"]
    assert forward[0].impact_type == "direct"
    assert "关系=同环节" in forward[0].evidence[-1]
    assert forward[1].impact_type == "indirect"
    assert "关系=上游" in forward[1].evidence[-1]


def test_storage_event_maps_demingly_to_canonical_symbol() -> None:
    news = NewsItem("SSD和嵌入式存储需求回暖", "同花顺")
    company = AShareCompany(
        "001309.SZ",
        "德明利",
        "A股",
        themes=("SSD/存储模组",),
        business_summary="固态硬盘、嵌入式存储和内存条",
        source="baostock+akshare",
    )
    report = build_research_report(news, [], [company])

    assert [impact.symbol for impact in report.stock_impacts] == ["001309.SZ"]
    assert report.stock_impacts[0].verification_status == "verified"


def test_llm_candidate_without_local_relation_stays_unverified() -> None:
    news = NewsItem("光模块需求增长", "同花顺")
    proposed = StockImpact(
        "600519.SH",
        "贵州茅台",
        "A股",
        "direct",
        "high",
        reasoning="LLM guess",
    )
    report = build_research_report(news, [], proposed_impacts=(proposed,))

    verified = verify_research_report_candidates(
        report,
        [],
        [
            AShareCompany(
                "600519.SH",
                "贵州茅台",
                "A股",
                industry="酒、饮料和精制茶制造业",
                business_summary="白酒生产和销售",
                source="baostock+akshare",
            )
        ],
    )

    assert verified.stock_impacts[0].verification_status == "unverified"
