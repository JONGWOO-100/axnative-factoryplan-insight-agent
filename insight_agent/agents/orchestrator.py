"""오케스트레이터 -- multiagent_system_demo의 키워드 라우터를 확장한 버전.

원본은 카테고리 없이 "에이전트/코딩/조사" 키워드로만 라우팅하고 MCP도
HITL도 없었다. 여기서는 라우팅 축을 카테고리가 아니라 '도메인'(생산/품질/
시장/통합)으로 잡고, 선택된 도메인 에이전트가 MCP 툴을 호출하도록 바꿨다.
"""
from __future__ import annotations

from typing import Any, Optional

from insight_agent.agents import integration_agent, market_agent, production_agent, quality_agent
from insight_agent.harness.trace import TraceLogger

ROUTING_TABLE = {
    "production": ["설비", "생산", "oee", "가동률", "라인"],
    "quality": ["불량", "품질", "결함", "defect"],
    "market": ["매출", "점유율", "판매", "시장"],
    "integration": ["원인", "영향", "통합", "리포트", "인과"],
}


def classify(query: str) -> str:
    scores = {
        domain: sum(1 for kw in keywords if kw in query)
        for domain, keywords in ROUTING_TABLE.items()
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "integration"


def route(query: str, trace: Optional[TraceLogger] = None, **kwargs: Any) -> dict:
    # 어떤 도메인으로 라우팅되든 같은 TraceLogger를 공유해, 라우팅 결정부터
    # 실제 에이전트 호출까지 하나의 run_id로 추적되게 한다.
    trace = trace or TraceLogger()
    domain = classify(query)
    trace.log("orchestrator.classify", {"query": query}, {"domain": domain})

    kwargs["trace"] = trace
    if domain == "production":
        result = production_agent.run(**kwargs)
    elif domain == "quality":
        result = quality_agent.run(**kwargs)
    elif domain == "market":
        result = market_agent.run(**kwargs)
    else:
        result = integration_agent.run(**kwargs)
    return {"domain": domain, "result": result, "run_id": trace.run_id}
