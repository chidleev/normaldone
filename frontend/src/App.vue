<script setup>
import { ArrowUpRight } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import RunToolbar from "./components/RunToolbar.vue";
import SourceTableEditor from "./components/SourceTableEditor.vue";
import ClusterTabs from "./components/ClusterTabs.vue";
import StatusLine from "./components/StatusLine.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import IconButton from "./components/IconButton.vue";
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
import { Cog } from "@lucide/vue";

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
const showNormalizeRecoveryActions = ref(false);
const statusText = ref("Готово");
const statusTone = ref("muted");
const statusProgress = ref(null);
const confirmDialog = ref({
  open: false,
  title: "",
  message: "",
  confirmText: "Подтвердить",
  cancelText: "Отмена",
  secondaryText: "",
  danger: false,
  resolver: null,
});

const activeTab = ref("source");
const memorySearchQuery = ref("");
const memorySearchResults = ref([]);
const memorySearchLoading = ref(false);
const highlightedClusterRow = ref({
  clusterIndex: -1,
  rowIndex: -1,
  timer: null,
});

function toClusterRows(cluster) {
  const attrs = Array.from(new Set((cluster.attributes || []).filter(Boolean)));
  const rows = (cluster.rows || [])
    .map((r) => {
      const fallbackAlias =
        (r.aliases || [])
          .map((name) => String(name || "").trim())
          .find(Boolean) || "";
      const item = String(r.item || fallbackAlias || "").trim();
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
            ])
          ),
        }))
        .filter((member) => member.item);
      return {
        item,
        enriched_name: enriched,
        aliases: aliases.length ? aliases : item ? [item] : [],
        source: r.source === "memory" ? "memory" : "ai",
        deleted: Boolean(r.deleted),
        values: Object.fromEntries(
          attrs.map((a) => [a, String(r.values?.[a] || "")])
        ),
        members,
      };
    })
    .filter((r) => r.item || r.enriched_name);
  if (rows.length) {
    const normalized = {
      ...cluster,
      attributes: attrs,
      source: ["memory", "ai", "manual"].includes(
        String(cluster.source || "")
          .trim()
          .toLowerCase()
      )
        ? String(cluster.source || "")
            .trim()
            .toLowerCase()
        : undefined,
      memory_cluster_name: String(cluster.memory_cluster_name || "").trim(),
      enriched_name_template: String(cluster.enriched_name_template || ""),
      attribute_merge: { ...(cluster.attribute_merge || {}) },
      attribute_merge_separators: {
        ...(cluster.attribute_merge_separators || {}),
      },
      rows,
    };
    if (!normalized.__initialSignature) {
      normalized.__initialSignature = clusterSignature(normalized);
    }
    if (!normalized.__memorySavedSignature) {
      normalized.__memorySavedSignature =
        String(normalized.source || "")
          .trim()
          .toLowerCase() === "memory"
          ? clusterSignature(normalized)
          : "";
    }
    return normalized;
  }
  const created = {
    name: cluster.name || "Cluster",
    attributes: attrs,
    source: ["memory", "ai", "manual"].includes(
      String(cluster.source || "")
        .trim()
        .toLowerCase()
    )
      ? String(cluster.source || "")
          .trim()
          .toLowerCase()
      : "ai",
    memory_cluster_name: String(cluster.memory_cluster_name || "").trim(),
    enriched_name_template: String(cluster.enriched_name_template || ""),
    attribute_merge: { ...(cluster.attribute_merge || {}) },
    attribute_merge_separators: {
      ...(cluster.attribute_merge_separators || {}),
    },
    rows: (cluster.items || []).map((item) => ({
      item: String(item),
      source: "ai",
      deleted: false,
      values: Object.fromEntries(attrs.map((a) => [a, ""])),
    })),
  };
  if (!created.__initialSignature) {
    created.__initialSignature = clusterSignature(created);
  }
  if (!created.__memorySavedSignature) {
    created.__memorySavedSignature = "";
  }
  return created;
}

function clustersToPayload() {
  return clusters.value.map((cluster) => ({
    name: cluster.name,
    source: cluster.source || "ai",
    memory_cluster_name: String(cluster.memory_cluster_name || "").trim(),
    attributes: cluster.attributes,
    enriched_name_template: String(cluster.enriched_name_template || ""),
    attribute_merge: { ...(cluster.attribute_merge || {}) },
    attribute_merge_separators: {
      ...(cluster.attribute_merge_separators || {}),
    },
    items: cluster.rows
      .filter((r) => !r.deleted)
      .map((r) => String(r.enriched_name || r.item || "").trim())
      .filter(Boolean),
    rows: cluster.rows
      .filter((r) => !r.deleted)
      .map((r) => ({
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
const memoryClusters = ref([]);

const activeClusterIdx = computed(() =>
  activeTab.value.startsWith("cluster-")
    ? Number(activeTab.value.split("-")[1])
    : -1
);

function isClusterSaved(cluster) {
  const savedSignature = String(cluster?.__memorySavedSignature || "");
  if (!savedSignature) return false;
  return savedSignature === clusterSignature(cluster);
}

function getUnsavedClusterIndexes() {
  return clusters.value
    .map((cluster, index) => ({ cluster, index }))
    .filter(({ cluster }) => !isClusterSaved(cluster))
    .map(({ index }) => index);
}

const activeClusterSaved = computed(() => {
  const cluster = getCurrentCluster();
  return cluster ? isClusterSaved(cluster) : false;
});
const activeHighlightRowIndex = computed(() =>
  highlightedClusterRow.value.clusterIndex === activeClusterIdx.value
    ? highlightedClusterRow.value.rowIndex
    : null
);

function getCurrentCluster() {
  if (activeClusterIdx.value < 0 || !clusters.value[activeClusterIdx.value])
    return null;
  return clusters.value[activeClusterIdx.value];
}

function stableObject(obj) {
  return Object.fromEntries(
    Object.entries(obj || {})
      .map(([key, value]) => [String(key), String(value ?? "")])
      .sort(([a], [b]) => a.localeCompare(b))
  );
}

function clusterSignature(cluster) {
  return JSON.stringify({
    name: String(cluster?.name || "").trim(),
    source: String(cluster?.source || "")
      .trim()
      .toLowerCase(),
    attributes: [...(cluster?.attributes || [])]
      .map((value) => String(value || "").trim())
      .sort(),
    enriched_name_template: String(
      cluster?.enriched_name_template || ""
    ).trim(),
    rows: (cluster?.rows || []).map((row) => ({
      item: String(row?.item || "").trim(),
      enriched_name: String(row?.enriched_name || "").trim(),
      source: String(row?.source || "")
        .trim()
        .toLowerCase(),
      deleted: Boolean(row?.deleted),
      aliases: [...(row?.aliases || [])]
        .map((value) => String(value || "").trim())
        .sort(),
      values: stableObject(row?.values || {}),
      members: (row?.members || [])
        .map((member) => ({
          item: String(member?.item || "").trim(),
          source: String(member?.source || "")
            .trim()
            .toLowerCase(),
          values: stableObject(member?.values || {}),
        }))
        .sort((a, b) => a.item.localeCompare(b.item)),
    })),
  });
}

async function askConfirm({
  title = "Подтверждение",
  message = "",
  confirmText = "Подтвердить",
  cancelText = "Отмена",
  danger = false,
}) {
  const outcome = await new Promise((resolve) => {
    confirmDialog.value = {
      open: true,
      title,
      message,
      confirmText,
      cancelText,
      secondaryText: "",
      danger,
      resolver: resolve,
    };
  });
  return outcome === "confirm";
}

async function askChoice({
  title = "Выбор действия",
  message = "",
  primaryText = "Подтвердить",
  secondaryText = "Второй вариант",
  cancelText = "Отмена",
  danger = false,
}) {
  return await new Promise((resolve) => {
    confirmDialog.value = {
      open: true,
      title,
      message,
      confirmText: primaryText,
      cancelText,
      secondaryText,
      danger,
      resolver: resolve,
    };
  });
}

function closeConfirm(result) {
  const resolver = confirmDialog.value.resolver;
  confirmDialog.value = {
    open: false,
    title: "",
    message: "",
    confirmText: "Подтвердить",
    cancelText: "Отмена",
    secondaryText: "",
    danger: false,
    resolver: null,
  };
  if (typeof resolver === "function") {
    resolver(result);
  }
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
    source: "manual",
    memory_cluster_name: "",
    enriched_name_template: current?.enriched_name_template || "",
    attribute_merge: { ...(current?.attribute_merge || {}) },
    attribute_merge_separators: {
      ...(current?.attribute_merge_separators || {}),
    },
    rows: [],
    items: [],
  });
  clusters.value.push(cluster);
  activeTab.value = `cluster-${clusters.value.length - 1}`;
  setStatus("Кластер добавлен", "ok");
}

async function loadMemoryClusterByName(clusterName) {
  await runSafe(async () => {
    await ensureSession();
    const selected = String(clusterName || "").trim();
    if (!selected) {
      throw new Error("В памяти нет доступных кластеров");
    }
    const data = await request(
      "POST",
      `/ui/api/clusters/${sessionId.value}/memory/load`,
      {
        cluster_name: selected,
      }
    );
    const loaded = toClusterRows(data.cluster || {});
    const memoryName = String(loaded.memory_cluster_name || selected).trim();
    const existingLocalIdx = clusters.value.findIndex(
      (current) =>
        String(current?.memory_cluster_name || "").trim() === memoryName
    );
    if (existingLocalIdx >= 0) {
      clusters.value[existingLocalIdx] = loaded;
      activeTab.value = `cluster-${existingLocalIdx}`;
    } else {
      clusters.value.push(loaded);
      activeTab.value = `cluster-${clusters.value.length - 1}`;
    }
    setStatus(`Кластер из памяти загружен: ${selected}`, "ok");
  }, "Загрузка кластера из памяти");
}

async function loadActiveClusterFullyFromMemory() {
  await runSafe(async () => {
    await ensureSession();
    const clusterIdx = activeClusterIdx.value;
    if (!Number.isInteger(clusterIdx) || clusterIdx < 0 || clusterIdx >= clusters.value.length) {
      throw new Error("Выберите кластер для полной загрузки из памяти");
    }
    const data = await request(
      "POST",
      `/ui/api/clusters/${sessionId.value}/${clusterIdx}/memory/load-full`,
    );
    const loaded = toClusterRows(data.cluster || {});
    clusters.value[clusterIdx] = loaded;
    activeTab.value = `cluster-${clusterIdx}`;
    setStatus("Кластер полностью загружен из памяти", "ok");
  }, "Полная загрузка кластера из памяти");
}

function openMemorySearchTab() {
  activeTab.value = "search";
}

function clearRowHighlightTimer() {
  const timer = highlightedClusterRow.value.timer;
  if (timer) {
    clearTimeout(timer);
  }
  highlightedClusterRow.value = { clusterIndex: -1, rowIndex: -1, timer: null };
}

function markClusterRow(clusterIndex, rowIndex) {
  clearRowHighlightTimer();
  const timer = setTimeout(() => {
    highlightedClusterRow.value = {
      clusterIndex: -1,
      rowIndex: -1,
      timer: null,
    };
  }, 4000);
  highlightedClusterRow.value = { clusterIndex, rowIndex, timer };
}

async function performMemorySearch() {
  const query = String(memorySearchQuery.value || "").trim();
  if (!query) {
    setStatus("Введите текст для поиска в памяти", "err");
    return;
  }
  memorySearchLoading.value = true;
  try {
    const data = await request("POST", "/ui/api/memory/search", {
      query,
      limit: 25,
    });
    memorySearchResults.value = (data.items || []).map((item) => ({
      text: String(item.text || "").trim(),
      cluster_name: String(item.cluster_name || "").trim(),
    }));
    setStatus(`Найдено совпадений: ${memorySearchResults.value.length}`, "ok");
  } finally {
    memorySearchLoading.value = false;
  }
}

async function openSearchResult(result) {
  const clusterName = String(result?.cluster_name || "").trim();
  const enrichedText = String(result?.text || "").trim();
  if (!clusterName || !enrichedText) return;
  await loadMemoryClusterByName(clusterName);
  const clusterIndex = clusters.value.findIndex(
    (cluster) =>
      String(cluster?.memory_cluster_name || "").trim() === clusterName ||
      String(cluster?.name || "").trim() === clusterName
  );
  if (clusterIndex < 0) return;
  const cluster = clusters.value[clusterIndex];
  const rowIndex = (cluster.rows || []).findIndex(
    (row) => String(row?.enriched_name || "").trim() === enrichedText
  );
  if (rowIndex >= 0) {
    markClusterRow(clusterIndex, rowIndex);
  }
}

async function deleteCluster(index) {
  if (index < 0 || index >= clusters.value.length) return;
  const cluster = clusters.value[index];
  const clusterName = cluster?.name || `Кластер ${index + 1}`;
  const isMemoryCluster =
    String(cluster?.source || "")
      .trim()
      .toLowerCase() === "memory";
  const isPristineMemory =
    isMemoryCluster &&
    String(cluster?.__initialSignature || "") &&
    String(cluster.__initialSignature) === clusterSignature(cluster);
  if (!isPristineMemory) {
    const approved = await askConfirm({
      title: "Закрыть кластер",
      message: `Закрыть «${clusterName}»?\nНесохраненные изменения будут потеряны.`,
      confirmText: "Закрыть",
      cancelText: "Отмена",
      danger: true,
    });
    if (!approved) return;
  }
  clusters.value.splice(index, 1);
  if (!clusters.value.length) {
    activeTab.value = "source";
  } else if (
    activeClusterIdx.value >= clusters.value.length ||
    activeClusterIdx.value === index
  ) {
    activeTab.value = `cluster-${Math.max(
      0,
      Math.min(index, clusters.value.length - 1)
    )}`;
  }
  setStatus("Кластер закрыт", "ok");
}

async function deleteClusterRow(rowIndex) {
  const cluster = getCurrentCluster();
  if (!cluster || rowIndex < 0 || rowIndex >= cluster.rows.length) return;
  const [row] = cluster.rows.splice(rowIndex, 1);
  if (!row) return;
  row.deleted = true;
  cluster.rows.push(row);
  setStatus(
    "Строка помечена удаленной, перенесена в конец и отключена до восстановления",
    "ok"
  );
}

function restoreClusterRow(rowIndex) {
  const cluster = getCurrentCluster();
  if (!cluster || rowIndex < 0 || rowIndex >= cluster.rows.length) return;
  const [row] = cluster.rows.splice(rowIndex, 1);
  if (!row) return;
  row.deleted = false;
  const firstDeletedIdx = cluster.rows.findIndex((candidate) =>
    Boolean(candidate?.deleted)
  );
  if (firstDeletedIdx === -1) {
    cluster.rows.push(row);
  } else {
    cluster.rows.splice(firstDeletedIdx, 0, row);
  }
  setStatus("Строка восстановлена и возвращена в конец активных строк", "ok");
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
  const leadColumn = cluster.rows.some((r) =>
    String(r.enriched_name || "").trim()
  )
    ? ENRICHED_NAME_COLUMN
    : NOMENCLATURE_COLUMN;
  const name = String(
    cells[leadColumn] || cells[NOMENCLATURE_COLUMN] || ""
  ).trim();
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
  if (!cluster || name === NOMENCLATURE_COLUMN || name === ENRICHED_NAME_COLUMN)
    return;
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
    (c, index) =>
      index !== activeClusterIdx.value && String(c.name || "").trim() === next
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
  if (!cluster.attribute_merge_separators)
    cluster.attribute_merge_separators = {};
  cluster.attribute_merge[attribute] =
    behavior === "accumulative" ? "accumulative" : "priority";
  if (behavior === "accumulative" && separator) {
    cluster.attribute_merge_separators[attribute] = separator;
  } else {
    delete cluster.attribute_merge_separators[attribute];
  }
  for (const row of cluster.rows || []) {
    recalculateRowMergedValues(
      row,
      cluster.attribute_merge || {},
      cluster.attribute_merge_separators || {}
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
    cluster.attribute_merge_separators || {}
  );
  if (!newRow) return;
  regenerateRowEnriched(row, cluster.enriched_name_template || "");
  cluster.rows.splice(rowIndex + 1, 0, newRow);
  setStatus(`Извлечено: ${alias}`, "ok");
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
    cluster.attribute_merge_separators || {}
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
      `/ui/api/clusters/${sessionId.value}/rededupe`
    );
    clusters.value = (data.clusters || []).map((cluster) =>
      toClusterRows(cluster)
    );
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

async function refreshMemoryClusters() {
  await ensureSession();
  const listing = await request("GET", "/ui/api/memory/clusters");
  memoryClusters.value = (listing.clusters || [])
    .map((name) => String(name || "").trim())
    .filter(Boolean);
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
    clearRowHighlightTimer();
    await ensureSession();
    await dropSession();
    await ensureSession();
    clear();
    clusters.value = [];
    showNormalizeRecoveryActions.value = false;
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

async function pollTask(type, label, options = {}) {
  const { allowFailed = false, onStatus = null } = options;
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
    if (typeof onStatus === "function") {
      await onStatus(status, context);
    }
    if (status.status === "FAILED") {
      if (allowFailed) {
        return status;
      }
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

async function refreshClustersFromSession() {
  const clusterData = await request(
    "GET",
    `/ui/api/clusters/${sessionId.value}`
  );
  clusters.value = (clusterData.clusters || []).map((c) => toClusterRows(c));
  if (!activeTab.value.startsWith("cluster-") && clusters.value.length) {
    activeTab.value = "cluster-0";
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

async function startNormalize({
  mode = "start",
  clusterIndexes = [],
  clusterAttributeMode = "default",
} = {}) {
  await runSafe(async () => {
    showNormalizeRecoveryActions.value = false;
    setTaskProgress("Сохранение кластеров…", "Нормализация");
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clustersToPayload(),
    });
    setTaskProgress("Запуск нормализации…", "Нормализация");
    await request("POST", "/ui/api/normalize/start", {
      session_id: sessionId.value,
      provider: normalizeProvider.value,
      mode,
      cluster_indexes: clusterIndexes,
      cluster_attribute_mode: clusterAttributeMode,
    });
    const status = await pollTask("normalize", "Нормализация", {
      allowFailed: true,
      onStatus: async (currentStatus) => {
        if (
          currentStatus.result?.is_partial ||
          currentStatus.status === "COMPLETED"
        ) {
          await refreshClustersFromSession();
        }
      },
    });
    if (status.status === "FAILED") {
      showNormalizeRecoveryActions.value = true;
      await refreshClustersFromSession();
      const remaining = Number(status?.result?.remaining_items_count || 0);
      setStatus(
        `Нормализация остановлена: ${formatTaskError(
          status.error
        )}. Осталось: ${remaining}`,
        "err",
        null
      );
      return;
    }
    showNormalizeRecoveryActions.value = false;
    await refreshClustersFromSession();
    const count =
      status?.result?.actual_count ?? status?.result?.normalized?.length ?? 0;
    setStatus(`Нормализация завершена: ${count} позиций`, "ok", 100);
  }, "Нормализация");
}

async function startNormalizeFromToolbar() {
  const unsavedIndexes = getUnsavedClusterIndexes();
  const hasSaved = unsavedIndexes.length < clusters.value.length;
  if (!hasSaved || !unsavedIndexes.length) {
    await startNormalize({ mode: "start" });
    return;
  }
  const decision = await askChoice({
    title: "Режим нормализации",
    message:
      "Есть сохраненные кластеры. Нормализовать только несохраненные кластеры или все кластеры?",
    primaryText: "Только несохраненные",
    secondaryText: "Все кластеры",
    cancelText: "Отмена",
  });
  if (decision === "confirm") {
    await startNormalize({ mode: "start", clusterIndexes: unsavedIndexes });
    return;
  }
  if (decision === "secondary") {
    await startNormalize({ mode: "start" });
  }
}

async function renormalizeActiveCluster() {
  const cluster = getCurrentCluster();
  if (!cluster) return;
  const clusterIdx = activeClusterIdx.value;
  if (!Number.isInteger(clusterIdx) || clusterIdx < 0) return;
  const decision = await askChoice({
    title: "Перенормализация кластера",
    message:
      "Выберите режим перенормализации текущего кластера: все атрибуты или только новые/пустые.",
    primaryText: "Все атрибуты",
    secondaryText: "Новые и пустые",
    cancelText: "Отмена",
  });
  if (decision === "confirm") {
    await startNormalize({
      mode: "start",
      clusterIndexes: [clusterIdx],
      clusterAttributeMode: "all",
    });
    return;
  }
  if (decision === "secondary") {
    await startNormalize({
      mode: "start",
      clusterIndexes: [clusterIdx],
      clusterAttributeMode: "missing",
    });
  }
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
    for (const cluster of clusters.value) {
      cluster.rows = (cluster.rows || []).filter((row) => !row.deleted);
      cluster.source = "memory";
      if (!String(cluster.memory_cluster_name || "").trim()) {
        cluster.memory_cluster_name = String(cluster.name || "").trim();
      }
      const savedSig = clusterSignature(cluster);
      cluster.__memorySavedSignature = savedSig;
      cluster.__initialSignature = savedSig;
    }
    await refreshMemoryClusters();
    setStatus(`Сохранено в память: ${data.saved_count || 0}`, "ok");
  }, "Сохранение в память");
}

async function saveActiveClusterToMemory() {
  await runSafe(async () => {
    await ensureSession();
    const clusterIdx = getActiveClusterExportIndex();
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clustersToPayload(),
    });
    const data = await request("POST", "/ui/api/memory/save", {
      session_id: sessionId.value,
      cluster_index: clusterIdx,
    });
    const cluster = clusters.value[clusterIdx];
    if (cluster) {
      cluster.rows = (cluster.rows || []).filter((row) => !row.deleted);
      cluster.source = "memory";
      if (!String(cluster.memory_cluster_name || "").trim()) {
        cluster.memory_cluster_name = String(cluster.name || "").trim();
      }
      const savedSig = clusterSignature(cluster);
      cluster.__memorySavedSignature = savedSig;
      cluster.__initialSignature = savedSig;
    }
    await refreshMemoryClusters();
    setStatus(`Кластер сохранен в память: ${data.saved_count || 0}`, "ok");
  }, "Сохранение кластера в память");
}

async function flushRedis() {
  const approved = await askConfirm({
    title: "Очистка Redis",
    message:
      "Очистить весь Redis? Будут удалены статусы задач и кэш ответов LLM.",
    confirmText: "Очистить",
    cancelText: "Отмена",
    danger: true,
  });
  if (!approved) {
    return;
  }
  await runSafe(async () => {
    const data = await request("POST", "/ui/api/admin/flush-redis");
    setStatus(data.message || "Redis очищен", "ok", null);
  }, "Очистка Redis");
}

async function flushQdrant() {
  const approved = await askConfirm({
    title: "Очистка Qdrant",
    message:
      "Очистить векторную память Qdrant? Все сохранённые товары будут удалены из коллекции.",
    confirmText: "Очистить",
    cancelText: "Отмена",
    danger: true,
  });
  if (!approved) {
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

async function exportCsv() {
  await runSafe(async () => {
    await ensureSession();
    if (clusters.value.length) {
      await request("POST", "/ui/api/clusters/save", {
        session_id: sessionId.value,
        clusters: clustersToPayload(),
      });
    }
    await downloadExport(
      `/ui/api/export/${sessionId.value}/csv`,
      `clusters_${sessionId.value}_csv.zip`
    );
    setStatus("Экспорт CSV (по кластерам) готов", "ok");
  }, "Экспорт CSV");
}

function getActiveClusterExportIndex() {
  const idx = activeClusterIdx.value;
  if (!Number.isInteger(idx) || idx < 0 || idx >= clusters.value.length) {
    throw new Error("Выберите кластер для экспорта.");
  }
  return idx;
}

async function downloadExport(endpoint, filenameFallback) {
  const response = await fetch(apiUrl(endpoint));
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
  a.download = filenameFallback;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

async function exportActiveClusterXlsx() {
  await runSafe(async () => {
    await ensureSession();
    if (clusters.value.length) {
      await request("POST", "/ui/api/clusters/save", {
        session_id: sessionId.value,
        clusters: clustersToPayload(),
      });
    }
    const clusterIdx = getActiveClusterExportIndex();
    await downloadExport(
      `/ui/api/export/${sessionId.value}/cluster/${clusterIdx}/xlsx`,
      `cluster_${clusterIdx + 1}_${sessionId.value}.xlsx`
    );
    setStatus("Экспорт кластера XLSX готов", "ok");
  }, "Экспорт кластера XLSX");
}

async function exportActiveClusterCsv() {
  await runSafe(async () => {
    await ensureSession();
    if (clusters.value.length) {
      await request("POST", "/ui/api/clusters/save", {
        session_id: sessionId.value,
        clusters: clustersToPayload(),
      });
    }
    const clusterIdx = getActiveClusterExportIndex();
    await downloadExport(
      `/ui/api/export/${sessionId.value}/cluster/${clusterIdx}/csv`,
      `cluster_${clusterIdx + 1}_${sessionId.value}.csv`
    );
    setStatus("Экспорт кластера CSV готов", "ok");
  }, "Экспорт кластера CSV");
}

async function deleteActiveClusterFromMemory() {
  await runSafe(async () => {
    const cluster = getCurrentCluster();
    if (!cluster) return;
    const memoryClusterName = String(
      cluster.memory_cluster_name || cluster.name || ""
    ).trim();
    if (!memoryClusterName) {
      throw new Error("Memory cluster name is empty");
    }
    const approved = await askConfirm({
      title: "Удалить кластер из памяти",
      message: `Удалить из памяти «${memoryClusterName}»?\nБудут удалены все записи этого кластера.`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!approved) return;
    await request("POST", "/ui/api/memory/cluster/delete", {
      cluster_name: memoryClusterName,
    });
    const idx = activeClusterIdx.value;
    if (idx >= 0) {
      clusters.value.splice(idx, 1);
      if (!clusters.value.length) {
        activeTab.value = "source";
      } else {
        activeTab.value = `cluster-${Math.max(
          0,
          Math.min(idx, clusters.value.length - 1)
        )}`;
      }
    }
    await refreshMemoryClusters();
    setStatus("Кластер удален из памяти", "ok");
  }, "Удаление кластера из памяти");
}

async function loadTestCluster() {
  await runSafe(async () => {
    await ensureSession();
    clusters.value = buildTestClusters().map((cluster) =>
      toClusterRows(cluster)
    );
    activeTab.value = "cluster-0";
    await request("POST", "/ui/api/clusters/save", {
      session_id: sessionId.value,
      clusters: clustersToPayload(),
    });
    setStatus(
      "Загружен тестовый кластер «Тест: фильтры (демо)»: 3 строки, шаблон, members, аккумулятивные атрибуты",
      "ok"
    );
  }, "Тестовый кластер");
}

onMounted(async () => {
  await runSafe(async () => {
    clearRowHighlightTimer();
    await ensureSession();
    await refreshMemoryClusters();
    setStatus(
      "Начните работу: создайте кластер вручную, откройте существующий из памяти или импортируйте CSV/XLSX.",
      "ok"
    );
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
      :show-normalize-recovery-actions="showNormalizeRecoveryActions"
      :cluster-count="clusters.length"
      @update:backend-url="(value) => (backendUrl = value)"
      @update:embedding-provider="(value) => (embeddingProvider = value)"
      @update:profile-provider="(value) => (profileProvider = value)"
      @update:normalize-provider="(value) => (normalizeProvider = value)"
      @reset-session="resetSession"
      @clusterize="startClusterize"
      @normalize="startNormalizeFromToolbar"
      @normalize-resume="() => startNormalize({ mode: 'resume' })"
      @normalize-restart="() => startNormalize({ mode: 'restart' })"
      @save-memory="saveMemory"
      @export-xlsx="exportXlsx"
      @export-csv="exportCsv"
      @flush-redis="flushRedis"
      @flush-qdrant="flushQdrant"
      @load-test-cluster="loadTestCluster"
      @open-memory-search="openMemorySearchTab"
    />

    <StatusLine
      :text="statusText"
      :tone="statusTone"
      :progress="statusProgress"
    />
    <ConfirmDialog
      :open="confirmDialog.open"
      :title="confirmDialog.title"
      :message="confirmDialog.message"
      :confirm-text="confirmDialog.confirmText"
      :cancel-text="confirmDialog.cancelText"
      :secondary-text="confirmDialog.secondaryText"
      :danger="confirmDialog.danger"
      @confirm="closeConfirm('confirm')"
      @secondary="closeConfirm('secondary')"
      @cancel="closeConfirm('cancel')"
    />

    <section class="table-card">
      <ClusterTabs
        v-if="
          activeTab === 'source' || activeTab === 'search' || clusters.length
        "
        :clusters="clusters"
        :memory-clusters="memoryClusters"
        :active-tab="activeTab"
        @tab-change="(tab) => (activeTab = tab)"
        @add-cluster="addCluster"
        @select-memory-cluster="loadMemoryClusterByName"
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

      <section v-else-if="activeTab === 'search'" class="table-editor">
        <div class="table-header">
          <div class="table-meta">
            <h3>Поиск по памяти</h3>
          </div>
          <div class="icon-actions">
            <input
              v-model="memorySearchQuery"
              type="text"
              placeholder="Введите текст для поиска по памяти"
              @keydown.enter.prevent="
                runSafe(() => performMemorySearch(), 'Поиск по памяти')
              "
            />
            <button
              type="button"
              class="btn-with-icon"
              :disabled="memorySearchLoading"
              @click="runSafe(() => performMemorySearch(), 'Поиск по памяти')"
            >
              Найти
            </button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th class="sticky-check">
                  <Cog
                    class="table-actions-head-icon"
                    title="Действия"
                    aria-hidden="true"
                  />
                </th>
                <th>Обогащенное стандартизованное наименование</th>
                <th>Кластер</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in memorySearchResults"
                :key="`${item.cluster_name}::${item.text}`"
              >
                <td class="sticky-check table-check-cell">
                  <div class="row-action-cell">
                    <IconButton
                      title="Открыть кластер"
                      @click="
                        runSafe(
                          () => openSearchResult(item),
                          'Открытие кластера'
                        )
                      "
                    >
                      <ArrowUpRight aria-hidden="true" />
                    </IconButton>
                  </div>
                </td>
                <td>{{ item.text }}</td>
                <td>{{ item.cluster_name }}</td>
              </tr>
              <tr v-if="!memorySearchResults.length">
                <td colspan="3" class="muted">
                  Нет результатов. Введите запрос и нажмите «Найти».
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <SourceTableEditor
        v-else-if="activeClusterTable"
        mode="cluster"
        :table="activeClusterTable"
        :cluster-saved="activeClusterSaved"
        :move-targets="clusterMoveTargets"
        :highlight-row-index="activeHighlightRowIndex"
        @row-edit="applyClusterRowEdit"
        @add-row-form="applyClusterAddRow"
        @delete-row="
          (rowIndex) =>
            runSafe(() => deleteClusterRow(rowIndex), 'Удаление строки')
        "
        @restore-row="restoreClusterRow"
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
        @export-cluster-xlsx="exportActiveClusterXlsx"
        @export-cluster-csv="exportActiveClusterCsv"
        @save-cluster-memory="saveActiveClusterToMemory"
        @load-memory-full="loadActiveClusterFullyFromMemory"
        @renormalize-cluster="renormalizeActiveCluster"
        @delete-memory-cluster="deleteActiveClusterFromMemory"
        @notify="({ text, tone }) => setStatus(text, tone)"
      />
    </section>
  </div>
</template>
