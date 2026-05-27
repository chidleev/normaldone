"""Стандартизация единиц измерения и синонимов в атрибутах."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Pattern


class DataStandardizer:
    """Приводит значения атрибутов к эталонным единицам и формулировкам."""

    def __init__(self, dictionaries_path: str = "config/dictionaries.json") -> None:
        """Загружает словари синонимов в память при старте сервера."""
        path = Path(dictionaries_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.rules: dict[str, list[str]] = {
            str(canonical): [str(synonym) for synonym in synonyms]
            for canonical, synonyms in payload.items()
        }
        self._compiled_patterns: list[tuple[str, Pattern[str]]] = self._compile_patterns()

    def _compile_patterns(self) -> list[tuple[str, Pattern[str]]]:
        """Компилирует regex для безопасной замены синонимов без учета регистра."""
        compiled: list[tuple[str, Pattern[str]]] = []
        for canonical, synonyms in self.rules.items():
            all_variants = [canonical, *synonyms]
            escaped_variants = [re.escape(variant) for variant in all_variants]
            pattern = re.compile(
                rf"(?<!\w)(?:{'|'.join(escaped_variants)})(?!\w)",
                flags=re.IGNORECASE,
            )
            compiled.append((canonical, pattern))
        return compiled

    def _normalize_value(self, value: str) -> str:
        """Нормализует строку значения и убирает лишние пробелы."""
        normalized = value
        for canonical, pattern in self._compiled_patterns:
            normalized = pattern.sub(canonical, normalized)
            normalized = re.sub(
                rf"(\d+(?:[.,]\d+)?)\s*{re.escape(canonical)}\b",
                rf"\1 {canonical}",
                normalized,
                flags=re.IGNORECASE,
            )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def process_item(self, attributes: dict[str, str]) -> dict[str, str]:
        """Возвращает копию словаря атрибутов с унифицированными значениями."""
        processed: dict[str, str] = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                processed[key] = self._normalize_value(value)
            else:
                processed[key] = str(value)
        return processed
