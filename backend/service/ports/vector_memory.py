"""Порт векторной памяти номенклатуры."""

from __future__ import annotations

from typing import Any, Protocol


class VectorMemoryPort(Protocol):
    """Контракт для сохранения и поиска по эмбеддингам."""

    def save_items(
        self,
        texts: list[str],
        local_vectors: list[list[float]],
        gemini_vectors: list[list[float]] | None,
        attributes: list[dict[str, Any]],
        cluster_names: list[str] | None = None,
        original_items_list: list[list[str]] | None = None,
        original_item_values_list: list[dict[str, dict[str, Any]]] | None = None,
        attribute_merge_list: list[dict[str, str]] | None = None,
        attribute_merge_separators_list: list[dict[str, str]] | None = None,
    ) -> None: ...

    def find_similar(
        self,
        local_vectors: list[list[float]],
        gemini_vectors: list[list[float]] | None = None,
        item_texts: list[str] | None = None,
        threshold: float = 0.15,
    ) -> list[dict[str, Any] | None]: ...

    def list_memory_clusters(self) -> list[str]: ...

    def load_cluster_items(self, cluster_name: str) -> list[dict[str, Any]]: ...

    def get_vector_size(self) -> int | None: ...

    def delete_cluster_items(self, cluster_name: str) -> int: ...

    def delete_item_by_text(self, text: str) -> int: ...

    def search_local(
        self,
        vector: list[float],
        limit: int = 20,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]: ...
