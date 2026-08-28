"""프로젝트 루트를 sys.path에 올려 `insight_agent` 패키지를 테스트에서 import 가능하게 한다.

여기에 더해, 테스트가 프로젝트의 실제 산출물 디렉터리에 쓰지 못하도록 격리한다
(아래 `isolate_writable_dirs` 참조).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 산출물 경로를 import 시점에 상수로 굳혀 두는 모듈들. `from insight_agent.config
# import X` 형태라 config를 나중에 바꿔도 이 바인딩은 그대로다 -- 그래서 모듈 속성을
# 직접 갈아끼워야 한다. 새로 쓰기 시작하는 모듈이 생기면 여기에 추가한다.
_WRITABLE_PATH_BINDINGS = [
    ("insight_agent.harness.trace", "RUNS_DIR", "runs"),
    ("insight_agent.hitl.approvals", "PENDING", "approvals/pending"),
    ("insight_agent.hitl.approvals", "APPROVED", "approvals/approved"),
    ("insight_agent.hitl.approvals", "REJECTED", "approvals/rejected"),
    ("insight_agent.hitl.approvals", "OUTPUTS_DIR", "outputs"),
    ("insight_agent.chat.store", "CHAT_SESSIONS_DIR", "runs/chat"),
    ("insight_agent.chat.report", "OUTPUTS_DIR", "outputs"),
]


@pytest.fixture(autouse=True)
def isolate_writable_dirs(monkeypatch, tmp_path):
    """테스트가 실제 `runs/` · `outputs/` · `approvals/`에 쓰지 못하게 막는다.

    격리하지 않으면 HITL 경로를 태우는 테스트가 실행할 때마다 픽스처 로트
    (LOT-F001/F002)를 프로젝트의 실제 승인 큐에 쌓는다. 그러면 사람이 큐를 열었을 때
    진짜 승인 대기 건과 테스트 찌꺼기가 섞여, HITL이라는 기능 자체를 믿을 수 없게 된다.
    `runs/`와 `outputs/`도 같은 이유로 격리한다.

    autouse인 이유: 개별 테스트가 격리를 '기억해서' 해야 한다면 언젠가 잊는다.
    실제로 test_chat_engine만 OUTPUTS_DIR을 격리하고 있었고 나머지는 빠져 있었다.
    """
    import importlib

    for module_path, attr, subdir in _WRITABLE_PATH_BINDINGS:
        target = tmp_path / subdir
        target.mkdir(parents=True, exist_ok=True)
        module = importlib.import_module(module_path)
        # raising=True: 대상 속성이 사라지거나 이름이 바뀌면 조용히 넘어가지 않고
        # 여기서 깨져야 한다. 격리가 풀린 채로 테스트가 도는 것이 더 나쁘다.
        monkeypatch.setattr(module, attr, target, raising=True)
    return tmp_path
