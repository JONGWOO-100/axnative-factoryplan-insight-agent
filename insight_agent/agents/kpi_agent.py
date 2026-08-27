"""KPI 에이전트 -- DX 스마트팩토리 월별 운영 성과 추이를 조회한다."""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    year_month: Optional[str] = None,
    quarter: Optional[str] = None,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"year_month": year_month, "quarter": quarter}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_dx_kpi_trend", args)

    result = run_with_retry(_call)
    trace.log("kpi_agent.get_dx_kpi_trend", args, result)
    return result
