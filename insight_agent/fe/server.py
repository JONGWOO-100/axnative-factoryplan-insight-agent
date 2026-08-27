"""로컬 웹 FE 백엔드 -- 외부 프레임워크 없이 stdlib http.server만으로 구현한다.

화면: 대화형 에이전트(+파이프라인 시각화) / 대화 리포트 / PRD(Day1 실습) /
트레이스 / HITL 승인 큐 / HOTL 모니터. 모두 insight_agent가 실제로 만든 로컬
파일(outputs/runs/approvals/docs)을 그대로 읽고 쓴다 -- FE 전용 별도
데이터베이스는 없다.

대화 리포트(.md)는 자동으로 생성되지 않는다 -- 사용자가 채팅 UI의 "리포트
저장" 버튼을 눌러야만 `POST /api/chat/sessions/<id>/report`가 호출된다. AI
PRD 작성은 이 리포트를 참고해 사용자가 별도로 직접 하는 작업이다.

파이프라인 시각화는 별도 이벤트 채널(SSE/WebSocket) 없이, 대화 턴이 이미
남기는 `runs/<run_id>.jsonl` 트레이스를 FE가 폴링해서 그린다 -- harness의
TraceLogger가 이미 있는 sole source of truth를 그대로 재사용한다.

실행:
    python -m insight_agent.fe.server
    -> http://127.0.0.1:8899
"""
from __future__ import annotations

import json
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from insight_agent import domain
from insight_agent.agents import integration_agent
from insight_agent.chat import engine, store as chat_store, suggestions
from insight_agent.config import OUTPUTS_DIR, PROJECT_ROOT, RUNS_DIR
from insight_agent.harness.trace import TraceLogger
from insight_agent.hitl import approvals
from insight_agent.hotl import monitor

STATIC_DIR = Path(__file__).parent / "static"
PRD_PATH = PROJECT_ROOT / "docs" / "prd.md"

ROUTES: list[tuple[str, re.Pattern, Callable]] = []

# 대화 턴은 백그라운드 스레드에서 처리한다 (MCP 서브프로세스 호출이 몇 초씩 걸리므로,
# 요청을 블로킹하지 않고 즉시 run_id를 돌려줘야 FE가 그 사이 파이프라인 트레이스를
# 실시간으로 폴링해 애니메이션을 그릴 수 있다). ThreadingHTTPServer가 이미 요청마다
# 스레드를 쓰므로, 여기서도 공유 딕셔너리 접근을 락으로만 보호하면 충분하다.
_pending_lock = threading.Lock()
_pending_turns: dict[str, dict] = {}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def route(method: str, pattern: str):
    regex = re.compile("^" + pattern + "$")

    def deco(fn: Callable) -> Callable:
        ROUTES.append((method, regex, fn))
        return fn

    return deco


# ---- API handlers: 기존 4개 뷰(PRD/트레이스/HITL/HOTL) ----------------------

@route("GET", r"/api/prd")
def api_prd(handler: "Handler", match: re.Match) -> Any:
    text = PRD_PATH.read_text(encoding="utf-8") if PRD_PATH.exists() else "# PRD 없음\n\ndocs/prd.md가 없습니다."
    return {"markdown": text}


@route("GET", r"/api/lots")
def api_lots(handler: "Handler", match: re.Match) -> Any:
    tables = domain.load_tables()
    cols = ["lot_id", "product_node", "company_name", "major_defect_mechanism"]
    return domain.df_to_records(tables.fact_wafer_lot_yield[cols])


@route("POST", r"/api/run")
def api_run(handler: "Handler", match: re.Match) -> Any:
    body = handler.read_json_body()
    lot_id = body.get("lot_id")
    if not lot_id:
        raise ApiError(400, "lot_id is required")
    trace = TraceLogger()
    try:
        outcome = integration_agent.run(lot_id, trace=trace)
    except (ValueError, RuntimeError) as exc:
        message = str(exc)
        if "unknown lot_id" in message:
            raise ApiError(404, message)
        raise
    outcome["run_id"] = trace.run_id
    return outcome


@route("GET", r"/api/runs")
def api_runs(handler: "Handler", match: re.Match) -> Any:
    runs = []
    for path in sorted(RUNS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        records = _read_jsonl(path)
        lot_id = None
        for rec in records:
            if isinstance(rec.get("input"), dict) and "lot_id" in rec["input"]:
                lot_id = rec["input"]["lot_id"]
                break
        runs.append({
            "run_id": path.stem,
            "step_count": len(records),
            "lot_id": lot_id,
            "modified_at": path.stat().st_mtime,
        })
    return runs


@route("GET", r"/api/runs/(?P<run_id>[\w-]+)")
def api_run_detail(handler: "Handler", match: re.Match) -> Any:
    path = RUNS_DIR / f"{match.group('run_id')}.jsonl"
    if not path.exists():
        raise ApiError(404, "run not found")
    return _read_jsonl(path)


@route("GET", r"/api/approvals")
def api_approvals(handler: "Handler", match: re.Match) -> Any:
    status = handler.query.get("status", ["pending"])[0]
    folder = {
        "pending": approvals.PENDING,
        "approved": approvals.APPROVED,
        "rejected": approvals.REJECTED,
    }.get(status)
    if folder is None:
        raise ApiError(400, "status must be pending/approved/rejected")
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


@route("POST", r"/api/approvals/(?P<approval_id>[\w-]+)/approve")
def api_approve(handler: "Handler", match: re.Match) -> Any:
    try:
        status = approvals.approve(match.group("approval_id"))
    except FileNotFoundError:
        raise ApiError(404, "approval not found")
    return {"status": status}


@route("POST", r"/api/approvals/(?P<approval_id>[\w-]+)/reject")
def api_reject(handler: "Handler", match: re.Match) -> Any:
    body = handler.read_json_body()
    try:
        status = approvals.reject(match.group("approval_id"), body.get("reason", ""))
    except FileNotFoundError:
        raise ApiError(404, "approval not found")
    return {"status": status}


@route("GET", r"/api/hotl")
def api_hotl(handler: "Handler", match: re.Match) -> Any:
    snapshot_path = OUTPUTS_DIR / "hotl_snapshot.json"
    if not snapshot_path.exists():
        return {"trend": [], "alerts": [], "message": "스냅샷이 아직 없습니다. 새로고침을 눌러 생성하세요."}
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


@route("POST", r"/api/hotl/refresh")
def api_hotl_refresh(handler: "Handler", match: re.Match) -> Any:
    tables = domain.load_tables()
    return monitor.build_snapshot(tables)


@route("GET", r"/api/reports")
def api_reports(handler: "Handler", match: re.Match) -> Any:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUTPUTS_DIR.glob("report_*.json"))]


# ---- API handlers: 대화형 에이전트 + 파이프라인 + 대화 리포트 -----------------

@route("POST", r"/api/chat/sessions")
def api_chat_create(handler: "Handler", match: re.Match) -> Any:
    session = chat_store.create()
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "suggested_questions": suggestions.seed_questions(),
    }


@route("GET", r"/api/chat/sessions/(?P<session_id>[\w-]+)")
def api_chat_get(handler: "Handler", match: re.Match) -> Any:
    try:
        session = chat_store.load(match.group("session_id"))
    except FileNotFoundError:
        raise ApiError(404, "session not found")
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "turns": session.turns,
        "turn_count": chat_store.user_turn_count(session),
        "report_generated": session.report_generated,
        "report_path": session.report_path,
    }


@route("POST", r"/api/chat/sessions/(?P<session_id>[\w-]+)/messages")
def api_chat_message(handler: "Handler", match: re.Match) -> Any:
    body = handler.read_json_body()
    message = (body.get("message") or "").strip()
    if not message:
        raise ApiError(400, "message is required")
    session_id = match.group("session_id")
    try:
        session = chat_store.load(session_id)
    except FileNotFoundError:
        raise ApiError(404, "session not found")

    trace = TraceLogger()
    run_id = trace.run_id
    with _pending_lock:
        _pending_turns[run_id] = {"status": "running"}

    def _worker() -> None:
        try:
            result = engine.handle_turn(session, message, trace=trace)
            with _pending_lock:
                _pending_turns[run_id] = {"status": "done", "result": result}
        except ValueError as exc:
            with _pending_lock:
                _pending_turns[run_id] = {"status": "error", "error": str(exc)}
        except Exception:
            traceback.print_exc()
            with _pending_lock:
                _pending_turns[run_id] = {"status": "error", "error": "internal error"}

    threading.Thread(target=_worker, daemon=True).start()
    return {"run_id": run_id, "status": "processing"}


@route("GET", r"/api/chat/turns/(?P<run_id>[\w-]+)")
def api_chat_turn_status(handler: "Handler", match: re.Match) -> Any:
    with _pending_lock:
        state = _pending_turns.get(match.group("run_id"))
    if state is None:
        raise ApiError(404, "turn not found")
    return state


@route("POST", r"/api/chat/sessions/(?P<session_id>[\w-]+)/report")
def api_chat_report_generate(handler: "Handler", match: re.Match) -> Any:
    """사용자가 채팅 UI의 "리포트 저장" 버튼을 눌렀을 때만 호출된다 (자동 트리거 없음)."""
    try:
        session = chat_store.load(match.group("session_id"))
    except FileNotFoundError:
        raise ApiError(404, "session not found")
    try:
        path = engine.generate_report(session)
    except ValueError as exc:
        raise ApiError(400, str(exc))
    return {"report_path": path}


@route("GET", r"/api/chat/reports")
def api_chat_report_list(handler: "Handler", match: re.Match) -> Any:
    items = []
    for path in sorted(OUTPUTS_DIR.glob("chat_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({
            "filename": path.name,
            "session_id": path.stem.replace("chat_report_", ""),
            "modified_at": path.stat().st_mtime,
            "size_bytes": path.stat().st_size,
        })
    return items


@route("GET", r"/api/chat/reports/(?P<filename>chat_report_[\w-]+\.md)")
def api_chat_report_file(handler: "Handler", match: re.Match) -> Any:
    path = OUTPUTS_DIR / match.group("filename")
    if not path.exists():
        raise ApiError(404, "report file not found")
    return {"markdown": path.read_text(encoding="utf-8")}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---- HTTP handler ---------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # 콘솔 로그를 조용하게
        pass

    @property
    def query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _dispatch(self, method: str) -> None:
        path = urlparse(self.path).path

        if method == "GET" and not path.startswith("/api/"):
            self._serve_static(path)
            return

        for m, regex, fn in ROUTES:
            if m != method:
                continue
            match = regex.match(path)
            if match:
                try:
                    result = fn(self, match)
                    self._send_json(200, result)
                except ApiError as exc:
                    self._send_json(exc.status, {"error": exc.message})
                except Exception:
                    traceback.print_exc()
                    self._send_json(500, {"error": "internal server error"})
                return
        self._send_json(404, {"error": "not found"})

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        file_path = (STATIC_DIR / rel).resolve()
        if STATIC_DIR.resolve() not in file_path.parents and file_path != STATIC_DIR.resolve():
            self._send_json(403, {"error": "forbidden"})
            return
        if not file_path.exists() or not file_path.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")


def serve(host: str = "127.0.0.1", port: int = 8899) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"electronics-insight-agent FE: http://{host}:{port}  (Ctrl+C로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
