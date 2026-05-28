"""Порт векторной памяти номенклатуры."""

from __future__ import annotations

from typing import Any, Protocol


class VectorMemoryPort(Protocol):
    """Контракт для сохранения и поиска по эмбеддингам."""

    def save_items(
        self,
        texts: list[str],
        vectors: list[list[float]],
        attributes: list[dict[str, Any]],
    ) -> None: ...

    def find_similar(
        self,
        vectors: list[list[float]],
        threshold: float = 0.15,
    ) -> list[dict[str, Any] | None]: ...
