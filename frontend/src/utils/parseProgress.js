/** Извлекает процент из строки вида «кластер 2/5» или «2/5». */
export function parseProgressPercent(progressText) {
  const text = String(progressText ?? "");
  const match = text.match(/(\d+)\s*\/\s*(\d+)/);
  if (!match) return null;
  const current = Number(match[1]);
  const total = Number(match[2]);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
  return Math.min(100, Math.max(0, Math.round((current / total) * 100)));
}
