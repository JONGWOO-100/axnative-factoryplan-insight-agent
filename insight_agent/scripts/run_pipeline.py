"""엔드투엔드 데모 -- product_id 하나를 받아 통합 에이전트를 실행하고
트레이스/HITL 상태/HOTL 스냅샷까지 한 번에 만들어본다.

사용법:
    python -m insight_agent.scripts.run_pipeline --product-id PRD-1076
"""
from __future__ import annotations

import argparse
import json

from insight_agent import domain
from insight_agent.agents import integration_agent
from insight_agent.harness.guardrails import check_source_consistency
from insight_agent.harness.trace import TraceLogger
from insight_agent.hotl import monitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", required=True)
    args = parser.parse_args()

    trace = TraceLogger()

    tables = domain.load_tables()
    mismatches = check_source_consistency(tables)
    trace.log("harness.check_source_consistency", {}, {"mismatches": mismatches})
    if mismatches:
        print("CSV/xlsx 소스 불일치 발견:", mismatches)

    outcome = integration_agent.run(args.product_id, trace=trace)
    print(f"상태: {outcome['status']}")
    print(json.dumps(outcome["report"], ensure_ascii=False, indent=2))

    snapshot = monitor.build_snapshot(tables)
    trace.log("hotl.build_snapshot", {}, {"alert_count": len(snapshot["alerts"])})
    print(f"\nHOTL 알림 {len(snapshot['alerts'])}건 (outputs/hotl_snapshot.json 참고)")
    print(f"트레이스 로그: runs/{trace.run_id}.jsonl")


if __name__ == "__main__":
    main()
