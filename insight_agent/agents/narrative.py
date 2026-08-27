"""통합 리포트를 사람이 읽기 좋은 서술형 요약으로 바꾸는 지점.

ANTHROPIC_API_KEY가 설정되어 있으면 Claude API로 서술형 요약을 생성하고,
없으면 결정론적 템플릿으로 대체한다. multiagent_system_demo의
"Mock 모드(API 키 불필요) / 실제 LLM 모드" 패턴을 그대로 따른다 -- 이 프로젝트는
키가 없어도 항상 끝까지 동작해야 한다.
"""
from __future__ import annotations

import os


def summarize(report: dict) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _summarize_with_llm(report)
        except Exception as exc:  # LLM 실패는 파이프라인을 막지 않고 템플릿으로 대체
            return _summarize_with_template(report) + f" (LLM 요약 실패: {exc})"
    return _summarize_with_template(report)


def _summarize_with_template(report: dict) -> str:
    lines = [
        f"{report['model_name']} ({report['product_id']}, {report['category']})에서 "
        f"생산 이상 {report['anomaly_run_count']}건, Critical 품질 결함 "
        f"{report['critical_defect_count']}건이 발견되었습니다."
    ]
    if report["critical_defect_types"]:
        top = max(report["critical_defect_types"].items(), key=lambda kv: kv[1])
        lines.append(f"가장 빈번한 Critical 결함 유형은 '{top[0]}'({top[1]}건)입니다.")
    if report["latest_market_share_pct"] is not None:
        lines.append(f"가장 최근 시장점유율은 {report['latest_market_share_pct']}%입니다.")
    return " ".join(lines)


def _summarize_with_llm(report: dict) -> str:
    import anthropic  # 키가 없을 때는 이 의존성 자체가 필요 없도록 지연 임포트

    client = anthropic.Anthropic()
    prompt = (
        "다음 제조/시장 통합 분석 리포트를 경영진이 바로 읽을 수 있는 "
        "한국어 3~4문장 요약으로 정리해줘. 근거 없는 인과 단정은 하지 말고 "
        "사실(수치)만 근거로 서술해줘.\n\n"
        f"{report}"
    )
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
