"""트레이스 로거 -- 에이전트/툴 호출을 JSONL로 기록해 재현·감사 가능하게 한다.

harness-engineering/harness/observability/tracing.py의 개념을 이 프로젝트
규모에 맞게 축소한 버전이다.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from insight_agent.config import RUNS_DIR


class TraceLogger:
    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RUNS_DIR / f"{self.run_id}.jsonl"

    def log(self, step: str, input_data: Any, output_data: Any) -> None:
        record = {
            "ts": time.time(),
            "run_id": self.run_id,
            "step": step,
            "input": input_data,
            "output": output_data,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
