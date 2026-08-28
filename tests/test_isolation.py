"""테스트 격리 자체를 검증한다.

HITL 경로를 태우는 테스트가 프로젝트의 실제 승인 큐에 픽스처 로트를 쌓던 회귀가
있었다(pytest 1회 실행마다 approvals/pending에 LOT-F002 1건). 사람이 큐를 열었을 때
진짜 승인 대기 건과 테스트 찌꺼기가 섞이면 HITL 기능 자체를 믿을 수 없게 되므로,
격리가 살아 있는지를 테스트로 고정한다.
"""
from insight_agent.chat import report as chat_report
from insight_agent.chat import store as chat_store
from insight_agent.config import APPROVALS_DIR, CHAT_SESSIONS_DIR, OUTPUTS_DIR, RUNS_DIR
from insight_agent.harness import trace as trace_module
from insight_agent.hitl import approvals


def test_writable_dirs_are_redirected_away_from_the_project(tmp_path):
    """쓰기 대상 경로가 전부 tmp로 돌려져 있어야 한다."""
    redirected = {
        "trace.RUNS_DIR": trace_module.RUNS_DIR,
        "approvals.PENDING": approvals.PENDING,
        "approvals.APPROVED": approvals.APPROVED,
        "approvals.REJECTED": approvals.REJECTED,
        "approvals.OUTPUTS_DIR": approvals.OUTPUTS_DIR,
        "chat_store.CHAT_SESSIONS_DIR": chat_store.CHAT_SESSIONS_DIR,
        "chat_report.OUTPUTS_DIR": chat_report.OUTPUTS_DIR,
    }
    project_dirs = {RUNS_DIR, OUTPUTS_DIR, CHAT_SESSIONS_DIR,
                    APPROVALS_DIR / "pending", APPROVALS_DIR / "approved",
                    APPROVALS_DIR / "rejected"}

    for name, path in redirected.items():
        assert path not in project_dirs, f"{name}이 프로젝트 실제 경로를 가리킨다: {path}"
        assert tmp_path.parent in path.parents or "pytest" in str(path), (
            f"{name}이 tmp 경로가 아니다: {path}"
        )


def test_submitting_an_approval_does_not_touch_the_real_queue():
    """승인 제출이 실제 큐에 파일을 만들지 않아야 한다."""
    real_pending = APPROVALS_DIR / "pending"
    before = {p.name for p in real_pending.glob("*.json")} if real_pending.exists() else set()

    approvals.submit_for_approval({
        "lot_id": "LOT-ISOLATION-TEST",
        "fdc_interlock_count": 1,
        "fdc_vm_error_anomaly_count": 1,
        "die_yield_pct": 50.0,
    })

    after = {p.name for p in real_pending.glob("*.json")} if real_pending.exists() else set()
    assert before == after, "테스트가 실제 승인 큐에 썼다"
    # 격리된 큐에는 정상적으로 들어가 있어야 한다 (기능이 죽은 게 아니라 옮겨진 것)
    assert len(list(approvals.PENDING.glob("*.json"))) == 1


def test_trace_writes_land_in_the_isolated_runs_dir():
    logger = trace_module.TraceLogger()
    logger.log("isolation.check", {}, {"ok": True})

    assert logger.path.exists()
    assert logger.path.parent == trace_module.RUNS_DIR
    assert not (RUNS_DIR / f"{logger.run_id}.jsonl").exists()
