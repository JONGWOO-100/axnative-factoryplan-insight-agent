"""domain.py의 조회 함수가 올바르게 동작하는지 확인.

실제 dataset_1이 아니라 tests/fixtures/의 소형 synthetic 데이터로 돈다 --
fresh clone에서 dataset_1 없이도 unit test가 통과해야 한다. dataset_1을 쓰는
엔드투엔드 데모/골든셋 이밸류에이션은 README의 실행 섹션에서 별도로 다룬다.
"""
from pathlib import Path

from insight_agent import domain

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_load_tables_row_counts():
    tables = domain.load_tables(FIXTURES_DIR)
    assert len(tables.dim_company_product) == 3
    assert len(tables.dim_equipment) == 2
    assert len(tables.fact_production_run) == 4
    assert len(tables.fact_equipment_sensor) == 4
    assert len(tables.fact_quality_defect) == 4
    assert len(tables.fact_market_sales) == 4


def test_get_quality_defects_severity_filter():
    tables = domain.load_tables(FIXTURES_DIR)
    critical = domain.get_quality_defects(tables, severity="Critical")
    assert len(critical) == 2
    assert set(critical["product_id"]) == {"PRD-F001", "PRD-F003"}
    assert set(critical["severity"]) == {"Critical"}


def test_get_production_anomalies_oee_and_sensor_flag():
    tables = domain.load_tables(FIXTURES_DIR)
    anomalies = domain.get_production_anomalies(tables)
    # RUN-F002: OEE 82.0 (<90) + 센서 anomaly_flag=1 -- 둘 다 걸려도 한 번만 잡힘
    # RUN-F003: OEE 95.0(정상)이지만 센서 anomaly_flag=1 -- OR 조건으로 잡혀야 함
    assert set(anomalies["run_id"]) == {"RUN-F002", "RUN-F003"}


def test_build_causal_report_known_product():
    tables = domain.load_tables(FIXTURES_DIR)
    report = domain.build_causal_report(tables, "PRD-F001")
    assert report["product_id"] == "PRD-F001"
    assert report["production_run_count"] == 2
    assert report["anomaly_run_count"] == 1  # RUN-F002만 PRD-F001 소속
    assert report["critical_defect_count"] == 1
    assert report["latest_market_share_pct"] == 15.0  # 2024-02(가장 최근) 값
    assert isinstance(report["market_share_trend"], list)
    assert len(report["market_share_trend"]) == 2


def test_build_causal_report_unknown_product_raises():
    tables = domain.load_tables(FIXTURES_DIR)
    try:
        domain.build_causal_report(tables, "PRD-9999")
        assert False, "should have raised ValueError"
    except ValueError:
        pass
