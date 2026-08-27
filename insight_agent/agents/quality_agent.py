"""품질 에이전트 -- severity/category 기준으로 불량 패턴을 짚어낸다."""
from __future__ import annotations

from typing import Optional

from insight_agent.mymcp.client import McpClient


def run(severity: Optional[str] = "Critical", category: Optional[str] = None) -> list[dict]:
    with McpClient() as client:
        return client.call_tool(
            "get_quality_defects", {"severity": severity, "category": category}
        )
