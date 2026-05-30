<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import {
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  Cog,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
  Square,
  Star,
  Trash2,
} from "@lucide/vue";
import IconButton from "./IconButton.vue";
import NomenclatureAliasesMenu from "./NomenclatureAliasesMenu.vue";
import DraftTextInput from "./DraftTextInput.vue";
import ClusterRowMenu from "./ClusterRowMenu.vue";
import AttributeMergeMenu from "./AttributeMergeMenu.vue";
import PriorityValueMenu from "./PriorityValueMenu.vue";
import {
  ENRICHED_NAME_COLUMN,
  NOMENCLATURE_COLUMN,
} from "../utils/clusterTable";

const props = defineProps({
  mode: { type: String, default: "source" },
  source: { type: Object, default: null },
  table: { type: Object, default: null },
  clusterSaved: { type: Boolean, default: false },
  moveTargets: { type: Array, default: () => [] },
  highlightRowIndex: { type: Number, default: null },
});

const emit = defineEmits([
  "toggle-row",
  "row-edit",
  "add-column",
  "rename-column",
  "delete-column",
  "toggle-column",
  "set-source-column",
  "change-page",
  "file-upload",
  "add-row-form",
  "delete-row",
  "restore-row",
  "move-row",
  "rename-title",
  "update-template",
  "set-attribute-merge-config",
  "regenerate-row",
  "regenerate-all",
  "split-alias",
  "merge-row-into",
  "rededupe",
  "export-cluster-xlsx",
  "export-cluster-csv",
  "load-memory-full",
  "save-cluster-memory",
  "renormalize-cluster",
  "delete-memory-cluster",
  "notify",
]);

const isSource = computed(() => props.mode === "source");
const isCluster = computed(() => props.mode === "cluster");

const tableData = computed(() => props.table || props.source || emptyTable());

const newColumnName = ref("");
const hiddenFileInput = ref(null);
const disabledSet = computed(
  () => new Set(tableData.value.disabledColumns || [])
);
const isDragActive = ref(false);
const addRowCells = ref({});
const hoveredColumn = ref(null);
const columnLongestCache = reactive({});
const clusterTitleLongest = ref("");
const clusterTemplateLongest = ref("");
const tableWrapRef = ref(null);

function rememberColumnText(header, text) {
  const key = String(header ?? "").trim();
  if (!key) return;
  const value = String(text ?? "");
  const prev = columnLongestCache[key] ?? "";
  if (value.length > prev.length) {
    columnLongestCache[key] = value;
  }
}

watch(
  () => tableData.value.headers,
  (headers) => {
    for (const header of headers || []) {
      rememberColumnText(header, header);
    }
  },
  { immediate: true }
);

watch(
  () => tableData.value.rows,
  (rows) => {
    for (const row of rows || []) {
      for (const header of tableData.value.headers || []) {
        rememberColumnText(header, row.cells?.[header]);
      }
    }
  },
  { immediate: true, deep: true }
);

watch(
  addRowCells,
  (cells) => {
    for (const [header, value] of Object.entries(cells)) {
      rememberColumnText(header, value);
    }
  },
  { deep: true }
);

function dataSourceTitle(dataSource) {
  if (dataSource === "memory") {
    return "Источник: векторная память (Qdrant)";
  }
  return "Источник: ИИ (кластеризация / нормализация)";
}

function emptyTable() {
  return {
    title: "",
    headers: [],
    selectedColumn: "",
    disabledColumns: [],
    enrichedNameTemplate: "",
    clusterSource: "ai",
    memoryClusterName: "",
    useEnrichedNames: false,
    rows: [],
    page: 1,
    totalPages: 1,
    totalRows: 0,
  };
}

function onTheadMouseOver(event) {
  const cell = event.target.closest("[data-column]");
  if (cell) hoveredColumn.value = cell.dataset.column;
}

function onTheadMouseLeave(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    hoveredColumn.value = null;
  }
}

function submitAddColumn() {
  const value = newColumnName.value.trim();
  if (!value) {
    emit("notify", { text: "Введите название колонки", tone: "err" });
    return;
  }
  emit("add-column", value);
  newColumnName.value = "";
}

function onFileChange(event) {
  const file = event.target.files?.[0];
  if (file) emit("file-upload", file);
  event.target.value = "";
}

function onDragOver(event) {
  event.preventDefault();
  isDragActive.value = true;
}

function onDragLeave() {
  isDragActive.value = false;
}

function onDrop(event) {
  event.preventDefault();
  isDragActive.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) emit("file-upload", file);
}

function triggerFileDialog() {
  hiddenFileInput.value?.click();
}

function applyMakeSource(header) {
  emit("set-source-column", header);
}

function applyToggleEnabled(header) {
  const enabled = disabledSet.value.has(header);
  emit("toggle-column", { name: header, enabled });
}

function applyDeleteColumn(header) {
  emit("delete-column", header);
}

function submitAddRowForm() {
  const sourceCol =
    tableData.value.selectedColumn || tableData.value.headers[0];
  const sourceValue = String(addRowCells.value[sourceCol] || "").trim();
  if (!sourceValue) {
    emit("notify", { text: "Укажите номенклатуру", tone: "err" });
    return;
  }
  const payload = Object.fromEntries(
    (tableData.value.headers || []).map((h) => [
      h,
      String(addRowCells.value[h] || "").trim(),
    ])
  );
  payload[sourceCol] = sourceValue;
  emit("add-row-form", payload);
  addRowCells.value = {};
}

function getColumnClass(header) {
  return {
    "col-source": header === tableData.value.selectedColumn,
    "col-disabled": disabledSet.value.has(header),
    "col-active":
      header === tableData.value.selectedColumn &&
      !disabledSet.value.has(header),
  };
}

function isCellEditable(header) {
  if (isCluster.value) return true;
  return header === tableData.value.selectedColumn;
}

function isRowDeleted(row) {
  return Boolean(row?.deleted);
}

function isRowCellEditable(row, header) {
  if (isRowDeleted(row)) return false;
  return isCellEditable(header);
}

/** В форме новой строки редактируется только номенклатура (как в исходных данных). */
function isAddRowCellEditable(header) {
  return header === sourceColumn.value;
}

/** Самая длинная строка в колонке — задаёт ширину полей ввода. */
const columnLongestText = computed(() => {
  const result = {};
  for (const header of tableData.value.headers || []) {
    let longest = columnLongestCache[header] || header;
    for (const row of tableData.value.rows || []) {
      const text = String(row.cells?.[header] ?? "");
      if (text.length > longest.length) longest = text;
    }
    const draft = String(addRowCells.value[header] ?? "");
    if (draft.length > longest.length) longest = draft;
    if (header === sourceColumn.value) {
      const placeholder = "Новая номенклатура";
      if (placeholder.length > longest.length) longest = placeholder;
    }
    result[header] = longest || "\u00a0";
  }
  return result;
});

function fieldSizerText(header, current = "") {
  const columnText = columnLongestText.value[header] ?? String(header ?? "");
  const value = String(current ?? "");
  if (value.length >= columnText.length) return value || "\u00a0";
  return columnText;
}

function newColumnSizerText() {
  const text = newColumnName.value.trim() || "Новая колонка";
  return text;
}

function onMoveRow(rowIndex, targetClusterIdx) {
  emit("move-row", { rowIndex, targetClusterIdx });
}

function noteCellInput(header, event) {
  rememberColumnText(header, event.target.value);
}

function onAddRowCellInput(header, event) {
  addRowCells.value[header] = event.target.value;
  noteCellInput(header, event);
}

const sectionTitle = computed(() => {
  if (tableData.value.title) return tableData.value.title;
  return isSource.value ? "Исходные данные" : "Кластер";
});

watch(
  () => (isCluster.value ? tableData.value.title : ""),
  (title) => {
    const text = String(title ?? "").trim();
    if (text.length > clusterTitleLongest.value.length) {
      clusterTitleLongest.value = text;
    }
  },
  { immediate: true }
);

function clusterTitleSizerText(current = "") {
  const placeholder = "Название кластера";
  const cached = clusterTitleLongest.value;
  const value = String(current ?? "");
  let longest = cached.length >= placeholder.length ? cached : placeholder;
  if (value.length > longest.length) longest = value;
  return longest || "\u00a0";
}

function noteClusterTitleInput(event) {
  const text = String(event.target.value ?? "");
  if (text.length > clusterTitleLongest.value.length) {
    clusterTitleLongest.value = text;
  }
}

function onClusterTitleCommit(value) {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) {
    emit("notify", { text: "Введите название кластера", tone: "err" });
    return;
  }
  clusterTitleLongest.value = trimmed;
  emit("rename-title", trimmed);
}

watch(
  () => (isCluster.value ? tableData.value.enrichedNameTemplate : ""),
  (template) => {
    const text = String(template ?? "").trim();
    if (text.length > clusterTemplateLongest.value.length) {
      clusterTemplateLongest.value = text;
    }
  },
  { immediate: true }
);

function clusterTemplateSizerText(current = "") {
  const placeholder = "Шаблон: {бренд} фильтр {артикул}";
  const cached = clusterTemplateLongest.value;
  const value = String(current ?? "");
  let longest = cached.length >= placeholder.length ? cached : placeholder;
  if (value.length > longest.length) longest = value;
  return longest || "\u00a0";
}

function noteClusterTemplateInput(event) {
  const text = String(event.target.value ?? "");
  if (text.length > clusterTemplateLongest.value.length) {
    clusterTemplateLongest.value = text;
  }
}

function onClusterTemplateCommit(value) {
  const trimmed = String(value ?? "").trim();
  clusterTemplateLongest.value = trimmed || clusterTemplateLongest.value;
  emit("update-template", trimmed);
}

function onRowCellCommit(rowIndex, header, value) {
  emit("row-edit", { rowIndex, header, value: String(value ?? "") });
}

function mergeTargetsForRow(rowIndex) {
  return (tableData.value.rows || [])
    .filter((row) => row.row_index !== rowIndex)
    .map((row) => ({
      index: row.row_index,
      name:
        String(row.cells?.[sourceColumn.value] || "").trim() ||
        `Строка ${row.row_index + 1}`,
    }))
    .filter((target) => target.name);
}

function attributeMergeBehavior(header) {
  const map = tableData.value.attributeMerge || {};
  return map[header] === "accumulative" ? "accumulative" : "priority";
}

function attributeMergeSeparator(header) {
  const map = tableData.value.attributeMergeSeparators || {};
  return String(map[header] || map[String(header).toLowerCase()] || "");
}

function priorityConflictValues(row, header) {
  if (!isCluster.value || !showEnrichedNames.value) return [];
  if (attributeMergeBehavior(header) !== "priority") return [];
  const values = [];
  for (const member of row.members || []) {
    const value = String(member.values?.[header] ?? "").trim();
    if (value && !values.includes(value)) {
      values.push(value);
    }
  }
  const current = String(row.cells?.[header] ?? "").trim();
  if (current && !values.includes(current)) {
    values.unshift(current);
  }
  return values.length > 1 ? values : [];
}

function onColumnRenameCommit(oldName, value) {
  emit("rename-column", { oldName, newName: String(value ?? "") });
}

const showEnrichedNames = computed(
  () => isCluster.value && Boolean(tableData.value.useEnrichedNames)
);

const sourceColumn = computed(() => {
  const headers = tableData.value.headers || [];
  const selected = tableData.value.selectedColumn;
  if (selected && headers.includes(selected)) return selected;
  return headers[0] || "";
});

const attributeHeaders = computed(() =>
  (tableData.value.headers || []).filter(
    (header) => header !== sourceColumn.value
  )
);

const deletedRowsCount = computed(
  () => (tableData.value.rows || []).filter((row) => isRowDeleted(row)).length
);

watch(
  () => props.highlightRowIndex,
  async (rowIndex) => {
    if (!isCluster.value || rowIndex === null || rowIndex === undefined) return;
    await nextTick();
    const wrap = tableWrapRef.value;
    if (!wrap) return;
    const row = wrap.querySelector(`tr[data-row-index="${rowIndex}"]`);
    if (row && typeof row.scrollIntoView === "function") {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
);
</script>

<template>
  <div
    v-if="tableData.headers.length"
    class="table-editor"
    :class="{ 'table-editor--cluster': isCluster }"
  >
    <div class="table-header">
      <div class="table-meta">
        <h3 v-if="isSource">{{ sectionTitle }}</h3>
        <DraftTextInput
          v-else
          class="cluster-title-edit"
          input-class="cell-edit cluster-title-input"
          :model-value="tableData.title || ''"
          :allow-empty="false"
          @commit="onClusterTitleCommit"
        >
          <template #sizer="{ text }">
            <span class="cell-field-sizer" aria-hidden="true">{{
              clusterTitleSizerText(text)
            }}</span>
          </template>
        </DraftTextInput>
        <div v-if="isCluster" class="cluster-template-field">
          <label class="cluster-template-label"
            >Шаблон обогащенного стандартизованного наименования</label
          >
          <DraftTextInput
            class="cluster-template-edit"
            input-class="cell-edit cluster-template-input"
            :model-value="tableData.enrichedNameTemplate || ''"
            placeholder="Пример: {бренд} фильтр {артикул}"
            @commit="onClusterTemplateCommit"
          >
            <template #sizer="{ text }">
              <span class="cell-field-sizer" aria-hidden="true">{{
                clusterTemplateSizerText(text)
              }}</span>
            </template>
          </DraftTextInput>
        </div>
        <div v-if="isSource" class="meta-line">
          <span
            >Страница {{ tableData.page }} из {{ tableData.totalPages }} · Всего
            строк: {{ tableData.totalRows }}</span
          >
          <span class="meta-pagination icon-actions">
            <IconButton
              title="Назад"
              :disabled="tableData.page <= 1"
              @click="emit('change-page', tableData.page - 1)"
            >
              <ChevronLeft aria-hidden="true" />
            </IconButton>
            <IconButton
              title="Вперед"
              :disabled="tableData.page >= tableData.totalPages"
              @click="emit('change-page', tableData.page + 1)"
            >
              <ChevronRight aria-hidden="true" />
            </IconButton>
          </span>
        </div>
        <div v-else class="meta-line cluster-meta-actions">
          <span>Строк: {{ tableData.totalRows }}</span>
          <button
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
            :title="
              props.clusterSaved
                ? 'Кластер сохранен в Qdrant'
                : 'Сохранить кластер в Qdrant'
            "
            :disabled="props.clusterSaved"
            @click="emit('save-cluster-memory')"
          >
            <CheckSquare v-if="props.clusterSaved" aria-hidden="true" />
            <Save v-else aria-hidden="true" />
            {{ props.clusterSaved ? "Кластер сохранен" : "Сохранить кластер" }}
          </button>
          <span class="cluster-export-actions">
            <button
              type="button"
              class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
              title="Скачать текущий кластер в XLSX"
              @click="emit('export-cluster-xlsx')"
            >
              <Download aria-hidden="true" />
              XLSX
            </button>
            <button
              type="button"
              class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
              title="Скачать текущий кластер в CSV"
              @click="emit('export-cluster-csv')"
            >
              <Download aria-hidden="true" />
              CSV
            </button>
          </span>
          <button
            v-if="showEnrichedNames"
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
            @click="emit('regenerate-all')"
          >
            <RotateCcw aria-hidden="true" />
            Пересоздать имена
          </button>
          <button
            v-if="showEnrichedNames"
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
            @click="emit('rededupe')"
          >
            <Sparkles aria-hidden="true" />
            Пересчитать дубликаты
          </button>
          <button
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
            @click="emit('renormalize-cluster')"
          >
            <Sparkles aria-hidden="true" />
            Перенормализовать
          </button>
          <button
            v-if="tableData.clusterSource === 'memory' && tableData.memoryClusterName"
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini"
            title="Подгрузить весь кластер из памяти"
            @click="emit('load-memory-full')"
          >
            <Database aria-hidden="true" />
            Загрузить полностью
          </button>
          <button
            v-if="tableData.clusterSource === 'memory'"
            type="button"
            class="btn-with-icon btn-with-icon--secondary btn-with-icon--mini danger cluster-meta-actions__danger"
            @click="emit('delete-memory-cluster')"
          >
            <Trash2 aria-hidden="true" />
            Удалить из памяти
          </button>
          <span v-if="deletedRowsCount" class="cluster-deleted-hint">
            Удаленные строки: {{ deletedRowsCount }} (перенесены в конец и
            исключены из сохранения)
          </span>
        </div>
      </div>
    </div>

    <div ref="tableWrapRef" class="table-wrap">
      <table>
        <thead
          @mouseover="onTheadMouseOver"
          @focusin="onTheadMouseOver"
          @mouseleave="onTheadMouseLeave"
        >
          <tr class="col-toolbar-row">
            <th class="sticky-check col-toolbar-spacer" />
            <th
              v-if="sourceColumn"
              :key="`tool-${sourceColumn}`"
              :data-column="sourceColumn"
              :class="[
                getColumnClass(sourceColumn),
                'col-toolbar-cell',
                { 'col-column--hover': hoveredColumn === sourceColumn },
              ]"
            >
              <div class="col-hover-actions">
                <IconButton
                  v-if="isSource"
                  title="Сделать источником"
                  @click="applyMakeSource(sourceColumn)"
                >
                  <Star aria-hidden="true" />
                </IconButton>
                <IconButton
                  v-if="isSource"
                  :title="
                    disabledSet.has(sourceColumn)
                      ? 'Включить атрибут'
                      : 'Исключить атрибут'
                  "
                  @click="applyToggleEnabled(sourceColumn)"
                >
                  <Square
                    v-if="disabledSet.has(sourceColumn)"
                    aria-hidden="true"
                  />
                  <CheckSquare v-else aria-hidden="true" />
                </IconButton>
                <IconButton
                  title="Удалить столбец"
                  danger
                  :disabled="tableData.headers.length <= 1"
                  @click="applyDeleteColumn(sourceColumn)"
                >
                  <Trash2 aria-hidden="true" />
                </IconButton>
              </div>
            </th>
            <th class="col-add-column col-toolbar-cell">
              <div class="col-hover-actions col-hover-actions--always">
                <IconButton title="Добавить колонку" @click="submitAddColumn">
                  <Plus aria-hidden="true" />
                </IconButton>
              </div>
            </th>
            <th
              v-for="header in attributeHeaders"
              :key="`tool-${header}`"
              :data-column="header"
              :class="[
                getColumnClass(header),
                'col-toolbar-cell',
                { 'col-column--hover': hoveredColumn === header },
              ]"
            >
              <div class="col-hover-actions">
                <IconButton
                  v-if="isSource"
                  title="Сделать источником"
                  @click="applyMakeSource(header)"
                >
                  <Star aria-hidden="true" />
                </IconButton>
                <IconButton
                  v-if="isSource"
                  :title="
                    disabledSet.has(header)
                      ? 'Включить атрибут'
                      : 'Исключить атрибут'
                  "
                  @click="applyToggleEnabled(header)"
                >
                  <Square v-if="disabledSet.has(header)" aria-hidden="true" />
                  <CheckSquare v-else aria-hidden="true" />
                </IconButton>
                <AttributeMergeMenu
                  v-if="isCluster && showEnrichedNames"
                  :attribute="header"
                  :behavior="attributeMergeBehavior(header)"
                  :separator="attributeMergeSeparator(header)"
                  @update-config="
                    (payload) => emit('set-attribute-merge-config', payload)
                  "
                />
                <IconButton
                  title="Удалить столбец"
                  danger
                  :disabled="tableData.headers.length <= 1"
                  @click="applyDeleteColumn(header)"
                >
                  <Trash2 aria-hidden="true" />
                </IconButton>
              </div>
            </th>
          </tr>
          <tr class="col-head-row">
            <th class="sticky-check">
              <Cog
                v-if="isCluster"
                class="table-actions-head-icon"
                title="Действия"
                aria-hidden="true"
              />
              <template v-else>Вкл</template>
            </th>
            <th
              v-if="sourceColumn"
              :key="sourceColumn"
              :data-column="sourceColumn"
              :class="[
                getColumnClass(sourceColumn),
                'col-head-cell',
                { 'col-column--hover': hoveredColumn === sourceColumn },
              ]"
            >
              <div class="col-head">
                <DraftTextInput
                  class="cell-field-box"
                  input-class="cell-edit col-input"
                  :model-value="sourceColumn"
                  @commit="(value) => onColumnRenameCommit(sourceColumn, value)"
                >
                  <template #sizer="{ text }">
                    <span class="cell-field-sizer" aria-hidden="true">{{
                      fieldSizerText(sourceColumn, text)
                    }}</span>
                  </template>
                </DraftTextInput>
              </div>
            </th>
            <th class="col-add-column col-head-cell">
              <div class="col-head">
                <div class="cell-field-box">
                  <span class="cell-field-sizer" aria-hidden="true">{{
                    newColumnSizerText()
                  }}</span>
                  <input
                    v-model="newColumnName"
                    class="cell-edit col-input"
                    type="text"
                    placeholder="Новая колонка"
                    @keydown.enter.prevent="submitAddColumn"
                  />
                </div>
              </div>
            </th>
            <th
              v-for="header in attributeHeaders"
              :key="header"
              :data-column="header"
              :class="[
                getColumnClass(header),
                'col-head-cell',
                { 'col-column--hover': hoveredColumn === header },
              ]"
            >
              <div class="col-head">
                <DraftTextInput
                  class="cell-field-box"
                  input-class="cell-edit col-input"
                  :model-value="header"
                  @commit="(value) => onColumnRenameCommit(header, value)"
                >
                  <template #sizer="{ text }">
                    <span class="cell-field-sizer" aria-hidden="true">{{
                      fieldSizerText(header, text)
                    }}</span>
                  </template>
                </DraftTextInput>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr class="add-row-form">
            <td class="sticky-check add-row-cell table-check-cell">
              <div class="row-action-cell">
                <IconButton title="Добавить запись" @click="submitAddRowForm">
                  <Plus aria-hidden="true" />
                </IconButton>
              </div>
            </td>
            <td
              v-if="sourceColumn"
              class="cell-field"
              :class="getColumnClass(sourceColumn)"
            >
              <div class="cell-field-box">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(
                    sourceColumn,
                    addRowCells[sourceColumn] || "Новая номенклатура"
                  )
                }}</span>
                <input
                  class="cell-edit"
                  type="text"
                  :value="addRowCells[sourceColumn] || ''"
                  @input="onAddRowCellInput(sourceColumn, $event)"
                  placeholder="Новая номенклатура"
                  @keydown.enter.prevent="submitAddRowForm"
                />
              </div>
            </td>
            <td class="col-add-column cell-inert" />
            <td
              v-for="header in attributeHeaders"
              :key="`new-${header}`"
              :class="[
                { 'cell-inert': !isAddRowCellEditable(header) },
                { 'cell-field': isAddRowCellEditable(header) },
              ]"
            >
              <div v-if="isAddRowCellEditable(header)" class="cell-field-box">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(header, addRowCells[header])
                }}</span>
                <input
                  class="cell-edit"
                  type="text"
                  :value="addRowCells[header] || ''"
                  @input="onAddRowCellInput(header, $event)"
                  @keydown.enter.prevent="submitAddRowForm"
                />
              </div>
            </td>
          </tr>
          <tr
            v-for="row in tableData.rows"
            :key="row.row_index"
            :data-row-index="row.row_index"
            :class="{
              'table-row--deleted': isRowDeleted(row),
              'table-row--highlight': isCluster && props.highlightRowIndex === row.row_index,
            }"
          >
            <td class="sticky-check table-check-cell">
              <div class="row-action-cell">
                <IconButton
                  v-if="isCluster && isRowDeleted(row)"
                  title="Восстановить строку"
                  @click="emit('restore-row', row.row_index)"
                >
                  <RotateCcw aria-hidden="true" />
                </IconButton>
                <ClusterRowMenu
                  v-else-if="isCluster"
                  :aliases="row.aliases"
                  :merge-targets="mergeTargetsForRow(row.row_index)"
                  :move-targets="moveTargets"
                  :show-enriched-actions="showEnrichedNames"
                  @regenerate="emit('regenerate-row', row.row_index)"
                  @split-alias="
                    (alias) =>
                      emit('split-alias', { rowIndex: row.row_index, alias })
                  "
                  @merge-into="
                    (targetIndex) =>
                      emit('merge-row-into', {
                        sourceIndex: row.row_index,
                        targetIndex,
                      })
                  "
                  @move-row="
                    (targetClusterIdx) =>
                      onMoveRow(row.row_index, targetClusterIdx)
                  "
                  @delete-row="emit('delete-row', row.row_index)"
                />
                <template v-else>
                  <IconButton
                    :title="
                      row.included ? 'Исключить строку' : 'Включить строку'
                    "
                    @click="
                      emit('toggle-row', {
                        rowIndex: row.row_index,
                        included: !row.included,
                      })
                    "
                  >
                    <CheckSquare v-if="row.included" aria-hidden="true" />
                    <Square v-else aria-hidden="true" />
                  </IconButton>
                  <IconButton
                    title="Удалить строку"
                    danger
                    @click="emit('delete-row', row.row_index)"
                  >
                    <Trash2 aria-hidden="true" />
                  </IconButton>
                </template>
              </div>
            </td>
            <td
              v-if="sourceColumn"
              :class="[
                getColumnClass(sourceColumn),
                { 'cell-field': isRowCellEditable(row, sourceColumn) },
              ]"
            >
              <div
                v-if="isRowCellEditable(row, sourceColumn)"
                class="cell-field-box"
                :class="{
                  'cell-field-box--with-source': isCluster,
                  'cell-field-box--with-aliases':
                    isCluster && showEnrichedNames,
                }"
              >
                <NomenclatureAliasesMenu
                  v-if="isCluster && showEnrichedNames"
                  :aliases="row.aliases"
                />
                <span
                  v-if="isCluster && row.dataSource"
                  class="row-source-icon"
                  :title="dataSourceTitle(row.dataSource)"
                >
                  <Database
                    v-if="row.dataSource === 'memory'"
                    class="row-source-icon__svg"
                    aria-hidden="true"
                  />
                  <Sparkles
                    v-else
                    class="row-source-icon__svg"
                    aria-hidden="true"
                  />
                </span>
                <DraftTextInput
                  class="cell-field-inner"
                  input-class="cell-edit"
                  :model-value="String(row.cells?.[sourceColumn] ?? '')"
                  @commit="
                    (value) =>
                      onRowCellCommit(row.row_index, sourceColumn, value)
                  "
                >
                  <template #sizer="{ text }">
                    <span class="cell-field-sizer" aria-hidden="true">{{
                      fieldSizerText(sourceColumn, text)
                    }}</span>
                  </template>
                </DraftTextInput>
              </div>
              <div
                v-else
                class="cell-field-box cell-field-box--static"
                :class="{
                  'cell-field-box--with-source': isCluster && row.dataSource,
                  'cell-field-box--with-aliases':
                    isCluster && showEnrichedNames,
                }"
              >
                <NomenclatureAliasesMenu
                  v-if="isCluster && showEnrichedNames"
                  :aliases="row.aliases"
                />
                <span
                  v-if="isCluster && row.dataSource"
                  class="row-source-icon"
                  :title="dataSourceTitle(row.dataSource)"
                >
                  <Database
                    v-if="row.dataSource === 'memory'"
                    class="row-source-icon__svg"
                    aria-hidden="true"
                  />
                  <Sparkles
                    v-else
                    class="row-source-icon__svg"
                    aria-hidden="true"
                  />
                </span>
                <div class="cell-field-inner">
                  <span class="cell-field-sizer" aria-hidden="true">{{
                    fieldSizerText(sourceColumn, row.cells?.[sourceColumn])
                  }}</span>
                  <span class="cell-static-text">{{
                    String(row.cells?.[sourceColumn] ?? "")
                  }}</span>
                </div>
              </div>
            </td>
            <td class="col-add-column cell-inert" />
            <td
              v-for="header in attributeHeaders"
              :key="`${row.row_index}-${header}`"
              :class="[
                getColumnClass(header),
                { 'cell-inert': !isRowCellEditable(row, header) },
                { 'cell-field': isRowCellEditable(row, header) },
              ]"
            >
              <div
                v-if="isRowCellEditable(row, header)"
                class="cell-field-box"
                :class="{
                  'cell-field-box--with-priority-conflict':
                    priorityConflictValues(row, header).length > 1,
                }"
              >
                <DraftTextInput
                  class="cell-field-inner"
                  input-class="cell-edit"
                  :model-value="String(row.cells?.[header] ?? '')"
                  @commit="
                    (value) => onRowCellCommit(row.row_index, header, value)
                  "
                >
                  <template #sizer="{ text }">
                    <span class="cell-field-sizer" aria-hidden="true">{{
                      fieldSizerText(header, text)
                    }}</span>
                  </template>
                </DraftTextInput>
                <PriorityValueMenu
                  v-if="priorityConflictValues(row, header).length > 1"
                  :values="priorityConflictValues(row, header)"
                  :current-value="String(row.cells?.[header] ?? '')"
                  @select="
                    (value) => onRowCellCommit(row.row_index, header, value)
                  "
                />
              </div>
              <div v-else class="cell-field-box cell-field-box--static">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(header, row.cells?.[header])
                }}</span>
                <span class="cell-static-text">{{
                  String(row.cells?.[header] ?? "")
                }}</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div
    v-else-if="isSource"
    class="empty-state dropzone"
    :class="{ 'dropzone-active': isDragActive }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
    @click="triggerFileDialog"
  >
    <p>Перетащите CSV/XLSX файл сюда</p>
    <p class="muted">или выберите файл вручную</p>
    <input
      ref="hiddenFileInput"
      class="sr-file-input"
      type="file"
      accept=".csv,.xlsx,.xlsm"
      @change="onFileChange"
    />
  </div>
</template>
