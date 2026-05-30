"""Обертка над Qdrant для хранения товарной памяти."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

# Namespace для детерминированных UUID точек Qdrant
_POINT_NAMESPACE = uuid.UUID("a3f2c8e1-5b4d-4e9a-9c7f-1d2e3f4a5b6c")

from qdrant_client import QdrantClient
from qdrant_client.http import models

_LEGACY_CLUSTER_NAME = "Память"
_LOCAL_VECTOR_NAME = "local"
_GEMINI_VECTOR_NAME = "gemini"
_DEFAULT_GEMINI_VECTOR_SIZE = 3072

logger = logging.getLogger(__name__)


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

    @staticmethod
    def _normalize_lookup_text(text: str) -> str:
        """Нормализация текста для устойчивого поиска по original_items."""
        return " ".join(str(text).strip().lower().split())

    @staticmethod
    def _parse_match_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
        """Преобразует payload точки в структуру совпадения для clusterize."""
        raw_attributes = payload.get("attributes")
        if not isinstance(raw_attributes, dict) or not raw_attributes:
            return None
        cluster_name = str(payload.get("cluster_name") or "").strip() or _LEGACY_CLUSTER_NAME
        text = str(payload.get("text") or "").strip()
        raw_originals = payload.get("original_items")
        originals: list[str] = []
        if isinstance(raw_originals, list):
            originals = [str(name).strip() for name in raw_originals if str(name).strip()]
        raw_original_item_values = payload.get("original_item_values")
        original_item_values: dict[str, dict[str, Any]] = {}
        if isinstance(raw_original_item_values, dict):
            for alias, values in raw_original_item_values.items():
                alias_name = str(alias).strip()
                if not alias_name or not isinstance(values, dict):
                    continue
                original_item_values[alias_name] = {
                    str(key).strip(): value
                    for key, value in values.items()
                    if str(key).strip()
                }
        raw_attribute_merge = payload.get("attribute_merge")
        attribute_merge: dict[str, str] = {}
        if isinstance(raw_attribute_merge, dict):
            attribute_merge = {
                str(key).strip(): str(value).strip()
                for key, value in raw_attribute_merge.items()
                if str(key).strip() and str(value).strip()
            }
        raw_attribute_merge_separators = payload.get("attribute_merge_separators")
        attribute_merge_separators: dict[str, str] = {}
        if isinstance(raw_attribute_merge_separators, dict):
            attribute_merge_separators = {
                str(key).strip(): str(value).strip()
                for key, value in raw_attribute_merge_separators.items()
                if str(key).strip() and str(value).strip()
            }
        return {
            "text": text,
            "cluster_name": cluster_name,
            "attributes": {str(k): v for k, v in raw_attributes.items()},
            "original_items": originals,
            "original_item_values": original_item_values,
            "attribute_merge": attribute_merge,
            "attribute_merge_separators": attribute_merge_separators,
        }

    @staticmethod
    def _parse_payload_loose(payload: dict[str, Any]) -> dict[str, Any]:
        """Преобразует payload без требования непустых attributes."""
        cluster_name = str(payload.get("cluster_name") or "").strip() or _LEGACY_CLUSTER_NAME
        text = str(payload.get("text") or "").strip()
        raw_attributes = payload.get("attributes")
        attributes: dict[str, Any] = {}
        if isinstance(raw_attributes, dict):
            attributes = {str(k): v for k, v in raw_attributes.items()}
        raw_originals = payload.get("original_items")
        originals: list[str] = []
        if isinstance(raw_originals, list):
            originals = [str(name).strip() for name in raw_originals if str(name).strip()]
        raw_original_item_values = payload.get("original_item_values")
        original_item_values: dict[str, dict[str, Any]] = {}
        if isinstance(raw_original_item_values, dict):
            for alias, values in raw_original_item_values.items():
                alias_name = str(alias).strip()
                if not alias_name or not isinstance(values, dict):
                    continue
                original_item_values[alias_name] = {
                    str(key).strip(): value
                    for key, value in values.items()
                    if str(key).strip()
                }
        raw_attribute_merge = payload.get("attribute_merge")
        attribute_merge: dict[str, str] = {}
        if isinstance(raw_attribute_merge, dict):
            attribute_merge = {
                str(key).strip(): str(value).strip()
                for key, value in raw_attribute_merge.items()
                if str(key).strip() and str(value).strip()
            }
        raw_attribute_merge_separators = payload.get("attribute_merge_separators")
        attribute_merge_separators: dict[str, str] = {}
        if isinstance(raw_attribute_merge_separators, dict):
            attribute_merge_separators = {
                str(key).strip(): str(value).strip()
                for key, value in raw_attribute_merge_separators.items()
                if str(key).strip() and str(value).strip()
            }
        return {
            "text": text,
            "cluster_name": cluster_name,
            "attributes": attributes,
            "original_items": originals,
            "original_item_values": original_item_values,
            "attribute_merge": attribute_merge,
            "attribute_merge_separators": attribute_merge_separators,
        }

    def _build_original_items_index(self) -> dict[str, dict[str, Any]]:
        """Строит индекс normalized original_items -> parsed payload."""
        index: dict[str, dict[str, Any]] = {}
        offset: Any = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                if not isinstance(payload, dict):
                    continue
                parsed = self._parse_match_payload(payload)
                if parsed is None:
                    continue
                original_items = list(parsed.get("original_items") or [])
                text_value = str(parsed.get("text") or "").strip()
                if text_value:
                    original_items.append(text_value)
                for original in original_items:
                    key = self._normalize_lookup_text(original)
                    if key and key not in index:
                        index[key] = parsed
            if offset is None:
                break
        return index

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
    ) -> None:
        """Сохраняет товары: эмбеддинги + атрибуты + имя кластера в payload."""
        if not (len(texts) == len(local_vectors) == len(attributes)):
            raise ValueError("texts, local_vectors и attributes должны быть одной длины")
        if gemini_vectors is not None and len(gemini_vectors) != len(texts):
            raise ValueError("gemini_vectors должны быть той же длины, что texts")
        if cluster_names is not None and len(cluster_names) != len(texts):
            raise ValueError("cluster_names должны быть той же длины, что texts")
        if original_items_list is not None and len(original_items_list) != len(texts):
            raise ValueError("original_items_list должны быть той же длины, что texts")
        if original_item_values_list is not None and len(original_item_values_list) != len(texts):
            raise ValueError("original_item_values_list должны быть той же длины, что texts")
        if attribute_merge_list is not None and len(attribute_merge_list) != len(texts):
            raise ValueError("attribute_merge_list должны быть той же длины, что texts")
        if (
            attribute_merge_separators_list is not None
            and len(attribute_merge_separators_list) != len(texts)
        ):
            raise ValueError("attribute_merge_separators_list должны быть той же длины, что texts")
        if not texts:
            return

        local_vector_size = len(local_vectors[0])
        gemini_vector_size = None
        if gemini_vectors:
            gemini_vector_size = len(gemini_vectors[0])
        else:
            raw_size = os.getenv("MEMORY_GEMINI_VECTOR_SIZE") or os.getenv("GEMINI_VECTOR_SIZE")
            if raw_size and str(raw_size).strip():
                try:
                    gemini_vector_size = int(str(raw_size).strip())
                except ValueError:
                    logger.warning(
                        "Invalid MEMORY_GEMINI_VECTOR_SIZE=%s, fallback to default %s",
                        raw_size,
                        _DEFAULT_GEMINI_VECTOR_SIZE,
                    )
        gemini_vector_size = gemini_vector_size or _DEFAULT_GEMINI_VECTOR_SIZE
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    _LOCAL_VECTOR_NAME: models.VectorParams(
                        size=local_vector_size,
                        distance=models.Distance.COSINE,
                    ),
                    _GEMINI_VECTOR_NAME: models.VectorParams(
                        size=gemini_vector_size,
                        distance=models.Distance.COSINE,
                    ),
                },
            )

        points: list[models.PointStruct] = []
        for index, (text, local_vector, item_attributes) in enumerate(
            zip(texts, local_vectors, attributes, strict=True)
        ):
            cluster_name = (
                str(cluster_names[index]).strip()
                if cluster_names is not None
                else _LEGACY_CLUSTER_NAME
            )
            originals: list[str] = []
            if original_items_list is not None:
                originals = [
                    str(name).strip()
                    for name in original_items_list[index]
                    if str(name).strip()
                ]
            original_item_values_payload: dict[str, dict[str, Any]] = {}
            if original_item_values_list is not None:
                for alias, values in dict(original_item_values_list[index]).items():
                    alias_name = str(alias).strip()
                    if not alias_name or not isinstance(values, dict):
                        continue
                    original_item_values_payload[alias_name] = {
                        str(key).strip(): value
                        for key, value in values.items()
                        if str(key).strip()
                    }
            attribute_merge_payload: dict[str, str] = {}
            if attribute_merge_list is not None:
                attribute_merge_payload = {
                    str(key).strip(): str(value).strip()
                    for key, value in dict(attribute_merge_list[index]).items()
                    if str(key).strip() and str(value).strip()
                }
            attribute_merge_separators_payload: dict[str, str] = {}
            if attribute_merge_separators_list is not None:
                attribute_merge_separators_payload = {
                    str(key).strip(): str(value).strip()
                    for key, value in dict(attribute_merge_separators_list[index]).items()
                    if str(key).strip() and str(value).strip()
                }
            points.append(
                models.PointStruct(
                    id=self._item_id(text),
                    vector={
                        _LOCAL_VECTOR_NAME: local_vector,
                        **(
                            {_GEMINI_VECTOR_NAME: gemini_vectors[index]}
                            if gemini_vectors is not None and gemini_vectors[index]
                            else {}
                        ),
                    },
                    payload={
                        "text": text,
                        "attributes": item_attributes,
                        "cluster_name": cluster_name or _LEGACY_CLUSTER_NAME,
                        "original_items": originals,
                        "original_item_values": original_item_values_payload,
                        "attribute_merge": attribute_merge_payload,
                        "attribute_merge_separators": attribute_merge_separators_payload,
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def find_similar(
        self,
        local_vectors: list[list[float]],
        gemini_vectors: list[list[float]] | None = None,
        item_texts: list[str] | None = None,
        threshold: float = 0.15,
    ) -> list[dict[str, Any] | None]:
        """
        Ищет похожие товары по эмбеддингам.

        threshold — макс. косинусное расстояние (0.15 ≈ similarity >= 0.85).

        Возвращает список длиной как вход:
        - dict {text, cluster_name, attributes} при достаточном сходстве,
        - None, если совпадение не найдено.
        """
        if not local_vectors:
            return []
        if not self.client.collection_exists(self.collection_name):
            return [None for _ in local_vectors]
        if gemini_vectors is not None and len(gemini_vectors) != len(local_vectors):
            raise ValueError("gemini_vectors должны быть той же длины, что local_vectors")
        if item_texts is not None and len(item_texts) != len(local_vectors):
            raise ValueError("item_texts должны быть той же длины, что local_vectors")

        min_similarity = 1.0 - threshold
        original_items_index = self._build_original_items_index() if item_texts else {}
        matches: list[dict[str, Any] | None] = []
        for index, local_vector in enumerate(local_vectors):
            vector_match: dict[str, Any] | None = None
            gemini_vector = gemini_vectors[index] if gemini_vectors is not None else None
            if gemini_vector:
                try:
                    result = self.client.query_points(
                        collection_name=self.collection_name,
                        query=gemini_vector,
                        using=_GEMINI_VECTOR_NAME,
                        limit=1,
                        score_threshold=min_similarity,
                        with_payload=True,
                    )
                    if result.points:
                        payload = result.points[0].payload or {}
                        if isinstance(payload, dict):
                            vector_match = self._parse_match_payload(payload)
                            if vector_match is not None:
                                vector_match["matched_by"] = _GEMINI_VECTOR_NAME
                except Exception:
                    logger.warning("Gemini memory lookup failed, fallback to local", exc_info=True)
            if vector_match is None:
                try:
                    result = self.client.query_points(
                        collection_name=self.collection_name,
                        query=local_vector,
                        using=_LOCAL_VECTOR_NAME,
                        limit=1,
                        score_threshold=min_similarity,
                        with_payload=True,
                    )
                except Exception:
                    # Legacy fallback for old single-vector collections.
                    result = self.client.query_points(
                        collection_name=self.collection_name,
                        query=local_vector,
                        limit=1,
                        score_threshold=min_similarity,
                        with_payload=True,
                    )
                if result.points:
                    payload = result.points[0].payload or {}
                    if isinstance(payload, dict):
                        vector_match = self._parse_match_payload(payload)
                        if vector_match is not None:
                            vector_match["matched_by"] = _LOCAL_VECTOR_NAME

            payload_match: dict[str, Any] | None = None
            if item_texts:
                lookup_key = self._normalize_lookup_text(item_texts[index])
                payload_match = original_items_index.get(lookup_key)
                if payload_match is not None:
                    payload_match = dict(payload_match)
                    payload_match["matched_by"] = "payload"

            matches.append(payload_match or vector_match)

        return matches

    def get_points_count(self) -> int:
        """Возвращает число точек в коллекции (0, если коллекции нет)."""
        if not self.client.collection_exists(self.collection_name):
            return 0
        info = self.client.get_collection(self.collection_name)
        return int(info.points_count or 0)

    def get_vector_size(self) -> int | None:
        """Возвращает размер local-вектора коллекции или None, если коллекции нет."""
        if not self.client.collection_exists(self.collection_name):
            return None
        info = self.client.get_collection(self.collection_name)
        vectors = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(vectors, "vectors", None)
        if isinstance(vectors, models.VectorParams):
            return int(vectors.size)
        if isinstance(vectors, dict):
            local_vector = vectors.get(_LOCAL_VECTOR_NAME)
            if isinstance(local_vector, models.VectorParams):
                return int(local_vector.size)
            first = next(iter(vectors.values()), None)
            if isinstance(first, models.VectorParams):
                return int(first.size)
        return None

    def list_memory_clusters(self) -> list[str]:
        """Возвращает список имен кластеров, сохраненных в памяти."""
        if not self.client.collection_exists(self.collection_name):
            return []
        clusters: set[str] = set()
        offset: Any = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                if not isinstance(payload, dict):
                    continue
                cluster_name = str(payload.get("cluster_name") or "").strip() or _LEGACY_CLUSTER_NAME
                clusters.add(cluster_name)
            if offset is None:
                break
        return sorted(clusters)

    def load_cluster_items(self, cluster_name: str) -> list[dict[str, Any]]:
        """Возвращает все точки памяти по имени кластера."""
        name = str(cluster_name).strip()
        if not name:
            return []
        if not self.client.collection_exists(self.collection_name):
            return []

        items: list[dict[str, Any]] = []
        offset: Any = None
        query_filter = models.Filter(
            must=[models.FieldCondition(key="cluster_name", match=models.MatchValue(value=name))]
        )
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
                scroll_filter=query_filter,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                if isinstance(payload, dict):
                    items.append(self._parse_payload_loose(payload))
            if offset is None:
                break

        if name == _LEGACY_CLUSTER_NAME:
            offset = None
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    offset=offset,
                    limit=256,
                    with_payload=True,
                    with_vectors=False,
                )
                if not points:
                    break
                for point in points:
                    payload = point.payload or {}
                    if not isinstance(payload, dict):
                        continue
                    cluster_raw = str(payload.get("cluster_name") or "").strip()
                    if cluster_raw:
                        continue
                    items.append(self._parse_payload_loose(payload))
                if offset is None:
                    break

        return items

    def _point_ids_for_cluster_name(self, cluster_name: str) -> list[Any]:
        """Возвращает id точек, относящихся к cluster_name."""
        name = str(cluster_name).strip()
        if not name:
            return []
        ids: list[Any] = []
        offset: Any = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                if not isinstance(payload, dict):
                    continue
                parsed = self._parse_payload_loose(payload)
                if str(parsed.get("cluster_name") or "").strip() == name:
                    ids.append(point.id)
            if offset is None:
                break
        return ids

    def _point_ids_for_text(self, text: str) -> list[Any]:
        """Возвращает id точек по exact text payload."""
        needle = str(text).strip()
        if not needle:
            return []
        ids: list[Any] = []
        offset: Any = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                if not isinstance(payload, dict):
                    continue
                parsed = self._parse_payload_loose(payload)
                if str(parsed.get("text") or "").strip() == needle:
                    ids.append(point.id)
            if offset is None:
                break
        return ids

    def delete_cluster_items(self, cluster_name: str) -> int:
        """Удаляет все точки конкретного кластера памяти."""
        if not self.client.collection_exists(self.collection_name):
            return 0
        ids = self._point_ids_for_cluster_name(cluster_name)
        if not ids:
            return 0
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=ids),
        )
        return len(ids)

    def delete_item_by_text(self, text: str) -> int:
        """Удаляет точку памяти по полю text (обогащенное имя)."""
        if not self.client.collection_exists(self.collection_name):
            return 0
        ids = self._point_ids_for_text(text)
        if not ids:
            return 0
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=ids),
        )
        return len(ids)

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

    def search_local(
        self,
        vector: list[float],
        limit: int = 20,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Возвращает top-N ближайших записей памяти по local-вектору."""
        if not vector:
            return []
        if limit <= 0:
            return []
        if not self.client.collection_exists(self.collection_name):
            return []

        try:
            result = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                using=_LOCAL_VECTOR_NAME,
                limit=limit,
                score_threshold=min_similarity,
                with_payload=True,
            )
        except Exception:
            # Legacy fallback for old single-vector collections.
            result = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit,
                score_threshold=min_similarity,
                with_payload=True,
            )
        rows: list[dict[str, Any]] = []
        for point in result.points:
            payload = point.payload or {}
            if not isinstance(payload, dict):
                continue
            parsed = self._parse_match_payload(payload)
            if parsed is None:
                continue
            rows.append(
                {
                    "text": str(parsed.get("text") or "").strip(),
                    "cluster_name": str(parsed.get("cluster_name") or "").strip()
                    or _LEGACY_CLUSTER_NAME,
                    "relevance": float(getattr(point, "score", 0.0) or 0.0),
                }
            )
        return rows
