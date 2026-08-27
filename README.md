# electronics-insight-agent

`dataset_1`(생산·설비·품질·시장 통합 3개년 스타 스키마 데이터)을 기반으로 만든
멀티에이전트 + 커스텀 MCP + 하네스 엔지니어링 + HITL/HOTL 실습 패키지의 MVP입니다.

## 핵심 시나리오

"이 제품의 설비/품질 이상이 시장 성과에 영향을 줬는가?"를 `product_id` 하나로
추적해, Critical 등급 결함이 임계치 이상 누적된 경우에만 사람 승인을 거쳐
리포트를 발행합니다.

## 데이터

기본 경로는 `/Users/chunghyo/Desktop/dataset_1`이며, 환경변수로 바꿀 수 있습니다.

```bash
export DATASET_DIR=/path/to/other/dataset
```

## 구조

```
insight_agent/
  config.py          # 경로/임계치 설정
  domain.py          # 데이터 접근·조인 로직 (스키마 지식은 전부 여기에)
  mymcp/             # 커스텀 MCP 서버/클라이언트 (SDK 없이 stdio + Content-Length 직접 구현)
    framing.py
    server.py
    client.py
  agents/            # 도메인 기반 4분할: 생산/품질/시장/통합(인과)
    production_agent.py
    quality_agent.py
    market_agent.py
    integration_agent.py
    orchestrator.py  # 키워드 기반 의도 분류 -> 도메인 에이전트 라우팅
  harness/
    trace.py         # JSONL 트레이스 로깅
    loop.py          # 재시도 루프
    guardrails.py     # 리포트 스키마 검증 + CSV/xlsx 소스 정합성 검증
  hitl/
    approvals.py      # 파일 기반 승인 큐 (pending/approved/rejected)
    cli.py             # 승인 큐 CLI
  hotl/
    monitor.py         # 리전x카테고리 시장점유율 상시 스냅샷 + 급락 알림
  evals/
    build_golden_set.py
    run_eval.py
  scripts/
    run_pipeline.py    # 엔드투엔드 데모 진입점
```

## 설치

```bash
cd /path/to/electronics-insight-agent
pip install -r requirements.txt
```

## 실행

### 1. 엔드투엔드 데모

```bash
# 자동 발행 경로 (Critical 결함 2건 -> 임계치 미만)
python -m insight_agent.scripts.run_pipeline --product-id PRD-1076

# HITL 승인 대기 경로 (Critical 결함 4건 -> 임계치 이상, 승인 큐로 이동)
python -m insight_agent.scripts.run_pipeline --product-id PRD-1013
```

내부적으로 (1) CSV/xlsx 소스 정합성 검사 -> (2) 통합 에이전트가 MCP 서버에
`build_causal_report` 호출 -> (3) 가드레일 검증 -> (4) HITL 게이트 판단
(Critical 결함 3건 이상이면 승인 대기, 아니면 자동 발행) -> (5) HOTL 스냅샷 생성
순서로 동작하며, `runs/<run_id>.jsonl`에 전체 트레이스가 남습니다. 두 product_id로
자동 발행/승인 대기 두 경로를 각각 실습할 수 있습니다.

### 2. HITL 승인 큐 확인/처리

```bash
python -m insight_agent.hitl.cli list
python -m insight_agent.hitl.cli approve appr-xxxxxxxx
python -m insight_agent.hitl.cli reject appr-xxxxxxxx --reason "원인 재확인 필요"
```

### 3. MCP 서버 단독 실행 (Claude Code 등에 등록할 때)

```json
{
  "mcpServers": {
    "electronics-insight": {
      "command": "python",
      "args": ["-m", "insight_agent.mymcp.server"],
      "cwd": "/path/to/electronics-insight-agent"
    }
  }
}
```

### 4. 골든셋 이밸류에이션

```bash
python -m insight_agent.evals.build_golden_set   # 최초 1회, golden_defects.jsonl 생성
python -m insight_agent.evals.run_eval           # 통과율 출력, 미달 시 non-zero exit
```

### 5. 테스트

```bash
pytest -v
```

### 6. 웹 FE

```bash
python -m insight_agent.fe.server
# -> http://127.0.0.1:8899
```

외부 프레임워크 없이 stdlib `http.server`만으로 만든 백엔드 + 바닐라 JS SPA입니다.
4개 탭(PRD / 트레이스 / HITL 승인 큐 / HOTL 모니터)에서 상단의 제품 선택 후
"분석 실행"을 누르면 통합 에이전트가 실제로 실행되고, 그 결과가 트레이스/승인 큐/HOTL
탭에 그대로 반영됩니다.

## HITL vs HOTL

- **HITL** (`insight_agent/hitl/`): 통합 에이전트가 만든 리포트에서 Critical 결함이
  `CRITICAL_DEFECT_HITL_THRESHOLD`(기본 3건) 이상이면 자동 발행을 멈추고
  `approvals/pending/`에 대기시킵니다. 사람이 승인해야 `outputs/`에 최종 리포트가
  생성됩니다.
- **HOTL** (`insight_agent/hotl/`): 승인 대기 없이 항상 계산·노출되는 시장점유율
  스냅샷입니다. 전분기 대비 `MARKET_SHARE_DROP_ALERT_PP`(기본 -2.0%p) 이하로
  하락한 리전x카테고리만 `alerts`에 표시되고, 사람은 필요할 때만 개입합니다.

## 참고 문서

- [docs/prd.md](docs/prd.md) — PRD
- [docs/TOKEN_OPTIMIZATION.md](docs/TOKEN_OPTIMIZATION.md) — Claude Code 토큰 최적화 가이드

## 다음 단계 (이 MVP 이후)

1. `mymcp/`를 공식 MCP SDK 기반으로 교체 (전송 계층만 바뀌고 `domain.py`는 그대로 재사용)
2. `narrative.py`의 LLM 요약을 실제 운영 톤/포맷 가이드에 맞게 프롬프트 다듬기
3. 리전별/공장별 접근 권한 분리 (지금은 모든 사용자가 전체 데이터를 조회 가능)
