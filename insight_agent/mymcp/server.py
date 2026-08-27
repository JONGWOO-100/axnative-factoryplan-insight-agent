"""dataset_1 조회 전용 MCP 서버 -- FastMCP 기반, 로컬 stdio로 실행한다.

도메인 로직은 전부 domain.py에 있고, 이 파일은 FastMCP의 @mcp.tool 데코레이터로
그 함수들을 MCP 툴 4개(get_production_anomalies / get_quality_defects /
get_market_impact / build_causal_report)로 노출하는 얇은 어댑터다.

실행:
    python -m insight_agent.mymcp.server

Claude Code에 등록하려면 .mcp.json에 다음과 같이 추가한다:
    {
      "mcpServers": {
        "electronics-insight": {
          "command": "python",
          "args": ["-m", "insight_agent.mymcp.server"],
          "cwd": "/path/to/electronics-insight-agent"
        }
      }
    }
"""
from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from insight_agent import domain
from insight_agent.config import DATASET_DIR

mcp = FastMCP("electronics-insight-mcp")
_tables = domain.load_tables(DATASET_DIR)


@mcp.tool
def get_production_anomalies(
    factory_code: Optional[str] = None, min_oee_pct: float = 90.0
) -> list[dict]:
    """OEE 저하 또는 설비 센서 이상(anomaly_flag)이 발생한 생산 실행 목록을 조회한다."""
    df = domain.get_production_anomalies(_tables, factory_code=factory_code, min_oee_pct=min_oee_pct)
    return domain.df_to_records(df)


@mcp.tool
def get_quality_defects(
    severity: Optional[str] = None, category: Optional[str] = None
) -> list[dict]:
    """품질 불량 이력을 severity/category로 필터링해 조회한다."""
    df = domain.get_quality_defects(_tables, severity=severity, category=category)
    return domain.df_to_records(df)


@mcp.tool
def get_market_impact(product_id: str, region: Optional[str] = None) -> list[dict]:
    """특정 product_id의 매출/시장점유율 추이를 조회한다."""
    df = domain.get_market_impact(_tables, product_id=product_id, region=region)
    return domain.df_to_records(df)


@mcp.tool
def build_causal_report(product_id: str) -> dict:
    """생산 이상 -> 품질 불량 -> 시장 성과를 product_id로 엮은 통합 리포트를 만든다."""
    return domain.build_causal_report(_tables, product_id)


def serve() -> None:
    mcp.run()


if __name__ == "__main__":
    serve()
