"""Разделители для аккумулятивного слияния атрибутов."""

from __future__ import annotations

import re

_SEPARATOR_CANDIDATES: tuple[tuple[str, str], ...] = (
    (";", "; "),
    (",", ", "),
    ("|", " | "),
)
_SPLIT_RE = re.compile(r"[;,|]")


def normalize_merge_separator(value: str | None) -> str | None:
    """Нормализует ввод пользователя. Пусто → None (авто)."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in {";", "; "}:
        return "; "
    if raw in {",", ", "}:
        return ", "
    if raw in {"|", " | "}:
        return " | "
    return raw


def split_accumulator_parts(value: str) -> list[str]:
    parts: list[str] = []
    for chunk in _SPLIT_RE.split(str(value or "")):
        piece = chunk.strip()
        if piece and piece not in parts:
            parts.append(piece)
    return parts


def detect_accumulator_separator(*values: str) -> str:
    scores = {join: 0 for _, join in _SEPARATOR_CANDIDATES}
    for value in values:
        text = str(value or "")
        for char, join in _SEPARATOR_CANDIDATES:
            scores[join] += text.count(char)
    best_join = "; "
    best_score = -1
    for join, score in scores.items():
        if score > best_score:
            best_score = score
            best_join = join
    return best_join


def resolve_accumulator_separator(
    explicit: str | None,
    *values: str,
) -> str:
    normalized = normalize_merge_separator(explicit)
    if normalized:
        return normalized
    return detect_accumulator_separator(*values)


def join_accumulator_parts(parts: list[str], separator: str) -> str:
    return separator.join(parts)


def merge_accumulator_values(
    current: str,
    incoming: str,
    explicit_separator: str | None,
) -> str:
    join_sep = resolve_accumulator_separator(explicit_separator, current, incoming)
    merged: list[str] = []
    for piece in split_accumulator_parts(current) + split_accumulator_parts(incoming):
        if piece not in merged:
            merged.append(piece)
    return join_accumulator_parts(merged, join_sep)
