"""그래프 에이전트 -- GraphRAG 지식 그래프에서 엔터티 관계(k-hop 서브그래프)를 짚어낸다.

"이 에이전트가 어떤 챔버를 제어해?", "이 공정과 연결된 결함은?"처럼 단일 팩트
테이블 조회로는 답하기 어려운 관계형 질문에 쓴다.
"""
from __future__ import annotations

from typing import Optional

from insight_agent.config import GRAPH_RETRIEVAL_HOPS
from insight_agent.harness.loop import run_with_retry
from insight_agent.harness.trace import TraceLogger
from insight_agent.mymcp.client import McpClient


def run(
    query: str,
    hops: int = GRAPH_RETRIEVAL_HOPS,
    trace: Optional[TraceLogger] = None,
) -> dict:
    trace = trace or TraceLogger()
    args = {"query": query, "hops": hops}

    def _call() -> dict:
        with McpClient() as client:
            return client.call_tool("graph_query", args)

    result = run_with_retry(_call)
    trace.log("graph_agent.graph_query", args, result)
    return result
