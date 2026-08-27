"""domain.py의 조회 함수가 실제 dataset_1 데이터에 대해 올바르게 동작하는지 확인."""
from insight_agent import domain


def test_load_tables_row_counts():
    tables = domain.load_tables()
    assert len(tables.dim_company_product) == 100
    assert len(tables.dim_equipment) == 54
    assert len(tables.fact_production_run) == 1200
    assert len(tables.fact_equipment_sensor) == 2400
    assert len(tables.fact_quality_defect) == 1200
    assert len(tables.fact_market_sales) == 12000


def test_get_quality_defects_severity_filter():
    tables = domain.load_tables()
    critical = domain.get_quality_defects(tables, severity="Critical")
    assert len(critical) == 152
    assert set(critical["severity"]) == {"Critical"}


def test_build_causal_report_known_product():
    tables = domain.load_tables()
    product_id = tables.dim_company_product.iloc[0]["product_id"]
    report = domain.build_causal_report(tables, product_id)
    assert report["product_id"] == product_id
    assert report["critical_defect_count"] >= 0
    assert isinstance(report["market_share_trend"], list)


def test_build_causal_report_unknown_product_raises():
    tables = domain.load_tables()
    try:
        domain.build_causal_report(tables, "PRD-9999")
        assert False, "should have raised ValueError"
    except ValueError:
        pass
