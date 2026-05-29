"""Порт локальной векторизации текста."""

from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    """Контракт для получения эмбеддингов списка строк."""

    def get_embeddings(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]: ...
