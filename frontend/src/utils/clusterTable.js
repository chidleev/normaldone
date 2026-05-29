export const NOMENCLATURE_COLUMN = "Номенклатура";
export const ENRICHED_NAME_COLUMN = "Обогащенное стандартизованное наименование";

export function clusterUsesEnrichedNames(cluster) {
  return (cluster.rows || []).some((row) => String(row.enriched_name || "").trim());
}

/** Формат таблицы для SourceTableEditor (режим cluster). */
export function clusterToTable(cluster, title) {
  const useEnriched = clusterUsesEnrichedNames(cluster);
  const leadColumn = useEnriched ? ENRICHED_NAME_COLUMN : NOMENCLATURE_COLUMN;
  const headers = [leadColumn, ...(cluster.attributes || [])];
  return {
    title: title || cluster.name || "Кластер",
    headers,
    selectedColumn: leadColumn,
    disabledColumns: [],
    enrichedNameTemplate: String(cluster.enriched_name_template || ""),
    attributeMerge: { ...(cluster.attribute_merge || {}) },
    attributeMergeSeparators: { ...(cluster.attribute_merge_separators || {}) },
    useEnrichedNames: useEnriched,
    rows: (cluster.rows || []).map((row, row_index) => {
      const aliases = (row.aliases || [])
        .map((name) => String(name || "").trim())
        .filter(Boolean);
      const members = (row.members || [])
        .map((member) => ({
          item: String(member.item || "").trim(),
          values: Object.fromEntries(
            Object.entries(member.values || {}).map(([key, value]) => [
              String(key || "").trim(),
              String(value || ""),
            ]),
          ),
          source: member.source === "memory" ? "memory" : "ai",
        }))
        .filter((member) => member.item);
      const displayName = useEnriched
        ? String(row.enriched_name || "").trim()
        : String(row.item ?? "");
      return {
        row_index,
        included: true,
        dataSource: row.source === "memory" ? "memory" : "ai",
        aliases: aliases.length ? aliases : [String(row.item || "").trim()].filter(Boolean),
        members,
        cells: Object.fromEntries(
          headers.map((h) => [
            h,
            h === leadColumn
              ? displayName
              : String(row.values?.[h] ?? ""),
          ]),
        ),
      };
    }),
    page: 1,
    totalPages: 1,
    totalRows: (cluster.rows || []).length,
  };
}
