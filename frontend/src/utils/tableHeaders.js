/** Порядок колонок: источник → (опционально новая) → остальные атрибуты. */
export function orderHeadersWithSourceFirst(headers, sourceColumn, newColumnName = null) {
  const list = Array.isArray(headers) ? [...headers] : [];
  if (!list.length) return list;

  const source =
    sourceColumn && list.includes(sourceColumn) ? sourceColumn : list[0];
  const attributes = list.filter((header) => header !== source);

  if (newColumnName) {
    const trimmed = String(newColumnName).trim();
    if (trimmed && attributes.includes(trimmed)) {
      const rest = attributes.filter((header) => header !== trimmed);
      return [source, trimmed, ...rest];
    }
  }

  return [source, ...attributes];
}
