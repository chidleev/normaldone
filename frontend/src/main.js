import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const SESSION_KEY = "normaldone_ui_session_id";

const state = {
  sessionId: null,
  source: {
    headers: [],
    rows: [],
    page: 1,
    pageSize: 10,
    totalRows: 0,
    totalPages: 1,
    selectedColumn: "",
    selectedAttrs: [],
  },
  clusters: [],
  activeTab: "source",
  normalizeProvider: "g4f",
  embeddingProvider: "local",
  profileProvider: "g4f",
  status: "",
};

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function request(method, path, payload, isForm = false) {
  const options = { method };
  if (payload !== undefined) {
    if (isForm) options.body = payload;
    else {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(payload);
    }
  }
  const res = await fetch(apiUrl(path), options);
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = text;
  }
  if (!res.ok) throw new Error(typeof data === "string" ? data : JSON.stringify(data));
  return data;
}

function setStatus(message, cls = "muted") {
  state.status = message;
  const el = document.getElementById("statusLine");
  el.className = `status ${cls}`;
  el.textContent = message;
}

async function ensureSession() {
  const stored = localStorage.getItem(SESSION_KEY);
  const data = await request("POST", "/ui/api/session/ensure", {
    session_id: state.sessionId || stored || null,
  });
  state.sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, state.sessionId);
}

async function resetSession() {
  await ensureSession();
  await request("POST", "/ui/api/session/drop", { session_id: state.sessionId });
  localStorage.removeItem(SESSION_KEY);
  state.sessionId = null;
  await ensureSession();
  state.source = {
    headers: [],
    rows: [],
    page: 1,
    pageSize: 10,
    totalRows: 0,
    totalPages: 1,
    selectedColumn: "",
    selectedAttrs: [],
  };
  state.clusters = [];
  state.activeTab = "source";
  setStatus("Сессия сброшена", "ok");
  render();
}

async function uploadFile(file) {
  await ensureSession();
  await request("POST", "/ui/api/session/reset", { session_id: state.sessionId });
  const form = new FormData();
  form.append("session_id", state.sessionId);
  form.append("file", file);
  const data = await request("POST", "/ui/api/upload", form, true);
  state.source.headers = data.headers || [];
  state.source.selectedColumn = state.source.headers[0] || "";
  state.source.selectedAttrs = state.source.headers.filter((h) => h !== state.source.selectedColumn);
  state.clusters = [];
  state.activeTab = "source";
  await loadRows(1);
  setStatus(
    `Загружено ${data.stats.rows_total}, после очистки ${data.stats.rows_after_cleaning}`,
    "ok",
  );
  render();
}

async function loadRows(page) {
  await ensureSession();
  const data = await request(
    "GET",
    `/ui/api/rows/${state.sessionId}?page=${page}&page_size=${state.source.pageSize}`,
  );
  state.source.page = data.page;
  state.source.totalPages = data.total_pages;
  state.source.totalRows = data.total_rows;
  state.source.rows = data.rows || [];
}

async function toggleRow(rowIndex, included) {
  await ensureSession();
  await request("POST", "/ui/api/rows/include", {
    session_id: state.sessionId,
    row_index: rowIndex,
    included,
  });
}

async function saveConfig() {
  await ensureSession();
  const payload = {
    session_id: state.sessionId,
    selected_column: state.source.selectedColumn,
    base_attributes: state.source.selectedAttrs,
  };
  const data = await request("POST", "/ui/api/configure", payload);
  setStatus(`Конфиг сохранен. Товаров в работе: ${data.items_count}`, "ok");
}

async function clusterize() {
  await saveConfig();
  const data = await request("POST", "/ui/api/clusterize/start", {
    session_id: state.sessionId,
    base_url: document.getElementById("baseUrl").value.trim(),
    embedding_provider: state.embeddingProvider,
    profile_provider: state.profileProvider,
  });
  setStatus(`Кластеризация запущена: ${data.task_id}`, "muted");
  await pollTask("clusterize");
}

async function normalize() {
  await request("POST", "/ui/api/clusters/save", {
    session_id: state.sessionId,
    clusters: state.clusters,
  });
  const data = await request("POST", "/ui/api/normalize/start", {
    session_id: state.sessionId,
    base_url: document.getElementById("baseUrl").value.trim(),
    provider: state.normalizeProvider,
  });
  setStatus(`Нормализация запущена: ${data.task_id}`, "muted");
  await pollTask("normalize");
}

async function pollTask(type) {
  await ensureSession();
  while (true) {
    const data = await request("GET", `/ui/api/task/${state.sessionId}/${type}`);
    if (data.status === "FAILED") {
      setStatus(`Ошибка: ${data.error || "неизвестно"}`, "err");
      return;
    }
    if (data.status === "COMPLETED") {
      if (type === "clusterize") {
        const clusters = await request("GET", `/ui/api/clusters/${state.sessionId}`);
        state.clusters = (clusters.clusters || []).map((c) => ({
          name: c.name || "Cluster",
          attributes: c.attributes || [],
          items: c.items || [],
        }));
        state.activeTab = state.clusters.length ? "cluster-0" : "source";
        render();
      }
      setStatus(type === "clusterize" ? "Кластеризация завершена" : "Нормализация завершена", "ok");
      return;
    }
    setStatus(data.progress || "Выполняется...", "muted");
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function saveMemory() {
  await ensureSession();
  const data = await request("POST", "/ui/api/memory/save", {
    session_id: state.sessionId,
    base_url: document.getElementById("baseUrl").value.trim(),
  });
  setStatus(`Сохранено в память: ${data.saved_count || 0}`, "ok");
}

function exportXlsx() {
  if (!state.sessionId) return;
  window.open(apiUrl(`/ui/api/export/${state.sessionId}/xlsx`), "_blank");
}

function renderTabs() {
  const tabs = [{ id: "source", label: "Исходные данные" }];
  state.clusters.forEach((c, idx) => tabs.push({ id: `cluster-${idx}`, label: c.name || `Кластер ${idx + 1}` }));
  return tabs
    .map((tab) => `<button class="tab ${state.activeTab === tab.id ? "active" : ""}" data-tab="${tab.id}">${tab.label}</button>`)
    .join("");
}

function renderSourceTable() {
  const headers = state.source.headers;
  if (!headers.length) return `<div class="muted">Загрузите CSV/XLSX для начала.</div>`;
  const rows = state.source.rows;
  const head = ["Вкл", "#", ...headers].map((h) => `<th>${h}</th>`).join("");
  const body = rows
    .map((row) => {
      const checked = row.included ? "checked" : "";
      const cells = headers.map((h) => `<td>${(row.cells?.[h] ?? "").toString()}</td>`).join("");
      return `<tr>
        <td><input type="checkbox" data-row="${row.row_index}" ${checked} /></td>
        <td>${row.row_index + 1}</td>
        ${cells}
      </tr>`;
    })
    .join("");
  return `<div class="pager">
      <span>Стр. ${state.source.page}/${state.source.totalPages}, строк: ${state.source.totalRows}</span>
      <button class="secondary" id="prevPageBtn" ${state.source.page <= 1 ? "disabled" : ""}>Назад</button>
      <button class="secondary" id="nextPageBtn" ${state.source.page >= state.source.totalPages ? "disabled" : ""}>Вперед</button>
    </div>
    <div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderClusterTable(clusterIdx) {
  const cluster = state.clusters[clusterIdx];
  if (!cluster) return `<div class="muted">Нет данных кластера.</div>`;
  const head = ["#", "Номенклатура", ...cluster.attributes].map((h) => `<th>${h}</th>`).join("");
  const body = cluster.items
    .map((item, idx) => `<tr><td>${idx + 1}</td><td>${item}</td>${cluster.attributes.map(() => "<td></td>").join("")}</tr>`)
    .join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function render() {
  const app = document.getElementById("app");
  const activeClusterIdx = state.activeTab.startsWith("cluster-")
    ? Number(state.activeTab.split("-")[1])
    : -1;

  app.innerHTML = `
    <div class="page">
      <div class="toolbar">
        <div class="toolbar-grid">
          <div class="field">
            <label>Backend URL</label>
            <input id="baseUrl" type="text" value="http://localhost:8000" />
          </div>
          <div class="field">
            <label>Файл</label>
            <input id="fileInput" type="file" accept=".csv,.xlsx,.xlsm" />
          </div>
          <div class="field">
            <label>Колонка номенклатуры</label>
            <select id="sourceColumnSelect">${state.source.headers.map((h) => `<option ${h === state.source.selectedColumn ? "selected" : ""}>${h}</option>`).join("")}</select>
          </div>
          <div class="field">
            <label>Векторизация</label>
            <select id="embeddingSelect">
              <option value="local" ${state.embeddingProvider === "local" ? "selected" : ""}>local</option>
              <option value="gemini" ${state.embeddingProvider === "gemini" ? "selected" : ""}>gemini</option>
            </select>
          </div>
          <div class="field">
            <label>Профиль кластера</label>
            <select id="profileSelect">
              <option value="g4f" ${state.profileProvider === "g4f" ? "selected" : ""}>g4f</option>
              <option value="gemini" ${state.profileProvider === "gemini" ? "selected" : ""}>gemini</option>
            </select>
          </div>
          <div class="field">
            <label>Нормализация</label>
            <select id="normalizeSelect">
              <option value="g4f" ${state.normalizeProvider === "g4f" ? "selected" : ""}>g4f</option>
              <option value="gemini" ${state.normalizeProvider === "gemini" ? "selected" : ""}>gemini</option>
            </select>
          </div>
        </div>
        <div class="row" style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
          <button id="resetBtn" class="secondary">Сбросить сессию</button>
          <button id="clusterizeBtn">Кластеризовать</button>
          <button id="normalizeBtn">Нормализовать</button>
          <button id="saveMemoryBtn" class="secondary">Сохранить в память</button>
          <button id="exportBtn" class="secondary">Экспорт XLSX</button>
        </div>
        <div id="statusLine" class="status muted">${state.status || "Готово"}</div>
      </div>
      <div class="table-card">
        <div class="tabs">${renderTabs()}</div>
        ${activeClusterIdx >= 0 ? renderClusterTable(activeClusterIdx) : renderSourceTable()}
      </div>
    </div>
  `;

  document.getElementById("fileInput").addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await uploadFile(file);
    } catch (err) {
      setStatus(`Ошибка загрузки: ${err.message}`, "err");
    }
  });
  document.getElementById("resetBtn").addEventListener("click", () => resetSession().catch((e) => setStatus(e.message, "err")));
  document.getElementById("clusterizeBtn").addEventListener("click", () => clusterize().catch((e) => setStatus(e.message, "err")));
  document.getElementById("normalizeBtn").addEventListener("click", () => normalize().catch((e) => setStatus(e.message, "err")));
  document.getElementById("saveMemoryBtn").addEventListener("click", () => saveMemory().catch((e) => setStatus(e.message, "err")));
  document.getElementById("exportBtn").addEventListener("click", exportXlsx);

  const sourceSelect = document.getElementById("sourceColumnSelect");
  if (sourceSelect) {
    sourceSelect.addEventListener("change", (e) => {
      state.source.selectedColumn = e.target.value;
      state.source.selectedAttrs = state.source.headers.filter((h) => h !== state.source.selectedColumn);
    });
  }
  document.getElementById("embeddingSelect").addEventListener("change", (e) => {
    state.embeddingProvider = e.target.value;
  });
  document.getElementById("profileSelect").addEventListener("change", (e) => {
    state.profileProvider = e.target.value;
  });
  document.getElementById("normalizeSelect").addEventListener("change", (e) => {
    state.normalizeProvider = e.target.value;
  });

  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeTab = btn.dataset.tab;
      render();
    });
  });
  document.querySelectorAll("[data-row]").forEach((checkbox) => {
    checkbox.addEventListener("change", async () => {
      try {
        await toggleRow(Number(checkbox.dataset.row), checkbox.checked);
      } catch (err) {
        setStatus(`Ошибка строки: ${err.message}`, "err");
      }
    });
  });
  const prev = document.getElementById("prevPageBtn");
  const next = document.getElementById("nextPageBtn");
  if (prev) prev.addEventListener("click", () => loadRows(state.source.page - 1).then(render));
  if (next) next.addEventListener("click", () => loadRows(state.source.page + 1).then(render));
}

async function init() {
  try {
    await ensureSession();
    setStatus("Сессия готова", "muted");
    render();
  } catch (err) {
    setStatus(`Ошибка инициализации: ${err.message}`, "err");
    render();
  }
}

init();
