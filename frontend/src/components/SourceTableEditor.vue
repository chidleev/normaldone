<script setup>
import { computed, reactive, ref, watch } from "vue";
import {
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Plus,
  Square,
  Star,
  Trash2,
} from "@lucide/vue";
import IconButton from "./IconButton.vue";
import MoveClusterMenu from "./MoveClusterMenu.vue";

const props = defineProps({
  mode: { type: String, default: "source" },
  source: { type: Object, default: null },
  table: { type: Object, default: null },
  moveTargets: { type: Array, default: () => [] },
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
  "move-row",
  "notify",
]);

const isSource = computed(() => props.mode === "source");
const isCluster = computed(() => props.mode === "cluster");

const tableData = computed(() => props.table || props.source || emptyTable());

const newColumnName = ref("");
const hiddenFileInput = ref(null);
const disabledSet = computed(() => new Set(tableData.value.disabledColumns || []));
const isDragActive = ref(false);
const addRowCells = ref({});
const hoveredColumn = ref(null);
const columnLongestCache = reactive({});

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
  { immediate: true },
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
  { immediate: true, deep: true },
);

watch(
  addRowCells,
  (cells) => {
    for (const [header, value] of Object.entries(cells)) {
      rememberColumnText(header, value);
    }
  },
  { deep: true },
);

function emptyTable() {
  return {
    title: "",
    headers: [],
    selectedColumn: "",
    disabledColumns: [],
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
  const sourceCol = tableData.value.selectedColumn || tableData.value.headers[0];
  const sourceValue = String(addRowCells.value[sourceCol] || "").trim();
  if (!sourceValue) {
    emit("notify", { text: "Укажите номенклатуру", tone: "err" });
    return;
  }
  const payload = Object.fromEntries(
    (tableData.value.headers || []).map((h) => [h, String(addRowCells.value[h] || "").trim()]),
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
      header === tableData.value.selectedColumn && !disabledSet.value.has(header),
  };
}

function isCellEditable(header) {
  if (isCluster.value) return true;
  return header === tableData.value.selectedColumn;
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

const sourceColumn = computed(() => {
  const headers = tableData.value.headers || [];
  const selected = tableData.value.selectedColumn;
  if (selected && headers.includes(selected)) return selected;
  return headers[0] || "";
});

const attributeHeaders = computed(() =>
  (tableData.value.headers || []).filter((header) => header !== sourceColumn.value),
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
        <h3>{{ sectionTitle }}</h3>
        <div v-if="isSource" class="meta-line">
          <span
            >Страница {{ tableData.page }} из {{ tableData.totalPages }} · Всего строк:
            {{ tableData.totalRows }}</span
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
        <div v-else class="meta-line">
          <span>Строк: {{ tableData.totalRows }}</span>
        </div>
      </div>
    </div>

    <div class="table-wrap">
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
                    disabledSet.has(sourceColumn) ? 'Включить атрибут' : 'Исключить атрибут'
                  "
                  @click="applyToggleEnabled(sourceColumn)"
                >
                  <Square v-if="disabledSet.has(sourceColumn)" aria-hidden="true" />
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
                  :title="disabledSet.has(header) ? 'Включить атрибут' : 'Исключить атрибут'"
                  @click="applyToggleEnabled(header)"
                >
                  <Square v-if="disabledSet.has(header)" aria-hidden="true" />
                  <CheckSquare v-else aria-hidden="true" />
                </IconButton>
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
            <th class="sticky-check">{{ isCluster ? "Действия" : "Вкл" }}</th>
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
                <div class="cell-field-box">
                  <span class="cell-field-sizer" aria-hidden="true">{{
                    fieldSizerText(sourceColumn, sourceColumn)
                  }}</span>
                  <input
                    class="cell-edit col-input"
                    type="text"
                    :value="sourceColumn"
                    @input="noteCellInput(sourceColumn, $event)"
                    @change="
                      emit('rename-column', {
                        oldName: sourceColumn,
                        newName: $event.target.value,
                      })
                    "
                  />
                </div>
              </div>
            </th>
            <th class="col-add-column col-head-cell">
              <div class="col-head">
                <div class="cell-field-box">
                  <span class="cell-field-sizer" aria-hidden="true">{{ newColumnSizerText() }}</span>
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
                <div class="cell-field-box">
                  <span class="cell-field-sizer" aria-hidden="true">{{
                    fieldSizerText(header, header)
                  }}</span>
                  <input
                    class="cell-edit col-input"
                    type="text"
                    :value="header"
                    @input="noteCellInput(header, $event)"
                    @change="emit('rename-column', { oldName: header, newName: $event.target.value })"
                  />
                </div>
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
            <td v-if="sourceColumn" class="cell-field" :class="getColumnClass(sourceColumn)">
              <div class="cell-field-box">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(sourceColumn, addRowCells[sourceColumn] || "Новая номенклатура")
                }}</span>
                <input
                  class="cell-edit"
                  type="text"
                  :value="addRowCells[sourceColumn] || ''"
                  @input="onAddRowCellInput(sourceColumn, $event)"
                  placeholder="Новая номенклатура"
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
                />
              </div>
            </td>
          </tr>
          <tr v-for="row in tableData.rows" :key="row.row_index">
            <td class="sticky-check table-check-cell">
              <div class="row-action-cell">
                <IconButton title="Удалить строку" danger @click="emit('delete-row', row.row_index)">
                  <Trash2 aria-hidden="true" />
                </IconButton>
                <MoveClusterMenu
                  v-if="isCluster"
                  :targets="moveTargets"
                  @select="(targetClusterIdx) => onMoveRow(row.row_index, targetClusterIdx)"
                />
                <template v-else>
                  <IconButton
                    :title="row.included ? 'Исключить строку' : 'Включить строку'"
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
                </template>
              </div>
            </td>
            <td
              v-if="sourceColumn"
              :class="[
                getColumnClass(sourceColumn),
                { 'cell-field': isCellEditable(sourceColumn) },
              ]"
            >
              <div v-if="isCellEditable(sourceColumn)" class="cell-field-box">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(sourceColumn, row.cells?.[sourceColumn])
                }}</span>
                <input
                  class="cell-edit"
                  type="text"
                  :value="String(row.cells?.[sourceColumn] ?? '')"
                  @input="noteCellInput(sourceColumn, $event)"
                  @change="
                    emit('row-edit', {
                      rowIndex: row.row_index,
                      header: sourceColumn,
                      value: $event.target.value,
                    })
                  "
                />
              </div>
              <div v-else class="cell-field-box cell-field-box--static">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(sourceColumn, row.cells?.[sourceColumn])
                }}</span>
                <span class="cell-static-text">{{ String(row.cells?.[sourceColumn] ?? "") }}</span>
              </div>
            </td>
            <td class="col-add-column cell-inert" />
            <td
              v-for="header in attributeHeaders"
              :key="`${row.row_index}-${header}`"
              :class="[
                getColumnClass(header),
                { 'cell-inert': !isCellEditable(header) },
                { 'cell-field': isCellEditable(header) },
              ]"
            >
              <div v-if="isCellEditable(header)" class="cell-field-box">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(header, row.cells?.[header])
                }}</span>
                <input
                  class="cell-edit"
                  type="text"
                  :value="String(row.cells?.[header] ?? '')"
                  @input="noteCellInput(header, $event)"
                  @change="
                    emit('row-edit', {
                      rowIndex: row.row_index,
                      header,
                      value: $event.target.value,
                    })
                  "
                />
              </div>
              <div v-else class="cell-field-box cell-field-box--static">
                <span class="cell-field-sizer" aria-hidden="true">{{
                  fieldSizerText(header, row.cells?.[header])
                }}</span>
                <span class="cell-static-text">{{ String(row.cells?.[header] ?? "") }}</span>
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
