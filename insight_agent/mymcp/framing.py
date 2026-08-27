"""MCP 표준 stdio 전송 방식(LSP 스타일 Content-Length 프레이밍)의 최소 구현.

공식 mcp SDK를 쓰지 않고 손으로 구현했다 -- "나만의 MCP 구현"의 핵심은 이 파일이다.
서버/클라이언트가 동일한 프레이밍을 공유하므로, 나중에 Claude Code의 .mcp.json에
그대로 등록해도 동작한다 (stdio + JSON-RPC 2.0 + Content-Length 헤더).
"""
from __future__ import annotations

import json
from typing import Any, BinaryIO, Optional


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header + body)
    stream.flush()


def read_message(stream: BinaryIO) -> Optional[dict[str, Any]]:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None  # EOF
        decoded = line.decode("ascii", errors="replace").strip()
        if decoded == "":
            break
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    length = int(headers.get("content-length", 0))
    if length == 0:
        return None
    body = stream.read(length)
    return json.loads(body.decode("utf-8"))
