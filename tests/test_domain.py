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


def test_build_causal_report_unknown_lot_raises():
    tables = domain.load_tables(FIXTURES_DIR)
    try:
        domain.build_causal_report(tables, "LOT-9999-99999")
        assert False, "should have raised ValueError"
    except ValueError:
        pass
