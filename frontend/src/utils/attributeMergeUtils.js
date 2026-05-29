/** Кандидаты для автоопределения разделителя (символ → строка склейки). */
const SEPARATOR_CANDIDATES = [
  { char: ";", join: "; " },
  { char: ",", join: ", " },
  { char: "|", join: " | " },
];

const SPLIT_RE = /[;,|]/;

/** Нормализует ввод пользователя в строку склейки. Пусто → null (авто). */
export function normalizeMergeSeparator(input) {
  const raw = String(input ?? "").trim();
  if (!raw) return null;
  if (raw === ";" || raw === "; ") return "; ";
  if (raw === "," || raw === ", ") return ", ";
  if (raw === "|" || raw === " | ") return " | ";
  return raw;
}

/** Разбивает значение на части по типичным разделителям. */
export function splitAccumulatorParts(value) {
  const parts = [];
  for (const chunk of String(value || "").split(SPLIT_RE)) {
    const piece = chunk.trim();
    if (piece && !parts.includes(piece)) parts.push(piece);
  }
  return parts;
}

/** Определяет разделитель по содержимому значений. */
export function detectAccumulatorSeparator(...values) {
  const scores = Object.fromEntries(SEPARATOR_CANDIDATES.map(({ join }) => [join, 0]));
  for (const value of values) {
    const text = String(value || "");
    for (const { char, join } of SEPARATOR_CANDIDATES) {
      const parts = text.split(char);
      if (parts.length > 1) scores[join] += parts.length - 1;
    }
  }
  let best = "; ";
  let bestScore = -1;
  for (const [join, score] of Object.entries(scores)) {
    if (score > bestScore) {
      bestScore = score;
      best = join;
    }
  }
  return best;
}

export function resolveAccumulatorSeparator(explicitSeparator, ...values) {
  const normalized = normalizeMergeSeparator(explicitSeparator);
  if (normalized) return normalized;
  return detectAccumulatorSeparator(...values);
}

export function mergeAccumulatorValues(current, incoming, explicitSeparator) {
  const joinSep = resolveAccumulatorSeparator(explicitSeparator, current, incoming);
  const merged = [];
  for (const piece of [...splitAccumulatorParts(current), ...splitAccumulatorParts(incoming)]) {
    if (!merged.includes(piece)) merged.push(piece);
  }
  return { value: merged.join(joinSep), separator: joinSep };
}

export function mergeBehavior(attributeMerge, attr) {
  const name = String(attr || "").trim();
  if (!name) return "priority";
  const map = attributeMerge || {};
  const behavior = map[name] || map[name.toLowerCase()];
  return behavior === "accumulative" ? "accumulative" : "priority";
}

export function mergeSeparatorForAttr(attributeMergeSeparators, attr) {
  const name = String(attr || "").trim();
  if (!name) return null;
  const map = attributeMergeSeparators || {};
  return normalizeMergeSeparator(map[name] ?? map[name.toLowerCase()]);
}
