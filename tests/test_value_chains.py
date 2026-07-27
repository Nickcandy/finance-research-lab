from finance_research_lab.value_chains import (
    best_value_chain_relation,
    infer_value_chain_nodes,
)
import pytest


def test_ascii_alias_requires_token_boundary() -> None:
    assert not infer_value_chain_nodes("CrowdStrike 发布安全报告")
    assert [node.label for node in infer_value_chain_nodes("CRO 行业订单改善")] == ["药物发现/CRO"]


def test_value_chain_relation_contains_real_shortest_path() -> None:
    company_nodes = infer_value_chain_nodes("公司主营光芯片")
    event_nodes = infer_value_chain_nodes("云厂商扩大数据中心投资")

    relation = best_value_chain_relation(company_nodes, event_nodes)

    assert relation is not None
    assert relation.relation == "上游"
    assert relation.path == ("光芯片", "光模块", "交换机/服务器", "数据中心/云厂商")


@pytest.mark.parametrize(
    ("company_text", "event_text", "expected_distance"),
    [
        ("半导体材料", "智能终端", 4),
        ("机器人减速器", "机器人应用", 3),
        ("锂矿", "新能源汽车", 4),
        ("CRO", "医药商业化", 3),
    ],
)
def test_each_configured_graph_has_an_auditable_directed_path(
    company_text: str,
    event_text: str,
    expected_distance: int,
) -> None:
    relation = best_value_chain_relation(
        infer_value_chain_nodes(company_text),
        infer_value_chain_nodes(event_text),
    )

    assert relation is not None
    assert relation.distance == expected_distance
    assert len(relation.path) == expected_distance + 1
