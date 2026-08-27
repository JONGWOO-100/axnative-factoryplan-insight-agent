"""프로젝트 공통 설정 — 데이터 경로, 산출물 경로, HITL/HOTL 임계치."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_DIR = Path(os.environ.get("DATASET_DIR", str(Path.home() / "Desktop" / "dataset_2")))
XLSX_PATH = DATASET_DIR / "semiconductor_ds_dx_smart_factory_3yr.xlsx"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RUNS_DIR = PROJECT_ROOT / "runs"
APPROVALS_DIR = PROJECT_ROOT / "approvals"
CHAT_SESSIONS_DIR = PROJECT_ROOT / "runs" / "chat"

# HITL: 로트(lot_id) 하나에 FDC 인터록(fdc_interlock_flag) 이벤트가 이 값 이상
# 발생하면 자동 발행을 멈추고 사람 승인 대기로 넘긴다.
FDC_INTERLOCK_HITL_THRESHOLD = 1

# HOTL: 공정 노드(product_node)×분기(quarter) 평균 다이 수율(die_yield_pct)이
# 직전 분기 대비 이 값(퍼센트포인트) 이하로 떨어지면 알림.
DIE_YIELD_DROP_ALERT_PP = -0.5

# GraphRAG: 엔터티 매칭 후 몇 홉까지 이웃 노드를 확장할지.
GRAPH_RETRIEVAL_HOPS = 2
