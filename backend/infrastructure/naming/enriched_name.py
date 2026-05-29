"""Рендер шаблона обогащённого наименования и дедупликация по эмбеддингам."""

from __future__ import annotations

import re
from typing import Any

from infrastructure.ml.ml_config import read_enriched_dedup_threshold
from infrastructure.naming.merge_separators import (
    join_accumulator_parts,
    normalize_merge_separator,
    resolve_accumulator_separator,
    split_accumulator_parts,
)

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_DEFAULT_MERGE_BEHAVIOR = "priority"
_VALID_MERGE_BEHAVIORS = frozenset({"priority", "accumulative"})


def read_dedup_threshold() -> float:
    """Макс. косинусное расстояние для объединения обогащённых имён."""
    return read_enriched_dedup_threshold()


def _values_lookup(values: dict[str, str]) -> dict[str, str]:
    return {str(key).strip().lower(): str(val).strip() for key, val in values.items()}


def _merge_behavior(attribute_merge: dict[str, str] | None, attr: str) -> str:
    if not attribute_merge:
        return _DEFAULT_MERGE_BEHAVIOR
    behavior = attribute_merge.get(attr) or attribute_merge.get(str(attr).strip().lower())
    if behavior in _VALID_MERGE_BEHAVIORS:
        return str(behavior)
    return _DEFAULT_MERGE_BEHAVIOR


def _explicit_separator(
    attribute_merge_separators: dict[str, str] | None,
    attr: str,
) -> str | None:
    if not attribute_merge_separators:
        return None
    raw = attribute_merge_separators.get(attr) or attribute_merge_separators.get(
        str(attr).strip().lower()
    )
    return normalize_merge_separator(str(raw) if raw is not None else None)


def merge_values_by_behavior(
    target_values: dict[str, str],
    incoming_values: dict[str, str],
    attribute_merge: dict[str, str] | None,
    attr: str,
    attribute_merge_separators: dict[str, str] | None = None,
) -> None:
    """Сливает одно поле values по режиму priority|accumulative."""
    attr_name = str(attr).strip()
    if not attr_name:
        return
    behavior = _merge_behavior(attribute_merge, attr_name)
    incoming = str(incoming_values.get(attr_name, incoming_values.get(attr, "")) or "").strip()
    current = str(target_values.get(attr_name, "") or "").strip()
    if behavior == "accumulative":
        explicit = _explicit_separator(attribute_merge_separators, attr_name)
        join_sep = resolve_accumulator_separator(explicit, current, incoming)
        merged: list[str] = []
        for piece in split_accumulator_parts(current) + split_accumulator_parts(incoming):
            if piece not in merged:
                merged.append(piece)
        target_values[attr_name] = join_accumulator_parts(merged, join_sep)
        return
    if not current and incoming:
        target_values[attr_name] = incoming


def _merge_all_values(
    target_values: dict[str, str],
    members: list[dict[str, Any]],
    attribute_merge: dict[str, str] | None,
    attribute_merge_separators: dict[str, str] | None = None,
) -> None:
    for member in members:
        incoming = {str(k).strip(): str(v).strip() for k, v in dict(member.get("values") or {}).items()}
        for attr in incoming:
            merge_values_by_behavior(
                target_values,
                incoming,
                attribute_merge,
                attr,
                attribute_merge_separators=attribute_merge_separators,
            )


def entry_to_member(entry: dict[str, Any]) -> dict[str, Any]:
    """Одна исходная позиция до/после слияния."""
    item = str(entry.get("item") or "").strip()
    if not item:
        aliases = entry.get("aliases") or []
        if aliases:
            item = str(aliases[0]).strip()
    return {
        "item": item,
        "values": {str(k).strip(): str(v).strip() for k, v in dict(entry.get("values") or {}).items()},
        "source": str(entry.get("source") or "ai"),
    }


def members_from_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry_to_member(entry) for entry in entries if entry_to_member(entry).get("item")]


def render_template(template: str, values: dict[str, str]) -> str:
    """Подставляет {атрибут} из values (регистронезависимо)."""
    lookup = _values_lookup(values)
    if not str(template or "").strip():
        return ""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip().lower()
        return lookup.get(key, "")

    rendered = _PLACEHOLDER_RE.sub(replace, template)
    return re.sub(r"\s+", " ", rendered).strip()


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 1.0
    similarity = dot / (norm_left * norm_right)
    return max(0.0, 1.0 - similarity)


def dedupe_enriched_groups(
    entries: list[dict[str, Any]],
    embeddings: list[list[float]],
    threshold: float | None = None,
    attribute_merge: dict[str, str] | None = None,
    attribute_merge_separators: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Группирует строки с похожими enriched_name.

    entries: [{enriched_name, item, values, source, ...}]
    Возвращает группы: [{enriched_name, aliases, values, source, members}]
    """
    if not entries:
        return []
    if len(entries) != len(embeddings):
        raise ValueError("entries и embeddings должны быть одной длины")

    limit = threshold if threshold is not None else read_dedup_threshold()
    groups: list[dict[str, Any]] = []

    for index, entry in enumerate(entries):
        vector = embeddings[index]
        enriched = str(entry.get("enriched_name") or "").strip()
        alias = str(entry.get("item") or "").strip()
        if not enriched and alias:
            enriched = alias

        placed = False
        for group in groups:
            group_index = int(group["_index"])
            distance = _cosine_distance(vector, embeddings[group_index])
            if distance <= limit:
                if alias and alias not in group["aliases"]:
                    group["aliases"].append(alias)
                group["_members"].append(entry)
                placed = True
                break

        if placed:
            continue

        groups.append(
            {
                "_index": index,
                "enriched_name": enriched,
                "aliases": [alias] if alias else [],
                "values": dict(entry.get("values") or {}),
                "source": str(entry.get("source") or "ai"),
                "_members": [entry],
            }
        )

    for group in groups:
        members = group.pop("_members", [])
        group.pop("_index", None)
        if not group["enriched_name"]:
            group["enriched_name"] = group["aliases"][0] if group["aliases"] else ""
        merged_values = dict(group.get("values") or {})
        _merge_all_values(
            merged_values,
            members,
            attribute_merge,
            attribute_merge_separators=attribute_merge_separators,
        )
        group["values"] = merged_values
        group["members"] = members_from_entries(members)

    return groups


def collapse_cluster_rows(
    entries: list[dict[str, Any]],
    embeddings: list[list[float]],
    threshold: float | None = None,
    attribute_merge: dict[str, str] | None = None,
    attribute_merge_separators: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Схлопывает нормализованные строки кластера в уникальные обогащённые имена."""
    groups = dedupe_enriched_groups(
        entries,
        embeddings,
        threshold=threshold,
        attribute_merge=attribute_merge,
        attribute_merge_separators=attribute_merge_separators,
    )
    collapsed: list[dict[str, Any]] = []
    for group in groups:
        aliases = [str(name).strip() for name in group.get("aliases") or [] if str(name).strip()]
        enriched = str(group.get("enriched_name") or "").strip() or (aliases[0] if aliases else "")
        members = group.get("members") or members_from_entries(group.get("_members") or [])
        if not members and aliases:
            members = [
                {
                    "item": alias,
                    "values": dict(group.get("values") or {}),
                    "source": str(group.get("source") or "ai"),
                }
                for alias in aliases
            ]
        collapsed.append(
            {
                "enriched_name": enriched,
                "aliases": aliases or ([enriched] if enriched else []),
                "item": aliases[0] if aliases else enriched,
                "values": dict(group.get("values") or {}),
                "source": str(group.get("source") or "ai"),
                "members": members,
            }
        )
    return collapsed
