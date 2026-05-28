<script setup>
import { computed, onMounted, ref } from "vue";
import RunToolbar from "./components/RunToolbar.vue";
import SourceTableEditor from "./components/SourceTableEditor.vue";
import ClusterTabs from "./components/ClusterTabs.vue";
import StatusLine from "./components/StatusLine.vue";
import { useApi } from "./composables/useApi";
import { useSession } from "./composables/useSession";
import { useSourceTable } from "./composables/useSourceTable";
import {
  extractDetail,
  formatApiError,
  formatTaskError,
  translateDetail,
} from "./utils/formatApiError";
import { parseProgressPercent } from "./utils/parseProgress";
import { NOMENCLATURE_COLUMN, clusterToTable } from "./utils/clusterTable";

const backendUrl = ref(import.meta.env.VITE_DEFAULT_BACKEND_URL || "");

const { request, apiUrl } = useApi(() => backendUrl.value);
const { sessionId, ensureSession, dropSession } = useSession(request);
const {
  source,
  getBaseAttributes,
  uploadFile,
  loadRows,
  toggleRow,
  updateRowCell,
  addRow,
  deleteRow,
  addColumn,
  renameColumn,
  deleteColumn,
  setColumnEnabled,
  setSourceColumn,
  clear,
} = useSourceTable(request, ensureSession, sessionId);

const embeddingProvider = ref("local");
const profileProvider = ref("g4f");
const normalizeProvider = ref("g4f");
const statusText = ref("Готово");
const statusTone = ref("muted");
const statusProgress = ref(null);

const activeTab = ref("source");

function toClusterRows(cluster) {
  const attrs = Array.from(new Set((cluster.attributes || []).filter(Boolean)));
  const rows = (cluster.rows || [])
    .map((r) => ({
      item: String(r.item || "").trim(),
      values: Object.fromEntries(attrs.map((a) => [a, String(r.values?.[a] || "")])),
    }))
    .filter((r) => r.item);
  if (rows.length) return { ...cluster, attributes: attrs, rows };
  return {
    name: cluster.name || "Cluster",
    attributes: attrs,
    rows: (cluster.items || []).map((item) => ({
      item: String(item),
      values: Object.fromEntries(attrs.map((a) => [a, ""])),
    })),
  };
}

const clusters = ref([]);

const activeClusterIdx = computed(() =>
  activeTab.value.startsWith("cluster-") ? Number(activeTab.value.split("-")[1]) : -1,
);

function getCurrentCluster() {
  if (activeClusterIdx.value < 0 || !clusters.value[activeClusterIdx.value]) return null;
  return clusters.value[activeClusterIdx.value];
}

const activeClusterTable = computed(() => {
  const cluster = getCurrentCluster();
  if (!cluster) return null;
  return clusterToTable(cluster, cluster.name);
});

const clusterMoveTargets = computed(() =>
  clusters.value
    .map((cluster, index) => ({
      index,
      name: cluster.name || `Кластер ${index + 1}`,
    }))
    .filter((target) => target.index !== activeClusterIdx.value),
);

function applyClusterRowEdit({ rowIndex, header, value }) {
  const cluster = getCurrentCluster();
  if (!cluster || !cluster.rows[rowIndex]) return;
  if (header === NOMENCLATURE_COLUMN) {
    cluster.rows[rowIndex].item = value;
    return;
  }
  cluster.rows[rowIndex].values[header] = value;
}

function applyClusterAddRow(cells) {
  const cluster = getCurrentCluster();
  if (!cluster) return;
  const item = String(cells[NOMENCLATURE_COLUMN] || "").trim();
  if (!item) return;
  const values = Object.fromEntries(
    cluster.attributes.map((attr) => [attr, String(cells[attr] || "").trim()]),
  );
  cluster.rows.unshift({ item, values });
}

function applyClusterAddColumn(name) {
  const cluster = getCurrentCluster();
  if (!cluster || cluster.attributes.includes(name)) return;
  cluster.attributes.unshift(name);
  cluster.rows.forEach((row) => {
    row.values[name] = "";
  });
}

function applyClusterRenameColumn({ oldName, newName }) {
  const cluster = getCurrentCluster();
  const next = String(newName || "").trim();
  if (!cluster || !next || oldName === next) return;
  if (oldName === NOMENCLATURE_COLUMN || next === NOMENCLATURE_COLUMN) return;
  if (cluster.attributes.includes(next)) return;
  cluster.attributes = cluster.attributes.map((attr) => (attr === oldName ? next : attr));
  cluster.rows.forEach((row) => {
    row.values[next] = row.values[oldName] || "";
    delete row.values[oldName];
  });
}

function applyClusterDeleteColumn(name) {
  const cluster = getCurrentCluster();
  if (!cluster || name === NOMENCLATURE_COLUMN) return;
  cluster.attributes = cluster.attributes.filter((attr) => attr !== name);
  cluster.rows.forEach((row) => {
    delete row.values[name];
  });
}

function moveClusterRow({ rowIndex, targetClusterIdx }) {
  const from = getCurrentCluster();
  const to = clusters.value[targetClusterIdx];
  if (!from || !to || targetClusterIdx === activeClusterIdx.value) return;
  const [row] = from.rows.splice(rowIndex, 1);
  if (!row) return;
  for (const attr of to.attributes) {
    if (row.values[attr] === undefined) row.values[attr] = "";
  }
  for (const attr of from.attributes) {
    if (to.attributes.includes(attr)) continue;
    if (row.values[attr] !== undefined && row.values[attr] !== "") {
      to.attributes.push(attr);
      to.rows.forEach((r) => {
        if (r.values[attr] === undefined) r.values[attr] = "";
      });
    }
  }
  to.rows.push(row);
  setStatus(`Перенесено в «${to.name || `Кластер ${targetClusterIdx + 1}`}»`, "ok");
}

function setStatus(text, tone = "muted", progress = null) {
  statusText.value = text;
  statusTone.value = tone;
  statusProgress.value = progress;
}

function setTaskProgress(message, fallbackLabel = "Выполняется") {
  const text = message || fallbackLabel;
  const percent = parseProgressPercent(message);
  setStatus(text, "progress", percent ?? -1);
}

async function runSafe(fn, contextLabel) {
  try {
    await fn();
  } catch (error) {
    setStatus(formatApiError(error, contextLabel), "err", null);
  }
}

async function handleUpload(file) {
  await runSafe(async () => {
    const data = await uploadFile(file);
    activeTab.value = "source";
    setStatus(
      `Загружено ${data.stats.rows_total}, после очистки ${data.stats.rows_after_cleaning}`,
      "ok",
    );
  }, "Загрузка файла");
}

async function resetSession() {
  await runSafe(async () => {
    await ensureSession();
    await dropSession();
    await ensureSession();
    clear();
    clusters.value = [];
    activeTab.value = "source";
    setStatus("Сессия сброшена", "ok");
  }, "Сброс сессии");
}

async function saveConfig({ silent = false } = {}) {
  await ensureSession();
  let selectedColumn = source.selectedColumn;
  if (!selectedColumn || !source.headers.includes(selectedColumn)) {
    selectedColumn = source.headers[0] || "";
  }
  if (!selectedColumn) {
    throw new Error("Колонка-источник не задана. Загрузите файл или выберите источник.");
  }
  source.selectedColumn = selectedColumn;
  const data = await request("POST", "/ui/api/configure", {
    session_id: sessionId.value,
    selected_column: selectedColumn,
    base_attributes: getBaseAttributes(),
  });
  if (!silent) {
    setStatus(`Конфиг сохранен. Товаров в работе: ${data.items_count}`, "ok", null);
  }
  return data;
}

async function pollTask(type, label) {
  let providerHint = "";
  while (true) {
    const status = await request("GET", `/ui/api/task/${sessionId.value}/${type}`);
    if (!providerHint) {
      const parts = [];
      if (status.embedding_provider) {
        const em = status.embedding_model
          ? `${status.embedding_provider}/${status.embedding_model}`
          : status.embedding_provider;
        parts.push(`vec:${em}`);
      }
      if (status.llm_provider) {
        const lm = status.llm_model
          ? `${status.llm_provider}/${status.llm_model}`
          : status.llm_provider;
        parts.push(`llm:${lm}`);
      }
      if (parts.length) providerHint = parts.join(" · ");
    }
    const context = providerHint ? `${label} (${providerHint})` : label;
    if (status.status === "FAILED") {
      throw new Error(formatTaskError(status.error));
    }
    if (status.status === "COMPLETED") {
      setTaskProgress(status.progress || `${context}: готово`, context);
      return status;
    }
    setTaskProgress(status.progress, context);
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

async function startClusterize() {
  await runSafe(async () => {
    setTaskProgress("Сохранение конфигурации…", "Кластеризация");
    await saveConfig({ silent: true });
    setTaskProgress("Запуск кластеризации…", "Кластеризация");
    await request("POST", "/ui/api/clusterize/start", {
      session_id: sessionId.value,
      embedding_provider: embeddingProvider.value,
      profile_provider: profileProvider.value,
    });
    await pollTask("clusterize", "Кластеризация");
    const clusterData = await request("GET", `/ui/api/clusters/${sessionId.value}`);
    const fromApi = (clusterData.clusters || []).map((c) => toClusterRows(c));
    if (fromApi.length) {
      clusters.value = fromApi;
      activeTab.value = "cluster-0";
    }
    setStatus("Кластеризация завершена", "ok", 100);
  }, "Кластеризация");
}

async function startNormalize() {
  await runSafe(async () => {
    setTaskProgress("Сохранение кластеров…", "Нормализация");
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clusters.value.map((cluster) => ({
        name: cluster.name,
        attributes: cluster.attributes,
        items: cluster.rows.map((r) => r.item).filter(Boolean),
      })),
    });
    setTaskProgress("Запуск нормализации…", "Нормализация");
    await request("POST", "/ui/api/normalize/start", {
      session_id: sessionId.value,
      provider: normalizeProvider.value,
    });
    const status = await pollTask("normalize", "Нормализация");
    const clusterData = await request("GET", `/ui/api/clusters/${sessionId.value}`);
    clusters.value = (clusterData.clusters || []).map((c) => toClusterRows(c));
    const count = status?.result?.actual_count ?? status?.result?.normalized?.length ?? 0;
    if (!activeTab.value.startsWith("cluster-") && clusters.value.length) {
      activeTab.value = "cluster-0";
    }
    setStatus(`Нормализация завершена: ${count} позиций`, "ok", 100);
  }, "Нормализация");
}

async function saveMemory() {
  await runSafe(async () => {
    if (clusters.value.length) {
      await request("POST", "/ui/api/clusters/save", {
        session_id: sessionId.value,
        clusters: clusters.value.map((cluster) => ({
          name: cluster.name,
          attributes: cluster.attributes,
          items: cluster.rows.map((r) => r.item).filter(Boolean),
        })),
      });
    }
    const data = await request("POST", "/ui/api/memory/save", {
      session_id: sessionId.value,
    });
    setStatus(`Сохранено в память: ${data.saved_count || 0}`, "ok");
  }, "Сохранение в память");
}

async function flushRedis() {
  if (
    !window.confirm(
      "Очистить весь Redis?\nБудут удалены статусы задач и кэш ответов LLM.",
    )
  ) {
    return;
  }
  await runSafe(async () => {
    const data = await request("POST", "/ui/api/admin/flush-redis");
    setStatus(data.message || "Redis очищен", "ok", null);
  }, "Очистка Redis");
}

async function flushQdrant() {
  if (
    !window.confirm(
      "Очистить векторную память Qdrant?\nВсе сохранённые товары будут удалены из коллекции.",
    )
  ) {
    return;
  }
  await runSafe(async () => {
    const data = await request("POST", "/ui/api/admin/flush-qdrant");
    setStatus(data.message || "Qdrant очищен", "ok", null);
  }, "Очистка Qdrant");
}

async function exportXlsx() {
  await runSafe(async () => {
    await ensureSession();
    const response = await fetch(apiUrl(`/ui/api/export/${sessionId.value}/xlsx`));
    if (!response.ok) {
      const text = await response.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = text;
      }
      const detail = extractDetail(data);
      throw new Error(translateDetail(detail) || detail || `Экспорт не удался (${response.status})`);
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = `clusters_${sessionId.value}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
    setStatus("Экспорт готов", "ok");
  }, "Экспорт");
}

onMounted(async () => {
  await runSafe(async () => {
    await ensureSession();
    setStatus("Сессия готова", "ok");
  }, "Инициализация");
});
</script>

<template>
  <div class="page">
    <RunToolbar
      :backend-url="backendUrl"
      :embedding-provider="embeddingProvider"
      :profile-provider="profileProvider"
      :normalize-provider="normalizeProvider"
      @update:backend-url="(value) => (backendUrl = value)"
      @update:embedding-provider="(value) => (embeddingProvider = value)"
      @update:profile-provider="(value) => (profileProvider = value)"
      @update:normalize-provider="(value) => (normalizeProvider = value)"
      @reset-session="resetSession"
      @clusterize="startClusterize"
      @normalize="startNormalize"
      @save-memory="saveMemory"
      @export-xlsx="exportXlsx"
      @flush-redis="flushRedis"
      @flush-qdrant="flushQdrant"
    />

    <StatusLine :text="statusText" :tone="statusTone" :progress="statusProgress" />

    <section class="table-card">
      <ClusterTabs
        :clusters="clusters"
        :active-tab="activeTab"
        @tab-change="(tab) => (activeTab = tab)"
      />

      <SourceTableEditor
        v-if="activeTab === 'source'"
        mode="source"
        :source="source"
        @toggle-row="({ rowIndex, included }) => runSafe(() => toggleRow(rowIndex, included), 'Строка')"
        @row-edit="({ rowIndex, header, value }) => runSafe(() => updateRowCell(rowIndex, header, value), 'Строка')"
        @add-row-form="(cells) => runSafe(() => addRow(cells), 'Добавление строки')"
        @delete-row="(rowIndex) => runSafe(() => deleteRow(rowIndex), 'Удаление строки')"
        @add-column="(name) => runSafe(() => addColumn(name), 'Колонка')"
        @rename-column="({ oldName, newName }) => runSafe(() => renameColumn(oldName, newName), 'Колонка')"
        @delete-column="(name) => runSafe(() => deleteColumn(name), 'Колонка')"
        @toggle-column="({ name, enabled }) => setColumnEnabled(name, enabled)"
        @set-source-column="(name) => runSafe(() => setSourceColumn(name), 'Колонка-источник')"
        @change-page="(page) => runSafe(() => loadRows(page), 'Страница')"
        @file-upload="handleUpload"
        @notify="({ text, tone }) => setStatus(text, tone)"
      />

      <SourceTableEditor
        v-else-if="activeClusterTable"
        mode="cluster"
        :table="activeClusterTable"
        :move-targets="clusterMoveTargets"
        @row-edit="applyClusterRowEdit"
        @add-row-form="applyClusterAddRow"
        @delete-row="
          (rowIndex) => {
            const c = getCurrentCluster();
            if (c) c.rows.splice(rowIndex, 1);
          }
        "
        @add-column="applyClusterAddColumn"
        @rename-column="applyClusterRenameColumn"
        @delete-column="applyClusterDeleteColumn"
        @move-row="moveClusterRow"
        @notify="({ text, tone }) => setStatus(text, tone)"
      />
    </section>
  </div>
</template>
