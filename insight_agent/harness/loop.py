"""재시도 한도가 있는 오케스트레이션 루프 -- 하네스 엔지니어링의 최소 단위.

MCP 서버 기동 지연, 일시적 IO 실패 등 재시도로 해결되는 실패만 감싼다.
데이터 오류(ValueError 등 도메인 예외)는 재시도해도 결과가 같으므로 그대로 올린다.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retry(
    fn: Callable[[], T],
    max_retries: int = 2,
    backoff_sec: float = 0.5,
    retry_on: tuple[type[BaseException], ...] = (RuntimeError, OSError),
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retry_on as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(backoff_sec)
    assert last_exc is not None
    raise last_exc
