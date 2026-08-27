"""오케스트레이터가 도메인 라우팅과 트레이스 로깅을 실제로 함께 수행하는지 확인.

harness(TraceLogger)가 integration 경로에서만 동작하고 fdc/yield/kpi/graph
경로에서는 조용히 빠지는 회귀를 잡기 위한 테스트다 -- 모든 도메인이 같은
run_id로 트레이스를 남겨야 한다.
"""
import json
from pathlib import Path

import pytest

from insight_agent.agents import orchestrator
from insight_agent.config import RUNS_DIR

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _use_fixture_dataset(monkeypatch):
    monkeypatch.setenv("DATASET_DIR", str(FIXTURES_DIR))


def _read_trace(run_id: str) -> list[dict]:
    path = RUNS_DIR / f"{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.parametrize(
    "query,expected_domain,expected_step_prefix",
    [
        ("설비 챔버 이상 확인해줘", "fdc", "fdc_agent."),
        ("수율 결함 보여줘", "yield", "yield_agent."),
        ("이번 분기 데이터레이크 kpi 알려줘", "kpi", "kpi_agent."),
        ("AGT-F01와 AGT-F02는 서로 어떤 관계야?", "graph", "graph_agent."),
    ],
)
def test_route_classifies_and_traces_each_domain(query, expected_domain, expected_step_prefix):
    outcome = orchestrator.route(query)
    assert outcome["domain"] == expected_domain

    records = _read_trace(outcome["run_id"])
    steps = [r["step"] for r in records]
    assert steps[0] == "orchestrator.classify"
    assert any(step.startswith(expected_step_prefix) for step in steps)


def test_route_detects_lot_id_and_routes_to_integration():
    outcome = orchestrator.route("LOT-F001 원인 분석해줘")
    assert outcome["domain"] == "integration"
    assert outcome["result"]["status"] == "published"  # LOT-F001은 interlock 0건 -> 임계치 미만

    records = _read_trace(outcome["run_id"])
    steps = [r["step"] for r in records]
    assert steps[0] == "orchestrator.classify"
    assert "integration_agent.build_causal_report" in steps
    assert "hitl.auto_publish" in steps


def test_route_falls_back_to_integration_without_lot_id_raises_value_error():
    # 키워드가 전혀 매칭되지 않아 기본값(integration)으로 떨어졌는데 로트 ID도
    # 없는 경우: TypeError로 죽지 않고 재시도해도 같은 결과인 도메인 에러(ValueError)로
    # 명확히 실패해야 한다 (fe/server.py와 chat/engine.py가 이걸 사용자 메시지로 보여준다).
    with pytest.raises(ValueError):
        orchestrator.route("이건 아무 키워드도 없는 애매한 질문이다")


def test_route_integration_hitl_path():
    outcome = orchestrator.route("이 로트 원인 분석해줘", lot_id="LOT-F002")
    assert outcome["domain"] == "integration"
    assert outcome["result"]["status"] == "pending_approval"  # LOT-F002는 interlock 1건 -> 임계치 이상

    records = _read_trace(outcome["run_id"])
    steps = [r["step"] for r in records]
    assert "hitl.submit_for_approval" in steps
