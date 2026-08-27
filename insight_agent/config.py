"""프로젝트 공통 설정 — 데이터 경로, 산출물 경로, HITL/HOTL 임계치."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_DIR = Path(os.environ.get("DATASET_DIR", "/Users/chunghyo/Desktop/dataset_1"))
XLSX_PATH = DATASET_DIR / "electronics_manufacturing_market_data_3yr.xlsx"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RUNS_DIR = PROJECT_ROOT / "runs"
APPROVALS_DIR = PROJECT_ROOT / "approvals"

# HITL: product_id 하나에 Critical 결함이 이 값 이상 누적되면 자동 발행을 멈추고 사람 승인 대기
CRITICAL_DEFECT_HITL_THRESHOLD = 3

# HOTL: 리전×카테고리 시장점유율이 전분기 대비 이 값(퍼센트포인트) 이하로 떨어지면 알림
MARKET_SHARE_DROP_ALERT_PP = -2.0
