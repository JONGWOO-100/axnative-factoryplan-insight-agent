"""골든셋 이밸류에이션 -- 수율 에이전트가 결함 로트를 정확히 짚어내는지 검증한다.

harness-engineering/evals의 '릴리스 게이트' 개념 축소판: 통과율이 100% 미만이면
비정상 종료 코드를 반환해 CI 게이트로 쓸 수 있게 한다.

사용법:
    python -m insight_agent.evals.build_golden_set   # 최초 1회
    python -m insight_agent.evals.run_eval
"""
from __future__ import annotations

import json
from pathlib import Path

from insight_agent.agents import yield_agent

GOLDEN_PATH = Path(__file__).parent / "golden_defects.jsonl"


def run() -> None:
    if not GOLDEN_PATH.exists():
        raise SystemExit("golden_defects.jsonl이 없습니다. 먼저 build_golden_set을 실행하세요.")

    cases = [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line]
    defects = yield_agent.run()
    found_ids = {d["lot_id"] for d in defects}

    passed = sum(1 for case in cases if case["lot_id"] in found_ids)
    total = len(cases)
    print(f"골든셋 통과: {passed}/{total} ({passed / total:.0%})")
    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
