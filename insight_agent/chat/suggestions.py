"""프롬프트 창에 보여줄 예상 질문 -- 초기 시드 세트 + 턴마다 갱신되는 후속 질문.

LLM 키 없이도 항상 몇 개는 뜨도록, 마지막 응답의 GraphRAG 서브그래프 노드
타입에서 결정론적으로 후속 질문을 만든다. 사용자가 이 칩을 눌러가며 대화를
이어가면 자연스럽게 10턴 이상 쌓이고, AI PRD 자동 생성 트리거에 닿는다.
"""
from __future__ import annotations

import random

SEED_QUESTIONS = [
    "LOT-2503-50790 로트의 FDC 이상과 수율 관계를 분석해줘",
    "AGT-APC-03 에이전트가 제어하는 챔버와 인터록 이력을 보여줘",
    "3nm GAA High-Perf 공정 노드의 최근 분기 다이 수율 추이는 어때?",
    "Gate Particle 결함이 가장 많이 발생한 공정은 어디야?",
    "이번 분기 데이터 레이크 유입량과 AI 자율의사결정률 추이를 알려줘",
    "PRC-004 공정과 연결된 챔버, AI 에이전트, 대표 결함을 그래프로 설명해줘",
    "LOT-2309-50001 로트는 왜 자동 발행됐는지 설명해줘",
    "FDC 인터록이 가장 많이 발생한 챔버는 어디야?",
]

_DOMAIN_FOLLOWUP = {
    "integration": "이 로트와 같은 공정 노드의 평균 다이 수율과 비교해줘",
    "fdc": "이 로그를 제어한 AI 에이전트가 관여한 다른 챔버도 보여줘",
    "yield": "이 결함 유형이 가장 많이 발생한 공정은 어디야?",
    "kpi": "직전 분기 대비 semiconductor_ds_cpk 변화 추이를 알려줘",
    "graph": "이 관계에 관여한 로트들의 평균 수율은 어때?",
}

_NODE_TYPE_FOLLOWUP = {
    "agent": "{label} 에이전트가 관여한 다른 로트도 보여줘",
    "process": "{label} 공정의 최근 FDC 이상 이력을 보여줘",
    "chamber": "{label} 챔버의 인터록 이력을 알려줘",
    "defect": "'{label}' 결함이 발생한 다른 로트들도 보여줘",
}


def seed_questions(limit: int = 4) -> list[str]:
    return random.sample(SEED_QUESTIONS, k=min(limit, len(SEED_QUESTIONS)))


def followups(domain: str, graph_result: dict | None, limit: int = 3) -> list[str]:
    candidates: list[str] = []
    for node in (graph_result or {}).get("nodes", [])[:20]:
        template = _NODE_TYPE_FOLLOWUP.get(node.get("type", ""))
        if template:
            candidates.append(template.format(label=node.get("label", node.get("id", ""))))

    generic = _DOMAIN_FOLLOWUP.get(domain)
    if generic:
        candidates.append(generic)
    candidates.extend(SEED_QUESTIONS)

    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= limit:
            break
    return out
