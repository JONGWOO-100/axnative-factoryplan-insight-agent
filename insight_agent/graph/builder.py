"""GraphRAG 지식 그래프 빌더 -- dataset_2의 스타 스키마를 노드/엣지 그래프로 재구성한다.

임베딩/외부 인덱싱 서비스 없이, FK 관계로부터 결정론적으로 그래프를 만든다.
데이터가 작기 때문에(로트 1,500 / FDC 2,500 / 차원 <20건) 전체 그래프를 한 번에
메모리에 올려도 충분하다. `domain.py`가 CSV 스키마 지식을 캡슐화하듯, 이 모듈은
그래프 구조 지식을 캡슐화한다 -- 다른 레이어는 이 모듈을 거쳐야 그래프에 접근한다.
"""
from __future__ import annotations

import networkx as nx

from insight_agent.domain import Tables

NODE_TYPE_PROCESS = "process"
NODE_TYPE_AGENT = "agent"
NODE_TYPE_LAKE = "lake"
NODE_TYPE_CHAMBER = "chamber"
NODE_TYPE_LOT = "lot"
NODE_TYPE_DEFECT = "defect"


def defect_node_id(mechanism: str) -> str:
    return f"DEFECT::{mechanism}"


def build_graph(tables: Tables) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()

    for _, row in tables.dim_process_design.iterrows():
        g.add_node(
            row["process_id"],
            type=NODE_TYPE_PROCESS,
            name=row["process_name"],
            design_technology=row["design_technology"],
            target_cpk=float(row["target_cpk"]),
        )

    for _, row in tables.dim_ai_automation_role.iterrows():
        g.add_node(
            row["agent_id"],
            type=NODE_TYPE_AGENT,
            name=row["agent_name"],
            core_responsibility=row["core_responsibility"],
            ai_algorithm_stack=row["ai_algorithm_stack"],
        )

    for _, row in tables.dim_semicon_dx_architecture.iterrows():
        g.add_node(
            row["data_lake_id"],
            type=NODE_TYPE_LAKE,
            name=row["dataset_name"],
            lake_layer=row["lake_layer"],
        )

    chamber_ids = set(tables.fact_fdc_chamber_sensor["chamber_id"].unique()) | set(
        tables.dim_process_design["target_chamber_unit"].unique()
    )
    for chamber_id in chamber_ids:
        g.add_node(chamber_id, type=NODE_TYPE_CHAMBER, name=chamber_id)

    defect_names = set(tables.fact_wafer_lot_yield["major_defect_mechanism"].unique()) - {"None(Clean)"}
    for name in defect_names:
        g.add_node(defect_node_id(name), type=NODE_TYPE_DEFECT, name=name)

    for _, row in tables.dim_process_design.iterrows():
        g.add_edge(row["process_id"], row["target_chamber_unit"], relation="designed_for")

    for _, row in tables.fact_wafer_lot_yield.iterrows():
        g.add_node(
            row["lot_id"],
            type=NODE_TYPE_LOT,
            name=row["lot_id"],
            product_node=row["product_node"],
            company_name=row["company_name"],
            die_yield_pct=float(row["die_yield_pct"]),
            wafer_yield_pct=float(row["wafer_yield_pct"]),
            production_date=str(row["production_date"]),
        )
        if row["major_defect_mechanism"] != "None(Clean)":
            g.add_edge(row["lot_id"], defect_node_id(row["major_defect_mechanism"]), relation="exhibits")

    # MultiDiGraph는 add_edge를 부를 때마다 병렬 엣지를 새로 만든다 -- lot_id별로
    # 유니크한 (process, chamber, agent) 관계를 chamber<->agent 같은 허브 관계에
    # 그대로 적용하면 같은 두 노드 사이에 수백 개의 중복 엣지가 생긴다. 관계
    # 종류별로 실제 유니크한 쌍만 남도록 별도의 seen 집합으로 관리한다.
    seen_lot_process: set[tuple] = set()
    seen_lot_chamber: set[tuple] = set()
    seen_chamber_agent: set[tuple] = set()
    seen_interlock: set[tuple] = set()
    for _, row in tables.fact_fdc_chamber_sensor.iterrows():
        lot_process = (row["lot_id"], row["process_id"])
        if lot_process not in seen_lot_process:
            seen_lot_process.add(lot_process)
            g.add_edge(row["lot_id"], row["process_id"], relation="processed_by")

        lot_chamber = (row["lot_id"], row["chamber_id"])
        if lot_chamber not in seen_lot_chamber:
            seen_lot_chamber.add(lot_chamber)
            g.add_edge(row["lot_id"], row["chamber_id"], relation="processed_in")

        chamber_agent = (row["chamber_id"], row["controlling_ai_agent"])
        if chamber_agent not in seen_chamber_agent:
            seen_chamber_agent.add(chamber_agent)
            g.add_edge(row["chamber_id"], row["controlling_ai_agent"], relation="controlled_by")

        if bool(row["fdc_interlock_flag"]) and lot_chamber not in seen_interlock:
            seen_interlock.add(lot_chamber)
            g.add_edge(row["lot_id"], row["chamber_id"], relation="interlock_event")

    return g


def graph_stats(g: nx.MultiDiGraph) -> dict:
    type_counts: dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        t = attrs.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    return {
        "node_count": g.number_of_nodes(),
        "edge_count": g.number_of_edges(),
        "node_types": type_counts,
    }
