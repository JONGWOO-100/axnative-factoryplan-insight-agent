"""통합(인과) 에이전트 -- FDC/수율/AI에이전트를 lot_id로 엮고 HITL 게이트를 적용한다.

이 프로젝트의 핵심 시나리오: "이 로트의 챔버 설비 이상이 수율 하락의 원인인가,
어떤 AI 에이전트가 관여했는가"를 하나의 리포트로 만들고, FDC 인터록이 임계치
이상 발생한 경우에만 사람 승인을 기다린다. GraphRAG 서브그래프를 함께 붙여
사람 승인자/서술 요약이 팩트 테이블 조회만으로는 안 보이는 관계(같은 챔버를
공유하는 다른 로트, 같은 에이전트가 담당하는 다른 공정 등)까지 볼 수 있게 한다.
"""
from __future__ import annotations

from typing import Optional

from insight_agent.agents import graph_agent, narrative
from insight_agent.config import FDC_INTERLOCK_HITL_THRESHOLD
from insight_agent.harness.guardrails import validate_graph_result, validate_report
from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.hitl import approvals
from insight_agent.mymcp.client import McpClient


def run(lot_id: str, trace: Optional[TraceLogger] = None) -> dict:
    trace = trace or TraceLogger()

    def _call() -> dict:
        with McpClient() as client:
            return client.call_tool("build_causal_report", {"lot_id": lot_id})

    report = run_with_retry(_call)
    trace.log("integration_agent.build_causal_report", {"lot_id": lot_id}, report)

    validate_report(report)
    trace.log("harness.guardrails.validate_report", {"lot_id": lot_id}, {"ok": True})

    graph_context = graph_agent.run(lot_id, trace=trace)
    validate_graph_result(graph_context)
    trace.log("harness.guardrails.validate_graph", {"lot_id": lot_id}, {"ok": True})
    report["graph_context"] = graph_context

    report["narrative_summary"] = narrative.summarize(report)
    trace.log("integration_agent.narrative", {"lot_id": lot_id}, report["narrative_summary"])

    if report["fdc_interlock_count"] >= FDC_INTERLOCK_HITL_THRESHOLD:
        status = approvals.submit_for_approval(report)
        trace.log("hitl.submit_for_approval", {"lot_id": lot_id}, {"status": status})
    else:
        status = approvals.auto_publish(report)
        trace.log("hitl.auto_publish", {"lot_id": lot_id}, {"status": status})

    return {"report": report, "status": status}
