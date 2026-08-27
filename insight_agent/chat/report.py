"""대화 기록 -> 분석 리포트(.md) 수동 생성.

사용자가 채팅 UI의 "리포트 저장" 버튼을 눌렀을 때만 호출된다 (자동 트리거
없음). 이 리포트는 AI PRD가 아니다 -- AI PRD는 이 대화형 분석이 끝난 뒤
사용자가 별도로, 직접 작성하는 문서다(`docs/prd.md`와 같은 성격). 이 모듈은
그 작업의 입력 자료로 쓸 수 있도록 "무엇을 물었고 무엇을 확인했는지"를
마크다운 한 장으로 정리해줄 뿐이다.

LLM 키가 있으면 대화 전체를 근거로 요약을 작성하게 하고, 없으면 결정론적
템플릿으로 대체한다 -- narrative.py와 같은 "키 없어도 항상 끝까지 동작"
불변식을 따른다.

이 모듈은 의도적으로 얇다. 리포트 형식/섹션 구성은 실습 목적에 맞게 교육생이
자유롭게 바꿔도 되는 지점이다.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from insight_agent.agents import llm
from insight_agent.chat.store import ChatSession, user_turn_count
from insight_agent.config import OUTPUTS_DIR


def output_path(session: ChatSession):
    return OUTPUTS_DIR / f"chat_report_{session.session_id}.md"


def generate(session: ChatSession) -> str:
    transcript = _format_transcript(session)
    if llm.available():
        try:
            return _generate_with_llm(session, transcript)
        except Exception as exc:  # LLM 실패는 리포트 생성 자체를 막지 않고 템플릿으로 대체
            return _generate_template(session, transcript) + (
                f"\n\n> ⚠️ LLM 생성에 실패해 템플릿으로 대체되었습니다: {exc}\n"
            )
    return _generate_template(session, transcript)


def _header(session: ChatSession) -> str:
    ts = datetime.fromtimestamp(session.created_at).strftime("%Y-%m-%d %H:%M")
    return (
        f"# 대화 기반 분석 리포트 (세션 {session.session_id})\n\n"
        f"생성 시각: {ts} · 대화 턴 수: {user_turn_count(session)}\n\n"
        "> 이 문서는 AI PRD가 아닙니다. 대화형 에이전트와 나눈 분석 내용을 정리한 "
        "자료이며, AI PRD는 이 자료를 참고해 사용자가 별도로 직접 작성합니다."
    )


def _format_transcript(session: ChatSession) -> str:
    lines = []
    turn_no = 0
    for turn in session.turns:
        if turn["role"] == "user":
            turn_no += 1
            lines.append(f"**Q{turn_no}.** {turn['content']}")
        else:
            lines.append(f"**A{turn_no}.** {turn['content']}")
    return "\n\n".join(lines)


def _generate_with_llm(session: ChatSession, transcript: str) -> str:
    prompt = (
        "다음은 반도체 DS 수율/DX 스마트팩토리 데이터에 대해 사용자가 대화형 AI 에이전트와 "
        f"나눈 {user_turn_count(session)}턴의 대화 기록이다. 이 대화 내용을 근거로, 나중에 "
        "사람이 PRD를 작성할 때 참고할 수 있는 한국어 분석 리포트를 마크다운으로 작성해줘.\n\n"
        "다음 섹션을 포함해:\n"
        "1. 개요\n"
        "2. 이번 대화에서 조회/분석한 항목 요약 (로트/공정/챔버/에이전트/결함 등 실제 언급된 대상 기준)\n"
        "3. 확인된 주요 수치/사실 (대화에 실제로 등장한 것만)\n"
        "4. 활용 데이터 소스\n"
        "5. 후속으로 더 확인이 필요해 보이는 질문\n\n"
        "대화에 없는 내용을 지어내지 말고, 대화 내용에서 직접 근거를 찾을 수 있는 것만 "
        f"작성해. PRD(제품 요구사항 문서) 형식으로 쓰지 말고, 분석 결과 요약으로만 써줘.\n\n"
        f"=== 대화 기록 ===\n{transcript}"
    )
    body = llm.generate(prompt, max_tokens=1800)
    return _header(session) + "\n\n" + body


def _generate_template(session: ChatSession, transcript: str) -> str:
    domain_counts = Counter(
        t.get("domain") for t in session.turns if t["role"] == "assistant" and t.get("domain")
    )
    lines = [
        _header(session),
        "",
        "## 1. 개요",
        "",
        f"이 문서는 대화형 인사이트 에이전트와 나눈 {user_turn_count(session)}턴의 대화를 "
        "사용자 요청으로 정리한 분석 리포트입니다. "
        "(ANTHROPIC_API_KEY/OPENAI_API_KEY 미설정 -> 템플릿 생성 경로)",
        "",
        "## 2. 대화에서 다룬 분석 도메인",
        "",
    ]
    for d, c in domain_counts.most_common():
        lines.append(f"- `{d}`: {c}회")
    if not domain_counts:
        lines.append("- (아직 도메인 라우팅 기록 없음)")

    lines += ["", "## 3. 조회/분석 질의 목록", ""]
    for turn in session.turns:
        if turn["role"] == "user":
            lines.append(f"- {turn['content']}")

    lines += [
        "",
        "## 4. 활용 데이터 소스",
        "",
        "- dataset_2: dim_process_design / dim_ai_automation_role / "
        "dim_semicon_dx_architecture / fact_wafer_lot_yield / fact_fdc_chamber_sensor / "
        "fact_dx_smart_factory_kpi",
        "- GraphRAG 지식 그래프 (로트-공정-챔버-AI에이전트-결함 관계)",
        "",
        "---",
        "",
        "## 부록: 전체 대화 기록",
        "",
        transcript,
    ]
    return "\n".join(lines)
