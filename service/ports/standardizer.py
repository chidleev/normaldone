"""Порт стандартизации значений атрибутов."""

from __future__ import annotations

from typing import Protocol


class StandardizerPort(Protocol):
    """Контракт очистки и унификации атрибутов товара."""

    def process_item(self, attributes: dict[str, str]) -> dict[str, str]: ...
