export const NOMENCLATURE_COLUMN = "Номенклатура";

/** Формат таблицы для SourceTableEditor (режим cluster). */
export function clusterToTable(cluster, title) {
  const headers = [NOMENCLATURE_COLUMN, ...(cluster.attributes || [])];
  return {
    title: title || cluster.name || "Кластер",
    headers,
    selectedColumn: NOMENCLATURE_COLUMN,
    disabledColumns: [],
    rows: (cluster.rows || []).map((row, row_index) => ({
      row_index,
      included: true,
      cells: Object.fromEntries(
        headers.map((h) => [
          h,
          h === NOMENCLATURE_COLUMN
            ? String(row.item ?? "")
            : String(row.values?.[h] ?? ""),
        ]),
      ),
    })),
    page: 1,
    totalPages: 1,
    totalRows: (cluster.rows || []).length,
  };
}
