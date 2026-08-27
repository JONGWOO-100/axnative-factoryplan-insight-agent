"""Critical 등급 결함 중 일부를 샘플링해 골든셋(정답 세트)을 만든다.

품질 에이전트가 이 표본을 다시 조회했을 때 같은 defect_id/product_id를
짚어내는지 검증하는 데 쓴다. harness-engineering/evals/datasets/golden
개념을 이 프로젝트 규모로 축소한 버전.

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
    critical = domain.get_quality_defects(tables, severity="Critical")
    sample = critical.sample(n=min(sample_size, len(critical)), random_state=seed)

    with GOLDEN_PATH.open("w", encoding="utf-8") as f:
        for _, row in sample.iterrows():
            f.write(json.dumps({
                "defect_id": row["defect_id"],
                "expected_product_id": row["product_id"],
                "expected_severity": "Critical",
            }, ensure_ascii=False) + "\n")
    print(f"골든셋 {len(sample)}건을 {GOLDEN_PATH}에 저장했습니다.")


if __name__ == "__main__":
    build()
