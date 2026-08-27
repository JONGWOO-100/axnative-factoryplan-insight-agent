"""대화형 세션의 파일 기반 저장소 -- 승인 큐(hitl/approvals.py)와 같은 패턴이다.

세션 하나당 `runs/chat/<session_id>.json` 파일 하나. 별도 DB 없이 로컬 파일로
지속시켜, FE를 새로고침해도 대화가 이어지고 사용자가 몇 턴을 진행했는지
정확히 셀 수 있게 한다.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from insight_agent.config import CHAT_SESSIONS_DIR

CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ChatSession:
    session_id: str
    created_at: float
    turns: list[dict[str, Any]] = field(default_factory=list)
    report_generated: bool = False
    report_path: Optional[str] = None


def new_session_id() -> str:
    return uuid.uuid4().hex[:10]


def create() -> ChatSession:
    session = ChatSession(session_id=new_session_id(), created_at=time.time())
    save(session)
    return session


def path_for(session_id: str):
    return CHAT_SESSIONS_DIR / f"{session_id}.json"


def save(session: ChatSession) -> None:
    path_for(session.session_id).write_text(
        json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(session_id: str) -> ChatSession:
    path = path_for(session_id)
    if not path.exists():
        raise FileNotFoundError(session_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return ChatSession(**data)


def list_sessions() -> list[dict]:
    out = []
    for path in sorted(CHAT_SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append({
            "session_id": data["session_id"],
            "created_at": data["created_at"],
            "turn_count": user_turn_count_raw(data["turns"]),
            "report_generated": data.get("report_generated", False),
        })
    return out


def user_turn_count(session: ChatSession) -> int:
    return user_turn_count_raw(session.turns)


def user_turn_count_raw(turns: list[dict]) -> int:
    return sum(1 for t in turns if t.get("role") == "user")
