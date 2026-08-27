"""FDC(설비) 에이전트 -- 인터록/가상계측 오차가 발생한 챔버 센서 로그를 짚어낸다.

데이터에 직접 접근하지 않고 MCP 클라이언트를 통해서만 조회한다.
"""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    process_id: Optional[str] = None,
    chamber_id: Optional[str] = None,
    max_vm_error_pct: float = 1.5,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"process_id": process_id, "chamber_id": chamber_id, "max_vm_error_pct": max_vm_error_pct}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_fdc_anomalies", args)

    result = run_with_retry(_call)
    trace.log("fdc_agent.get_fdc_anomalies", args, result)
    return result
