"""domain.py의 조회 함수가 올바르게 동작하는지 확인.

실제 dataset_2가 아니라 tests/fixtures/의 소형 synthetic 데이터로 돈다 --
fresh clone에서 dataset_2 없이도 unit test가 통과해야 한다. dataset_2를 쓰는
엔드투엔드 데모/골든셋 이밸류에이션은 README의 실행 섹션에서 별도로 다룬다.
"""
from pathlib import Path

from insight_agent import domain

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_load_tables_row_counts():
    tables = domain.load_tables(FIXTURES_DIR)
    assert len(tables.dim_ai_automation_role) == 2
    assert len(tables.dim_process_design) == 2
    assert len(tables.dim_semicon_dx_architecture) == 1
    assert len(tables.fact_wafer_lot_yield) == 4
    assert len(tables.fact_fdc_chamber_sensor) == 5
    assert len(tables.fact_dx_smart_factory_kpi) == 2


def test_get_yield_defects_default_excludes_clean():
    tables = domain.load_tables(FIXTURES_DIR)
    defects = domain.get_yield_defects(tables)
    assert set(defects["lot_id"]) == {"LOT-F002", "LOT-F004"}


def test_get_yield_defects_mechanism_filter():
    tables = domain.load_tables(FIXTURES_DIR)
    defects = domain.get_yield_defects(tables, defect_mechanism="Gate Particle")
    assert set(defects["lot_id"]) == {"LOT-F002"}


def test_get_fdc_anomalies_interlock_and_vm_error():
    tables = domain.load_tables(FIXTURES_DIR)
    anomalies = domain.get_fdc_anomalies(tables)
    # FDC-F002: interlock_flag=1 -> 잡힘
    # FDC-F005: interlock_flag=0이지만 VM 오차율이 임계치(1.5%)를 넘음 -> OR 조건으로 잡힘
    assert set(anomalies["fdc_log_id"]) == {"FDC-F002", "FDC-F005"}


def test_build_causal_report_known_lot():
    tables = domain.load_tables(FIXTURES_DIR)
    report = domain.build_causal_report(tables, "LOT-F002")
    assert report["lot_id"] == "LOT-F002"
    assert report["fdc_row_count"] == 2  # FDC-F002, FDC-F003
    assert report["fdc_interlock_count"] == 1
    assert report["fdc_vm_error_anomaly_count"] == 1  # FDC-F002만 VM 오차 임계치 초과
    assert report["die_yield_pct"] == 78.0
    assert report["product_node_avg_die_yield_pct"] == 82.0  # Node-A: (86.0+78.0)/2
    assert {p["process_id"] for p in report["involved_processes"]} == {"PRC-F01", "PRC-F02"}
    assert {a["agent_id"] for a in report["controlling_agents"]} == {"AGT-F01", "AGT-F02"}
    assert report["dx_kpi_context"]["kpi_month_id"] == "KPI-F01"


def test_build_causal_report_reports_overlap_between_interlock_and_vm():
    """인터록 건수와 VM 오차 건수를 따로 세면 같은 행이 두 번 세어진다.

    합집합(fdc_anomaly_row_count)과 교집합(fdc_interlock_vm_coincident_count)을
    함께 실어야 읽는 쪽이 근거를 중복 계수하지 않는다.
    """
    tables = domain.load_tables(FIXTURES_DIR)

    # LOT-F002: FDC-F002 한 행이 인터록이면서 동시에 VM 오차 초과 -> 완전히 겹침
    both = domain.build_causal_report(tables, "LOT-F002")
    assert both["fdc_interlock_count"] == 1
    assert both["fdc_vm_error_anomaly_count"] == 1
    assert both["fdc_anomaly_row_count"] == 1  # 1+1=2가 아니다
    assert both["fdc_interlock_vm_coincident_count"] == 1

    # LOT-F003: FDC-F005는 인터록이 아니면서 VM 오차만 초과 -> 겹치지 않음
    vm_only = domain.build_causal_report(tables, "LOT-F003")
    assert vm_only["fdc_interlock_count"] == 0
    assert vm_only["fdc_vm_error_anomaly_count"] == 1
    assert vm_only["fdc_anomaly_row_count"] == 1
    assert vm_only["fdc_interlock_vm_coincident_count"] == 0


def test_judge_causality_never_asserts_causation():
    """어떤 입력에도 판정은 UNKNOWN이고, 달라지는 것은 '왜 근거가 없는지'뿐이다.

    단일 로트에는 비교군이 없고, dataset_2 전체에서도 인터록과 수율의 상관이
    +0.005다 (decisions.md D-004). 이상과 저수율이 함께 보여도 동시 발생까지가
    말할 수 있는 전부다.
    """
    cases = [
        (0, -3.0, "no_fdc_anomaly"),    # 이상이 없으면 저수율이어도 따질 근거가 없다
        (2, None, "no_baseline"),        # 비교 기준이 없다
        (2, +0.16, "no_yield_deficit"),  # 이상은 있으나 수율 저하가 없다
        (2, -2.5, "coincident_only"),    # 둘 다 있으나 동시 발생일 뿐이다
    ]
    for rows, delta, expected_reason in cases:
        v = domain.judge_causality(rows, delta)
        assert v["verdict"] == "UNKNOWN", (rows, delta)
        assert v["reason"] == expected_reason
        assert v["explanation"].strip()


def test_judge_causality_treats_noise_sized_gaps_as_no_deficit():
    """임계치(-0.5%p) 안쪽의 차이는 수율 저하로 보지 않는다."""
    assert domain.judge_causality(1, -0.4)["reason"] == "no_yield_deficit"
    assert domain.judge_causality(1, -0.6)["reason"] == "coincident_only"


def test_build_causal_report_carries_causal_verdict():
    tables = domain.load_tables(FIXTURES_DIR)

    # LOT-F002: 이상 1행 + 수율 78.0 vs 노드 평균 82.0 -> -4.0%p, 동시 발생
    with_deficit = domain.build_causal_report(tables, "LOT-F002")
    assert with_deficit["die_yield_delta_pp"] == -4.0
    assert with_deficit["causal_verdict"]["verdict"] == "UNKNOWN"
    assert with_deficit["causal_verdict"]["reason"] == "coincident_only"

    # LOT-F001: FDC 이상 없음
    clean = domain.build_causal_report(tables, "LOT-F001")
    assert clean["causal_verdict"]["reason"] == "no_fdc_anomaly"


def test_build_causal_report_unknown_lot_raises():
    tables = domain.load_tables(FIXTURES_DIR)
    try:
        domain.build_causal_report(tables, "LOT-9999-99999")
        assert False, "should have raised ValueError"
    except ValueError:
        pass
