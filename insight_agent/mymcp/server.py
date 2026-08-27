"""dataset_1 조회 전용 커스텀 MCP 서버.

공식 SDK 없이 stdio + Content-Length 프레이밍으로 JSON-RPC 2.0을 직접 구현한다.
지원 메서드: initialize, tools/list, tools/call.

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

import json
import sys
from pathlib import Path
from typing import Any, Optional

from insight_agent import domain
from insight_agent.config import DATASET_DIR
from insight_agent.mymcp.framing import read_message, write_message

TOOLS = [
    {
        "name": "get_production_anomalies",
        "description": "OEE 저하 또는 설비 센서 이상(anomaly_flag)이 발생한 생산 실행 목록을 조회한다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "factory_code": {"type": "string", "description": "예: FAC-KR-01"},
                "min_oee_pct": {"type": "number", "default": 90.0},
            },
        },
    },
    {
        "name": "get_quality_defects",
        "description": "품질 불량 이력을 severity/category로 필터링해 조회한다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["Critical", "Major", "Minor"]},
                "category": {"type": "string"},
            },
        },
    },
    {
        "name": "get_market_impact",
        "description": "특정 product_id의 매출/시장점유율 추이를 조회한다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "region": {"type": "string"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "build_causal_report",
        "description": "생산 이상 -> 품질 불량 -> 시장 성과를 product_id로 엮은 통합 리포트를 만든다.",
        "inputSchema": {
            "type": "object",
            "properties": {"product_id": {"type": "string"}},
            "required": ["product_id"],
        },
    },
]


def _dispatch(tables: domain.Tables, name: str, arguments: dict) -> Any:
    if name == "get_production_anomalies":
        df = domain.get_production_anomalies(
            tables,
            factory_code=arguments.get("factory_code"),
            min_oee_pct=arguments.get("min_oee_pct", 90.0),
        )
        return domain.df_to_records(df)
    if name == "get_quality_defects":
        df = domain.get_quality_defects(
            tables, severity=arguments.get("severity"), category=arguments.get("category")
        )
        return domain.df_to_records(df)
    if name == "get_market_impact":
        df = domain.get_market_impact(
            tables, product_id=arguments["product_id"], region=arguments.get("region")
        )
        return domain.df_to_records(df)
    if name == "build_causal_report":
        return domain.build_causal_report(tables, arguments["product_id"])
    raise ValueError(f"unknown tool: {name}")


def serve(data_dir: Optional[Path] = None) -> None:
    tables = domain.load_tables(data_dir or DATASET_DIR)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        message = read_message(stdin)
        if message is None:
            break

        req_id = message.get("id")
        method = message.get("method")

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "electronics-insight-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params", {})
                output = _dispatch(tables, params["name"], params.get("arguments", {}) or {})
                result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}]}
            else:
                write_message(stdout, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                })
                continue
        except Exception as exc:  # 툴 실행 오류를 JSON-RPC 에러 응답으로 변환
            write_message(stdout, {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            })
            continue

        if req_id is not None:
            write_message(stdout, {"jsonrpc": "2.0", "id": req_id, "result": result})


if __name__ == "__main__":
    serve()
