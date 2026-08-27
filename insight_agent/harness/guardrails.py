"""가드레일 -- (1) 통합 리포트 스키마 검증 (2) 그래프 조회 결과 스키마 검증
(3) CSV/xlsx 소스 정합성 검증.

harness-engineering/harness/guardrails/output_validators.py 개념을 이 프로젝트에
맞게 옮긴 것. 여기서 걸러지지 않으면 HITL 승인 단계로도 나쁜 데이터가 넘어간다.
"""
from __future__ import annotations

from insight_agent import domain
from insight_agent.config import XLSX_PATH

REQUIRED_REPORT_FIELDS = {
    "lot_id",
    "fdc_interlock_count",
    "fdc_vm_error_anomaly_count",
    "die_yield_pct",
}

REQUIRED_GRAPH_FIELDS = {"seed_nodes", "nodes", "facts", "context_text"}


def validate_report(report: dict) -> None:
    missing = REQUIRED_REPORT_FIELDS - report.keys()
    if missing:
        raise ValueError(f"report missing required fields: {missing}")
    if report["fdc_interlock_count"] < 0:
        raise ValueError("fdc_interlock_count must be >= 0")
    if report["fdc_vm_error_anomaly_count"] < 0:
        raise ValueError("fdc_vm_error_anomaly_count must be >= 0")


def validate_graph_result(result: dict) -> None:
    """graph_query MCP 툴 결과가 GraphRAG 리트리버 계약(seed/nodes/facts/context_text)을
    지키는지 확인한다. seed_nodes가 빈 리스트인 것 자체는 정상(매칭 실패)이므로
    구조가 맞는지만 검사하고 값의 존재 여부는 강제하지 않는다."""
    missing = REQUIRED_GRAPH_FIELDS - result.keys()
    if missing:
        raise ValueError(f"graph result missing required fields: {missing}")
    if not isinstance(result["nodes"], list) or not isinstance(result["facts"], list):
        raise ValueError("graph result 'nodes'/'facts' must be lists")


def check_source_consistency(tables: domain.Tables) -> list[dict]:
    return domain.check_source_consistency(tables, XLSX_PATH)
