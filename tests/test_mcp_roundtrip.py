"""커스텀 stdio MCP 서버/클라이언트 왕복 테스트.

fixtures 데이터를 DATASET_DIR로 지정해 dataset_1 없이도 통과해야 한다.
"""
from pathlib import Path

from insight_agent.mymcp.client import McpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_tools_list_and_call():
    with McpClient(data_dir=str(FIXTURES_DIR)) as client:
        tools = client.list_tools()
        names = {t["name"] for t in tools}
        assert "get_quality_defects" in names
        assert "build_causal_report" in names

        defects = client.call_tool("get_quality_defects", {"severity": "Critical"})
        assert len(defects) == 2

        report = client.call_tool("build_causal_report", {"product_id": "PRD-F001"})
        assert report["critical_defect_count"] == 1
