"""server.py를 서브프로세스로 띄워 stdio로 통신하는 최소 MCP 클라이언트.

에이전트들은 domain.py를 직접 import하지 않고 반드시 이 클라이언트를 거쳐
MCP 서버의 툴을 호출한다 -- 그래야 "에이전트가 MCP 프로토콜을 통해서만
데이터에 접근한다"는 이번 실습의 핵심 제약이 지켜진다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from insight_agent.mymcp.framing import read_message, write_message

_SERVER_MODULE = "insight_agent.mymcp.server"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class McpClient:
    def __init__(self, data_dir: Optional[str] = None):
        env = os.environ.copy()
        if data_dir:
            env["DATASET_DIR"] = data_dir

        self._proc = subprocess.Popen(
            [sys.executable, "-m", _SERVER_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )
        self._next_id = 1
        self._request("initialize", {})

    def _request(self, method: str, params: dict) -> Any:
        if self._proc.poll() is not None:
            stderr = self._proc.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP server process exited early: {stderr}")

        req_id = self._next_id
        self._next_id += 1
        write_message(self._proc.stdin, {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        })
        response = read_message(self._proc.stdout)
        if response is None:
            stderr = self._proc.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP server closed the connection: {stderr}")
        if "error" in response:
            raise RuntimeError(response["error"]["message"])
        return response["result"]

    def list_tools(self) -> list[dict]:
        return self._request("tools/list", {})["tools"]

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        text = result["content"][0]["text"]
        return json.loads(text)

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
