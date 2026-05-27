"""Обертка над ChromaDB для хранения товарной памяти."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings


class VectorStorage:
    """Хранилище эмбеддингов и атрибутов товаров в локальной ChromaDB."""

    def __init__(self, data_path: str = "./chroma_data") -> None:
        """Инициализирует PersistentClient и коллекцию памяти."""
        self.client = chromadb.PersistentClient(path=data_path, settings=Settings())
        self.collection: Collection = self.client.get_or_create_collection(
            name="nomenclature_memory",
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _item_id(text: str) -> str:
        """Строит стабильный ID на основе хэша названия товара."""
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()

    def save_items(
        self,
        texts: list[str],
        vectors: list[list[float]],
        attributes: list[dict[str, Any]],
    ) -> None:
        """Сохраняет товары в коллекцию: эмбеддинги + атрибуты в metadata."""
        if not (len(texts) == len(vectors) == len(attributes)):
            raise ValueError("texts, vectors и attributes должны быть одной длины")
        if not texts:
            return

        ids: list[str] = [self._item_id(text) for text in texts]
        metadatas: list[dict[str, str]] = [
            {
                "text": text,
                "attributes_json": json.dumps(item_attributes, ensure_ascii=False),
            }
            for text, item_attributes in zip(texts, attributes, strict=True)
        ]

        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=vectors,
            metadatas=metadatas,
        )

    def find_similar(
        self,
        vectors: list[list[float]],
        threshold: float = 0.15,
    ) -> list[dict[str, Any] | None]:
        """
        Ищет похожие товары по эмбеддингам.

        Возвращает список длиной как вход:
        - dict с сохраненными атрибутами, если расстояние < threshold,
        - None, если совпадение не найдено.
        """
        if not vectors:
            return []

        query_result = self.collection.query(
            query_embeddings=vectors,
            n_results=1,
            include=["metadatas", "distances"],
        )

        metadatas: list[list[dict[str, Any]]] = query_result.get("metadatas", [])
        distances: list[list[float]] = query_result.get("distances", [])

        matches: list[dict[str, Any] | None] = []
        for idx, vector_distances in enumerate(distances):
            if not vector_distances:
                matches.append(None)
                continue

            distance: float = vector_distances[0]
            if distance >= threshold:
                matches.append(None)
                continue

            metadata_row: dict[str, Any] = metadatas[idx][0]
            raw_attributes: str = str(metadata_row.get("attributes_json", "{}"))
            matches.append(json.loads(raw_attributes))

        return matches
