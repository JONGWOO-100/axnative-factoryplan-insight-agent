"""시장 에이전트 -- 제품별 매출/시장점유율 추이를 조회한다."""
from __future__ import annotations

from typing import Optional

from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    product_id: str,
    region: Optional[str] = None,
    trace: Optional[TraceLogger] = None,
) -> list[dict]:
    trace = trace or TraceLogger()
    args = {"product_id": product_id, "region": region}

    def _call() -> list[dict]:
        with McpClient() as client:
            return client.call_tool("get_market_impact", args)

    result = run_with_retry(_call)
    trace.log("market_agent.get_market_impact", args, result)
    return result
