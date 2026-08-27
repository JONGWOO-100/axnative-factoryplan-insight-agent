"""수율 에이전트 -- 결함 메커니즘/공정 노드 기준으로 웨이퍼 로트 수율 패턴을 짚어낸다."""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    defect_mechanism: Optional[str] = None,
    product_node: Optional[str] = None,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"defect_mechanism": defect_mechanism, "product_node": product_node}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_yield_defects", args)

    result = run_with_retry(_call)
    trace.log("yield_agent.get_yield_defects", args, result)
    return result
