// 바닐라 JS SPA -- 빌드 도구/프레임워크 없이 4개 탭(PRD/트레이스/HITL/HOTL)을 구현한다.

const state = {
  activeTab: "prd",
  approvalStatus: "pending",
  selectedRunId: null,
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

// 아주 작은 markdown -> html 변환기. prd.md에서 쓰는 문법(#/##, 표, 목록, **, `, >, ```)만 지원한다.
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

function onTabShown(tab) {
  if (tab === "prd") loadPrd();
  if (tab === "trace") loadRuns();
  if (tab === "hitl") loadApprovals();
  if (tab === "hotl") loadHotl();
}

// ---- PRD 탭 ---------------------------------------------------------------

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
      text: `${run.product_id || "(product 미상)"} · ${run.step_count}단계`,
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
    tr.appendChild(el("td", { text: `${report.model_name} (${report.product_id})` }));
    tr.appendChild(el("td", { text: report.category }));
    tr.appendChild(el("td", {
      html: `<span class="badge badge-critical">${report.critical_defect_count}건</span>`,
    }));
    tr.appendChild(el("td", { text: report.latest_market_share_pct != null ? `${report.latest_market_share_pct}%` : "-" }));
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
    tr.appendChild(el("td", { text: a.region }));
    tr.appendChild(el("td", { text: a.category }));
    tr.appendChild(el("td", { text: a.quarter }));
    tr.appendChild(el("td", { html: `<span class="badge badge-critical">${a.delta_pp}%p</span>` }));
    alertBody.appendChild(tr);
  }
  if (!(snapshot.alerts || []).length) {
    alertBody.appendChild(el("tr", {}, [el("td", { colspan: "4", class: "status-text", text: "현재 알림이 없습니다." })]));
  }

  const trendBody = document.getElementById("hotl-trend-body");
  trendBody.innerHTML = "";
  for (const t of (snapshot.trend || []).slice(-40)) {
    const tr = el("tr");
    tr.appendChild(el("td", { text: t.region }));
    tr.appendChild(el("td", { text: t.category }));
    tr.appendChild(el("td", { text: t.quarter }));
    tr.appendChild(el("td", { text: t.market_share_est_pct.toFixed(1) }));
    trendBody.appendChild(tr);
  }
}

document.getElementById("hotl-refresh-btn").addEventListener("click", async () => {
  await api("/api/hotl/refresh", { method: "POST" });
  loadHotl();
});

// ---- 상단 바: 제품 선택 + 분석 실행 ------------------------------------------

async function loadProducts() {
  const products = await api("/api/products");
  const select = document.getElementById("product-select");
  for (const p of products) {
    select.appendChild(el("option", { value: p.product_id, text: `${p.model_name} (${p.product_id})` }));
  }
}

document.getElementById("run-btn").addEventListener("click", async () => {
  const productId = document.getElementById("product-select").value;
  const statusEl = document.getElementById("run-status");
  if (!productId) { statusEl.textContent = "제품을 먼저 선택하세요."; return; }
  statusEl.textContent = "실행 중...";
  try {
    const outcome = await api("/api/run", { method: "POST", body: JSON.stringify({ product_id: productId }) });
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
loadProducts();
loadPrd();
