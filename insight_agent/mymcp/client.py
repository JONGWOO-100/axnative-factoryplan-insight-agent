"""server.py(FastMCP 서버)를 서브프로세스로 띄워 stdio로 통신하는 동기 클라이언트.

에이전트들은 domain.py를 직접 import하지 않고 반드시 이 클라이언트를 거쳐
MCP 서버의 툴을 호출한다 -- 그래야 "에이전트가 MCP 프로토콜을 통해서만
데이터에 접근한다"는 이번 실습의 핵심 제약이 지켜진다.

FastMCP의 공식 Client는 비동기 전용이라, 기존 동기 호출부(integration_agent,
FE 서버, pytest)를 그대로 재사용할 수 있도록 이 클래스가 내부적으로 자체
asyncio 이벤트 루프를 돌려 동기 인터페이스를 유지한다.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Optional

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

_SERVER_MODULE = "insight_agent.mymcp.server"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class McpClient:
    def __init__(self, data_dir: Optional[str] = None):
        env = os.environ.copy()
        if data_dir:
            env["DATASET_DIR"] = data_dir

        transport = StdioTransport(
            command=sys.executable,
            args=["-m", _SERVER_MODULE],
            env=env,
            cwd=str(_PROJECT_ROOT),
            keep_alive=False,
        )
        self._client = Client(transport)
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._client.__aenter__())

    def list_tools(self) -> list[dict]:
        tools = self._loop.run_until_complete(self._client.list_tools())
        return [tool.model_dump(exclude_none=True) for tool in tools]

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        try:
            result = self._loop.run_until_complete(self._client.call_tool(name, arguments or {}))
        except ToolError as exc:
            raise RuntimeError(str(exc)) from exc
        return result.data

    def close(self) -> None:
        try:
            self._loop.run_until_complete(self._client.__aexit__(None, None, None))
        finally:
            self._loop.close()

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
