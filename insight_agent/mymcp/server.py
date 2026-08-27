"""dataset_2 조회 전용 MCP 서버 -- FastMCP 기반, 로컬 stdio로 실행한다.

도메인 로직은 전부 domain.py/graph/에 있고, 이 파일은 FastMCP의 @mcp.tool
데코레이터로 그 함수들을 MCP 툴로 노출하는 얇은 어댑터다.

실행:
    python -m insight_agent.mymcp.server

Claude Code에 등록하려면 .mcp.json에 다음과 같이 추가한다:
    {
      "mcpServers": {
        "electronics-insight": {
          "command": "python",
          "args": ["-m", "insight_agent.mymcp.server"],
          "cwd": "/path/to/electronics-insight-agent"
        }
      }
    }

Codex CLI/Desktop에 등록하려면 README의 "Codex CLI/Desktop 연동" 절과
codex/config.toml 스니펫을 참고해 ~/.codex/config.toml에 [mcp_servers.*]
테이블로 병합한다 (Codex는 프로젝트 스코프 자동 등록 파일이 없다).
"""
from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from insight_agent import domain
from insight_agent.config import DATASET_DIR, GRAPH_RETRIEVAL_HOPS
from insight_agent.graph import builder as graph_builder
from insight_agent.graph import retriever as graph_retriever

mcp = FastMCP("electronics-insight-mcp")
_tables = domain.load_tables(DATASET_DIR)
_graph = graph_builder.build_graph(_tables)


@mcp.tool
def get_fdc_anomalies(
    process_id: Optional[str] = None,
    chamber_id: Optional[str] = None,
    max_vm_error_pct: float = 1.5,
) -> list[dict]:
    """FDC 인터록 이벤트 또는 가상계측(VM) 예측 오차가 임계치를 넘는 챔버 센서 로그를 조회한다."""
    df = domain.get_fdc_anomalies(
        _tables, process_id=process_id, chamber_id=chamber_id, max_vm_error_pct=max_vm_error_pct
    )
    return domain.df_to_records(df)


@mcp.tool
def get_yield_defects(
    defect_mechanism: Optional[str] = None, product_node: Optional[str] = None
) -> list[dict]:
    """웨이퍼 로트 수율 이력을 결함 메커니즘/공정 노드로 필터링해 조회한다."""
    df = domain.get_yield_defects(_tables, defect_mechanism=defect_mechanism, product_node=product_node)
    return domain.df_to_records(df)


@mcp.tool
def get_dx_kpi_trend(year_month: Optional[str] = None, quarter: Optional[str] = None) -> list[dict]:
    """DX 스마트팩토리 월별 운영 성과(KPI) 추이를 조회한다."""
    df = domain.get_dx_kpi_trend(_tables, year_month=year_month, quarter=quarter)
    return domain.df_to_records(df)


@mcp.tool
def build_causal_report(lot_id: str) -> dict:
    """FDC 설비 이상 -> 웨이퍼 수율 -> 담당 AI 에이전트를 lot_id로 엮은 통합 리포트를 만든다."""
    return domain.build_causal_report(_tables, lot_id)


@mcp.tool
def graph_query(query: str, hops: int = GRAPH_RETRIEVAL_HOPS) -> dict:
    """GraphRAG: 질의에서 로트/공정/챔버/AI에이전트 엔터티를 찾아 지식 그래프에서
    k-hop 이웃 서브그래프를 조회하고 (source, relation, target) 사실 목록으로 반환한다."""
    return graph_retriever.retrieve(_graph, query, hops=hops)


@mcp.tool
def graph_stats() -> dict:
    """지식 그래프의 노드/엣지 규모를 조회한다 (디버깅/소개용)."""
    return graph_builder.graph_stats(_graph)


def serve() -> None:
    # 배너는 stderr로 나가 stdio 프로토콜(stdout)을 깨지는 않지만, CLI 데모/이밸류
    # 출력과 섞여 매 서브프로세스 기동마다 노이즈를 만들어 꺼둔다.
    mcp.run(show_banner=False)


if __name__ == "__main__":
    serve()
