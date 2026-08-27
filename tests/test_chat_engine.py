"""대화형 에이전트 엔진(chat/engine.py)이 라우팅+GraphRAG+리포트 저장을 실제로
수행하는지 확인한다. LLM 키 없이(템플릿 경로) fixtures 데이터로 돈다.

리포트(.md)는 자동으로 생성되지 않는다 -- 사용자가 명시적으로
`engine.generate_report()`를 호출했을 때만 만들어진다는 게 이 테스트의
핵심 불변식이다 (AI PRD 작성은 이 대화형 분석과 별개로 사용자가 직접 한다).
"""
from pathlib import Path

import pytest

from insight_agent.chat import engine, store

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _use_fixture_dataset(monkeypatch):
    monkeypatch.setenv("DATASET_DIR", str(FIXTURES_DIR))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_handle_turn_routes_and_replies_without_llm_key():
    session = store.create()
    result = engine.handle_turn(session, "LOT-F002 원인 분석해줘")

    assert result["domain"] == "integration"
    assert result["turn_count"] == 1
    assert "승인 상태" in result["reply"]
    assert len(result["suggested_questions"]) > 0
    assert "report_path" not in result  # 자동 생성 필드가 남아있지 않아야 한다

    reloaded = store.load(session.session_id)
    assert store.user_turn_count(reloaded) == 1
    assert reloaded.turns[0]["role"] == "user"
    assert reloaded.turns[1]["role"] == "assistant"
    assert reloaded.report_generated is False  # 몇 턴이 쌓여도 자동 생성되지 않는다


def test_handle_turn_never_auto_generates_report_even_after_many_turns():
    session = store.create()
    for _ in range(12):
        engine.handle_turn(session, "설비 챔버 이상 확인해줘")

    reloaded = store.load(session.session_id)
    assert store.user_turn_count(reloaded) == 12
    assert reloaded.report_generated is False
    assert reloaded.report_path is None


def test_generate_report_requires_explicit_call(monkeypatch, tmp_path):
    from insight_agent.chat import report as report_module
    monkeypatch.setattr(report_module, "OUTPUTS_DIR", tmp_path)

    session = store.create()
    engine.handle_turn(session, "설비 챔버 이상 확인해줘")

    report_path = engine.generate_report(session)

    assert report_path is not None
    assert Path(report_path).exists()
    content = Path(report_path).read_text(encoding="utf-8")
    assert "대화 기반 분석 리포트" in content
    assert "AI PRD가 아닙니다" in content

    reloaded = store.load(session.session_id)
    assert reloaded.report_generated is True
    assert reloaded.report_path == report_path


def test_generate_report_without_any_turn_raises():
    session = store.create()
    with pytest.raises(ValueError):
        engine.generate_report(session)
