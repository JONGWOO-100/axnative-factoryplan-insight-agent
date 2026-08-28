"""서술 요약 테스트 -- 같은 근거를 여러 번 세지 않는지 검증한다.

인터록·VM 오차·에이전트 배정은 dataset_2에서 하나의 물리 사건(챔버 압력·플라즈마
임피던스·서셉터 온도 동시 상승)이 세 컬럼에 기록된 것이다. 셋을 나란히 적으면
독자가 근거 3개로 읽고, 없는 인과에 확신을 갖게 된다 -- 이 프로젝트가 가장 비싸다고
보는 오류다. LLM 키가 없는 환경을 기준으로 결정론적 템플릿 경로를 검증한다.
"""
from pathlib import Path

import pytest

from insight_agent import domain
from insight_agent.agents import llm, narrative

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def force_template_path(monkeypatch):
    """LLM 키가 있는 환경에서도 템플릿 경로를 검증하도록 고정한다."""
    monkeypatch.setattr(llm, "available", lambda: False)


@pytest.fixture
def tables():
    return domain.load_tables(FIXTURES_DIR)


def test_fully_overlapping_evidence_is_counted_once(tables):
    """인터록과 VM 오차가 같은 행이면 '하나의 근거'라고 밝혀야 한다."""
    report = domain.build_causal_report(tables, "LOT-F002")
    summary = narrative.summarize(report)

    assert "1행" in summary
    assert "하나의 근거" in summary
    # 옛 문구("인터록 1건, 가상계측(VM) 오차 이상 1건")로 되돌아가면 실패한다
    assert "인터록 1건, 가상계측(VM) 오차 이상 1건" not in summary


def test_agent_list_is_marked_as_derived_not_independent(tables):
    """에이전트 목록은 같은 FDC 행에서 뽑은 것이므로 별도 근거로 보이면 안 된다."""
    report = domain.build_causal_report(tables, "LOT-F002")
    summary = narrative.summarize(report)

    assert "별도 근거 아님" in summary
    assert "이 로트를 제어한 AI 에이전트" not in summary


def test_partial_overlap_reports_both_counts_and_the_overlap(tables):
    """겹치지 않는 경우까지 뭉뚱그리면 정보가 사라진다 -- 겹친 수를 함께 적는다."""
    report = domain.build_causal_report(tables, "LOT-F003")
    summary = narrative.summarize(report)

    assert "1행" in summary
    assert "같은 행" in summary
    assert "하나의 근거" not in summary


def test_no_anomaly_lot_says_so_without_inventing_evidence(tables):
    report = domain.build_causal_report(tables, "LOT-F001")
    summary = narrative.summarize(report)

    assert "발견되지 않았습니다" in summary


def test_summary_states_the_causal_verdict(tables):
    """독자가 두 수치를 보고 스스로 인과를 지어내지 않도록 판정을 문장에 싣는다."""
    summary = narrative.summarize(domain.build_causal_report(tables, "LOT-F002"))

    assert "인과 판정: UNKNOWN" in summary
    assert "인과로 볼 수 없습니다" in summary


def test_summary_never_asserts_a_cause(tables):
    for lot_id in ["LOT-F001", "LOT-F002", "LOT-F003"]:
        summary = narrative.summarize(domain.build_causal_report(tables, lot_id))
        assert "원인은" not in summary
        assert "때문입니다" not in summary


def test_summary_survives_reports_missing_the_new_fields(tables):
    """예전에 발행된 리포트(신규 필드 없음)에도 동작해야 한다."""
    report = domain.build_causal_report(tables, "LOT-F002")
    report.pop("fdc_anomaly_row_count")
    report.pop("fdc_interlock_vm_coincident_count")

    summary = narrative.summarize(report)
    assert "1행" in summary
