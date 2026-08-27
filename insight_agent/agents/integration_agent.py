"""통합(인과) 에이전트 -- 생산/품질/시장을 product_id로 엮고 HITL 게이트를 적용한다.

이 프로젝트의 핵심 시나리오: "이 제품의 설비/품질 이상이 시장 성과에
영향을 줬는가"를 하나의 리포트로 만들고, Critical 결함이 임계치 이상
누적된 경우에만 사람 승인을 기다린다.
"""
from __future__ import annotations

from typing import Optional

from insight_agent.config import CRITICAL_DEFECT_HITL_THRESHOLD
from insight_agent.harness.guardrails import validate_report
from insight_agent.harness.trace import TraceLogger
from insight_agent.hitl import approvals
from insight_agent.mymcp.client import McpClient
from insight_agent.agents import narrative


def run(product_id: str, trace: Optional[TraceLogger] = None) -> dict:
    trace = trace or TraceLogger()

    with McpClient() as client:
        report = client.call_tool("build_causal_report", {"product_id": product_id})
    trace.log("integration_agent.build_causal_report", {"product_id": product_id}, report)

    validate_report(report)

    report["narrative_summary"] = narrative.summarize(report)
    trace.log("integration_agent.narrative", {"product_id": product_id}, report["narrative_summary"])

    if report["critical_defect_count"] >= CRITICAL_DEFECT_HITL_THRESHOLD:
        status = approvals.submit_for_approval(report)
        trace.log("hitl.submit_for_approval", {"product_id": product_id}, {"status": status})
    else:
        status = approvals.auto_publish(report)
        trace.log("hitl.auto_publish", {"product_id": product_id}, {"status": status})

    return {"report": report, "status": status}
