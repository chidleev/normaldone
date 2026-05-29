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
import {
  ENRICHED_NAME_COLUMN,
  NOMENCLATURE_COLUMN,
  clusterToTable,
} from "./utils/clusterTable";
import {
  ensureRowMembers,
  mergeRowsInto,
  recalculateRowMergedValues,
  regenerateAllRowsEnriched,
  regenerateRowEnriched,
  splitAliasFromRow,
} from "./utils/clusterRowOps";
import { buildTestClusters } from "./fixtures/testCluster";

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

const embeddingProvider = ref("gemini");
const profileProvider = ref("gemini");
const normalizeProvider = ref("gemini");
const statusText = ref("Готово");
const statusTone = ref("muted");
const statusProgress = ref(null);

const activeTab = ref("source");

function toClusterRows(cluster) {
  const attrs = Array.from(new Set((cluster.attributes || []).filter(Boolean)));
  const rows = (cluster.rows || [])
    .map((r) => {
      const item = String(r.item || "").trim();
      const enriched = String(r.enriched_name || "").trim();
      const aliases = (r.aliases || [])
        .map((name) => String(name || "").trim())
        .filter(Boolean);
      const members = (r.members || [])
        .map((member) => ({
          item: String(member.item || "").trim(),
          source: member.source === "memory" ? "memory" : "ai",
          values: Object.fromEntries(
            Object.entries(member.values || {}).map(([key, value]) => [
              key,
              String(value || ""),
            ]),
          ),
        }))
        .filter((member) => member.item);
      return {
        item,
        enriched_name: enriched,
        aliases: aliases.length ? aliases : item ? [item] : [],
        source: r.source === "memory" ? "memory" : "ai",
        values: Object.fromEntries(
          attrs.map((a) => [a, String(r.values?.[a] || "")])
        ),
        members,
      };
    })
    .filter((r) => r.item || r.enriched_name);
  if (rows.length) {
    return {
      ...cluster,
      attributes: attrs,
      enriched_name_template: String(cluster.enriched_name_template || ""),
      attribute_merge: { ...(cluster.attribute_merge || {}) },
      attribute_merge_separators: { ...(cluster.attribute_merge_separators || {}) },
      rows,
    };
  }
  return {
    name: cluster.name || "Cluster",
    attributes: attrs,
    enriched_name_template: String(cluster.enriched_name_template || ""),
    attribute_merge: { ...(cluster.attribute_merge || {}) },
    attribute_merge_separators: { ...(cluster.attribute_merge_separators || {}) },
    rows: (cluster.items || []).map((item) => ({
      item: String(item),
      source: "ai",
      values: Object.fromEntries(attrs.map((a) => [a, ""])),
    })),
  };
}

function clustersToPayload() {
  return clusters.value.map((cluster) => ({
    name: cluster.name,
    attributes: cluster.attributes,
    enriched_name_template: String(cluster.enriched_name_template || ""),
    attribute_merge: { ...(cluster.attribute_merge || {}) },
    attribute_merge_separators: { ...(cluster.attribute_merge_separators || {}) },
    items: cluster.rows
      .map((r) => String(r.enriched_name || r.item || "").trim())
      .filter(Boolean),
    rows: cluster.rows.map((r) => ({
      item: r.item,
      enriched_name: r.enriched_name || "",
      aliases: r.aliases || (r.item ? [r.item] : []),
      source: r.source === "memory" ? "memory" : "ai",
      values: r.values || {},
      members: (r.members || []).map((member) => ({
        item: member.item,
        source: member.source === "memory" ? "memory" : "ai",
        values: member.values || {},
      })),
    })),
  }));
}

const clusters = ref([]);

const activeClusterIdx = computed(() =>
  activeTab.value.startsWith("cluster-")
    ? Number(activeTab.value.split("-")[1])
    : -1
);

function getCurrentCluster() {
  if (activeClusterIdx.value < 0 || !clusters.value[activeClusterIdx.value])
    return null;
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
    .filter((target) => target.index !== activeClusterIdx.value)
);

function addCluster() {
  const current = getCurrentCluster();
  const nextIndex = clusters.value.length + 1;
  const attributes = current?.attributes?.length
    ? [...current.attributes]
    : getBaseAttributes();
  const cluster = toClusterRows({
    name: `Новый кластер ${nextIndex}`,
    attributes,
    enriched_name_template: current?.enriched_name_template || "",
    attribute_merge: { ...(current?.attribute_merge || {}) },
    attribute_merge_separators: { ...(current?.attribute_merge_separators || {}) },
    rows: [],
    items: [],
  });
  clusters.value.push(cluster);
  activeTab.value = `cluster-${clusters.value.length - 1}`;
  setStatus("Кластер добавлен", "ok");
}

function deleteCluster(index) {
  if (index < 0 || index >= clusters.value.length) return;
  const clusterName = clusters.value[index]?.name || `Кластер ${index + 1}`;
  if (!window.confirm(`Удалить «${clusterName}»?`)) return;
  clusters.value.splice(index, 1);
  if (!clusters.value.length) {
    activeTab.value = "source";
  } else if (activeClusterIdx.value >= clusters.value.length || activeClusterIdx.value === index) {
    activeTab.value = `cluster-${Math.max(0, Math.min(index, clusters.value.length - 1))}`;
  }
  setStatus("Кластер удалён", "ok");
}

function applyClusterRowEdit({ rowIndex, header, value }) {
  const cluster = getCurrentCluster();
  if (!cluster || !cluster.rows[rowIndex]) return;
  if (header === ENRICHED_NAME_COLUMN) {
    cluster.rows[rowIndex].enriched_name = value;
    return;
  }
  if (header === NOMENCLATURE_COLUMN) {
    cluster.rows[rowIndex].item = value;
    return;
  }
  const row = cluster.rows[rowIndex];
  row.values[header] = value;
  // В merged-flow источником истины для слияния остаются members.
  // Для "простых" строк синхронизируем правку в members,
  // чтобы при будущем "Влить в..." ушло актуальное значение.
  // Но если по атрибуту уже есть конфликт значений между members,
  // не затираем их: пользователь редактирует только итоговое значение.
  ensureRowMembers(row);
  const memberValues = (row.members || [])
    .map((member) => String(member.values?.[header] ?? "").trim())
    .filter(Boolean);
  const uniqueMemberValues = [...new Set(memberValues)];
  const hasConflict = uniqueMemberValues.length > 1;
  if (!hasConflict) {
    for (const member of row.members || []) {
      if (!member.values) member.values = {};
      member.values[header] = value;
    }
  }
}

function applyClusterUpdateTemplate(template) {
  const cluster = getCurrentCluster();
  if (!cluster) return;
  cluster.enriched_name_template = String(template || "").trim();
}

function applyClusterAddRow(cells) {
  const cluster = getCurrentCluster();
  if (!cluster) return;
  const leadColumn = cluster.rows.some((r) => String(r.enriched_name || "").trim())
    ? ENRICHED_NAME_COLUMN
    : NOMENCLATURE_COLUMN;
  const name = String(cells[leadColumn] || cells[NOMENCLATURE_COLUMN] || "").trim();
  if (!name) return;
  const values = Object.fromEntries(
    cluster.attributes.map((attr) => [attr, String(cells[attr] || "").trim()])
  );
  const row = { item: name, values, source: "ai", aliases: [name] };
  if (leadColumn === ENRICHED_NAME_COLUMN) {
    row.enriched_name = name;
  }
  ensureRowMembers(row);
  cluster.rows.unshift(row);
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
  if (
    oldName === NOMENCLATURE_COLUMN ||
    next === NOMENCLATURE_COLUMN ||
    oldName === ENRICHED_NAME_COLUMN ||
    next === ENRICHED_NAME_COLUMN
  ) {
    return;
  }
  if (cluster.attributes.includes(next)) return;
  cluster.attributes = cluster.attributes.map((attr) =>
    attr === oldName ? next : attr
  );
  cluster.rows.forEach((row) => {
    row.values[next] = row.values[oldName] || "";
    delete row.values[oldName];
  });
}

function applyClusterDeleteColumn(name) {
  const cluster = getCurrentCluster();
  if (!cluster || name === NOMENCLATURE_COLUMN || name === ENRICHED_NAME_COLUMN) return;
  cluster.attributes = cluster.attributes.filter((attr) => attr !== name);
  cluster.rows.forEach((row) => {
    delete row.values[name];
  });
}

function applyClusterRenameTitle(name) {
  const cluster = getCurrentCluster();
  const next = String(name || "").trim();
  if (!cluster || !next) return;
  const duplicate = clusters.value.some(
    (c, index) => index !== activeClusterIdx.value && String(c.name || "").trim() === next,
  );
  if (duplicate) {
    setStatus("Кластер с таким именем уже существует", "err");
    return;
  }
  cluster.name = next;
}

function applyAttributeMergeConfig({ attribute, behavior, separator }) {
  const cluster = getCurrentCluster();
  if (!cluster || !attribute) return;
  if (!cluster.attribute_merge) cluster.attribute_merge = {};
  if (!cluster.attribute_merge_separators) cluster.attribute_merge_separators = {};
  cluster.attribute_merge[attribute] = behavior === "accumulative" ? "accumulative" : "priority";
  if (behavior === "accumulative" && separator) {
    cluster.attribute_merge_separators[attribute] = separator;
  } else {
    delete cluster.attribute_merge_separators[attribute];
  }
  for (const row of cluster.rows || []) {
    recalculateRowMergedValues(
      row,
      cluster.attribute_merge || {},
      cluster.attribute_merge_separators || {},
    );
  }
  setStatus(`Режим атрибута «${attribute}» обновлён`, "ok");
}

function applyRegenerateEnriched(rowIndex) {
  const cluster = getCurrentCluster();
  const row = cluster?.rows?.[rowIndex];
  if (!row) return;
  ensureRowMembers(row);
  regenerateRowEnriched(row, cluster.enriched_name_template || "");
  setStatus("Обогащённое имя пересоздано", "ok");
}

function applyRegenerateAllEnriched() {
  const cluster = getCurrentCluster();
  if (!cluster) return;
  const template = String(cluster.enriched_name_template || "").trim();
  if (!template) {
    setStatus("Задайте шаблон обогащённого имени", "err");
    return;
  }
  const count = regenerateAllRowsEnriched(cluster.rows, template);
  if (!count) {
    setStatus("Нет строк для пересоздания", "err");
    return;
  }
  setStatus(`Пересоздано обогащённых имён: ${count}`, "ok");
}

function applySplitAlias({ rowIndex, alias }) {
  const cluster = getCurrentCluster();
  const row = cluster?.rows?.[rowIndex];
  if (!cluster || !row) return;
  const newRow = splitAliasFromRow(
    row,
    alias,
    cluster.enriched_name_template || "",
    cluster.attribute_merge || {},
    cluster.attribute_merge_separators || {},
  );
  if (!newRow) return;
  regenerateRowEnriched(row, cluster.enriched_name_template || "");
  cluster.rows.splice(rowIndex + 1, 0, newRow);
  setStatus(`Вычленено: ${alias}`, "ok");
}

function applyMergeRowInto({ sourceIndex, targetIndex }) {
  const cluster = getCurrentCluster();
  if (!cluster || sourceIndex === targetIndex) return;
  const source = cluster.rows[sourceIndex];
  const target = cluster.rows[targetIndex];
  if (!source || !target) return;
  mergeRowsInto(
    target,
    source,
    cluster.attribute_merge || {},
    cluster.attribute_merge_separators || {},
  );
  regenerateRowEnriched(target, cluster.enriched_name_template || "");
  cluster.rows.splice(sourceIndex, 1);
  setStatus("Строки объединены", "ok");
}

async function rededupeCurrentClusters() {
  await runSafe(async () => {
    await ensureSession();
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clustersToPayload(),
    });
    setTaskProgress("Пересчёт дубликатов…", "Дедупликация");
    const data = await request(
      "POST",
      `/ui/api/clusters/${sessionId.value}/rededupe`,
    );
    clusters.value = (data.clusters || []).map((cluster) => toClusterRows(cluster));
    setStatus("Дубликаты пересчитаны", "ok", 100);
  }, "Пересчёт дубликатов");
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
  setStatus(
    `Перенесено в «${to.name || `Кластер ${targetClusterIdx + 1}`}»`,
    "ok"
  );
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
      "ok"
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
    throw new Error(
      "Колонка-источник не задана. Загрузите файл или выберите источник."
    );
  }
  source.selectedColumn = selectedColumn;
  const data = await request("POST", "/ui/api/configure", {
    session_id: sessionId.value,
    selected_column: selectedColumn,
    base_attributes: getBaseAttributes(),
  });
  if (!silent) {
    setStatus(
      `Конфиг сохранен. Товаров в работе: ${data.items_count}`,
      "ok",
      null
    );
  }
  return data;
}

async function pollTask(type, label) {
  let providerHint = "";
  while (true) {
    const status = await request(
      "GET",
      `/ui/api/task/${sessionId.value}/${type}`
    );
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
    const clusterData = await request(
      "GET",
      `/ui/api/clusters/${sessionId.value}`
    );
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
      clusters: clustersToPayload(),
    });
    setTaskProgress("Запуск нормализации…", "Нормализация");
    await request("POST", "/ui/api/normalize/start", {
      session_id: sessionId.value,
      provider: normalizeProvider.value,
    });
    const status = await pollTask("normalize", "Нормализация");
    const clusterData = await request(
      "GET",
      `/ui/api/clusters/${sessionId.value}`
    );
    clusters.value = (clusterData.clusters || []).map((c) => toClusterRows(c));
    const count =
      status?.result?.actual_count ?? status?.result?.normalized?.length ?? 0;
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
        clusters: clustersToPayload(),
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
      "Очистить весь Redis?\nБудут удалены статусы задач и кэш ответов LLM."
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
      "Очистить векторную память Qdrant?\nВсе сохранённые товары будут удалены из коллекции."
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
    const response = await fetch(
      apiUrl(`/ui/api/export/${sessionId.value}/xlsx`)
    );
    if (!response.ok) {
      const text = await response.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = text;
      }
      const detail = extractDetail(data);
      throw new Error(
        translateDetail(detail) ||
          detail ||
          `Экспорт не удался (${response.status})`
      );
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

async function loadTestCluster() {
  await runSafe(async () => {
    await ensureSession();
    clusters.value = buildTestClusters().map((cluster) => toClusterRows(cluster));
    activeTab.value = "cluster-0";
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clustersToPayload(),
    });
    setStatus(
      "Загружен тестовый кластер «Тест: фильтры (демо)»: 3 строки, шаблон, members, аккумулятивные атрибуты",
      "ok",
    );
  }, "Тестовый кластер");
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
      @load-test-cluster="loadTestCluster"
    />

    <StatusLine
      :text="statusText"
      :tone="statusTone"
      :progress="statusProgress"
    />

    <section class="table-card">
      <ClusterTabs
        v-if="clusters.length"
        :clusters="clusters"
        :active-tab="activeTab"
        @tab-change="(tab) => (activeTab = tab)"
        @add-cluster="addCluster"
        @delete-cluster="deleteCluster"
      />

      <SourceTableEditor
        v-if="activeTab === 'source'"
        mode="source"
        :source="source"
        @toggle-row="
          ({ rowIndex, included }) =>
            runSafe(() => toggleRow(rowIndex, included), 'Строка')
        "
        @row-edit="
          ({ rowIndex, header, value }) =>
            runSafe(() => updateRowCell(rowIndex, header, value), 'Строка')
        "
        @add-row-form="
          (cells) => runSafe(() => addRow(cells), 'Добавление строки')
        "
        @delete-row="
          (rowIndex) => runSafe(() => deleteRow(rowIndex), 'Удаление строки')
        "
        @add-column="(name) => runSafe(() => addColumn(name), 'Колонка')"
        @rename-column="
          ({ oldName, newName }) =>
            runSafe(() => renameColumn(oldName, newName), 'Колонка')
        "
        @delete-column="(name) => runSafe(() => deleteColumn(name), 'Колонка')"
        @toggle-column="({ name, enabled }) => setColumnEnabled(name, enabled)"
        @set-source-column="
          (name) => runSafe(() => setSourceColumn(name), 'Колонка-источник')
        "
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
        @rename-title="applyClusterRenameTitle"
        @update-template="applyClusterUpdateTemplate"
        @set-attribute-merge-config="applyAttributeMergeConfig"
        @regenerate-row="applyRegenerateEnriched"
        @regenerate-all="applyRegenerateAllEnriched"
        @split-alias="applySplitAlias"
        @merge-row-into="applyMergeRowInto"
        @rededupe="rededupeCurrentClusters"
        @notify="({ text, tone }) => setStatus(text, tone)"
      />
    </section>
  </div>
</template>
