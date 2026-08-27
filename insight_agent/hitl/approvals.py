"""HITL 승인 큐 -- Critical 결함 누적 리포트는 사람이 승인해야 최종 발행된다.

pending/ -> (사람이 approve/reject) -> approved/outputs 또는 rejected.
파일 기반 큐라 별도 인프라 없이 CLI/FE 어느 쪽에서도 바로 붙일 수 있다.
"""
from __future__ import annotations

import json
import time
import uuid

from insight_agent.config import APPROVALS_DIR, OUTPUTS_DIR

PENDING = APPROVALS_DIR / "pending"
APPROVED = APPROVALS_DIR / "approved"
REJECTED = APPROVALS_DIR / "rejected"

for _dir in (PENDING, APPROVED, REJECTED, OUTPUTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


def submit_for_approval(report: dict) -> str:
    approval_id = f"appr-{uuid.uuid4().hex[:8]}"
    payload = {"approval_id": approval_id, "submitted_at": time.time(), "report": report}
    (PENDING / f"{approval_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return "pending_approval"


def auto_publish(report: dict) -> str:
    out_path = OUTPUTS_DIR / f"report_{report['product_id']}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return "published"


def list_pending() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PENDING.glob("*.json"))]


def approve(approval_id: str) -> str:
    src = PENDING / f"{approval_id}.json"
    if not src.exists():
        raise FileNotFoundError(approval_id)
    payload = json.loads(src.read_text(encoding="utf-8"))
    report = payload["report"]
    (OUTPUTS_DIR / f"report_{report['product_id']}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    src.rename(APPROVED / src.name)
    return "approved_and_published"


def reject(approval_id: str, reason: str = "") -> str:
    src = PENDING / f"{approval_id}.json"
    if not src.exists():
        raise FileNotFoundError(approval_id)
    payload = json.loads(src.read_text(encoding="utf-8"))
    payload["rejected_reason"] = reason
    (REJECTED / src.name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    src.unlink()
    return "rejected"
