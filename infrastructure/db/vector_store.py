"""Обертка над Qdrant для хранения товарной памяти."""

from __future__ import annotations

import hashlib
import os
from typing import Any

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

        vector_size = len(vectors[0])
        if not self.client.collection_exists(self.collection_name):
            self.client.recreate_collection(
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

        Возвращает список длиной как вход:
        - dict с сохраненными атрибутами, если расстояние < threshold,
        - None, если совпадение не найдено.
        """
        if not vectors:
            return []
        if not self.client.collection_exists(self.collection_name):
            return [None for _ in vectors]

        matches: list[dict[str, Any] | None] = []
        for vector in vectors:
            result = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=1,
                with_payload=True,
            )
            if not result.points:
                matches.append(None)
                continue

            score = float(result.points[0].score or 0.0)
            distance = 1.0 - score
            if distance >= threshold:
                matches.append(None)
                continue
            payload = result.points[0].payload or {}
            raw_attributes = payload.get("attributes")
            if isinstance(raw_attributes, dict):
                matches.append(raw_attributes)
            else:
                matches.append(None)

        return matches
