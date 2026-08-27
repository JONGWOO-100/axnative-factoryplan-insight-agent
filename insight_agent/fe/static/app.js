// 바닐라 JS SPA -- 빌드 도구/프레임워크 없이 6개 탭(대화형분석/대화리포트/PRD/트레이스/HITL/HOTL)을 구현한다.

const state = {
  activeTab: "chat",
  approvalStatus: "pending",
  selectedRunId: null,
  chatSessionId: null,
  chatPolling: false,
  selectedReportFilename: null,
};

// ---- 공통 유틸 -----------------------------------------------------------

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || `요청 실패: ${res.status}`);
  return body;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) node.appendChild(child);
  return node;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// 아주 작은 markdown -> html 변환기. prd.md/대화 리포트에서 쓰는 문법(#/##, 표, 목록, **, `, >, ```)만 지원한다.
function renderMarkdown(md) {
  const lines = md.split("\n");
  let html = "";
  let i = 0;
  let inList = false;
  let inCode = false;

  const inlineFmt = (s) =>
    escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith("```")) {
      if (!inCode) { closeList(); html += "<pre>"; inCode = true; }
      else { html += "</pre>"; inCode = false; }
      i++; continue;
    }
    if (inCode) { html += escapeHtml(line) + "\n"; i++; continue; }

    if (line.startsWith("# ")) { closeList(); html += `<h1>${inlineFmt(line.slice(2))}</h1>`; i++; continue; }
    if (line.startsWith("## ")) { closeList(); html += `<h2>${inlineFmt(line.slice(3))}</h2>`; i++; continue; }
    if (line.startsWith("> ")) { closeList(); html += `<blockquote>${inlineFmt(line.slice(2))}</blockquote>`; i++; continue; }

    if (line.startsWith("- ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inlineFmt(line.slice(2))}</li>`;
      i++; continue;
    }
    closeList();

    if (line.startsWith("|")) {
      const tableLines = [];
      while (i < lines.length && lines[i].startsWith("|")) { tableLines.push(lines[i]); i++; }
      const rows = tableLines
        .filter((l) => !/^\|[\s-]*\|$/.test(l.replace(/[-\s|]/g, (c) => (c === "|" ? "|" : ""))) && !/^\|(\s*-+\s*\|)+$/.test(l))
        .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
      if (rows.length) {
        html += "<table><thead><tr>" + rows[0].map((c) => `<th>${inlineFmt(c)}</th>`).join("") + "</tr></thead><tbody>";
        for (const r of rows.slice(1)) {
          html += "<tr>" + r.map((c) => `<td>${inlineFmt(c)}</td>`).join("") + "</tr>";
        }
        html += "</tbody></table>";
      }
      continue;
    }

    if (line.trim() === "") { i++; continue; }
    html += `<p>${inlineFmt(line)}</p>`;
    i++;
  }
  closeList();
  return html;
}

// ---- 탭 전환 --------------------------------------------------------------

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      state.activeTab = btn.dataset.tab;
      onTabShown(btn.dataset.tab);
    });
  });
}

function showTab(tab) {
  document.querySelector(`.tab-btn[data-tab="${tab}"]`).click();
}

function onTabShown(tab) {
  if (tab === "prd") loadPrd();
  if (tab === "trace") loadRuns();
  if (tab === "hitl") loadApprovals();
  if (tab === "hotl") loadHotl();
  if (tab === "report") loadReportList();
}

// ---- 대화형 분석 탭 ---------------------------------------------------------

// 실제 실행 순서(engine.py)와 맞춘 단계 정의: 도메인이 아닌 통합(인과) 리포트
// 경로에서만 발생하는 ④/⑤ 단계는 fdc/yield/kpi/graph 질의에서는 의도적으로
// pending으로 남는다 -- 가드레일-리포트 검증과 HITL 게이트는 실제로 통합
// 리포트에만 적용되는 게이트이기 때문이다.
const PIPELINE_STAGES = [
  { key: "orchestrator", label: "① 오케스트레이터 (도메인 라우팅)", match: (s) => s === "pipeline.chat_turn" || s === "orchestrator.classify" },
  { key: "graph", label: "② GraphRAG 리트리버 + 그래프 검증", match: (s) => s.startsWith("graph_agent.") || s === "harness.guardrails.validate_graph" },
  { key: "agent", label: "③ 도메인 에이전트 (MCP 툴 호출)", match: (s) => /^(fdc_agent|yield_agent|kpi_agent|integration_agent)\./.test(s) },
  { key: "guardrails", label: "④ 리포트 가드레일 검증", match: (s) => s === "harness.guardrails.validate_report" },
  { key: "hitl", label: "⑤ HITL 게이트 (승인 필요 판단)", match: (s) => s.startsWith("hitl.") },
  { key: "narrative", label: "⑥ 응답 합성 (LLM/템플릿)", match: (s) => s === "pipeline.narrative" || s === "integration_agent.narrative" },
];

function renderPipelineSkeleton() {
  const container = document.getElementById("pipeline-viz");
  container.innerHTML = "";
  for (const stage of PIPELINE_STAGES) {
    const node = el("div", { class: "pipeline-node pending", id: `pipeline-node-${stage.key}` }, [
      el("span", { class: "pipeline-dot" }),
      el("span", { class: "pipeline-label", text: stage.label }),
    ]);
    container.appendChild(node);
  }
}

function updatePipeline(steps, isRunning) {
  const stepNames = steps.map((s) => s.step);
  let lastMatchedIdx = -1;
  const matched = PIPELINE_STAGES.map((stage, idx) => {
    const hit = stepNames.some((name) => stage.match(name));
    if (hit) lastMatchedIdx = idx;
    return hit;
  });
  PIPELINE_STAGES.forEach((stage, idx) => {
    const node = document.getElementById(`pipeline-node-${stage.key}`);
    if (!node) return;
    node.classList.remove("pending", "active", "done");
    if (!matched[idx]) { node.classList.add("pending"); return; }
    node.classList.add(isRunning && idx === lastMatchedIdx ? "active" : "done");
  });

  const graphStep = steps.find((s) => s.step === "graph_agent.graph_query");
  const graphBody = document.getElementById("graph-context-body");
  if (graphStep && graphStep.output) {
    const ctx = graphStep.output.context_text;
    graphBody.textContent = ctx && ctx.trim() ? ctx : "(이번 질의와 매칭되는 그래프 엔터티를 찾지 못했습니다)";
  }
}

function appendChatBubble(role, text) {
  const messages = document.getElementById("chat-messages");
  const bubble = el("div", { class: `chat-bubble chat-bubble-${role}` });
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function renderSuggestions(questions) {
  const container = document.getElementById("chat-suggestions");
  container.innerHTML = "";
  for (const q of questions || []) {
    const chip = el("button", { type: "button", class: "suggestion-chip", text: q });
    chip.addEventListener("click", () => sendChatMessage(q));
    container.appendChild(chip);
  }
}

function updateTurnCount(turnCount) {
  document.getElementById("chat-turn-count").textContent =
    turnCount > 0 ? `현재 ${turnCount}턴 대화 진행 중` : "대화를 시작해보세요.";
}

async function initChat() {
  const session = await api("/api/chat/sessions", { method: "POST" });
  state.chatSessionId = session.session_id;
  renderPipelineSkeleton();
  renderSuggestions(session.suggested_questions);
  updateTurnCount(0);
}

async function saveReport() {
  const btn = document.getElementById("chat-save-report-btn");
  if (!state.chatSessionId) return;
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "저장 중...";
  try {
    const { report_path } = await api(`/api/chat/sessions/${state.chatSessionId}/report`, { method: "POST" });
    const link = el("button", { type: "button", class: "report-ready-link", text: `리포트가 저장되었습니다 -- 보러 가기 (${report_path.split("/").pop()})` });
    link.addEventListener("click", () => showTab("report"));
    document.getElementById("chat-messages").appendChild(link);
    document.getElementById("chat-messages").scrollTop = document.getElementById("chat-messages").scrollHeight;
  } catch (err) {
    appendChatBubble("assistant", `리포트 저장 실패: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function pollTurn(runId) {
  state.chatPolling = true;
  const statusEl = document.getElementById("run-status");
  while (true) {
    let turnState, traceSteps;
    try {
      [turnState, traceSteps] = await Promise.all([
        api(`/api/chat/turns/${runId}`),
        api(`/api/runs/${runId}`).catch(() => []),
      ]);
    } catch (err) {
      appendChatBubble("assistant", `오류: ${err.message}`);
      break;
    }
    const running = turnState.status === "running";
    updatePipeline(traceSteps, running);
    if (turnState.status === "running") {
      await new Promise((r) => setTimeout(r, 400));
      continue;
    }
    if (turnState.status === "error") {
      appendChatBubble("assistant", `오류: ${turnState.error}`);
      break;
    }
    const result = turnState.result;
    appendChatBubble("assistant", result.reply);
    renderSuggestions(result.suggested_questions);
    updateTurnCount(result.turn_count);
    break;
  }
  state.chatPolling = false;
}

async function sendChatMessage(message) {
  if (!message || !state.chatSessionId || state.chatPolling) return;
  appendChatBubble("user", message);
  document.getElementById("chat-input").value = "";
  const { run_id } = await api(`/api/chat/sessions/${state.chatSessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  await pollTurn(run_id);
}

function setupChat() {
  document.getElementById("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const message = input.value.trim();
    if (message) sendChatMessage(message);
  });
  document.getElementById("chat-save-report-btn").addEventListener("click", saveReport);
}

// ---- 대화 리포트 탭 ----------------------------------------------------------

async function loadReportList() {
  const items = await api("/api/chat/reports");
  const list = document.getElementById("report-list");
  list.innerHTML = "";
  if (!items.length) {
    list.appendChild(el("div", { class: "status-text", text: "아직 저장된 리포트가 없습니다. 대화형 분석 탭에서 \"리포트 저장\" 버튼을 눌러보세요." }));
    return;
  }
  for (const item of items) {
    const node = el("div", {
      class: "list-item" + (item.filename === state.selectedReportFilename ? " active" : ""),
      text: `${item.session_id} · ${new Date(item.modified_at * 1000).toLocaleString()}`,
    });
    node.addEventListener("click", async () => {
      state.selectedReportFilename = item.filename;
      document.querySelectorAll("#report-list .list-item").forEach((n) => n.classList.remove("active"));
      node.classList.add("active");
      const { markdown } = await api(`/api/chat/reports/${item.filename}`);
      document.getElementById("report-content").innerHTML = renderMarkdown(markdown);
    });
    list.appendChild(node);
  }
}

document.getElementById("report-refresh-btn").addEventListener("click", loadReportList);

// ---- PRD(Day1) 탭 -----------------------------------------------------------

async function loadPrd() {
  const { markdown } = await api("/api/prd");
  document.getElementById("prd-content").innerHTML = renderMarkdown(markdown);
}

// ---- 트레이스 탭 ------------------------------------------------------------

async function loadRuns() {
  const runs = await api("/api/runs");
  const list = document.getElementById("run-list");
  list.innerHTML = "";
  if (!runs.length) {
    list.appendChild(el("div", { class: "status-text", text: "아직 실행 기록이 없습니다." }));
    return;
  }
  for (const run of runs) {
    const item = el("div", {
      class: "list-item" + (run.run_id === state.selectedRunId ? " active" : ""),
      text: `${run.lot_id || "(로트 미상)"} · ${run.step_count}단계`,
    });
    item.addEventListener("click", () => {
      state.selectedRunId = run.run_id;
      document.querySelectorAll(".list-item").forEach((n) => n.classList.remove("active"));
      item.classList.add("active");
      loadRunDetail(run.run_id);
    });
    list.appendChild(item);
  }
}

async function loadRunDetail(runId) {
  const records = await api(`/api/runs/${runId}`);
  const container = document.getElementById("run-detail");
  container.innerHTML = "";
  for (const rec of records) {
    const step = el("div", { class: "timeline-step" });
    step.appendChild(el("div", { class: "step-name", text: rec.step }));
    step.appendChild(el("pre", { text: JSON.stringify(rec.output, null, 2) }));
    container.appendChild(step);
  }
}

// ---- HITL 탭 ---------------------------------------------------------------

function setupHitlSubtabs() {
  document.querySelectorAll(".subtab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.approvalStatus = btn.dataset.status;
      loadApprovals();
    });
  });
}

async function loadApprovals() {
  const items = await api(`/api/approvals?status=${state.approvalStatus}`);
  const body = document.getElementById("approval-body");
  body.innerHTML = "";
  for (const item of items) {
    const report = item.report;
    const tr = el("tr");
    tr.appendChild(el("td", { text: item.approval_id }));
    tr.appendChild(el("td", { text: `${report.lot_id}` }));
    tr.appendChild(el("td", { text: report.product_node }));
    tr.appendChild(el("td", {
      html: `<span class="badge badge-critical">${report.fdc_interlock_count}건</span>`,
    }));
    tr.appendChild(el("td", { text: report.die_yield_pct != null ? `${report.die_yield_pct}%` : "-" }));
    tr.appendChild(el("td", { text: report.narrative_summary || "-" }));

    const actionCell = el("td");
    if (state.approvalStatus === "pending") {
      const approveBtn = el("button", { text: "승인" });
      approveBtn.addEventListener("click", async () => {
        await api(`/api/approvals/${item.approval_id}/approve`, { method: "POST" });
        loadApprovals();
      });
      const rejectBtn = el("button", { text: "반려" });
      rejectBtn.addEventListener("click", async () => {
        const reason = prompt("반려 사유를 입력하세요", "") || "";
        await api(`/api/approvals/${item.approval_id}/reject`, {
          method: "POST",
          body: JSON.stringify({ reason }),
        });
        loadApprovals();
      });
      actionCell.appendChild(approveBtn);
      actionCell.appendChild(rejectBtn);
    } else if (item.rejected_reason) {
      actionCell.textContent = `사유: ${item.rejected_reason}`;
    }
    tr.appendChild(actionCell);
    body.appendChild(tr);
  }
  if (!items.length) {
    body.appendChild(el("tr", {}, [el("td", { colspan: "7", class: "status-text", text: "해당 상태의 건이 없습니다." })]));
  }
}

// ---- HOTL 탭 ---------------------------------------------------------------

async function loadHotl() {
  const snapshot = await api("/api/hotl");
  document.getElementById("hotl-message").textContent = snapshot.message || "";

  const alertBody = document.getElementById("hotl-alert-body");
  alertBody.innerHTML = "";
  for (const a of snapshot.alerts || []) {
    const tr = el("tr");
    tr.appendChild(el("td", { text: a.product_node }));
    tr.appendChild(el("td", { text: a.quarter }));
    tr.appendChild(el("td", { html: `<span class="badge badge-critical">${a.delta_pp}%p</span>` }));
    alertBody.appendChild(tr);
  }
  if (!(snapshot.alerts || []).length) {
    alertBody.appendChild(el("tr", {}, [el("td", { colspan: "3", class: "status-text", text: "현재 알림이 없습니다." })]));
  }

  const trendBody = document.getElementById("hotl-trend-body");
  trendBody.innerHTML = "";
  for (const t of (snapshot.trend || []).slice(-40)) {
    const tr = el("tr");
    tr.appendChild(el("td", { text: t.product_node }));
    tr.appendChild(el("td", { text: t.quarter }));
    tr.appendChild(el("td", { text: t.die_yield_pct.toFixed(1) }));
    trendBody.appendChild(tr);
  }
}

document.getElementById("hotl-refresh-btn").addEventListener("click", async () => {
  await api("/api/hotl/refresh", { method: "POST" });
  loadHotl();
});

// ---- 상단 바: 로트 선택 + 분석 실행 (레거시 단건 실행 경로) -------------------

async function loadLots() {
  const lots = await api("/api/lots");
  const select = document.getElementById("lot-select");
  for (const l of lots) {
    select.appendChild(el("option", { value: l.lot_id, text: `${l.lot_id} (${l.product_node})` }));
  }
}

document.getElementById("run-btn").addEventListener("click", async () => {
  const lotId = document.getElementById("lot-select").value;
  const statusEl = document.getElementById("run-status");
  if (!lotId) { statusEl.textContent = "로트를 먼저 선택하세요."; return; }
  statusEl.textContent = "실행 중...";
  try {
    const outcome = await api("/api/run", { method: "POST", body: JSON.stringify({ lot_id: lotId }) });
    statusEl.textContent = `완료: ${outcome.status} (run ${outcome.run_id})`;
    if (state.activeTab === "trace") loadRuns();
    if (state.activeTab === "hitl") loadApprovals();
  } catch (err) {
    statusEl.textContent = `오류: ${err.message}`;
  }
});

// ---- 초기화 ----------------------------------------------------------------

setupTabs();
setupHitlSubtabs();
setupChat();
loadLots();
initChat();
