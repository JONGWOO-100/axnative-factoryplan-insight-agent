"""승인 큐를 다루는 CLI.

사용법:
    python -m insight_agent.hitl.cli list
    python -m insight_agent.hitl.cli approve appr-xxxxxxxx
    python -m insight_agent.hitl.cli reject appr-xxxxxxxx --reason "원인 재확인 필요"
"""
from __future__ import annotations

import argparse

from insight_agent.hitl import approvals


def main() -> None:
    parser = argparse.ArgumentParser(description="HITL 승인 큐 관리")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    approve_p = sub.add_parser("approve")
    approve_p.add_argument("approval_id")

    reject_p = sub.add_parser("reject")
    reject_p.add_argument("approval_id")
    reject_p.add_argument("--reason", default="")

    args = parser.parse_args()

    if args.command == "list":
        pending = approvals.list_pending()
        if not pending:
            print("대기 중인 승인 건이 없습니다.")
        for item in pending:
            report = item["report"]
            print(
                f"[{item['approval_id']}] lot={report['lot_id']} "
                f"fdc_interlock_count={report['fdc_interlock_count']} "
                f"die_yield_pct={report.get('die_yield_pct')}"
            )
    elif args.command == "approve":
        print(approvals.approve(args.approval_id))
    elif args.command == "reject":
        print(approvals.reject(args.approval_id, args.reason))


if __name__ == "__main__":
    main()
