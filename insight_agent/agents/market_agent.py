"""시장 에이전트 -- 제품별 매출/시장점유율 추이를 조회한다."""
from __future__ import annotations

from typing import Optional

from insight_agent.mymcp.client import McpClient


def run(product_id: str, region: Optional[str] = None) -> list[dict]:
    with McpClient() as client:
        return client.call_tool(
            "get_market_impact", {"product_id": product_id, "region": region}
        )
