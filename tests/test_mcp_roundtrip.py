"""커스텀 stdio MCP 서버/클라이언트 왕복 테스트.

fixtures 데이터를 DATASET_DIR로 지정해 dataset_2 없이도 통과해야 한다.
"""
from pathlib import Path

from insight_agent.mymcp.client import McpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_tools_list_and_call():
    with McpClient(data_dir=str(FIXTURES_DIR)) as client:
        tools = client.list_tools()
        names = {t["name"] for t in tools}
        assert "get_yield_defects" in names
        assert "get_fdc_anomalies" in names
        assert "get_dx_kpi_trend" in names
        assert "build_causal_report" in names
        assert "graph_query" in names

        defects = client.call_tool("get_yield_defects", {})
        assert len(defects) == 2

        report = client.call_tool("build_causal_report", {"lot_id": "LOT-F002"})
        assert report["fdc_interlock_count"] == 1


def test_graph_query_finds_seed_and_facts():
    with McpClient(data_dir=str(FIXTURES_DIR)) as client:
        result = client.call_tool("graph_query", {"query": "LOT-F002", "hops": 1})
        assert any(s["id"] == "LOT-F002" for s in result["seed_nodes"])
        assert len(result["facts"]) > 0
