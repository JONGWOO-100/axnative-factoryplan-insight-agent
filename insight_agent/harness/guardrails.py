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
    "causal_verdict",
}

REQUIRED_GRAPH_FIELDS = {"seed_nodes", "nodes", "facts", "context_text"}

# 이 리포트가 낼 수 있는 인과 판정은 UNKNOWN 하나뿐이다. 단일 로트 관측에는 비교군이
# 없어 인과를 세울 수 없고, dataset_2 전체에서도 인터록과 수율의 상관이 +0.005다
# (decisions.md D-004/D-007). 나중에 제대로 된 인과 분석을 붙인다면 이 집합을 넓히는
# 것이 그 변경의 일부여야 한다 -- 여기서 걸리는 것이 의도된 마찰이다.
ALLOWED_CAUSAL_VERDICTS = {"UNKNOWN"}

REQUIRED_VERDICT_FIELDS = {"verdict", "reason", "explanation"}


def validate_report(report: dict) -> None:
    missing = REQUIRED_REPORT_FIELDS - report.keys()
    if missing:
        raise ValueError(f"report missing required fields: {missing}")
    if report["fdc_interlock_count"] < 0:
        raise ValueError("fdc_interlock_count must be >= 0")
    if report["fdc_vm_error_anomaly_count"] < 0:
        raise ValueError("fdc_vm_error_anomaly_count must be >= 0")
    _validate_causal_verdict(report["causal_verdict"])


def _validate_causal_verdict(verdict: object) -> None:
    """인과 판정이 사유와 함께 붙어 있는지, 그리고 확정 주장이 아닌지 확인한다."""
    if not isinstance(verdict, dict):
        raise ValueError("causal_verdict must be an object")
    missing = REQUIRED_VERDICT_FIELDS - verdict.keys()
    if missing:
        raise ValueError(f"causal_verdict missing required fields: {missing}")
    if verdict["verdict"] not in ALLOWED_CAUSAL_VERDICTS:
        raise ValueError(
            f"causal_verdict.verdict must be one of {sorted(ALLOWED_CAUSAL_VERDICTS)}, "
            f"got {verdict['verdict']!r}"
        )
    # 사유 없는 UNKNOWN은 "모르겠다"가 아니라 판단 회피다.
    if not str(verdict["reason"]).strip() or not str(verdict["explanation"]).strip():
        raise ValueError("causal_verdict must carry a non-empty reason and explanation")


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
