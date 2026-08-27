"""오케스트레이터가 도메인 라우팅과 트레이스 로깅을 실제로 함께 수행하는지 확인.

harness(TraceLogger)가 integration 경로에서만 동작하고 production/quality/market
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
    "query,expected_domain,kwargs",
    [
        ("설비 이상 확인해줘", "production", {}),
        ("품질 불량 보여줘", "quality", {}),
        ("시장 점유율 알려줘", "market", {"product_id": "PRD-F001"}),
    ],
)
def test_route_classifies_and_traces_each_domain(query, expected_domain, kwargs):
    outcome = orchestrator.route(query, **kwargs)
    assert outcome["domain"] == expected_domain

    records = _read_trace(outcome["run_id"])
    steps = [r["step"] for r in records]
    assert steps[0] == "orchestrator.classify"
    assert any(step.startswith(f"{expected_domain}_agent.") for step in steps)


def test_route_integration_still_works_end_to_end():
    outcome = orchestrator.route("이 제품 원인 분석해줘", product_id="PRD-F001")
    assert outcome["domain"] == "integration"
    assert outcome["result"]["status"] == "published"  # PRD-F001은 Critical 1건 -> 임계치 미만

    records = _read_trace(outcome["run_id"])
    steps = [r["step"] for r in records]
    assert steps[0] == "orchestrator.classify"
    assert "integration_agent.build_causal_report" in steps
    assert "hitl.auto_publish" in steps
