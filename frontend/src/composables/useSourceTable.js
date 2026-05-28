import { reactive } from "vue";
import { orderHeadersWithSourceFirst } from "../utils/tableHeaders";

export function useSourceTable(request, ensureSession, sessionIdRef) {
  const source = reactive({
    headers: [],
    rows: [],
    page: 1,
    pageSize: 10,
    totalRows: 0,
    totalPages: 1,
    selectedColumn: "",
    disabledColumns: [],
  });

  function getBaseAttributes() {
    const disabled = new Set(source.disabledColumns);
    return source.headers.filter((h) => h !== source.selectedColumn && !disabled.has(h));
  }

  async function uploadFile(file) {
    await ensureSession();
    await request("POST", "/ui/api/session/reset", { session_id: sessionIdRef.value });
    const form = new FormData();
    form.append("session_id", sessionIdRef.value);
    form.append("file", file);
    const data = await request("POST", "/ui/api/upload", form, true);
    const headers = data.headers || [];
    source.selectedColumn = headers[0] || "";
    source.headers = orderHeadersWithSourceFirst(headers, source.selectedColumn);
    source.disabledColumns = [];
    await loadRows(1);
    return data;
  }

  async function loadRows(page = 1) {
    await ensureSession();
    const data = await request(
      "GET",
      `/ui/api/rows/${sessionIdRef.value}?page=${page}&page_size=${source.pageSize}`,
    );
    source.page = data.page;
    source.totalPages = data.total_pages;
    source.totalRows = data.total_rows;
    source.rows = data.rows || [];
  }

  async function toggleRow(rowIndex, included) {
    await request("POST", "/ui/api/rows/include", {
      session_id: sessionIdRef.value,
      row_index: rowIndex,
      included,
    });
    const row = source.rows.find((r) => r.row_index === rowIndex);
    if (row) row.included = included;
  }

  async function updateRowCell(rowIndex, header, value) {
    const row = source.rows.find((r) => r.row_index === rowIndex);
    if (row) {
      row.cells[header] = value;
    }
    await request("POST", "/ui/api/rows/update", {
      session_id: sessionIdRef.value,
      row_index: rowIndex,
      cells: { [header]: value },
    });
  }

  async function addRow(cells = null) {
    const key = source.selectedColumn || source.headers[0];
    const payloadCells = cells || { [key]: "Новая запись" };
    await request("POST", "/ui/api/rows/add", {
      session_id: sessionIdRef.value,
      cells: payloadCells,
    });
    await loadRows(1);
  }

  async function deleteRow(rowIndex) {
    await request("POST", "/ui/api/rows/delete", {
      session_id: sessionIdRef.value,
      row_index: rowIndex,
    });
    await loadRows(source.page);
  }

  async function addColumn(columnName) {
    const name = String(columnName || "").trim();
    const anchor = source.selectedColumn || source.headers[0] || "";
    const data = await request("POST", "/ui/api/columns/add", {
      session_id: sessionIdRef.value,
      column_name: name,
      after_column: anchor,
    });
    source.headers = orderHeadersWithSourceFirst(
      data.headers || source.headers,
      anchor,
      name,
    );
  }

  async function renameColumn(oldName, newName) {
    const data = await request("POST", "/ui/api/columns/rename", {
      session_id: sessionIdRef.value,
      old_name: oldName,
      new_name: newName,
    });
    source.headers = data.headers || source.headers;
    if (source.selectedColumn === oldName) source.selectedColumn = newName;
    source.disabledColumns = source.disabledColumns.map((h) => (h === oldName ? newName : h));
    await loadRows(source.page);
  }

  async function deleteColumn(name) {
    const data = await request("POST", "/ui/api/columns/delete", {
      session_id: sessionIdRef.value,
      column_name: name,
    });
    source.headers = data.headers || source.headers;
    if (!source.headers.includes(source.selectedColumn)) {
      source.selectedColumn = source.headers[0] || "";
    }
    source.disabledColumns = source.disabledColumns.filter((h) => h !== name);
    await loadRows(source.page);
  }

  function setColumnEnabled(name, enabled) {
    const disabled = new Set(source.disabledColumns);
    if (enabled) disabled.delete(name);
    else disabled.add(name);
    source.disabledColumns = Array.from(disabled);
  }

  async function setSourceColumn(name) {
    if (!source.headers.includes(name)) return;
    source.selectedColumn = name;
    source.headers = orderHeadersWithSourceFirst(source.headers, name);
    await request("POST", "/ui/api/columns/set-source", {
      session_id: sessionIdRef.value,
      column_name: name,
    });
  }

  function clear() {
    source.headers = [];
    source.rows = [];
    source.page = 1;
    source.totalRows = 0;
    source.totalPages = 1;
    source.selectedColumn = "";
    source.disabledColumns = [];
  }

  return {
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
  };
}
