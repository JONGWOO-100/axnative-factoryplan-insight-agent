"""통합 리포트를 사람이 읽기 좋은 서술형 요약으로 바꾸는 지점.

`llm.py`가 활성 프로바이더(Anthropic/OpenAI)를 자동 선택해 서술형 요약을 생성하고,
키가 하나도 없거나 호출이 실패하면 결정론적 템플릿으로 대체한다 -- 이 프로젝트는
키가 없어도 항상 끝까지 동작해야 한다.
"""
from __future__ import annotations

from insight_agent.agents import llm


def summarize(report: dict) -> str:
    if llm.available():
        try:
            return _summarize_with_llm(report)
        except Exception as exc:  # LLM 실패는 파이프라인을 막지 않고 템플릿으로 대체
            return _summarize_with_template(report) + f" (LLM 요약 실패: {exc})"
    return _summarize_with_template(report)


def _summarize_with_template(report: dict) -> str:
    lines = [
        f"{report['product_node']} 로트 {report['lot_id']}({report['company_name']})에서 "
        f"FDC 인터록 {report['fdc_interlock_count']}건, 가상계측(VM) 오차 이상 "
        f"{report['fdc_vm_error_anomaly_count']}건이 발견되었습니다."
    ]
    avg = report.get("product_node_avg_die_yield_pct")
    if avg is not None:
        comparison = "낮습니다" if report["die_yield_pct"] < avg else "비슷하거나 높습니다"
        lines.append(f"다이 수율은 {report['die_yield_pct']}%로, 동일 공정 노드 평균 {avg}% 대비 {comparison}.")
    if report["major_defect_mechanism"] != "None(Clean)":
        lines.append(f"주요 결함 유형은 '{report['major_defect_mechanism']}'입니다.")
    if report["controlling_agents"]:
        names = ", ".join(a["agent_name"] for a in report["controlling_agents"])
        lines.append(f"이 로트를 제어한 AI 에이전트: {names}.")
    return " ".join(lines)


def _summarize_with_llm(report: dict) -> str:
    prompt = (
        "다음 반도체 FDC/수율 통합 분석 리포트를 경영진이 바로 읽을 수 있는 "
        "한국어 3~4문장 요약으로 정리해줘. 근거 없는 인과 단정은 하지 말고 "
        "사실(수치)만 근거로 서술해줘.\n\n"
        f"{report}"
    )
    return llm.generate(prompt, max_tokens=400)
