"""GraphRAG 리트리버 -- 자연어 질의에서 엔터티를 찾아 k-hop 서브그래프를 뽑아낸다.

전형적인 GraphRAG의 "local search" 경로: (1) 질의에서 시드 노드를 식별하고,
(2) 그 이웃을 hop 단위로 확장하고, (3) 서브그래프를 (source, relation, target)
사실(facts)로 직렬화해 LLM 프롬프트/구조화 응답 양쪽에 넣을 수 있게 한다.
임베딩 인덱스 없이 결정론적 문자열 매칭만 쓰므로 API 키 없이도 항상 동작한다.
"""
from __future__ import annotations

import re

import networkx as nx

_ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+){1,4}\b")


def _label(g: nx.MultiDiGraph, node: str) -> str:
    attrs = g.nodes.get(node, {})
    return str(attrs.get("name") or attrs.get("product_node") or node)


def find_seed_nodes(g: nx.MultiDiGraph, query: str, limit: int = 5) -> list[str]:
    seeds: list[str] = []

    for match in _ID_PATTERN.finditer(query.upper()):
        node_id = match.group(0)
        if g.has_node(node_id) and node_id not in seeds:
            seeds.append(node_id)

    if len(seeds) < limit:
        tokens = [tok for tok in re.split(r"[\s,./]+", query) if len(tok) >= 2]
        for node, attrs in g.nodes(data=True):
            if node in seeds:
                continue
            label = str(attrs.get("name") or "")
            if not label:
                continue
            if label in query or any(tok and (tok in label or label in tok) for tok in tokens):
                seeds.append(node)
            if len(seeds) >= limit:
                break

    return seeds[:limit]


def khop_subgraph(
    g: nx.MultiDiGraph,
    seeds: list[str],
    hops: int = 2,
    max_nodes: int = 40,
    max_same_type_per_hop: int = 6,
) -> nx.MultiDiGraph:
    """시드에서 hop 단위로 이웃을 확장하되, 팬아웃이 큰 허브(공정/챔버 하나에
    수백 개 로트가 물려 있는 경우)가 동일 타입 이웃으로 예산을 전부 잠식해
    에이전트/결함 같은 다른 엔터티 타입을 밀어내지 않도록 타입별로 캡을 건다."""
    nodes = set(seeds)
    frontier = set(seeds)
    for _ in range(hops):
        if not frontier or len(nodes) >= max_nodes:
            break
        neighbors: set[str] = set()
        for n in frontier:
            if n not in g:
                continue
            neighbors |= set(g.successors(n)) | set(g.predecessors(n))
        neighbors -= nodes

        by_type: dict[str, list[str]] = {}
        for node in sorted(neighbors):
            node_type = g.nodes[node].get("type", "unknown")
            by_type.setdefault(node_type, []).append(node)
        capped: set[str] = set()
        for node_type, members in by_type.items():
            limit = max_same_type_per_hop if node_type == "lot" else len(members)
            capped.update(members[:limit])

        budget = max_nodes - len(nodes)
        if len(capped) > budget:
            capped = set(list(capped)[:budget])
        nodes |= capped
        frontier = capped
    return g.subgraph(nodes)


def describe_subgraph(g: nx.MultiDiGraph, sub: nx.MultiDiGraph) -> dict:
    facts = []
    seen_facts: set[tuple] = set()
    for u, v, data in sub.edges(data=True):
        relation = data.get("relation", "related_to")
        key = (u, relation, v)
        if key in seen_facts:
            continue
        seen_facts.add(key)
        facts.append({
            "source": _label(g, u),
            "source_id": u,
            "relation": relation,
            "target": _label(g, v),
            "target_id": v,
        })
    nodes_info = []
    for node, attrs in sub.nodes(data=True):
        info = {"id": node, "label": _label(g, node)}
        info.update({k: v for k, v in attrs.items() if k != "name"})
        nodes_info.append(info)
    return {"nodes": nodes_info, "facts": facts}


def retrieve(g: nx.MultiDiGraph, query: str, hops: int = 2, max_nodes: int = 40) -> dict:
    seeds = find_seed_nodes(g, query)
    if not seeds:
        return {"seed_nodes": [], "nodes": [], "facts": [], "context_text": ""}

    sub = khop_subgraph(g, seeds, hops=hops, max_nodes=max_nodes)
    described = describe_subgraph(g, sub)
    context_lines = [
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in described["facts"]
    ]
    return {
        "seed_nodes": [
            {"id": s, "label": _label(g, s), "type": g.nodes.get(s, {}).get("type", "unknown")}
            for s in seeds
        ],
        "nodes": described["nodes"],
        "facts": described["facts"],
        "context_text": "\n".join(context_lines[:60]),
    }
