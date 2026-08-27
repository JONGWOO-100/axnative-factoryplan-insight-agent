"""가드레일 -- (1) 통합 리포트 스키마 검증 (2) CSV/xlsx 소스 정합성 검증.

harness-engineering/harness/guardrails/output_validators.py 개념을 이 프로젝트에
맞게 옮긴 것. 여기서 걸러지지 않으면 HITL 승인 단계로도 나쁜 데이터가 넘어간다.
"""
from __future__ import annotations

from insight_agent import domain
from insight_agent.config import XLSX_PATH

REQUIRED_REPORT_FIELDS = {
    "product_id",
    "critical_defect_count",
    "anomaly_run_count",
    "market_share_trend",
}


def validate_report(report: dict) -> None:
    missing = REQUIRED_REPORT_FIELDS - report.keys()
    if missing:
        raise ValueError(f"report missing required fields: {missing}")
    if report["critical_defect_count"] < 0:
        raise ValueError("critical_defect_count must be >= 0")
    if report["anomaly_run_count"] < 0:
        raise ValueError("anomaly_run_count must be >= 0")


def check_source_consistency(tables: domain.Tables) -> list[dict]:
    return domain.check_source_consistency(tables, XLSX_PATH)
