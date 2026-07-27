from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_VALUE_CHAIN_PATH = Path("data/value_chains.json")


@dataclass(frozen=True)
class ValueChainNode:
    chain_id: str
    chain_label: str
    node_id: str
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ValueChainRelation:
    chain_label: str
    company_node: str
    event_node: str
    relation: str
    distance: int
    path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValueChainGraph:
    chain_id: str
    label: str
    nodes: tuple[ValueChainNode, ...]
    edges: tuple[tuple[str, str], ...]

    def node(self, node_id: str) -> ValueChainNode:
        return next(node for node in self.nodes if node.node_id == node_id)


def normalize_semantic_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


@lru_cache(maxsize=4)
def load_value_chains(path: str | Path = DEFAULT_VALUE_CHAIN_PATH) -> tuple[ValueChainGraph, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("chains"), list):
        raise ValueError("invalid value-chain configuration")
    graphs: list[ValueChainGraph] = []
    for raw_chain in payload["chains"]:
        chain_id = _required_text(raw_chain, "id")
        label = _required_text(raw_chain, "label")
        raw_nodes = raw_chain.get("nodes")
        raw_edges = raw_chain.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError(f"invalid value-chain nodes or edges: {chain_id}")
        nodes = tuple(
            ValueChainNode(
                chain_id=chain_id,
                chain_label=label,
                node_id=_required_text(raw_node, "id"),
                label=_required_text(raw_node, "label"),
                aliases=tuple(
                    _required_text({"value": alias}, "value")
                    for alias in raw_node.get("aliases", [])
                ),
            )
            for raw_node in raw_nodes
        )
        node_ids = {node.node_id for node in nodes}
        edges: list[tuple[str, str]] = []
        for edge in raw_edges:
            if (
                not isinstance(edge, list)
                or len(edge) != 2
                or not all(isinstance(item, str) for item in edge)
            ):
                raise ValueError(f"invalid value-chain edge: {chain_id}")
            if edge[0] not in node_ids or edge[1] not in node_ids:
                raise ValueError(f"unknown value-chain node in edge: {chain_id}")
            edges.append((edge[0], edge[1]))
        graphs.append(ValueChainGraph(chain_id, label, nodes, tuple(edges)))
    return tuple(graphs)


def infer_value_chain_nodes(
    text: str,
    graphs: tuple[ValueChainGraph, ...] | None = None,
) -> tuple[ValueChainNode, ...]:
    if not text.strip():
        return ()
    normalized_text = unicodedata.normalize("NFKC", text).casefold()
    semantic_text = "".join(
        character for character in normalized_text if character.isalnum()
    )
    matches: list[ValueChainNode] = []
    for graph in graphs or load_value_chains():
        for node in graph.nodes:
            terms = (node.label, *node.aliases)
            if any(
                _term_matches(normalized_text, semantic_text, term)
                for term in terms
            ):
                matches.append(node)
    return tuple(matches)


def canonical_theme_labels(texts: tuple[str, ...]) -> tuple[str, ...]:
    matches = infer_value_chain_nodes(" ".join(texts))
    return tuple(dict.fromkeys(node.label for node in matches))


def best_value_chain_relation(
    company_nodes: tuple[ValueChainNode, ...],
    event_nodes: tuple[ValueChainNode, ...],
    graphs: tuple[ValueChainGraph, ...] | None = None,
) -> ValueChainRelation | None:
    graph_by_id = {graph.chain_id: graph for graph in (graphs or load_value_chains())}
    candidates: list[ValueChainRelation] = []
    for company_node in company_nodes:
        for event_node in event_nodes:
            if company_node.chain_id != event_node.chain_id:
                continue
            graph = graph_by_id[company_node.chain_id]
            if company_node.node_id == event_node.node_id:
                candidates.append(
                    ValueChainRelation(
                        graph.label,
                        company_node.label,
                        event_node.label,
                        "同环节",
                        0,
                        (company_node.label,),
                    )
                )
                continue
            upstream_path = _shortest_path(graph.edges, company_node.node_id, event_node.node_id)
            if upstream_path is not None:
                candidates.append(
                    ValueChainRelation(
                        graph.label,
                        company_node.label,
                        event_node.label,
                        "上游",
                        len(upstream_path) - 1,
                        tuple(graph.node(node_id).label for node_id in upstream_path),
                    )
                )
            downstream_path = _shortest_path(graph.edges, event_node.node_id, company_node.node_id)
            if downstream_path is not None:
                candidates.append(
                    ValueChainRelation(
                        graph.label,
                        company_node.label,
                        event_node.label,
                        "下游",
                        len(downstream_path) - 1,
                        tuple(graph.node(node_id).label for node_id in downstream_path),
                    )
                )
    if not candidates:
        return None
    relation_order = {"同环节": 0, "上游": 1, "下游": 1}
    return min(
        candidates,
        key=lambda item: (
            relation_order[item.relation],
            item.distance,
            item.chain_label,
            item.company_node,
            item.event_node,
        ),
    )


def _shortest_path(
    edges: tuple[tuple[str, str], ...],
    start: str,
    end: str,
) -> tuple[str, ...] | None:
    neighbors: dict[str, list[str]] = {}
    for source, target in edges:
        neighbors.setdefault(source, []).append(target)
    frontier = [(start, (start,))]
    seen = {start}
    while frontier:
        node, path = frontier.pop(0)
        for target in neighbors.get(node, []):
            if target == end:
                return (*path, target)
            if target not in seen:
                seen.add(target)
                frontier.append((target, (*path, target)))
    return None


def _term_matches(normalized_text: str, semantic_text: str, term: str) -> bool:
    normalized_term = unicodedata.normalize("NFKC", term).casefold().strip()
    if not normalized_term:
        return False
    if any("\u4e00" <= character <= "\u9fff" for character in normalized_term):
        return normalize_semantic_text(normalized_term) in semantic_text
    return (
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
            normalized_text,
        )
        is not None
    )


def _required_text(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        raise ValueError("expected value-chain object")
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing value-chain field: {key}")
    return value.strip()
