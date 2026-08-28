# AGENTS.md

이 문서는 electronics-insight-agent를 확장하는 실습생/기여자가 지켜야 할 규칙이다.
"이 제품이 하는 일"을 규정하는 헌법이 아니라, 이 저장소에 실제로 존재하는
레이어 구조를 무너뜨리지 않기 위한 계약이다. 새 레이어를 상상해서 적지 않았다 --
아래 항목은 전부 지금 `insight_agent/` 아래에 실재하는 폴더 기준이다.

Claude Code와 Codex 양쪽 다 이 파일을 리포지토리를 열 때 자동으로 읽는다 --
두 런타임 모두 여기 적힌 레이어 경계와 체크리스트를 동일하게 따라야 한다.

## 레이어 경계

| 레이어 | 역할 | 하지 말아야 할 것 |
|---|---|---|
| `domain.py` | CSV/xlsx 스키마 지식 전부 (dataset_2: 차원 3 + 팩트 3) | 다른 레이어가 컬럼명을 직접 알게 하지 않는다 |
| `mymcp/` | MCP 프로토콜 어댑터 (`domain.py`/`graph/` 함수를 `@mcp.tool`로 얇게 노출) | 서버 파일 안에서 pandas/그래프 로직을 새로 작성하지 않는다 |
| `graph/` | GraphRAG 지식 그래프 빌더(`builder.py`) + k-hop 리트리버(`retriever.py`) | `domain.py`를 우회해 원본 CSV를 다시 읽지 않는다 — `Tables`를 인자로 받는다 |
| `agents/` | 도메인별 판단(FDC/수율/KPI/그래프/통합) | `domain.py`/`graph/`를 직접 import하지 않는다 — 반드시 `mymcp.client.McpClient`를 거친다 |
| `harness/` | trace(관측) · loop(재시도) · guardrails(리포트 스키마 + 그래프 결과 스키마 검증) | 에이전트가 이 세 개를 건너뛰고 MCP를 직접 호출하게 두지 않는다 |
| `chat/` | 대화형 세션 오케스트레이션(`engine.py`) · 파일 기반 세션 저장(`store.py`) · 예상 질문(`suggestions.py`) · 사용자 요청 시 분석 리포트 생성(`report.py`) | `orchestrator`/`agents`를 우회해 MCP 툴을 직접 호출하지 않는다 — 반드시 `orchestrator.route`/`graph_agent`를 거친다. 턴 수 기반으로 리포트를 자동 생성하지 않는다 — AI PRD는 사용자가 별도로 직접 쓰는 문서다 |
| `hitl/` `hotl/` | 사람 개입 지점(승인 큐 / 상시 모니터) | 임계치·게이트 로직을 이 폴더 밖(예: FE, chat/)에 심지 않는다 |
| `fe/` | `outputs/runs/approvals/runs/chat`을 읽고 쓰는 뷰어 + 대화형 API | 여기에 새로운 도메인 판단 로직을 넣지 않는다 — `chat.engine`/`hitl`/`hotl`을 호출만 한다 |

## 새 에이전트를 추가할 때 체크리스트

1. `harness.trace.TraceLogger`를 인자로 받고(없으면 새로 생성), 최소 1개 이상
   `trace.log(...)`를 호출한다 -- 어떤 도메인으로 라우팅되든 트레이스가
   비어 있으면 안 된다.
2. MCP 호출은 `harness.loop.run_with_retry`로 감싼다.
3. 구조화된 리포트를 반환한다면 `harness.guardrails`에 그 형태를 검증하는
   함수를 추가하고 통과시킨다 (`validate_report`/`validate_graph_result` 참고).
4. `orchestrator.ROUTING_TABLE`에 키워드를 추가하고, `orchestrator.route()`가
   새 에이전트에도 `trace`를 넘기는지 확인한다.
5. `tests/fixtures/`의 synthetic 데이터로 최소 1개 테스트를 추가한다
   (실제 `dataset_2`에 의존하는 테스트는 unit test가 아니라 e2e/eval로 분리한다).

## 그래프(GraphRAG)를 확장할 때

- 새 노드/엣지 타입은 `graph/builder.py`의 `build_graph()`에 추가한다.
  MultiDiGraph는 `add_edge`를 부를 때마다 병렬 엣지를 새로 만드므로, 허브가 될
  수 있는 관계(예: 챔버-에이전트)는 반드시 별도 `seen_*` 집합으로 유니크한
  쌍만 추가한다 -- 아니면 같은 두 노드 사이에 수백 개의 중복 엣지가 생긴다.
- 리트리버(`graph/retriever.py`)의 `khop_subgraph`는 타입별 팬아웃 캡
  (`max_same_type_per_hop`)을 갖고 있다. 로트처럼 개체 수가 많은 타입을 캡 없이
  확장하면 다른 엔터티 타입(에이전트/결함 등)이 예산에서 밀려난다.
- `graph_query` MCP 툴 결과는 항상 `harness.guardrails.validate_graph_result`를
  통과해야 한다 -- 이게 "그래프 엔지니어링이 하네스 엔지니어링과 같은 신뢰
  경계 안에서 동작한다"는 이 프로젝트의 설계 원칙이다.

## 대화형 에이전트(chat/)를 확장할 때

- 한 턴의 로직은 전부 `chat/engine.py::handle_turn`을 거친다. FE(`fe/server.py`)는
  세션을 백그라운드 스레드에서 실행하고 `run_id`를 즉시 돌려주는 오케스트레이션만
  담당한다 -- 도메인 판단/응답 합성 로직을 FE에 새로 넣지 않는다.
- 새 도메인 kwargs 추출 규칙(`_build_kwargs`)을 추가할 때도 실제 데이터
  조회는 항상 `orchestrator.route()` -> MCP 툴 경로를 거쳐야 한다.
- **리포트는 턴 수로 자동 생성하지 않는다.** `chat/report.py`의
  `generate_report()`는 사용자가 FE에서 "리포트 저장" 버튼을 눌렀을 때만
  `engine.generate_report(session)`을 통해 호출된다. AI PRD는 이 대화형
  분석이 끝난 뒤 사용자가 이 리포트를 참고해 별도로 직접 작성하는 문서라
  (`docs/prd.md`의 Day1 실습과 같은 성격), 턴 수 임계치 같은 자동 트리거를
  다시 넣지 않는다. 산출물은 `outputs/chat_report_*.md`에 쓴다 -- 이 경로를
  바꾸면 `.gitignore`도 함께 바꿔야 한다.
- **FE는 탭 2개(대화형 분석 / 산출물)만 유지한다.** 트레이스·HITL 승인 큐·HOTL
  모니터·PRD(Day1) 4개 탭과 상단 로트 선택+"분석 실행" 버튼(레거시 단건 실행)은
  화면에서 제거했다 -- `fe/server.py`의 해당 API 라우트(`/api/runs`, `/api/lots`,
  `/api/run`, `/api/approvals*`, `/api/hotl*`)와 `insight_agent/hitl/hotl` 모듈은
  그대로 남겨뒀다(CLI가 계속 쓰고, 나중에 다시 화면에 노출할 수도 있다). 새
  기능을 이 4개 영역에 추가한다면 백엔드/CLI에는 넣되, FE 탭을 다시 만들기
  전에 정말 화면이 필요한지부터 확인한다.
- **PRD 서브탭(`산출물 > PRD`)은 `docs/prd.md`가 없으면 `docs/PRD_TEMPLATE.md`를
  대신 보여준다** (`fe/server.py::api_prd`가 `is_template` 플래그로 구분한다).
  템플릿 파일은 git에 추적되는 일반 문서이므로 섹션을 고치면 바로 반영된다 --
  `docs/prd.md` 자체(교육생 산출물)와 혼동하지 않는다.
- 리포트 저장 버튼/형식/섹션 구성은 실습 목적에 맞게 교육생이 자유롭게
  바꿔도 되는 지점이다 -- `chat/report.py`가 의도적으로 얇게 만들어진 이유다.

## 하지 말아야 할 것

- **가드레일을 조용히 완화하지 않는다.** 실패하는 테스트를 통과시키려고
  `harness/guardrails.py`의 검증 조건을 느슨하게 만들 때는 왜 완화하는지
  커밋 메시지에 남긴다.
- **실데이터·키를 커밋하지 않는다.** `dataset_2`(`DATASET_DIR` 환경변수가
  가리키는 실제 경로)은 이 repo에 절대 포함하지 않는다. `.env`, API 키,
  자격증명도 마찬가지다. 유닛 테스트는 `tests/fixtures/`의 synthetic
  데이터만 사용한다.
- **평가 없이 머지하지 않는다.** `pytest`가 전부 통과해야 한다. 데이터
  스키마나 임계치를 바꿨다면 `insight_agent/evals/run_eval.py`도 통과를
  확인한다.
- **`docs/prd.md`를 채워서 커밋하지 않는다.** 각자 Day 1 실습으로 작성하는
  문서라 `.gitignore`에 있다. 실수로 다시 추적하지 않는다. (대화형 에이전트의
  "리포트 저장" 버튼으로 만드는 `outputs/chat_report_*.md`도 마찬가지로
  산출물이라 커밋하지 않는다.)

## 알려진 부채 (지금은 하지 않지만, 알고는 있어야 하는 것)

- **프롬프트가 아직 인라인이다.** `agents/narrative.py`/`chat/report.py`의 LLM
  프롬프트가 함수 안에 문자열로 박혀 있다. 새 프롬프트를 추가할 때는 여기부터
  따라 하지 말고, 별도 위치로 분리하는 쪽으로 만든다.
- **MCP 툴에 명시적 allowlist가 없다.** `mymcp/server.py`의 `@mcp.tool`은
  전부 노출된다. 툴을 추가할 때 이게 정말 외부에 노출돼도 되는 조회인지
  한 번 더 확인한다.
- **`chat/engine.py`의 kwargs 추출은 정규식/키워드 매칭 수준이다.** 실제
  NLU가 아니므로 복잡한 복합 질의(여러 필터 동시 지정 등)는 놓칠 수 있다.
- **`run_eval.py` 통과가 CI로 강제되지 않는다.** 지금은 사람이 직접
  실행해서 확인해야 한다.

## MCP 툴을 추가할 때

- `@mcp.tool`은 반드시 `domain.py`/`graph/`의 함수를 얇게 감싸는 형태로만
  추가한다.
- 새 tool을 추가하면 `tests/test_mcp_roundtrip.py`에 최소 1개 케이스를
  추가한다.

## Codex 관련 참고

- Codex CLI/Desktop에 MCP 서버를 등록하려면 [codex/config.toml](codex/config.toml)
  스니펫을 `~/.codex/config.toml`에 병합한다 (Codex는 Claude Code의 `.mcp.json`
  같은 프로젝트 스코프 자동 등록이 없다).
- 대화형 에이전트/대화 리포트/서술 요약의 LLM 호출은 `insight_agent/agents/llm.py`가
  `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` 중 설정된 쪽을 자동 선택한다. 새로운
  LLM 호출 지점을 추가할 때는 반드시 이 모듈을 거치고, 키가 없을 때의 결정론적
  템플릿 대체 경로를 함께 만든다.
- `.claude/commands/brainstorm-data.md`(Claude Code)와 `codex/prompts/brainstorm-data.md`
  (Codex, `~/.codex/prompts/`에 복사해서 사용)는 같은 프롬프트를 두 런타임용으로
  복제해둔 것이다. 프롬프트 내용을 고치면 두 파일을 함께 갱신한다 -- 원본 CSV/xlsx를
  직접 읽지 않고 MCP 툴 결과만으로 분석하게 하는 게 이 프롬프트의 핵심 제약이다.
