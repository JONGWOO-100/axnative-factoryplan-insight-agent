"""생산·설비 에이전트 -- OEE 저하/센서 이상이 발생한 생산 실행을 짚어낸다.

데이터에 직접 접근하지 않고 MCP 클라이언트를 통해서만 조회한다.
"""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    factory_code: Optional[str] = None,
    min_oee_pct: float = 90.0,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"factory_code": factory_code, "min_oee_pct": min_oee_pct}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_production_anomalies", args)

    result = run_with_retry(_call)
    trace.log("production_agent.get_production_anomalies", args, result)
    return result
