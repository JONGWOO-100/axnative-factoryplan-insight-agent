"""오케스트레이터 -- multiagent_system_demo의 키워드 라우터를 확장한 버전.

라우팅 축은 카테고리가 아니라 '도메인'(FDC설비/수율/DX KPI/그래프관계/통합)이고,
선택된 도메인 에이전트가 MCP 툴을 호출하도록 되어 있다. `LOT-xxxx-xxxxx` 형태의
lot_id가 질의에 직접 등장하면(이 프로젝트의 flagship 시나리오) 키워드 점수와
무관하게 통합 에이전트로 우선 라우팅한다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from insight_agent.agents import fdc_agent, graph_agent, integration_agent, kpi_agent, yield_agent
from insight_agent.harness.trace import TraceLogger

ROUTING_TABLE = {
    "fdc": ["설비", "챔버", "fdc", "인터록", "플라즈마", "센서"],
    "yield": ["수율", "불량", "결함", "yield", "defect"],
    "kpi": ["kpi", "성과", "데이터레이크", "자율", "가동률", "다운타임", "에너지"],
    "graph": ["관계", "연관", "그래프", "네트워크", "연결", "제어", "누가"],
    "integration": ["원인", "영향", "통합", "리포트", "인과", "로트"],
}

_LOT_ID_PATTERN = re.compile(r"\bLOT-[A-Za-z0-9-]+\b", re.IGNORECASE)


def classify(query: str) -> str:
    if _LOT_ID_PATTERN.search(query):
        return "integration"
    scores = {
        domain: sum(1 for kw in keywords if kw in query.lower())
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
    if domain == "fdc":
        result = fdc_agent.run(**kwargs)
    elif domain == "yield":
        result = yield_agent.run(**kwargs)
    elif domain == "kpi":
        result = kpi_agent.run(**kwargs)
    elif domain == "graph":
        kwargs.setdefault("query", query)
        result = graph_agent.run(**kwargs)
    else:
        lot_match = _LOT_ID_PATTERN.search(query)
        if "lot_id" not in kwargs and lot_match:
            kwargs["lot_id"] = lot_match.group(0).upper()
        if "lot_id" not in kwargs:
            # 키워드 점수가 전부 0이라 기본값(integration)으로 떨어졌는데 질의에
            # lot_id도 없는 경우 -- integration_agent.run()은 lot_id가 필수이므로,
            # TypeError로 죽는 대신 재시도해도 결과가 같은 결정론적 도메인 에러로
            # 명확히 올려 상위(chat/engine.py, fe/server.py)가 그대로 사용자에게
            # 보여줄 수 있게 한다.
            raise ValueError(
                "통합 리포트를 만들려면 로트 ID가 필요합니다. "
                "질의에 LOT-XXXX-XXXXX 형식의 로트 ID를 포함해 다시 질문해주세요."
            )
        result = integration_agent.run(**kwargs)
    return {"domain": domain, "result": result, "run_id": trace.run_id}
