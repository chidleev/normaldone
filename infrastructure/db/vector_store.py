"""Обертка над Qdrant для хранения товарной памяти."""

from __future__ import annotations

import os
import uuid
from typing import Any

# Namespace для детерминированных UUID точек Qdrant
_POINT_NAMESPACE = uuid.UUID("a3f2c8e1-5b4d-4e9a-9c7f-1d2e3f4a5b6c")

from qdrant_client import QdrantClient
from qdrant_client.http import models


class VectorStorage:
    """Хранилище эмбеддингов и атрибутов товаров в Qdrant."""

    def __init__(self, collection_name: str = "nomenclature_memory") -> None:
        """Инициализирует клиент Qdrant и создает коллекцию при необходимости."""
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_path = os.getenv("QDRANT_PATH", "./qdrant_data")
        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url)
        else:
            self.client = QdrantClient(path=qdrant_path)
        self.collection_name = collection_name

    @staticmethod
    def _item_id(text: str) -> str:
        """Стабильный UUID v5 по нормализованному названию (требование Qdrant)."""
        return str(uuid.uuid5(_POINT_NAMESPACE, text.strip().lower()))

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

        vector_size = len(vectors[0])
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        points: list[models.PointStruct] = []
        for text, vector, item_attributes in zip(texts, vectors, attributes, strict=True):
            points.append(
                models.PointStruct(
                    id=self._item_id(text),
                    vector=vector,
                    payload={"text": text, "attributes": item_attributes},
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def find_similar(
        self,
        vectors: list[list[float]],
        threshold: float = 0.15,
    ) -> list[dict[str, Any] | None]:
        """
        Ищет похожие товары по эмбеддингам.

        threshold — макс. косинусное расстояние (0.15 ≈ similarity >= 0.85).

        Возвращает список длиной как вход:
        - dict с атрибутами при достаточном сходстве,
        - None, если совпадение не найдено.
        """
        if not vectors:
            return []
        if not self.client.collection_exists(self.collection_name):
            return [None for _ in vectors]

        min_similarity = 1.0 - threshold
        matches: list[dict[str, Any] | None] = []
        for vector in vectors:
            result = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=1,
                score_threshold=min_similarity,
                with_payload=True,
            )
            if not result.points:
                matches.append(None)
                continue

            payload = result.points[0].payload or {}
            raw_attributes = payload.get("attributes")
            if isinstance(raw_attributes, dict) and raw_attributes:
                matches.append(raw_attributes)
            else:
                matches.append(None)

        return matches

    def get_points_count(self) -> int:
        """Возвращает число точек в коллекции (0, если коллекции нет)."""
        if not self.client.collection_exists(self.collection_name):
            return 0
        info = self.client.get_collection(self.collection_name)
        return int(info.points_count or 0)

    def clear_collection(self) -> bool:
        """
        Удаляет коллекцию векторной памяти.

        Returns:
            True, если коллекция существовала и была удалена.
        """
        if not self.client.collection_exists(self.collection_name):
            return False
        self.client.delete_collection(self.collection_name)
        return True
