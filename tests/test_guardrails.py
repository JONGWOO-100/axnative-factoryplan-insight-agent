"""CSV/xlsx 소스 정합성 가드레일 테스트."""
from insight_agent import domain
from insight_agent.harness.guardrails import check_source_consistency, validate_report


def test_source_consistency_currently_passes():
    tables = domain.load_tables()
    mismatches = check_source_consistency(tables)
    assert mismatches == []


def test_validate_report_rejects_missing_fields():
    try:
        validate_report({"product_id": "PRD-1001"})
        assert False, "should have raised ValueError"
    except ValueError:
        pass
