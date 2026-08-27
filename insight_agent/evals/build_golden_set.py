"""결함이 있는(major_defect_mechanism != 'None(Clean)') 로트 일부를 샘플링해
골든셋(정답 세트)을 만든다.

수율 에이전트가 이 표본을 다시 조회했을 때 같은 lot_id를 짚어내는지 검증하는 데
쓴다. harness-engineering/evals/datasets/golden 개념을 이 프로젝트 규모로 축소한
버전.

사용법:
    python -m insight_agent.evals.build_golden_set
"""
from __future__ import annotations

import json
from pathlib import Path

from insight_agent import domain

GOLDEN_PATH = Path(__file__).parent / "golden_defects.jsonl"


def build(sample_size: int = 20, seed: int = 42) -> None:
    tables = domain.load_tables()
    defects = domain.get_yield_defects(tables)
    sample = defects.sample(n=min(sample_size, len(defects)), random_state=seed)

    with GOLDEN_PATH.open("w", encoding="utf-8") as f:
        for _, row in sample.iterrows():
            f.write(json.dumps({
                "lot_id": row["lot_id"],
                "expected_defect_mechanism": row["major_defect_mechanism"],
            }, ensure_ascii=False) + "\n")
    print(f"골든셋 {len(sample)}건을 {GOLDEN_PATH}에 저장했습니다.")


if __name__ == "__main__":
    build()
