"""품질 에이전트 -- severity/category 기준으로 불량 패턴을 짚어낸다."""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    severity: Optional[str] = "Critical",
    category: Optional[str] = None,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"severity": severity, "category": category}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_quality_defects", args)

    result = run_with_retry(_call)
    trace.log("quality_agent.get_quality_defects", args, result)
    return result
