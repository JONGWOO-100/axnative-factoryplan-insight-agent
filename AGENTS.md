# AGENTS.md

이 문서는 electronics-insight-agent를 확장하는 실습생/기여자가 지켜야 할 규칙이다.
"이 제품이 하는 일"을 규정하는 헌법이 아니라, 이 저장소에 실제로 존재하는
레이어 구조를 무너뜨리지 않기 위한 계약이다. 새 레이어를 상상해서 적지 않았다 --
아래 항목은 전부 지금 `insight_agent/` 아래에 실재하는 폴더 기준이다.

## 레이어 경계

| 레이어 | 역할 | 하지 말아야 할 것 |
|---|---|---|
| `domain.py` | CSV/xlsx 스키마 지식 전부 | 다른 레이어가 컬럼명을 직접 알게 하지 않는다 |
| `mymcp/` | MCP 프로토콜 어댑터 (`domain.py` 함수를 `@mcp.tool`로 얇게 노출) | 서버 파일 안에서 pandas 로직을 새로 작성하지 않는다 |
| `agents/` | 도메인별 판단(생산/품질/시장/통합) | `domain.py`를 직접 import하지 않는다 — 반드시 `mymcp.client.McpClient`를 거친다 |
| `harness/` | trace(관측) · loop(재시도) · guardrails(검증) | 에이전트가 이 세 개를 건너뛰고 MCP를 직접 호출하게 두지 않는다 |
| `hitl/` `hotl/` | 사람 개입 지점(승인 큐 / 상시 모니터) | 임계치·게이트 로직을 이 폴더 밖(예: FE)에 심지 않는다 |
| `fe/` | `outputs/runs/approvals`를 읽고 쓰는 뷰어 | 여기에 새로운 도메인 판단 로직을 넣지 않는다 |

## 새 에이전트를 추가할 때 체크리스트

1. `harness.trace.TraceLogger`를 인자로 받고(없으면 새로 생성), 최소 1개 이상
   `trace.log(...)`를 호출한다 -- 어떤 도메인으로 라우팅되든 트레이스가
   비어 있으면 안 된다.
2. MCP 호출은 `harness.loop.run_with_retry`로 감싼다.
3. 구조화된 리포트를 반환한다면 `harness.guardrails`에 그 형태를 검증하는
   함수를 추가하고 통과시킨다.
4. `orchestrator.ROUTING_TABLE`에 키워드를 추가하고, `orchestrator.route()`가
   새 에이전트에도 `trace`를 넘기는지 확인한다.
5. `tests/fixtures/`의 synthetic 데이터로 최소 1개 테스트를 추가한다
   (실제 `dataset_1`에 의존하는 테스트는 unit test가 아니라 e2e/eval로 분리한다).

## 하지 말아야 할 것

- **가드레일을 조용히 완화하지 않는다.** 실패하는 테스트를 통과시키려고
  `harness/guardrails.py`의 검증 조건을 느슨하게 만들 때는 왜 완화하는지
  커밋 메시지에 남긴다.
- **실데이터·키를 커밋하지 않는다.** `dataset_1`(`DATASET_DIR` 환경변수가
  가리키는 실제 경로)은 이 repo에 절대 포함하지 않는다. `.env`, API 키,
  자격증명도 마찬가지다. 유닛 테스트는 `tests/fixtures/`의 synthetic
  데이터만 사용한다.
- **평가 없이 머지하지 않는다.** `pytest`가 전부 통과해야 한다. 데이터
  스키마나 임계치를 바꿨다면 `insight_agent/evals/run_eval.py`도 통과를
  확인한다.
- **`docs/prd.md`를 채워서 커밋하지 않는다.** 각자 Day 1 실습으로 작성하는
  문서라 `.gitignore`에 있다. 실수로 다시 추적하지 않는다.

## 알려진 부채 (지금은 하지 않지만, 알고는 있어야 하는 것)

- **프롬프트가 아직 인라인이다.** `agents/narrative.py`의 LLM 프롬프트가
  함수 안에 문자열로 박혀 있다. 새 프롬프트를 추가할 때는 여기부터 따라
  하지 말고, 별도 위치로 분리하는 쪽으로 만든다.
- **MCP 툴에 명시적 allowlist가 없다.** `mymcp/server.py`의 `@mcp.tool`은
  전부 노출된다. 툴을 추가할 때 이게 정말 외부에 노출돼도 되는 조회인지
  한 번 더 확인한다.
- **`run_eval.py` 통과가 CI로 강제되지 않는다.** 지금은 사람이 직접
  실행해서 확인해야 한다.

## MCP 툴을 추가할 때

- `@mcp.tool`은 반드시 `domain.py`의 함수를 얇게 감싸는 형태로만 추가한다.
- 새 tool을 추가하면 `tests/test_mcp_roundtrip.py`에 최소 1개 케이스를
  추가한다.
