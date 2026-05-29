import {
  mergeAccumulatorValues,
  mergeBehavior,
  mergeSeparatorForAttr,
} from "./attributeMergeUtils";

const PLACEHOLDER_RE = /\{([^{}]+)\}/g;

function valuesLookup(values) {
  const lookup = {};
  for (const [key, val] of Object.entries(values || {})) {
    lookup[String(key).trim().toLowerCase()] = String(val ?? "").trim();
  }
  return lookup;
}

export function renderEnrichedName(template, values) {
  const lookup = valuesLookup(values);
  const tpl = String(template || "").trim();
  if (!tpl) return "";

  const rendered = tpl.replace(PLACEHOLDER_RE, (_match, key) => {
    return lookup[String(key).trim().toLowerCase()] || "";
  });
  return rendered.replace(/\s+/g, " ").trim();
}

export function mergeAttributeValues(
  targetValues,
  incomingValues,
  attributeMerge,
  attr,
  attributeMergeSeparators,
) {
  const attrName = String(attr || "").trim();
  if (!attrName) return;
  const incoming = String(incomingValues?.[attrName] ?? incomingValues?.[attr] ?? "").trim();
  const current = String(targetValues?.[attrName] ?? "").trim();
  if (mergeBehavior(attributeMerge, attrName) === "accumulative") {
    const explicit = mergeSeparatorForAttr(attributeMergeSeparators, attrName);
    const { value } = mergeAccumulatorValues(current, incoming, explicit);
    targetValues[attrName] = value;
    return;
  }
  if (!current && incoming) {
    targetValues[attrName] = incoming;
  }
}

export function ensureRowMembers(row) {
  if (Array.isArray(row.members) && row.members.length) return row.members;
  const aliases = (row.aliases || [])
    .map((name) => String(name || "").trim())
    .filter(Boolean);
  const fallback = String(row.item || "").trim();
  const items = aliases.length ? aliases : fallback ? [fallback] : [];
  row.members = items.map((item) => ({
    item,
    values: { ...(row.values || {}) },
    source: row.source === "memory" ? "memory" : "ai",
  }));
  return row.members;
}

export function mergeRowsInto(targetRow, sourceRow, attributeMerge, attributeMergeSeparators) {
  ensureRowMembers(targetRow);
  ensureRowMembers(sourceRow);

  const aliasSet = new Set(
    (targetRow.aliases || []).map((name) => String(name || "").trim()).filter(Boolean),
  );
  for (const alias of sourceRow.aliases || []) {
    const name = String(alias || "").trim();
    if (name) aliasSet.add(name);
  }
  targetRow.aliases = [...aliasSet];

  for (const member of sourceRow.members || []) {
    targetRow.members.push({
      item: String(member.item || "").trim(),
      values: { ...(member.values || {}) },
      source: member.source === "memory" ? "memory" : "ai",
    });
    for (const attr of Object.keys(member.values || {})) {
      mergeAttributeValues(
        targetRow.values,
        member.values,
        attributeMerge,
        attr,
        attributeMergeSeparators,
      );
    }
  }

  recalculateMergedValues(targetRow, attributeMerge, attributeMergeSeparators);

  const item = String(targetRow.item || "").trim();
  if (!item && targetRow.aliases?.length) {
    targetRow.item = targetRow.aliases[0];
  }
}

export function splitAliasFromRow(
  row,
  alias,
  template,
  attributeMerge,
  attributeMergeSeparators,
) {
  const name = String(alias || "").trim();
  if (!name) return null;
  ensureRowMembers(row);

  const memberIndex = (row.members || []).findIndex(
    (entry) => String(entry.item || "").trim() === name,
  );
  const member =
    memberIndex >= 0
      ? row.members[memberIndex]
      : row.members.length === 1
        ? row.members[0]
        : null;

  const memberValues = { ...(member?.values || row.values || {}) };
  const memberSource = member?.source === "memory" ? "memory" : row.source === "memory" ? "memory" : "ai";

  row.aliases = (row.aliases || []).filter((entry) => String(entry).trim() !== name);
  if (memberIndex >= 0) {
    row.members.splice(memberIndex, 1);
  } else if (member && row.members.length === 1) {
    row.members = [];
  }

  const newRow = {
    item: name,
    aliases: [name],
    values: { ...memberValues },
    source: memberSource,
    members: [{ item: name, values: { ...memberValues }, source: memberSource }],
    enriched_name: renderEnrichedName(template, memberValues) || name,
  };

  if (!row.aliases.length) {
    const fallback = String(row.item || row.enriched_name || "").trim();
    row.aliases = fallback ? [fallback] : [];
  }
  if (!row.members.length && row.aliases.length) {
    row.members = row.aliases.map((entry) => ({
      item: entry,
      values: { ...(row.values || {}) },
      source: row.source === "memory" ? "memory" : "ai",
    }));
  }

  recalculateMergedValues(row, attributeMerge, attributeMergeSeparators);

  return newRow;
}

function recalculateMergedValues(row, attributeMerge, attributeMergeSeparators) {
  ensureRowMembers(row);
  const attrs = new Set(Object.keys(row.values || {}));
  for (const member of row.members || []) {
    for (const attr of Object.keys(member.values || {})) {
      attrs.add(attr);
    }
  }

  for (const attr of attrs) {
    const behavior = mergeBehavior(attributeMerge, attr);
    const memberValues = [];
    for (const member of row.members || []) {
      const incoming = String(member.values?.[attr] ?? "").trim();
      if (incoming && !memberValues.includes(incoming)) {
        memberValues.push(incoming);
      }
    }

    if (behavior === "accumulative") {
      const explicit = mergeSeparatorForAttr(attributeMergeSeparators, attr);
      let merged = "";
      for (const incoming of memberValues) {
        merged = mergeAccumulatorValues(merged, incoming, explicit).value;
      }
      row.values[attr] = merged;
      continue;
    }

    if (!memberValues.length) {
      row.values[attr] = "";
      continue;
    }

    if (memberValues.length === 1) {
      row.values[attr] = memberValues[0];
      continue;
    }

    const current = String(row.values?.[attr] ?? "").trim();
    row.values[attr] = memberValues.includes(current) ? current : memberValues[0];
  }
}

export function regenerateRowEnriched(row, template) {
  const enriched = renderEnrichedName(template, row.values || {});
  if (enriched) {
    row.enriched_name = enriched;
  }
  return row.enriched_name;
}

export function regenerateAllRowsEnriched(rows, template) {
  const tpl = String(template || "").trim();
  if (!tpl) return 0;
  let updated = 0;
  for (const row of rows || []) {
    ensureRowMembers(row);
    if (regenerateRowEnriched(row, tpl)) updated += 1;
  }
  return updated;
}

export function recalculateRowMergedValues(
  row,
  attributeMerge,
  attributeMergeSeparators,
) {
  recalculateMergedValues(row, attributeMerge, attributeMergeSeparators);
}
