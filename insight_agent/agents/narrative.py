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


def _fdc_evidence_sentence(report: dict) -> str:
    """FDC 이상을 '중복 없이' 한 문장으로 적는다.

    인터록 건수와 VM 오차 이상 건수를 나란히 적으면 읽는 쪽이 독립된 두 근거로
    센다. 실제로는 같은 행이 두 컬럼에 기록된 경우가 많아(dataset_2에서는 전부
    일치) 근거가 두 배로 부풀려진다. 그래서 기준을 '이상이 있는 행 수'로 잡고,
    겹침이 있으면 그 사실을 명시한다.
    """
    interlock = report["fdc_interlock_count"]
    vm = report["fdc_vm_error_anomaly_count"]
    # 예전 리포트에도 이 함수를 쓸 수 있도록, 새 필드가 없으면 보수적으로 추정한다.
    rows = report.get("fdc_anomaly_row_count")
    both = report.get("fdc_interlock_vm_coincident_count")
    if rows is None or both is None:
        rows, both = max(interlock, vm), min(interlock, vm)

    if rows == 0:
        return f"FDC 이상 징후는 발견되지 않았습니다(검사 {report['fdc_row_count']}행)."
    if both == interlock == vm:
        # 완전히 겹침 -- 근거는 하나다.
        return (
            f"FDC 이상이 {rows}행에서 발견되었습니다. 인터록과 가상계측(VM) 오차 이상이 "
            f"모두 같은 {rows}행이므로 독립된 두 근거가 아니라 하나의 근거입니다."
        )
    return (
        f"FDC 이상이 {rows}행에서 발견되었습니다"
        f"(인터록 {interlock}건, 가상계측(VM) 오차 이상 {vm}건, 이 중 {both}건은 같은 행)."
    )


def _summarize_with_template(report: dict) -> str:
    lines = [
        f"{report['product_node']} 로트 {report['lot_id']}({report['company_name']})에 대해 "
        + _fdc_evidence_sentence(report)
    ]
    avg = report.get("product_node_avg_die_yield_pct")
    if avg is not None:
        comparison = "낮습니다" if report["die_yield_pct"] < avg else "비슷하거나 높습니다"
        lines.append(f"다이 수율은 {report['die_yield_pct']}%로, 동일 공정 노드 평균 {avg}% 대비 {comparison}.")
    # 인과 판정은 수율 비교 바로 뒤에 둔다 -- 두 수치를 본 직후가 독자가 스스로
    # 인과를 지어내기 가장 쉬운 지점이다.
    verdict = report.get("causal_verdict")
    if verdict:
        lines.append(f"인과 판정: {verdict['verdict']} — {verdict['explanation']}")
    if report["major_defect_mechanism"] != "None(Clean)":
        lines.append(f"주요 결함 유형은 '{report['major_defect_mechanism']}'입니다.")
    if report["controlling_agents"]:
        # 이 목록은 위와 같은 FDC 행의 controlling_ai_agent 컬럼에서 뽑은 것이다.
        # 별도 근거처럼 읽히면 같은 사건을 세 번 세는 셈이 되므로 출처를 밝힌다.
        names = ", ".join(a["agent_name"] for a in report["controlling_agents"])
        lines.append(f"위 FDC 행에 배정된 AI 에이전트: {names}(같은 행에서 파생 — 별도 근거 아님).")
    return " ".join(lines)


def _summarize_with_llm(report: dict) -> str:
    prompt = (
        "다음 반도체 FDC/수율 통합 분석 리포트를 경영진이 바로 읽을 수 있는 "
        "한국어 3~4문장 요약으로 정리해줘. 근거 없는 인과 단정은 하지 말고 "
        "사실(수치)만 근거로 서술해줘.\n"
        "특히 같은 근거를 여러 번 세지 마라: fdc_interlock_count와 "
        "fdc_vm_error_anomaly_count는 같은 행에 겹쳐 기록되는 일이 많고, "
        "fdc_interlock_vm_coincident_count가 그 겹친 행 수다. 실제 이상 행 수는 "
        "fdc_anomaly_row_count이니 이 값을 기준으로 쓰고, controlling_agents는 "
        "그 행에서 파생된 목록이므로 독립된 근거로 제시하지 마라.\n"
        "causal_verdict는 그대로 옮겨라. verdict 값(UNKNOWN)과 explanation을 반드시 "
        "포함하고, 이 리포트가 인과를 확정한 것처럼 바꿔 쓰지 마라 -- '원인은 …이다', "
        "'…때문이다' 같은 표현을 쓰지 마라.\n\n"
        f"{report}"
    )
    return llm.generate(prompt, max_tokens=400)
