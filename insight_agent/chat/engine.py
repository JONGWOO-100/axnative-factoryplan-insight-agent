"""대화형 에이전트 오케스트레이션 -- 한 턴(사용자 발화 1회)을 처리하는 진입점.

harness(trace/retry/guardrails)를 그대로 통과시키면서, 기존 오케스트레이터
라우팅에 GraphRAG 컨텍스트를 얹어 "더 똑똑한" 응답을 만든다:

    1. GraphRAG로 질의에서 엔터티(로트/공정/챔버/AI에이전트)를 찾아 서브그래프를 뽑는다
       (harness.loop.run_with_retry + harness.trace로 감싸진 graph_agent를 통해).
    2. 그 서브그래프에서 얻은 엔터티를 도메인 에이전트 호출 인자로 재사용한다
       (예: 질의에 등장한 공정/챔버 ID를 fdc_agent의 process_id/chamber_id로).
    3. 구조화 툴 결과 + 그래프 사실(facts)을 근거로 자연어 답변을 만든다
       (LLM 있으면 LLM, 없으면 결정론적 템플릿).

리포트(.md) 생성은 자동으로 일어나지 않는다 -- 사용자가 FE에서 명시적으로
"리포트 저장" 버튼을 눌러 `generate_report()`를 호출할 때만 만들어진다. AI
PRD 작성 자체는 이 대화형 분석이 끝난 뒤 사용자가 별도로 하는 작업이라, 이
모듈은 그 판단(언제/무엇을 저장할지)을 대신하지 않는다.
"""
from __future__ import annotations

import json
import re
import time

from insight_agent.agents import graph_agent, llm, orchestrator
from insight_agent.chat import report, store, suggestions
from insight_agent.chat.store import ChatSession
from insight_agent.harness.guardrails import validate_graph_result
from insight_agent.harness.trace import TraceLogger

_DEFECT_MECHANISMS = ["Gate Particle", "Bridge Defect", "Under-etching", "Pattern Collapse"]
_PRODUCT_NODES = ["3D 256L V-NAND", "3nm GAA High-Perf", "5nm EUV FinFET", "8nm Auto-Grade"]
_YEAR_MONTH_PATTERN = re.compile(r"\b(20\d{2}-\d{2})\b")
_QUARTER_PATTERN = re.compile(r"\b(20\d{2}-Q[1-4])\b", re.IGNORECASE)


def _build_kwargs(domain: str, message: str, graph_result: dict) -> dict:
    """GraphRAG 시드 노드/키워드에서 도메인 에이전트 호출 인자를 가볍게 뽑아낸다.

    본격적인 NLU가 아니라, 지식 그래프가 이미 알고 있는 엔터티(공정/챔버 ID)와
    소수의 알려진 카테고리 값(결함 유형/공정 노드)에 대한 문자열 매칭이다 --
    실제 데이터 조회는 항상 MCP 툴을 통하므로 여기서 틀려도 파이프라인은 깨지지 않는다.
    """
    kwargs: dict = {}
    if domain == "fdc":
        for seed in graph_result.get("seed_nodes", []):
            if seed["type"] == "process" and "process_id" not in kwargs:
                kwargs["process_id"] = seed["id"]
            if seed["type"] == "chamber" and "chamber_id" not in kwargs:
                kwargs["chamber_id"] = seed["id"]
    elif domain == "yield":
        for mechanism in _DEFECT_MECHANISMS:
            if mechanism.lower() in message.lower():
                kwargs["defect_mechanism"] = mechanism
                break
        for node in _PRODUCT_NODES:
            if node.lower() in message.lower():
                kwargs["product_node"] = node
                break
    elif domain == "kpi":
        match = _YEAR_MONTH_PATTERN.search(message)
        if match:
            kwargs["year_month"] = match.group(1)
        else:
            quarter_match = _QUARTER_PATTERN.search(message)
            if quarter_match:
                kwargs["quarter"] = quarter_match.group(1).upper()
    return kwargs


_PREFERRED_PREVIEW_KEYS = [
    "lot_id", "fdc_log_id", "process_id", "process_name", "chamber_id", "agent_name",
    "product_node", "major_defect_mechanism", "die_yield_pct", "wafer_yield_pct",
    "year_month", "semiconductor_ds_cpk", "vm_error_pct", "fdc_interlock_flag",
]


def _compact_row(row: dict) -> str:
    parts = [f"{k}={row[k]}" for k in _PREFERRED_PREVIEW_KEYS if k in row]
    return ", ".join(parts) if parts else json.dumps(row, ensure_ascii=False, default=str)


def _template_reply(domain: str, result, graph_result: dict) -> str:
    if domain == "integration":
        report = result["report"]
        return f"{report['narrative_summary']} (승인 상태: {result['status']})"
    if domain == "graph":
        facts = result.get("facts", [])
        if not facts:
            return (
                "질의에서 알려진 로트/공정/챔버/AI에이전트 엔터티를 찾지 못했습니다. "
                "LOT-2309-50001, PRC-004, AGT-APC-03 같은 ID를 포함해 다시 질문해보세요."
            )
        lines = [f"{f['source']} -> {f['relation']} -> {f['target']}" for f in facts[:10]]
        return "지식 그래프에서 찾은 관계입니다:\n" + "\n".join(lines)
    if isinstance(result, list):
        if not result:
            return "조건에 해당하는 데이터를 찾지 못했습니다."
        preview_lines = [f"- {_compact_row(row)}" for row in result[:3]]
        return f"{len(result)}건을 찾았습니다.\n" + "\n".join(preview_lines)
    return json.dumps(result, ensure_ascii=False, default=str)[:1000]


def _llm_reply(message: str, domain: str, result, graph_result: dict) -> str:
    system = (
        "당신은 반도체 DS 수율/DX 스마트팩토리 데이터를 분석하는 대화형 어시스턴트입니다. "
        "근거 없는 인과 단정을 하지 말고, 제공된 구조화 데이터와 그래프 컨텍스트에 있는 "
        "사실만 근거로 한국어로 답하세요."
    )
    prompt = (
        f"사용자 질문: {message}\n\n"
        f"라우팅된 도메인: {domain}\n\n"
        f"MCP 툴 조회 결과(JSON, 최대 3000자):\n"
        f"{json.dumps(result, ensure_ascii=False, default=str)[:3000]}\n\n"
        f"GraphRAG 관련 사실:\n{graph_result.get('context_text') or '(관련 그래프 사실 없음)'}\n\n"
        "위 정보를 근거로 사용자 질문에 대해 3~6문장으로 답변해줘."
    )
    return llm.generate(prompt, system=system, max_tokens=600)


def reply_for(message: str, domain: str, result, graph_result: dict) -> str:
    if llm.available():
        try:
            return _llm_reply(message, domain, result, graph_result)
        except Exception as exc:  # LLM 실패는 대화를 막지 않고 템플릿으로 대체
            return _template_reply(domain, result, graph_result) + f"\n\n(LLM 응답 실패: {exc})"
    return _template_reply(domain, result, graph_result)


def generate_report(session: ChatSession) -> str:
    """사용자가 명시적으로 요청했을 때만 호출된다 (턴 수 임계치 없음).

    최소한의 조건만 확인한다 -- 대화가 아예 없으면 저장할 내용이 없으므로
    막는다. 그 외에는 언제든(1턴 뒤에도) 사용자가 원하면 저장할 수 있다.
    """
    if store.user_turn_count(session) < 1:
        raise ValueError("저장할 대화 내용이 없습니다. 먼저 질문을 하나 이상 해보세요.")
    markdown = report.generate(session)
    path = report.output_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    session.report_generated = True
    session.report_path = str(path)
    store.save(session)
    return session.report_path


def handle_turn(session: ChatSession, message: str, trace: TraceLogger | None = None) -> dict:
    trace = trace or TraceLogger()
    trace.log("pipeline.chat_turn", {"message": message}, {})
    session.turns.append({"role": "user", "content": message, "ts": time.time()})

    domain = orchestrator.classify(message)
    if domain == "graph":
        outcome = orchestrator.route(message, trace=trace)
        graph_result = outcome["result"]
        validate_graph_result(graph_result)
        trace.log("harness.guardrails.validate_graph", {"message": message}, {"ok": True})
    else:
        graph_result = graph_agent.run(message, trace=trace)
        validate_graph_result(graph_result)
        trace.log("harness.guardrails.validate_graph", {"message": message}, {"ok": True})
        kwargs = _build_kwargs(domain, message, graph_result)
        outcome = orchestrator.route(message, trace=trace, **kwargs)

    result = outcome["result"]
    reply = reply_for(message, domain, result, graph_result)
    trace.log("pipeline.narrative", {"message": message}, {"reply_preview": reply[:200]})

    session.turns.append({
        "role": "assistant",
        "content": reply,
        "ts": time.time(),
        "run_id": outcome["run_id"],
        "domain": domain,
    })

    turn_count = store.user_turn_count(session)
    store.save(session)

    return {
        "reply": reply,
        "run_id": outcome["run_id"],
        "domain": domain,
        "turn_count": turn_count,
        "suggested_questions": suggestions.followups(domain, graph_result),
    }
