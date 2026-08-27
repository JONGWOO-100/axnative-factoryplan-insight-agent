"""커스텀 stdio MCP 서버/클라이언트 왕복 테스트."""
from insight_agent.mymcp.client import McpClient


def test_tools_list_and_call():
    with McpClient() as client:
        tools = client.list_tools()
        names = {t["name"] for t in tools}
        assert "get_quality_defects" in names
        assert "build_causal_report" in names

        defects = client.call_tool("get_quality_defects", {"severity": "Critical"})
        assert len(defects) == 152
