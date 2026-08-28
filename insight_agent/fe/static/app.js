// 바닐라 JS SPA -- 빌드 도구/프레임워크 없이 2개 탭(대화형분석/산출물)을 구현한다.
// 트레이스/HITL 승인 큐/HOTL 모니터/레거시 단건 실행 UI는 제거됐다 -- 백엔드 API와
// 데이터(runs/approvals/outputs)는 그대로 남아 있어 CLI(`insight_agent.hitl.cli` 등)로는
// 계속 쓸 수 있고, 필요하면 나중에 다시 화면에 노출할 수 있다.

const state = {
  activeTab: "chat",
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
  if (tab === "outputs") refreshActiveOutputPanel();
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
    renderGraph(graphStep.output);
  }
}

// ---------------------------------------------------------------------------
// GraphRAG 시각화
//
// 외부 라이브러리를 쓰지 않는다 -- 이 FE는 stdlib http.server가 정적 파일만
// 내려주고, 오프라인/사내망에서도 그대로 떠야 한다. 노드 수가 최대 40개
// (retriever의 max_nodes)라 간단한 힘기반 배치로 충분하다.
// ---------------------------------------------------------------------------

const NODE_TYPES = {
  lot:     { label: "로트",    color: "var(--accent)" },
  process: { label: "공정",    color: "var(--ok)" },
  chamber: { label: "챔버",    color: "var(--warn)" },
  agent:   { label: "AI에이전트", color: "#8b5cf6" },
  defect:  { label: "결함",    color: "var(--danger)" },
  lake:    { label: "데이터레이크", color: "#0891b2" },
};
const UNKNOWN_TYPE = { label: "기타", color: "var(--muted)" };
const typeStyle = (t) => NODE_TYPES[t] || UNKNOWN_TYPE;

// 인터록은 이상 사건이므로 다른 관계와 구분해 표시한다. 나머지는 구조적 관계다.
const EVENT_RELATIONS = new Set(["interlock_event"]);

function layoutGraph(nodes, links, width, height) {
  // 초기 배치를 원형으로 두면(무작위 대신) 같은 질의가 같은 그림을 그린다.
  const n = nodes.length;
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n;
    const r = Math.min(width, height) * 0.32;
    node.x = width / 2 + r * Math.cos(angle);
    node.y = height / 2 + r * Math.sin(angle);
  });

  const byId = new Map(nodes.map((d) => [d.id, d]));
  const pairs = links
    .map((l) => [byId.get(l.source), byId.get(l.target)])
    .filter(([a, b]) => a && b);

  const SPRING = 82;        // 이웃 노드 사이 목표 거리
  const REPULSION = 6400;   // 서로 밀어내는 힘
  for (let step = 0; step < 320; step++) {
    const cooling = 1 - step / 320;
    nodes.forEach((a) => {
      let fx = 0;
      let fy = 0;
      nodes.forEach((b) => {
        if (a === b) return;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = Math.max(dx * dx + dy * dy, 40);
        const f = REPULSION / d2;
        fx += (dx / Math.sqrt(d2)) * f;
        fy += (dy / Math.sqrt(d2)) * f;
      });
      // 중심으로 살짝 당겨 화면 밖으로 흩어지지 않게 한다
      // 중심 인장이 세면 노드가 가운데로 뭉쳐 라벨이 겹친다 -- 약하게 둔다
      fx += (width / 2 - a.x) * 0.007;
      fy += (height / 2 - a.y) * 0.007;
      a.fx = fx;
      a.fy = fy;
    });
    pairs.forEach(([a, b]) => {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(Math.hypot(dx, dy), 1);
      const f = (dist - SPRING) * 0.05;
      const ux = (dx / dist) * f;
      const uy = (dy / dist) * f;
      a.fx += ux; a.fy += uy;
      b.fx -= ux; b.fy -= uy;
    });
    nodes.forEach((a) => {
      a.x += Math.max(-14, Math.min(14, a.fx)) * cooling;
      a.y += Math.max(-14, Math.min(14, a.fy)) * cooling;
      a.x = Math.max(46, Math.min(width - 46, a.x));
      a.y = Math.max(24, Math.min(height - 24, a.y));
    });
  }
  return nodes;
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  return node;
}

function renderGraph(result) {
  const host = document.getElementById("graph-viz");
  const legend = document.getElementById("graph-legend");
  const stats = document.getElementById("graph-stats");
  if (!host) return;
  host.textContent = "";

  const rawNodes = result.nodes || [];
  const facts = result.facts || [];
  if (!rawNodes.length) {
    host.appendChild(el("p", {
      class: "status-text graph-empty",
      text: "이번 질의와 매칭되는 그래프 엔터티를 찾지 못했습니다.",
    }));
    legend.hidden = true;
    stats.textContent = "";
    return;
  }

  const seedIds = new Set((result.seed_nodes || []).map((s) => s.id));
  const present = new Set(rawNodes.map((n) => n.id));
  const links = facts
    .filter((f) => present.has(f.source_id) && present.has(f.target_id))
    .map((f) => ({ source: f.source_id, target: f.target_id, relation: f.relation }));

  const degree = new Map(rawNodes.map((n) => [n.id, 0]));
  links.forEach((l) => {
    degree.set(l.source, (degree.get(l.source) || 0) + 1);
    degree.set(l.target, (degree.get(l.target) || 0) + 1);
  });

  const width = Math.max(host.clientWidth || 420, 320);
  const height = 360;
  const nodes = layoutGraph(
    rawNodes.map((n) => ({ ...n, seed: seedIds.has(n.id), deg: degree.get(n.id) || 0 })),
    links, width, height
  );
  const byId = new Map(nodes.map((n) => [n.id, n]));

  const svg = svgEl("svg", {
    class: "graph-svg", viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `지식 그래프: 노드 ${nodes.length}개, 관계 ${links.length}개`,
  });
  const defs = svgEl("defs");
  ["arrow-structural", "arrow-event"].forEach((id) => {
    const marker = svgEl("marker", {
      id, viewBox: "0 0 8 8", refX: "7", refY: "4",
      markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse",
    });
    marker.appendChild(svgEl("path", {
      d: "M0,0 L8,4 L0,8 Z",
      fill: id === "arrow-event" ? "var(--danger)" : "var(--muted)",
    }));
    marker.setAttribute("markerUnits", "strokeWidth");
    defs.appendChild(marker);
  });
  svg.appendChild(defs);

  // 간선을 먼저 그려 노드가 위에 오게 한다
  const edgeLayer = svgEl("g", { class: "graph-edges" });
  links.forEach((l) => {
    const a = byId.get(l.source);
    const b = byId.get(l.target);
    if (!a || !b) return;
    const isEvent = EVENT_RELATIONS.has(l.relation);
    const line = svgEl("line", {
      x1: a.x.toFixed(1), y1: a.y.toFixed(1), x2: b.x.toFixed(1), y2: b.y.toFixed(1),
      class: `graph-edge${isEvent ? " graph-edge-event" : ""}`,
      "marker-end": `url(#${isEvent ? "arrow-event" : "arrow-structural"})`,
      "data-a": l.source, "data-b": l.target,
    });
    line.appendChild(svgEl("title")).textContent = `${a.label} --${l.relation}--> ${b.label}`;
    edgeLayer.appendChild(line);
  });
  svg.appendChild(edgeLayer);

  const nodeLayer = svgEl("g", { class: "graph-nodes" });
  nodes.forEach((n) => {
    const style = typeStyle(n.type);
    const r = n.seed ? 11 : 6 + Math.min(n.deg, 6) * 0.7;
    const g = svgEl("g", { class: `graph-node${n.seed ? " is-seed" : ""}`, "data-id": n.id });
    if (n.seed) {
      // 시드는 질의에서 직접 매칭된 노드다 -- 링을 둘러 구분한다
      g.appendChild(svgEl("circle", {
        cx: n.x.toFixed(1), cy: n.y.toFixed(1), r: (r + 4).toFixed(1),
        class: "graph-seed-ring", stroke: style.color,
      }));
    }
    g.appendChild(svgEl("circle", {
      cx: n.x.toFixed(1), cy: n.y.toFixed(1), r: r.toFixed(1),
      fill: style.color, class: "graph-dot",
    }));
    const label = svgEl("text", {
      x: n.x.toFixed(1), y: (n.y - r - 5).toFixed(1),
      class: "graph-label", "text-anchor": "middle",
    });
    // 로트 ID는 뒷자리가 식별 정보이므로 자르지 않는다(14자). 공정명 등 긴 한글만 줄인다.
    label.textContent = n.label.length > 14 ? `${n.label.slice(0, 13)}…` : n.label;
    g.appendChild(label);
    g.appendChild(svgEl("title")).textContent =
      `${n.label}\n종류: ${style.label}\nID: ${n.id}\n연결 ${n.deg}개${n.seed ? "\n(질의에서 매칭된 시드)" : ""}`;
    nodeLayer.appendChild(g);
  });
  svg.appendChild(nodeLayer);
  host.appendChild(svg);

  // 라벨 겹침 해소 -- 배치만으로는 15개 내외에서 두세 쌍이 겹친다. DOM에 붙인 뒤
  // 실측(getBBox)해서 겹치는 라벨을 노드 아래로 내리고, 그래도 겹치면 조금 밀어낸다.
  const placed = [];
  const hits = (box) => placed.some((q) =>
    box.x < q.x + q.width && q.x < box.x + box.width &&
    box.y < q.y + q.height && q.y < box.y + box.height);
  // 중요한 라벨을 먼저 배치한다 -- 시드, 그다음 연결이 많은 노드. 자리가 없어
  // 떨어지는 것은 주변부 노드가 되고, 이름은 마우스를 올리면 title로 볼 수 있다.
  const ordered = [...nodeLayer.querySelectorAll(".graph-node")].sort((ga, gb) => {
    const a = byId.get(ga.dataset.id);
    const b = byId.get(gb.dataset.id);
    return (b.seed - a.seed) || (b.deg - a.deg);
  });
  ordered.forEach((g) => {
    const label = g.querySelector(".graph-label");
    const n = byId.get(g.dataset.id);
    if (!label || !n) return;
    const r = +g.querySelector(".graph-dot").getAttribute("r");
    const above = n.y - r - 5;
    const below = n.y + r + 11;
    // 가로 클램프를 먼저 한다. 라벨은 text-anchor=middle이라 긴 이름이 화면 밖으로
    // 삐져나가는데, 겹침 해소 뒤에 밀어넣으면 그 이동이 새 겹침을 만든다.
    const box = label.getBBox();
    if (box.x < 2) label.setAttribute("x", (n.x + (2 - box.x)).toFixed(1));
    else if (box.x + box.width > width - 2) {
      label.setAttribute("x", (n.x - (box.x + box.width - (width - 2))).toFixed(1));
    }
    // 그다음 세로로 자리를 찾는다. 어느 자리에도 안 들어가면 라벨을 지운다 --
    // 겹쳐서 둘 다 못 읽게 되는 것보다 하나를 비우는 편이 낫다.
    let seated = false;
    for (const y of [above, below, above - 12, below + 12, above - 24, below + 24]) {
      label.setAttribute("y", y.toFixed(1));
      if (!hits(label.getBBox())) { seated = true; break; }
    }
    if (!seated) { label.remove(); return; }
    placed.push(label.getBBox());
  });

  // 노드에 올리면 인접하지 않은 것을 흐리게 해 관계를 읽기 쉽게 한다
  nodeLayer.querySelectorAll(".graph-node").forEach((g) => {
    const id = g.dataset.id;
    g.addEventListener("mouseenter", () => {
      const near = new Set([id]);
      links.forEach((l) => {
        if (l.source === id) near.add(l.target);
        if (l.target === id) near.add(l.source);
      });
      svg.classList.add("is-focusing");
      nodeLayer.querySelectorAll(".graph-node").forEach((o) =>
        o.classList.toggle("is-dim", !near.has(o.dataset.id)));
      edgeLayer.querySelectorAll(".graph-edge").forEach((e) =>
        e.classList.toggle("is-dim", e.dataset.a !== id && e.dataset.b !== id));
    });
    g.addEventListener("mouseleave", () => {
      svg.classList.remove("is-focusing");
      svg.querySelectorAll(".is-dim").forEach((o) => o.classList.remove("is-dim"));
    });
  });

  const usedTypes = [...new Set(nodes.map((n) => n.type))];
  legend.textContent = "";
  usedTypes.forEach((t) => {
    const style = typeStyle(t);
    const item = el("span", { class: "graph-legend-item" });
    item.appendChild(el("i", { class: "graph-swatch", style: `background:${style.color}` }));
    item.appendChild(document.createTextNode(
      `${style.label} ${nodes.filter((n) => n.type === t).length}`));
    legend.appendChild(item);
  });
  if (links.some((l) => EVENT_RELATIONS.has(l.relation))) {
    const item = el("span", { class: "graph-legend-item" });
    item.appendChild(el("i", { class: "graph-swatch graph-swatch-event" }));
    item.appendChild(document.createTextNode("인터록 발생"));
    legend.appendChild(item);
  }
  legend.hidden = false;
  stats.textContent = `노드 ${nodes.length} · 관계 ${links.length} · 시드 ${seedIds.size}`;
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
    link.addEventListener("click", () => showTab("outputs"));
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
    renderTurnSummary(traceSteps);
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

// ---- 산출물 탭: 대화 리포트 / PRD 서브탭 -------------------------------------

function setupOutputSubtabs() {
  document.querySelectorAll(".subtab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".output-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`output-${btn.dataset.output}`).classList.add("active");
      refreshActiveOutputPanel();
    });
  });
}

function refreshActiveOutputPanel() {
  const active = document.querySelector(".subtab-btn.active");
  const which = active ? active.dataset.output : "report";
  if (which === "prd") loadPrd();
  else loadReportList();
}

async function loadReportList() {
  const items = await api("/api/chat/reports");
  const list = document.getElementById("report-list");
  list.innerHTML = "";
  if (!items.length) {
    list.appendChild(el("div", { class: "status-text", text: "아직 저장된 리포트가 없습니다. \"대화형 분석\" 탭에서 \"리포트 저장\" 버튼을 눌러보세요." }));
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

// PRD는 자동 생성되지 않는다 -- docs/prd.md가 없으면 docs/PRD_TEMPLATE.md를 대신
// 보여준다. 교육생은 이 템플릿을 복사해 docs/prd.md를 직접 작성한다.
async function loadPrd() {
  const { markdown, is_template } = await api("/api/prd");
  const banner = document.getElementById("prd-banner");
  banner.textContent = is_template
    ? "docs/prd.md가 아직 없습니다. 아래는 작성 가이드 템플릿(docs/PRD_TEMPLATE.md)입니다 -- 복사해서 docs/prd.md로 직접 작성해보세요."
    : "";
  banner.style.display = is_template ? "block" : "none";
  document.getElementById("prd-content").innerHTML = renderMarkdown(markdown);
}

// ---- 초기화 ----------------------------------------------------------------

setupTabs();
setupOutputSubtabs();
setupChat();
initChat();

// ---------------------------------------------------------------------------
// 수치 요약 도식화
//
// 리포트에 적힌 숫자를 문장으로만 두면 크기 비교가 안 된다. 턴이 끝나면 그 턴이
// 실제로 만든 수치를 트레이스에서 읽어 카드로 그린다 -- 새 판단을 하지 않고
// 이미 계산된 값만 표현한다(AGENTS.md: fe/에 도메인 판단 로직을 넣지 않는다).
//
// 형식 선택 근거:
//  - 스케일이 다른 지표를 한 축에 얹지 않는다. DX KPI 8종은 stat tile,
//    36개월 추이는 각자 축을 갖는 스파크라인 small multiples로 나눈다.
//  - 로트 수율과 노드 평균은 동급 계열이 아니라 '값과 기준'이므로 막대 하나 +
//    기준선으로 그린다.
//  - 근거 구성(인터록/겹침/VM초과)만 계열이 셋이라 범례를 붙이고, 세그먼트마다
//    직접 라벨을 단다. 라이트 모드에서 series-2/3 대비가 3:1 미만이어서
//    라벨이 필수 완화 조치다.
// ---------------------------------------------------------------------------

const KPI_LABELS = {
  daily_lake_ingest_tb: "레이크 유입량 (TB/일)",
  ai_closed_loop_decision_rate_pct: "AI 폐루프 의사결정률 (%)",
  oht_dispatch_latency_ms: "OHT 반송 지연 (ms)",
  data_lake_quality_score_pct: "데이터 품질 점수 (%)",
  unplanned_downtime_hours: "미계획 다운타임 (h)",
  monthly_energy_saving_mwh: "월 에너지 절감 (MWh)",
  active_ai_models_count: "운영 AI 모델 수",
  semiconductor_ds_cpk: "공정능력 Cpk",
};

const fmt = (v, digits = 2) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(digits);
};

function vizBlock(title, node, note) {
  const wrap = el("div", { class: "viz-block" }, [el("span", { class: "viz-block-title", text: title })]);
  wrap.appendChild(node);
  if (note) wrap.appendChild(el("p", { class: "viz-note", text: note }));
  return wrap;
}

function vizLegend(items) {
  const box = el("div", { class: "viz-legend" });
  items.forEach(({ label, color }) => {
    const it = el("span", { class: "viz-legend-item" });
    it.appendChild(el("i", { class: "viz-legend-swatch", style: `background:${color}` }));
    it.appendChild(document.createTextNode(label));
    box.appendChild(it);
  });
  return box;
}

/** 값 막대 하나 + 점선 기준선. 두 값을 나란한 계열로 두지 않는다. */
function chartBarVsReference({ value, reference, unit, valueLabel, refLabel }) {
  const W = 320, H = 62, PAD_L = 4, PAD_R = 4, BAR_Y = 14, BAR_H = 18;
  const max = Math.max(value, reference) * 1.12 || 1;
  const scale = (v) => PAD_L + ((W - PAD_L - PAD_R) * v) / max;
  const svg = svgEl("svg", {
    class: "viz-chart", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `${valueLabel} ${fmt(value)}${unit}, ${refLabel} ${fmt(reference)}${unit}`,
  });
  const bar = svgEl("rect", {
    x: PAD_L, y: BAR_Y, width: Math.max(scale(value) - PAD_L, 2), height: BAR_H,
    rx: 4, fill: "var(--viz-series-1)",
  });
  bar.appendChild(svgEl("title")).textContent = `${valueLabel} ${fmt(value)}${unit}`;
  svg.appendChild(bar);
  const vx = Math.min(scale(value) + 6, W - 46);
  const vl = svgEl("text", { x: vx, y: BAR_Y + 13, class: "viz-value-label" });
  vl.textContent = `${fmt(value)}${unit}`;
  svg.appendChild(vl);
  const rx = scale(reference);
  svg.appendChild(svgEl("line", { x1: rx, y1: BAR_Y - 6, x2: rx, y2: BAR_Y + BAR_H + 6, class: "viz-ref-line" }));
  const rl = svgEl("text", {
    x: Math.min(rx + 5, W - 4), y: H - 8, class: "viz-tick",
    "text-anchor": rx > W - 90 ? "end" : "start",
  });
  rl.textContent = `${refLabel} ${fmt(reference)}${unit}`;
  svg.appendChild(rl);
  return svg;
}

/** 누적 막대 하나. 세그먼트 사이에 서피스 색 간격을 두고 라벨을 직접 단다. */
function chartStackedBar(parts, totalLabel) {
  const shown = parts.filter((p) => p.value > 0);
  const total = shown.reduce((s, p) => s + p.value, 0);
  const W = 320, H = 52, BAR_Y = 6, BAR_H = 20, GAP = 2;
  const svg = svgEl("svg", {
    class: "viz-chart", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": shown.map((p) => `${p.label} ${p.value}`).join(", "),
  });
  if (!total) {
    const t = svgEl("text", { x: 4, y: 22, class: "viz-tick" });
    t.textContent = "이상 없음";
    svg.appendChild(t);
    return svg;
  }
  let x = 0;
  shown.forEach((p, i) => {
    const w = ((W - GAP * (shown.length - 1)) * p.value) / total;
    const seg = svgEl("rect", {
      x: x.toFixed(1), y: BAR_Y, width: Math.max(w, 2).toFixed(1), height: BAR_H,
      rx: i === 0 || i === shown.length - 1 ? 4 : 0, fill: p.color,
    });
    seg.appendChild(svgEl("title")).textContent = `${p.label}: ${p.value}건`;
    svg.appendChild(seg);
    // 대비가 낮은 색이 있어 라벨은 막대 밖 아래쪽에 둔다
    const lab = svgEl("text", {
      x: Math.min(Math.max(x + w / 2, 16), W - 16), y: BAR_Y + BAR_H + 13,
      class: "viz-value-label", "text-anchor": "middle",
    });
    lab.textContent = `${p.value}`;
    svg.appendChild(lab);
    x += w + GAP;
  });
  const t = svgEl("text", { x: 0, y: H - 2, class: "viz-tick" });
  t.textContent = totalLabel;
  svg.appendChild(t);
  return svg;
}

function chartSparkline(values, unit) {
  const W = 118, H = 30, PAD = 3;
  const svg = svgEl("svg", { class: "viz-chart", viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [
    PAD + ((W - PAD * 2) * i) / Math.max(values.length - 1, 1),
    H - PAD - ((H - PAD * 2) * (v - min)) / span,
  ]);
  svg.appendChild(svgEl("polyline", {
    points: pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "),
    fill: "none", stroke: "var(--viz-series-1)", "stroke-width": "2",
    "stroke-linejoin": "round", "stroke-linecap": "round",
  }));
  const [ex, ey] = pts[pts.length - 1];
  svg.appendChild(svgEl("circle", { cx: ex.toFixed(1), cy: ey.toFixed(1), r: 2.6, fill: "var(--viz-series-1)" }));
  svg.appendChild(svgEl("title")).textContent = `${fmt(min)} ~ ${fmt(max)}${unit || ""} (${values.length}개 구간)`;
  return svg;
}

function chartHistogram(values, unit, binCount = 12) {
  const W = 320, H = 84, PAD_B = 16, PAD_T = 12;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const bins = new Array(binCount).fill(0);
  values.forEach((v) => {
    const i = Math.min(binCount - 1, Math.floor(((v - min) / span) * binCount));
    bins[i] += 1;
  });
  const peak = Math.max(...bins) || 1;
  const bw = W / binCount;
  const svg = svgEl("svg", {
    class: "viz-chart", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `분포: ${fmt(min)} ~ ${fmt(max)}${unit || ""}, ${values.length}건`,
  });
  bins.forEach((c, i) => {
    const h = ((H - PAD_B - PAD_T) * c) / peak;
    const bar = svgEl("rect", {
      x: (i * bw + 1).toFixed(1), y: (H - PAD_B - h).toFixed(1),
      width: (bw - 2).toFixed(1), height: Math.max(h, c ? 1.5 : 0).toFixed(1),
      rx: 3, fill: "var(--viz-series-1)",
    });
    const lo = min + (span * i) / binCount, hi = min + (span * (i + 1)) / binCount;
    bar.appendChild(svgEl("title")).textContent = `${fmt(lo)} ~ ${fmt(hi)}${unit || ""}: ${c}건`;
    svg.appendChild(bar);
  });
  svg.appendChild(svgEl("line", { x1: 0, y1: H - PAD_B, x2: W, y2: H - PAD_B, class: "viz-axis" }));
  [[0, `${fmt(min)}${unit || ""}`, "start"], [W, `${fmt(max)}${unit || ""}`, "end"]].forEach(([x, txt, anchor]) => {
    const t = svgEl("text", { x, y: H - 4, class: "viz-tick", "text-anchor": anchor });
    t.textContent = txt;
    svg.appendChild(t);
  });
  const pk = svgEl("text", { x: W / 2, y: 9, class: "viz-tick", "text-anchor": "middle" });
  pk.textContent = `최다 구간 ${peak}건 · 총 ${values.length}건`;
  svg.appendChild(pk);
  return svg;
}

function categoryCounts(records, field) {
  const m = new Map();
  records.forEach((r) => {
    const k = r[field];
    if (k === undefined || k === null) return;
    m.set(k, (m.get(k) || 0) + 1);
  });
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

function chartCategoryBars(pairs) {
  const rows = pairs.slice(0, 6);
  const W = 320, ROW = 19, LABEL_W = 118;
  const H = rows.length * ROW + 4;
  const peak = Math.max(...rows.map((r) => r[1])) || 1;
  const svg = svgEl("svg", {
    class: "viz-chart", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": rows.map(([k, v]) => `${k} ${v}건`).join(", "),
  });
  rows.forEach(([k, v], i) => {
    const y = i * ROW + 3;
    const label = svgEl("text", { x: 0, y: y + 11, class: "viz-tick" });
    label.textContent = String(k).length > 15 ? `${String(k).slice(0, 14)}…` : String(k);
    svg.appendChild(label);
    const w = ((W - LABEL_W - 42) * v) / peak;
    const bar = svgEl("rect", {
      x: LABEL_W, y, width: Math.max(w, 2).toFixed(1), height: 13, rx: 3.5,
      fill: "var(--viz-series-1)",
    });
    bar.appendChild(svgEl("title")).textContent = `${k}: ${v}건`;
    svg.appendChild(bar);
    const val = svgEl("text", { x: LABEL_W + w + 5, y: y + 11, class: "viz-value-label" });
    val.textContent = String(v);
    svg.appendChild(val);
  });
  return svg;
}

function tileRow(entries) {
  const grid = el("div", { class: "viz-tiles" });
  entries.forEach(({ label, value }) => {
    grid.appendChild(el("div", { class: "viz-tile" }, [
      el("span", { class: "viz-tile-label", text: label }),
      el("div", { class: "viz-tile-value", text: value }),
    ]));
  });
  return grid;
}

/** 통합(인과) 리포트 요약 -- 이 프로젝트에서 '리포트'라고 부르는 산출물. */
function summarizeReport(report) {
  const frag = document.createDocumentFragment();
  const delta = report.die_yield_delta_pp;
  const verdict = report.causal_verdict || {};

  if (delta !== null && delta !== undefined) {
    frag.appendChild(el("div", { class: "viz-hero" }, [
      el("span", { class: "viz-hero-value", text: `${delta > 0 ? "+" : ""}${fmt(delta)}%p` }),
      el("span", { class: "viz-hero-label", text: "동일 공정 노드 평균 대비 다이 수율" }),
    ]));
  }
  if (verdict.verdict) {
    frag.appendChild(el("span", { class: "viz-badge viz-badge-unknown" }, [
      el("i", { class: "viz-badge-icon", text: "?" }),
      el("span", { text: `인과 판정 ${verdict.verdict} · ${verdict.reason || ""}` }),
    ]));
  }
  if (report.product_node_avg_die_yield_pct != null) {
    frag.appendChild(vizBlock("다이 수율", chartBarVsReference({
      value: report.die_yield_pct, reference: report.product_node_avg_die_yield_pct,
      unit: "%", valueLabel: "이 로트", refLabel: "노드 평균",
    })));
  }

  // 근거 구성: 인터록과 VM초과가 겹치는 만큼은 하나의 근거다
  const il = report.fdc_interlock_count || 0;
  const vm = report.fdc_vm_error_anomaly_count || 0;
  const both = report.fdc_interlock_vm_coincident_count || 0;
  const parts = [
    { label: "인터록만", value: il - both, color: "var(--viz-series-1)" },
    { label: "인터록 ∩ VM오차 (같은 행)", value: both, color: "var(--viz-series-2)" },
    { label: "VM오차만", value: vm - both, color: "var(--viz-series-3)" },
  ];
  const evidence = vizBlock(
    "FDC 근거 구성",
    chartStackedBar(parts, `이상 ${report.fdc_anomaly_row_count ?? 0}행 / 검사 ${report.fdc_row_count ?? 0}행`),
    both > 0 && both === il && both === vm
      ? "인터록과 VM오차가 전부 같은 행이다 — 근거는 둘이 아니라 하나다."
      : undefined
  );
  const usedParts = parts.filter((p) => p.value > 0);
  if (usedParts.length >= 2) evidence.appendChild(vizLegend(usedParts));
  frag.appendChild(evidence);

  frag.appendChild(tileRow([
    { label: "웨이퍼 수율", value: `${fmt(report.wafer_yield_pct)}%` },
    { label: "폐기 웨이퍼", value: `${fmt(report.scrap_wafer_qty)}장` },
    { label: "주요 결함", value: report.major_defect_mechanism || "—" },
  ]));

  const kpi = report.dx_kpi_context;
  if (kpi) {
    const entries = Object.keys(KPI_LABELS)
      .filter((k) => kpi[k] !== undefined)
      .map((k) => ({ label: KPI_LABELS[k], value: fmt(kpi[k]) }));
    if (entries.length) {
      // 스케일이 전부 달라 한 축에 얹지 않는다 -- 타일로 나란히 둔다
      frag.appendChild(vizBlock(`DX KPI 컨텍스트 (${kpi.year_month})`, tileRow(entries)));
    }
  }
  return frag;
}

function summarizeKpiRecords(records) {
  const frag = document.createDocumentFragment();
  const months = records.map((r) => r.year_month);
  const grid = el("div", { class: "viz-spark-grid" });
  Object.entries(KPI_LABELS).forEach(([key, label]) => {
    const vals = records.map((r) => r[key]).filter((v) => typeof v === "number");
    if (vals.length < 2) return;
    const cell = el("div", { class: "viz-spark" }, [
      el("span", { class: "viz-spark-label", text: label }),
      el("div", { class: "viz-spark-value", text: fmt(vals[vals.length - 1]) }),
    ]);
    cell.appendChild(chartSparkline(vals, ""));
    grid.appendChild(cell);
  });
  if (!grid.childNodes.length) return frag;
  frag.appendChild(vizBlock(
    `DX KPI 추이 (${months[0]} ~ ${months[months.length - 1]}, ${records.length}개월)`,
    grid,
    "지표마다 단위와 범위가 달라 각각 자기 축으로 그린다. 숫자는 마지막 달 값."
  ));
  return frag;
}

function summarizeYieldRecords(records) {
  const frag = document.createDocumentFragment();
  const yields = records.map((r) => r.die_yield_pct).filter((v) => typeof v === "number");
  if (yields.length) {
    const avg = yields.reduce((a, b) => a + b, 0) / yields.length;
    frag.appendChild(el("div", { class: "viz-hero" }, [
      el("span", { class: "viz-hero-value", text: `${fmt(avg)}%` }),
      el("span", { class: "viz-hero-label", text: `조회된 ${records.length}개 로트의 평균 다이 수율` }),
    ]));
    frag.appendChild(vizBlock("다이 수율 분포", chartHistogram(yields, "%")));
  }
  const defects = categoryCounts(records, "major_defect_mechanism");
  if (defects.length) frag.appendChild(vizBlock("결함 유형별 로트 수", chartCategoryBars(defects)));
  return frag;
}

function summarizeFdcRecords(records) {
  const frag = document.createDocumentFragment();
  const interlocks = records.filter((r) => Number(r.fdc_interlock_flag) === 1).length;
  frag.appendChild(el("div", { class: "viz-hero" }, [
    el("span", { class: "viz-hero-value", text: String(records.length) }),
    el("span", { class: "viz-hero-label", text: `이상 행 (이 중 인터록 ${interlocks}건)` }),
  ]));
  const errs = records.map((r) => r.vm_error_pct).filter((v) => typeof v === "number");
  if (errs.length) frag.appendChild(vizBlock("가상계측(VM) 오차율 분포", chartHistogram(errs, "%")));
  const chambers = categoryCounts(records, "chamber_id");
  if (chambers.length) frag.appendChild(vizBlock("챔버별 이상 건수", chartCategoryBars(chambers)));
  return frag;
}

const SUMMARY_SOURCES = [
  { step: "integration_agent.build_causal_report", domain: "통합(인과) 리포트", build: summarizeReport },
  { step: "kpi_agent.get_dx_kpi_trend", domain: "DX KPI", build: summarizeKpiRecords },
  { step: "yield_agent.get_yield_defects", domain: "수율", build: summarizeYieldRecords },
  { step: "fdc_agent.get_fdc_anomalies", domain: "FDC 설비", build: summarizeFdcRecords },
];

/** 턴이 끝난 뒤 그 턴의 수치를 카드로 그린다. 그릴 게 없으면 아무것도 안 만든다. */
function renderTurnSummary(steps) {
  for (const src of SUMMARY_SOURCES) {
    const hit = steps.find((s) => s.step === src.step);
    if (!hit || !hit.output) continue;
    const payload = hit.output;
    const hasData = Array.isArray(payload) ? payload.length : Object.keys(payload).length;
    if (!hasData) continue;
    let body;
    try {
      body = src.build(payload);
    } catch (err) {
      return; // 요약은 부가 기능이다 -- 실패해도 대화를 막지 않는다
    }
    if (!body || !body.childNodes.length) return;
    const card = el("section", { class: "viz-card viz-root" }, [
      el("div", { class: "viz-card-head" }, [
        el("h5", { text: "수치 요약" }),
        el("span", { class: "viz-domain", text: src.domain }),
      ]),
    ]);
    card.appendChild(body);
    const messages = document.getElementById("chat-messages");
    messages.appendChild(card);
    messages.scrollTop = messages.scrollHeight;
    return;
  }
}
